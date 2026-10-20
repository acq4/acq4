"""Acquire z-stacks, timelapses, and mosaics from an imager, plus the GUI to drive them.
Acquisition runs as gentletask tasks; the pure z-stack math lives in standalone functions."""

from __future__ import annotations

import itertools
import weakref
from dataclasses import dataclass
from typing import Union, Optional, Generator

import numpy as np
from gentletask import asynch
from scipy.optimize import least_squares, linear_sum_assignment
from skimage.metrics import structural_similarity as ssim

import acq4.Manager as Manager
import pyqtgraph as pg
from acq4.devices.Stage import MoveFuture, OutOfLimitsError, Stage
from acq4.util import Qt, ptime
from acq4.util.DataManager import DirHandle
from acq4.util.task import QtFriendlyTask, check_stop, current_task, set_state, sleep
from acq4.util.imaging import Frame, FrameSequence
from acq4.util.surface import find_surface
from acq4.util.task import run_in_gui_thread


#: Fractional slack allowed when counting whole steps into a span. The span is the
#: difference of two absolute depths, so it carries the rounding error of that
#: subtraction; an exact 40-step span read off millimetre-scale depths comes back as
#: 39.999999999 steps, which would otherwise drop the stack's top plane. Applied
#: relative to the step count rather than as a bare absolute, so it still covers that
#: error on stacks of a few thousand planes.
_STEP_COUNT_TOL = 1e-9


def commanded_depths(start: float, stop: float, step: float) -> np.ndarray:
    """The plane depths a stack of these bounds asks for, in order of travel.

    This is the single source of truth for how many planes a stack has and where they
    sit. Every stage of acquisition asks this function -- the fast sweep, the stepped
    fallback, and the up-front estimate that chooses between them -- so all of them
    agree by construction, rather than by three separate roundings happening to land on
    the same answer. Callers downstream of a mismatch have already had to defend against
    one: two of them compare the lengths of stacks acquired over identical bounds.

    How many planes there are depends only on ``abs(stop - start)`` and ``abs(step)``,
    and on nothing else. A 40 um span at 1 um steps is 41 planes whether it is acquired
    at the coverslip or 1 mm into the tissue, and whether it is swept upward or
    downward. Reducing to the span *before* dividing is what keeps the absolute depths
    out of the count: dividing the raw depths instead leaves the answer at the mercy of
    where the stack happens to sit. Where the planes then land is laid out from *start*
    toward *stop*, so a descending stack comes back descending.

    The count floors rather than rounds, so a span that is not a whole number of steps
    keeps only the planes that fit inside it -- the leftover partial step is dropped,
    never rounded up into a plane sitting past *stop*.

    Parameters
    ----------
    start: float
        Depth of the first plane, in metres. Always returned exactly.
    stop: float
        Depth the stack runs toward, in metres; may be above or below *start*. A plane
        lands on it only when the span is a whole multiple of *step*, otherwise the last
        plane stops short of it.
    step: float
        Distance between adjacent planes, in metres. Its sign is ignored -- *start* and
        *stop* are what set the direction of travel.

    Returns
    -------
    np.ndarray
        The commanded depths, ordered from *start* toward *stop*. Never empty: bounds
        less than one step apart still ask for the plane at *start*.
    """
    if step == 0:
        raise ValueError("Z stack step size must be non-zero.")
    span, step = abs(stop - start), abs(step)
    steps = span / step
    n = int(np.floor(steps + _STEP_COUNT_TOL * max(1.0, steps))) + 1
    return start + np.sign(stop - start) * step * np.arange(n)


def _depth_observations(depths: np.ndarray, times: np.ndarray, frame_interval: float):
    """Turn per-frame (time, reported depth) measurements into observations of the focus.

    A frame's depth is the controller's latest report when the frame was processed, which
    is close to its raw timestamp. A report first appearing on frame *e* was issued since
    frame e-1, so it is observed at ``times[e] - frame_interval / 2``. Frames repeating the
    previous depth add nothing, except while the focus is at rest before and after the
    sweep: there every frame observes the resting depth, skipping those within one report
    period of the motion, whose report may be stale.

    Only a report's age *within the frame carrying it* is recovered here. A controller
    that reports a depth it held some constant lag ago looks exactly like one that does
    not, so such a lag survives as a uniform ``speed * lag`` bias on every plane of a
    swept stack -- see :func:`plan_z_stack` for why that matters to ``mode="auto"``.

    Parameters
    ----------
    depths: np.ndarray
        Reported depth of each frame, in metres.
    times: np.ndarray
        Raw frame timestamps, in seconds.
    frame_interval: float
        Time between frames, in seconds.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, float, float]
        Observation times and depths, sorted by time with any repeated times dropped, and
        the times of the last leading-rest and first trailing-rest observations.
    """
    edges = np.flatnonzero(np.diff(depths)) + 1
    if len(edges) == 0:
        return np.array([]), np.array([]), np.inf, -np.inf
    runs = np.diff(np.concatenate(([0], edges, [len(depths)])))
    stale = int(round(np.median(runs)))
    lead = np.arange(0, max(1, edges[0] - stale + 1))
    trail = np.arange(min(len(depths) - 1, edges[-1] + stale), len(depths))
    index = np.concatenate((lead, edges, trail))
    obs_t = times[index] - frame_interval / 2
    obs_z = depths[index]
    order = np.argsort(obs_t, kind="stable")
    obs_t, obs_z = obs_t[order], obs_z[order]
    keep = np.concatenate(([True], np.diff(obs_t) > 0))
    shift = frame_interval / 2
    return obs_t[keep], obs_z[keep], times[lead[-1]] - shift, times[trail[0]] - shift


def _reduce_knots(obs_t: np.ndarray, obs_z: np.ndarray, tol: float) -> np.ndarray:
    """Pick the fewest observations to use as knots of a piecewise-linear fit.

    Douglas-Peucker: begin with a single segment joining the first and last observation,
    then repeatedly promote to a knot whichever observation lies furthest from the
    current fit, until no observation lies further from it than *tol*. One segment spans
    a whole stretch of constant velocity, so knots accumulate only where the focus
    changed speed.

    Parameters
    ----------
    obs_t: np.ndarray
        Observation times, increasing.
    obs_z: np.ndarray
        Depth observed at each time.
    tol: float
        Largest residual to leave unsplit, in metres. Smaller values keep more knots.

    Returns
    -------
    np.ndarray
        Ascending indices into *obs_t* of the knots to keep, always including both ends.
    """
    keep = {0, len(obs_t) - 1}
    todo = [(0, len(obs_t) - 1)]
    while todo:
        i, j = todo.pop()
        if j - i < 2:
            continue
        span = slice(i, j + 1)
        fit = np.interp(obs_t[span], obs_t[[i, j]], obs_z[[i, j]])
        resid = np.abs(obs_z[span] - fit)
        worst = int(np.argmax(resid))
        if resid[worst] > tol:
            keep.add(i + worst)
            todo += [(i, i + worst), (i + worst, j)]
    return np.array(sorted(keep))


def _irregular_frames(raw_times: np.ndarray) -> np.ndarray:
    """Return a mask of frames whose interval from the previous frame is irregular.

    A frame is irregular if its interval differs from the median by more than two
    standard deviations of all intervals (and by more than 0.1% of the median, so rounding
    noise on evenly spaced timestamps does not count): delivered late, or bunched behind
    a late one. The first frame is never irregular.
    """
    dt = np.diff(raw_times)
    median = np.median(dt)
    irregular = np.abs(dt - median) > max(2 * dt.std(), 1e-3 * abs(median))
    return np.concatenate(([False], irregular))


def _linearize_frame_times(raw_times: np.ndarray, use: np.ndarray) -> np.ndarray:
    """Return frame times from a least-squares line of raw timestamp against list index.

    Only frames where *use* is True are fitted; every frame gets a time off the line.

    The abscissa is the frame's position in the list, not the camera's own frame ``id``.
    An id would be the better choice if it counted exposures, because a dropped frame
    would then leave a gap in it and the line would place the frames after the drop
    correctly. It does not: MicroManagerCamera, PVCam and WebcamCamera all increment it
    once per image *retrieved*, so a drop -- a buffer overflow, which is the only way
    MicroManager loses one -- leaves the ids dense and the id is the index under another
    name. Where an id does differ from the index it differs wrongly, since a camera that
    repeats or restarts ids across a batch would bend the line instead of leaving it
    alone. So a drop costs the frames after it a depth error either way, and the index
    costs less of one.

    Raises
    ------
    ValueError
        If the fitted times do not advance.
    """
    index = np.arange(len(raw_times), dtype=float)
    slope, offset = np.polyfit(index[use], raw_times[use], 1)
    if not slope > 0:
        raise ValueError("Cannot linearize sweep depths: frame timestamps do not advance.")
    return slope * index + offset


def _fit_knots(obs_t: np.ndarray, obs_z: np.ndarray, knot_t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Least-squares fit of a piecewise-linear curve to observations, from initial knot times.

    Knot depths and interior knot times are both fitted; each interior knot may move up to
    halfway toward its neighbours, so their order is kept. The end knots keep their times.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Fitted knot times and depths.
    """
    # Normalize, so the solver sees both axes on a unit scale.
    t0, t_scale = obs_t[0], obs_t[-1] - obs_t[0]
    z0, z_scale = obs_z[0], max(float(np.ptp(obs_z)), 1e-12)
    ot, oz = (obs_t - t0) / t_scale, (obs_z - z0) / z_scale
    kt = (knot_t - t0) / t_scale
    n = len(kt)
    basis = np.stack([np.interp(ot, kt, unit) for unit in np.eye(n)], axis=1)
    kz = np.linalg.lstsq(basis, oz, rcond=None)[0]
    if n > 2:
        def residual(x):
            return np.interp(ot, np.concatenate(([kt[0]], x[:n - 2], [kt[-1]])), x[n - 2:]) - oz

        lower = np.concatenate((0.5 * (kt[:-2] + kt[1:-1]), np.full(n, -np.inf)))
        upper = np.concatenate((0.5 * (kt[1:-1] + kt[2:]), np.full(n, np.inf)))
        x = least_squares(residual, np.concatenate((kt[1:-1], kz)), bounds=(lower, upper)).x
        kt = np.concatenate(([kt[0]], x[:n - 2], [kt[-1]]))
        kz = x[n - 2:]
    return kt * t_scale + t0, kz * z_scale + z0


def estimate_swept_frame_depths(frames: list[Frame], report: "dict | None" = None) -> dict:
    """Re-derive each swept frame's time and depth, in place.

    A frame's reported depth is the controller's latest report when the frame was
    processed, so it lags the focus by up to one report period, and its raw timestamp
    bunches where the camera delivers frames in a batch. The procedure:

    1. Set aside frames with an irregular interval from the previous frame
       (:func:`_irregular_frames`); their time and depth are used by neither fit below.
       Turn the remaining frames' (raw time, reported depth) pairs into observations of
       the focus (:func:`_depth_observations`).
    2. Fit a piecewise-linear curve of depth against time to them: knots by
       :func:`_reduce_knots`, with a tolerance of half the reporting step widened to a
       whole step as reports approach one per frame (an observation's time is known only
       to within one frame interval). Knot times and depths are then least-squares
       fitted (:func:`_fit_knots`), so corners can fall between observations.
    3. Correct frame times to a least-squares line of time against position in the list,
       fitted to the regular frames
       (:func:`_linearize_frame_times`).
    4. Read each frame's depth off the curve at its corrected time.

    Only for a continuous sweep that begins and ends at rest, as acquire_z_stack
    arranges.

    Parameters
    ----------
    frames: list[Frame]
        Frames of one continuous sweep, in acquisition order. Their transforms and
        times are rewritten in place.
    report: dict | None
        If given, filled with ``irregular_frames`` (indices), ``frame_interval`` (s),
        ``max_time_correction`` (s),
        ``median_frames_per_report``, ``quantum`` (reporting step, m), ``tolerance`` (m),
        ``n_observations`` and ``n_knots``.

    Returns
    -------
    dict
        The fit, as ``frame_times`` (corrected), ``obs_times``, ``obs_depths``,
        ``knot_times`` and ``knot_depths``.

    Raises
    ------
    ValueError
        If the frames cannot be fitted: fewer than two, missing timestamps, frame times
        that do not advance, or fewer than two observations of the focus moving.
    """
    report = {} if report is None else report
    if len(frames) < 2:
        raise ValueError("Cannot linearize sweep depths: fewer than two frames.")
    try:
        depths = np.array([f.depth for f in frames], dtype=float)
        raw_times = np.array([f.time for f in frames], dtype=float)
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Cannot linearize sweep depths: no usable frame timestamps ({exc!r}).") from exc
    irregular = _irregular_frames(raw_times)
    report["irregular_frames"] = np.flatnonzero(irregular)
    regular = ~irregular
    times = _linearize_frame_times(raw_times, regular)
    frame_interval = float(np.median(np.diff(times)))
    report["frame_interval"] = frame_interval
    report["max_time_correction"] = float(np.abs(times - raw_times).max())

    obs_t, obs_z, rest_until, rest_from = _depth_observations(depths[regular], raw_times[regular], frame_interval)
    moving_z = obs_z[(obs_t > rest_until) & (obs_t < rest_from)]
    report["n_observations"] = len(obs_t)
    if len(moving_z) < 2:
        raise ValueError(
            f"Cannot linearize sweep depths: only {len(moving_z)} observation(s) of the focus moving."
        )
    edges = np.flatnonzero(np.diff(depths[regular])) + 1
    runs = np.diff(np.concatenate(([0], edges, [regular.sum()])))
    report["median_frames_per_report"] = frames_per_report = float(np.median(runs))
    quantum = float(np.median(np.abs(np.diff(moving_z))))
    tolerance = 0.5 * quantum * max(1.0, 2.0 / frames_per_report)
    report.update(quantum=quantum, tolerance=tolerance)

    knot_t, knot_z = _fit_knots(obs_t, obs_z, obs_t[_reduce_knots(obs_t, obs_z, tolerance)])
    report["n_knots"] = len(knot_t)

    for frame, time, depth in zip(frames, times, np.interp(times, knot_t, knot_z)):
        xform = frame.globalTransform().as_affine()
        xform.offset = [xform.offset[0], xform.offset[1], depth]
        frame.addInfo(transform=xform, time=time)
    return {
        "frame_times": times,
        "obs_times": obs_t,
        "obs_depths": obs_z,
        "knot_times": knot_t,
        "knot_depths": knot_z,
    }


#: How far outside the commanded planes a frame may sit and still be counted as part of
#: the stack, in metres. An absolute distance rather than a fraction of the step: what it
#: absorbs is the focus controller's reporting jitter at the two ends of the sweep, which
#: does not scale with the step. Roughly half a typical 1 um z-step. Frames further out
#: than this were exposed while the focus was still settling into, or already overshooting
#: out of, the commanded range, so they stand for no plane.
_RANGE_TOL = 5e-7


def select_planes(frames: list[Frame], depths: np.ndarray) -> list[Frame]:
    """Turn the frames a sweep acquired into exactly one frame per commanded plane.

    This is the middle of the three stages a swept stack passes through.
    :func:`estimate_swept_frame_depths` has already established what depth each frame was
    really exposed at; this decides which of those frames stands in for each plane the
    caller asked for; :func:`stamp_z_stack_planes` then writes
    the result. Nothing here re-derives the planes: *depths* is handed in, normally
    straight off ``ZStackPlan.depths``, and ``len(depths)`` is the length of what comes
    back. That is what makes the frame count a property of the request rather than of
    whichever path happened to run -- a promise two callers already carry defenses against
    not being kept.

    **How a plane is filled.** Each plane is the acquired frame nearest its commanded
    depth, keeping its own measured depth: a real exposure, at approximately the right
    place. Matching is done over the whole stack at once rather than plane by plane,
    because that is what keeps the assignment one-to-one -- a nearest-neighbour pass would
    happily hand one frame to two adjacent planes and leave a third unfilled. The frames so
    chosen then fill the planes in depth order, so planes that run deeper get frames that
    run deeper; see :func:`_assign_nearest` for why that costs the assignment nothing.

    **What gets rejected.** Frames outside the commanded range by more than ``_RANGE_TOL``
    are dropped before anything else: they were exposed while the focus was still settling
    into or overshooting out of the range, so they stand for no plane. There must be at
    least one frame per plane left afterwards. Finally, the frames used, taken in depth
    order, must also be in acquisition order: otherwise the sweep doubled back where it
    mattered. Reversals among frames that were not used (such as rounding noise at rest)
    do not count. Every one of those is a ``ValueError``, which is the signal
    ``acquire_z_stack`` takes as its cue to fall back to stepped acquisition.

    A plane is only ever filled from *this* sweep; nothing is invented, and no frame is
    used twice. Where several frames share a depth the sweep genuinely resolved fewer
    depths than the stack asked for, and the stack still comes back full, of the frames
    the sweep really took.

    Parameters
    ----------
    frames: list[Frame]
        Acquired frames, in acquisition order, each carrying the depth measured for it.
        Neither sorted nor distinct by depth; both are handled here.
    depths: np.ndarray
        The commanded plane depths, in the order the planes should be returned. Note that
        this is the *return* order, not the order the focus travelled in: ``acquire_z_stack``
        sweeps from start toward stop but hands these over sorted ascending, because that
        is the order its callers require.

    Returns
    -------
    list[Frame]
        Exactly ``len(depths)`` frames, one per entry of *depths*, in that order: the
        acquired frames themselves, untouched, still at their own measured depths.

    Raises
    ------
    ValueError
        If *depths* is empty; if fewer frames than planes lie inside the commanded range;
        or if the frames used are not in acquisition order when taken in depth order.
    """
    depths = np.asarray(depths, dtype=float)
    if depths.ndim != 1 or len(depths) == 0:
        raise ValueError("Cannot select planes: no commanded depths were given.")
    low, high = float(depths.min()), float(depths.max())

    # Trim first, so that neither the count nor the order check is decided by frames that
    # were never part of the stack to begin with.
    acquired = np.array(
        [i for i, f in enumerate(frames) if low - _RANGE_TOL <= f.depth <= high + _RANGE_TOL], dtype=int
    )
    kept = [frames[i] for i in acquired]
    if len(kept) < len(depths):
        raise ValueError(
            f"Insufficient frames to have one frame per step: {len(kept)} of {len(frames)} "
            f"acquired frames lie within the commanded {low * 1e6:.3f}..{high * 1e6:.3f} um, "
            f"but {len(depths)} planes were asked for."
        )

    have = np.array([f.depth for f in kept], dtype=float)
    # The one sort the pipeline does: the assignment needs depth order to return its picks
    # in plane order. Frames that tie in depth are ordered as the sweep travelled, so a tie
    # alone cannot fail the order check.
    travel = 1 if have[-1] >= have[0] else -1
    order = np.lexsort((travel * acquired, have))
    have, acquired = have[order], acquired[order]
    kept = [kept[i] for i in order]

    result, used = _assign_nearest(kept, have, depths)
    used_acquired = acquired[np.sort(used)]  # in depth order
    steps = np.diff(used_acquired)
    if not (np.all(steps > 0) or np.all(steps < 0)):
        raise ValueError(
            "Selected frames are not in acquisition order: the sweep doubled back across "
            f"the planes (frames {used_acquired.tolist()} in depth order)."
        )
    return result


def _assign_nearest(
    frames: list[Frame], have: np.ndarray, depths: np.ndarray
) -> tuple[list[Frame], np.ndarray]:
    """Give each commanded depth its own acquired frame, minimising total depth error.

    Hungarian assignment over ``|commanded - measured|``. Solving the whole stack at once
    is what makes the result one-to-one, and it also lets a frame go to a neighbouring
    plane when that costs the stack as a whole less than giving it to its own nearest.

    The frames it chose are then laid onto the planes in depth order -- the shallowest
    frame picked fills the shallowest plane, and so on. That is what makes the stack's
    ascending-depth contract structural rather than something to check afterwards. The
    assignment on its own does not give it: a stack asks for fewer planes than the sweep
    acquired frames, so the problem is rectangular and full of ties, and a solver is free
    to settle one by crossing -- handing plane *i* a deeper frame than plane *i+1*.

    Reordering costs nothing, because a crossing is only ever a tie and never a cheaper
    answer. Depths and measurements both live on a line, where ``|a-x| + |b-y| <=
    |a-y| + |b-x|`` for any ``a <= b`` and ``x <= y``: uncrossing a pair never raises the
    total, so some optimal assignment of the chosen frames is always an ordered one.

    Frames come back exactly as they arrived, still at their own measured depths: the plane
    a frame was chosen for says where it was *wanted*, not where it was. Also returns the
    index into *frames* of each pick.
    """
    cost = np.abs(depths[:, None] - have[None, :])
    rows, cols = linear_sum_assignment(cost)
    picks = np.full(len(depths), -1, dtype=int)
    picks[rows] = cols
    assert np.all(picks >= 0), "Hungarian assignment left a plane unfilled"
    # *have* is ascending, so sorting the picks orders the chosen frames by depth; the
    # planes are taken shallowest-first, whichever order the caller asked them back in.
    picks[np.argsort(depths, kind="stable")] = np.sort(picks)
    return [frames[j] for j in picks], picks


def enforce_linear_z_stack(frames: list[Frame], start: float, stop: float, step: float) -> list[Frame]:
    """Select one frame per commanded plane for a stack swept over ``[start, stop]``.

    A back-compatible spelling of :func:`select_planes` for callers holding the bounds
    rather than the planes: it asks :func:`commanded_depths` what planes those bounds want
    and hands them over. The bounds are sorted first, so the stack comes back ascending in
    depth whichever way round they were given -- the same ordering ``acquire_z_stack``
    guarantees, and which its consumers require.

    New code should prefer :func:`select_planes`. Passing the planes rather than the bounds
    is what stops a stepped fallback from re-deriving a different number of them than the
    fast attempt it is replacing; see :func:`commanded_depths`.

    Parameters
    ----------
    frames: list[Frame]
        Acquired frames, in acquisition order, each carrying the depth measured for it.
    start: float
        One commanded bound, in metres.
    stop: float
        The other commanded bound, in metres. May be above or below *start*.
    step: float
        Distance between adjacent planes, in metres. Its sign is ignored.

    Returns
    -------
    list[Frame]
        Exactly ``len(commanded_depths(start, stop, step))`` frames, ascending in depth.

    Raises
    ------
    ValueError
        If *step* is zero, or for any of the reasons :func:`select_planes` raises.
    """
    start, stop = sorted((start, stop))
    return select_planes(frames, commanded_depths(start, stop, step))


def calculate_hysteresis(frames: list[Frame], center: Frame, min_likeness=0.95) -> float:
    if not frames:
        raise ValueError("Stack is empty")

    # Check if center frame is potentially in the stack
    center_data = center.data()
    if all(not np.array_equal(center_data.shape, f.data().shape) for f in frames):
        raise ValueError("Center frame is not in the stack")

    similarities = []
    for f in frames:
        f_data = f.data()
        try:
            similarity = ssim(f_data, center_data)
            similarities.append(similarity)
        except ValueError:
            # Handle frames with different shapes or other issues
            similarities.append(-float('inf'))

    if all(sim < min_likeness for sim in similarities):
        raise ValueError("Center frame does not match any frame in the stack")

    closest_match = np.argmax(similarities)
    return frames[closest_match].depth - frames[len(frames) // 2].depth


def _focus_move(imager, depth: float, speed: Union[float, str], name: str | None = None) -> None:
    """Move the focus to *depth* metres and block until it arrives or the deadline passes.

    One move, no policy: every focus move a z-stack makes goes through here so that the
    deadline is computed the same way each time. That used to be
    ``max(10, 3 * abs(dz) / speed)`` -- the only distance-to-timeout calculation anywhere
    in the tree, and one that assumed the focus runs at *speed* from the first metre to
    the last. It does not: on a Dover focus axis a 500 um step is over before it has
    finished accelerating, and the constant-velocity figure is twenty times too short.
    The device now owns the ramp (:meth:`Stage.expectedMoveDuration`) and
    :class:`MoveFuture` owns the margin and the floor, so the two halves of that old
    expression live where every other move in the tree can reach them.

    ``imager.setFocusDepth`` goes through the motion planner and hands back a
    :class:`QtFriendlyTask`, not a :class:`MoveFuture`, so ``waitForMove`` is not
    available here and the same two pieces are composed by hand.

    *depth* and the distance derived from it are global metres, not device coordinates,
    so no :meth:`Stage.getAxisScale` conversion is wanted.
    """
    focus_dev = imager.getFocusDevice()
    distance = abs(depth - imager.getFocusDepth())
    timeout = MoveFuture.timeoutFor(focus_dev.expectedMoveDuration(distance, speed))
    imager.setFocusDepth(depth, speed, name=name).wait(timeout=timeout)


def approach_depth(
    imager,
    depth: float,
    direction: float,
    speed: Union[float, str] = "fast",
    hysteresis_correction: bool = True,
    name: str | None = None,
) -> None:
    """Park the focus at *depth*, arriving from the direction the stack is about to travel.

    Called **once per stack**, in either mode, before anything is acquired. That is the
    whole of the hysteresis policy: a stage's backlash shows up when it reverses, so the
    only move in a stack that can suffer from it is the one onto the first plane, which
    may well have come from the wrong side. Every move after that is another step in
    ``direction`` and has nothing to unwind.

    This used to be applied per step instead, with the *stack's* overall direction passed
    down into every one of them. On a downward stack that meant each plane was approached
    by driving ``hysteresisCorrection`` metres *above* its target and coming back -- a
    40 um round trip and two move-waits for every plane, at the 20 um
    :attr:`Stage.hysteresisCorrection` default, for a correction the previous step had
    already made unnecessary. This rig's DoverStage configures it to 0, which
    short-circuits the whole thing, so the saving is for rigs that do not.

    *direction* is any signed number: the sign of ``stop - start``. A correction is made
    only when the approach would otherwise arrive against it -- overshoot past *depth* by
    ``hysteresisCorrection`` on the far side, then come back onto it travelling the way
    the stack will. When the approach already arrives in *direction* (or the device
    reports no hysteresis, or *direction* is zero), there is a single move and nothing to
    correct. The second leg used to run unconditionally, even in that case: the code
    named it ``"redundant {name}"``, which it was.

    Parameters
    ----------
    imager: Camera
        The imager whose focal plane is being positioned; ``None`` *depth* is a no-op.
    depth: float
        Global z to arrive at, in metres.
    direction: float
        Sign of the stack's travel, ``stop - start``. Only its sign is used.
    speed: float | str
        m/s, or ``'fast'``/``'slow'`` for the focus device to resolve.
    hysteresis_correction: bool
        False to make the plain move and skip the approach entirely.
    name: str | None
        Label for the moves, for logs and the motion planner.
    """
    if depth is None:
        return

    correction = imager.getFocusDevice().hysteresisCorrection
    dz = depth - imager.getFocusDepth()
    # dz * direction < 0 is "the approach runs against the stack": a downward stack being
    # approached from below, or an upward one from above. Zero on either side means there
    # is nothing to reverse out of, so no overshoot is made.
    if hysteresis_correction and correction and dz * direction < 0:
        overshoot = -np.sign(direction) * correction
        _focus_move(imager, depth + overshoot, speed, name=f"{name} hysteresis correction")
    _focus_move(imager, depth, speed, name=name)


def _stepped_z_stack(imager, depths: np.ndarray, name) -> list[Frame]:
    """Acquire one frame at each of *depths*, stopping the focus at every one.

    The fast path's fallback, and what ``mode="stepped"`` means. It is deliberately this
    small: the timeout arithmetic belongs to :func:`_focus_move`, the hysteresis approach
    is made once by :func:`approach_depth` before this is called, and the plane
    arithmetic was done by :func:`commanded_depths`. What is left is the loop, which is
    the only part that is actually about stepping.

    Takes the planned depths rather than ``(start, stop, step)`` so that it cannot
    disagree with the fast path about how many planes a stack has: as the fast attempt's
    fallback it must return exactly the stack the attempt it replaces would have, and the
    only way to guarantee that is for both to be handed the same array. See
    :func:`commanded_depths`.

    *depths* is in order of travel, so every step after the first already approaches from
    the direction the caller's one-shot approach established.
    """
    frames = []
    with imager.ensureRunning(ensureFreshFrames=True):
        for z in depths:
            check_stop()
            _focus_move(imager, z, "slow", name=f"{name} step")
            frames.append(imager.acquireFrames(1).wait()[0])
    return frames


def _hold_imager_focus(idev, hold):
    """Tell the focus controller to lock or unlock."""
    fdev = idev.getFocusDevice()
    if fdev is None:
        raise Exception(f"Device {idev} is not connected to a focus controller.")
    if hasattr(fdev, "setHolding"):
        fdev.setHolding(hold)


def _open_shutter(idev, open):
    if hasattr(idev, "openShutter"):
        idev.openShutter(open)


def _status_message(iteration, maxIter):
    if maxIter == 0:
        return f"iter={iteration + 1}"
    else:
        return f"iter={iteration + 1}/{maxIter}"


def _save_results(
    frames: "Frame | list[Frame]",
    storage_dir: DirHandle,
    idx: int,
    is_timelapse: bool = False,
    is_mosaic: bool = False,
    is_z_stack: bool = False,
):
    """
    Returns either the containing dir or the single file handle.
        +-----------+--------+---------+------------------------+----------------+
        | timelapse | mosaic | z-stack |    resultant files     |  fh to return  |
        +-----------+--------+---------+------------------------+----------------+
        | true      | true   | true    | folders of z-stack mas |  storage_dir   |
        | true      | true   | false   | folders of images      |  storage_dir   |
        | true      | false  | true    | multiple z-stack mas   |  storage_dir   |
        | true      | false  | false   | single timelapse ma    |  timelapse.ma  |
        | false     | true   | true    | multiple z-stack mas   |  storage_dir   |
        | false     | true   | false   | multiple images        |  storage_dir   |
        | false     | false  | true    | single z-stack ma      |  z_stack.ma    |
        | false     | false  | false   | single image           |  image.tif     |
        +-----------+--------+---------+------------------------+----------------+
    """
    ret_fh = storage_dir
    if is_mosaic and is_timelapse:
        storage_dir = storage_dir.getDir(f"mosaic_{idx:03d}", create=True)

    if is_z_stack:
        stack = None
        for frame in frames:
            if stack is None:
                # TODO do we want to save the background/contrast display data for each frame, too
                stack = frame.saveImage(storage_dir, "z_stack.ma")
            else:
                stack = frame.appendImage(stack)
        if not is_timelapse and not is_mosaic:
            ret_fh = stack
    elif is_timelapse and not is_mosaic:
        if idx == 0:
            ret_fh = frames.saveImage(storage_dir, "timelapse.ma", autoIncrement=False)
        else:
            fh = storage_dir["timelapse.ma"]  # MC: I don't like this
            frames.appendImage(fh)
            ret_fh = fh
    else:
        fh = frames.saveImage(storage_dir, "image.tif")
        if not is_mosaic and not is_timelapse:
            ret_fh = fh

    return ret_fh


def run_image_sequence(
    imager,
    count: float = 1,
    interval: float = 0,
    pin: "Callable[[Frame]] | None" = None,
    z_stack: "tuple[float, float, float] | None" = None,
    mosaic: "tuple[float, float, float, float, float] | None" = None,
    storage_dir: "DirHandle | None" = None,
    name: str | None = None,
) -> QtFriendlyTask:
    """Start an image sequence as a QtFriendlyTask whose result is the acquired frames.

    Callers connect to sigStateChanged / sigFinished for live progress. The
    directory the frames were saved into is exposed on the task as
    ``imagesSavedIn`` once the task completes.
    """
    return QtFriendlyTask(
        _run_image_sequence,
        kwargs=dict(
            imager=imager,
            count=count,
            interval=interval,
            pin=pin,
            z_stack=z_stack,
            mosaic=mosaic,
            storage_dir=storage_dir,
            name=name,
        ),
        name=name or "run_image_sequence",
    )


def _run_image_sequence(
    imager,
    count: float = 1,
    interval: float = 0,
    pin: "Callable[[Frame]] | None" = None,
    z_stack: "tuple[float, float, float] | None" = None,
    mosaic: "tuple[float, float, float, float, float] | None" = None,
    storage_dir: "DirHandle | None" = None,
    name: str | None = None,
) -> "Frame | list[Frame | list[Frame | list[Frame]]]":
    _hold_imager_focus(imager, True)
    _open_shutter(imager, True)  # don't toggle shutter between stack frames
    man = Manager.getManager()
    result = []
    is_timelapse = count > 1
    ret_fh = None

    def handle_new_frames(f: "Frame | list[Frame]", idx: int):
        nonlocal ret_fh
        if is_timelapse:
            if idx + 1 > len(result):
                result.append([])
            dest = result[-1]
        else:
            dest = result
        dest.append(f)
        if pin:
            if z_stack:
                most_focused = find_surface(f) or (len(f) // 2)
                pin(f[most_focused])
            else:
                pin(f)
        if storage_dir:
            fh = _save_results(f, storage_dir, idx, count > 1, bool(mosaic), bool(z_stack))
            if ret_fh is None:
                ret_fh = fh

    # record
    with man.reserveDevices(imager.devicesToReserve(), reserver="run_image_sequence"):
        try:
            for i in itertools.count():
                if i >= count:
                    break
                start = ptime.time()
                for move in movements_to_cover_region(imager, mosaic, name):
                    move.wait()
                    if z_stack:
                        stack = acquire_z_stack(imager, *z_stack, name=name)
                        handle_new_frames(stack, i)
                    else:  # single frame
                        frame = imager.acquireFrames(1, ensureFreshFrames=True).wait()[0]
                        handle_new_frames(frame, i)
                    check_stop()
                set_state(_status_message(i, count))
                sleep(interval - (ptime.time() - start))
        finally:
            _open_shutter(imager, False)
            _hold_imager_focus(imager, False)
    task = current_task()
    if task is not None:
        task.imagesSavedIn = ret_fh
    return result


def movements_to_cover_region(
    imager, region: "tuple[float, float, float, float, float] | None", name: str = "mosaic"
) -> Generator[object, None, None]:
    """
    Generate a sequence of snaking movements to cover the region. `region` is a tuple containing the `left`, `top`,
    `right`, and `bottom` coordinates, as well as an `overlap`, all in global/meters. `region` can also be None, in
    which case this yields once with a no-op task.
    """
    if region is None:
        yield asynch(lambda: None)()
        return

    for pos in positions_to_cover_region(region, imager.globalCenterPosition(), imager.getBoundary(mode="roi")):
        yield imager.moveCenterToGlobal(pos, "fast", name=name)


def positions_to_cover_region(region, imager_center, imager_region) -> Generator[tuple, None, None]:
    """Ha! (ignoring overlap), `region` is (x1, y1, x2, y2), `imager_region` is (x1, y1, w, h)."""
    z = imager_center[2]
    img_x, img_y, img_w, img_h = imager_region
    img_top_left = np.array((img_x, img_y, z))
    move_offset = imager_center - img_top_left
    img_bottom_right = np.array((img_x + img_w, img_y + img_h, z))
    coverage_offset = imager_center - img_bottom_right
    overlap = region[-1]
    step = np.abs(img_bottom_right - img_top_left)[:2] - overlap
    if np.any(step <= 0):
        raise ValueError(f"Overlap {overlap:g} exceeds field of view")

    region_top_left = np.array((*region[:2], z))
    region_bottom_right = np.array((*region[2:4], z))
    pos = region_top_left + move_offset
    x_finished = y_finished = False
    x_tests = (
        lambda: (pos - coverage_offset)[0] >= region_bottom_right[0],
        lambda: (pos + coverage_offset)[0] <= region_top_left[0],
    )
    x_steps = (step[0], -step[0])
    x_direction = 0

    while not y_finished:
        y_finished = (pos - coverage_offset)[1] <= region_bottom_right[1]
        while not x_finished:
            yield pos
            x_finished = x_tests[x_direction]()
            if not x_finished:
                pos[0] += x_steps[x_direction]
        pos[1] -= step[1]
        x_direction = (x_direction + 1) % 2
        x_finished = False


#: Slack on the kinematic run-up distance, as a multiplier. ``v**2 / 2a`` is exact for a
#: stage that ramps at exactly the acceleration it reports; :attr:`Stage.acceleration` is
#: documented as a model rather than a measurement (a real controller may be running an
#: S-curve, in which case it takes longer than one constant ramp to reach speed), so the
#: distance it predicts is a floor. Overshooting the run-up costs a little travel that the
#: range trim discards anyway; undershooting it puts the stack's first plane back inside
#: the transient this exists to escape, so the error is made in the cheap direction.
_RUNUP_MARGIN = 1.5

#: Minimum run-up and overrun at each end of a fast sweep, in plane steps
#: (``_RUNUP_FRAMES * abs(step)`` metres).
_RUNUP_FRAMES = 2.0


def _runup_bounds(imager, start: float, stop: float, runup: float) -> tuple[float, float]:
    """Where a sweep over ``[start, stop]`` really begins and ends, given *runup* metres.

    ``(start - sign * runup, stop + sign * runup)``, or ``(start, stop)`` when the run-up
    is zero or either extended end would drive the focus device outside its configured
    limits. The check is :meth:`Stage.checkGlobalLimits`, reached the same way
    ``OptomechDevice.setFocusDepth`` reaches the stage -- a focus depth is a global z, and
    the limits are in device coordinates.

    Both ends are given up together when either fails. A stack that runs to within a
    micron of an axis limit has a problem this cannot fix, and running up at one end but
    not the other would leave the two ends of the sweep behaving differently, which is
    precisely the asymmetry the run-up exists to remove.
    """
    if runup <= 0:
        return start, stop
    # A zero-length stack has no direction to run up in; there is nothing to sweep.
    sign = np.sign(stop - start)
    if sign == 0:
        return start, stop
    park, overrun = start - sign * runup, stop + sign * runup
    focus_dev = imager.getFocusDevice()
    here = imager.getFocusDepth()
    x, y, z = focus_dev.globalPosition()[:3]
    try:
        for depth in (park, overrun):
            focus_dev.checkGlobalLimits((x, y, z + (depth - here)), False)
    except OutOfLimitsError:
        return start, stop
    return park, overrun


@dataclass(frozen=True)
class ZStackPlan:
    """Everything decided about a z-stack before any hardware moves.

    Planning is kept apart from acquiring so that the decision shaping a stack -- which
    mode runs, over which planes, at what speed -- is made once, in one place, out of
    scalars. ``acquire_z_stack`` then reads two numbers off the hardware, plans, runs one
    of two branches, and post-processes; nothing in the branches gets to decide anything
    the plan already settled.

    Attributes
    ----------
    mode: str
        ``"fast"`` or ``"stepped"``, never ``"auto"``. This is where ``"auto"`` is
        resolved, so no stage downstream has to ask the question again.
    depths: np.ndarray
        The commanded planes, in order of travel, from :func:`commanded_depths`. This
        array *is* the stack's frame count: ``len(plan.depths)`` is how many frames come
        back, whichever mode ran and whether or not a fast attempt fell back to
        stepped. Later stages consume this array
        rather than re-deriving anything from ``(start, stop, step)``, which is what
        makes that promise structural instead of something several separate roundings
        have to agree about -- they did not, and two callers still carry defenses
        against it.
    speed: float
        Sweep speed in metres per second. It governs the fast path; the stepped path
        moves at the focus device's own "slow" speed. It is computed either way because
        choosing between the two modes is a comparison of how long each would take, and
        the fast estimate is a function of this speed.
    runup: float
        Extra travel in metres to add at *each* end of a fast sweep, so that the focus is
        already at :attr:`speed` by the time it reaches the first commanded plane and has
        not begun slowing before it passes the last. See :func:`plan_z_stack` for where
        the number comes from. Zero in stepped mode, which never sweeps.
    imaging_fps, limiting_fps: float
        Camera frame rate, and the slower of it and the focus position-update rate.
    blur_speed, sampling_speed: float
        The two speed limits (m/s); *speed* is the smaller.
    est_fast_time, est_stepped_time: float
        Predicted duration (s) of each mode, compared when *mode* was ``"auto"``.
    """

    mode: str
    depths: np.ndarray
    speed: float
    runup: float
    imaging_fps: float = np.nan
    limiting_fps: float = np.nan
    blur_speed: float = np.nan
    sampling_speed: float = np.nan
    est_fast_time: float = np.nan
    est_stepped_time: float = np.nan

    def as_dict(self) -> dict:
        """Return the plan's fields, plus which speed limit won, as a plain dict."""
        return {
            "mode": self.mode,
            "n_planes": len(self.depths),
            "depths": self.depths,
            "imaging_fps": self.imaging_fps,
            "limiting_fps": self.limiting_fps,
            "blur_speed": self.blur_speed,
            "sampling_speed": self.sampling_speed,
            "speed": self.speed,
            "speed_limited_by": "blur" if self.blur_speed < self.sampling_speed else "sampling",
            "est_fast_time": self.est_fast_time,
            "est_stepped_time": self.est_stepped_time,
            "runup": self.runup,
        }


def plan_z_stack(
    start: float,
    stop: float,
    step: float,
    *,
    exposure: float,
    position_fps: float,
    mode: str = "auto",
    max_dz_per_frame: float = 5e-6,
    frames_per_step: float = 2.0,
    est_time_per_step: float = 1.0,
    acceleration: float = Stage.defaultAcceleration,
) -> ZStackPlan:
    """Work out how a z-stack over these bounds should be acquired.

    This is arithmetic over scalars and nothing else: the two hardware-derived rates
    arrive as arguments rather than being read off an imager, so the choice between a
    continuous sweep and stepping plane by plane can be inspected, reasoned about and
    tested without a rig -- which the same arithmetic inlined into ``acquire_z_stack``
    could not be.

    **How fast the sweep may run.** Two budgets bound it, and the tighter one wins.

    *Motion blur.* A frame exposed while the focus is travelling is smeared over however
    far the focus moved during the exposure. Holding that smear to *max_dz_per_frame*
    caps the speed at ``max_dz_per_frame * imaging_fps``.

    *Sampling.* Every commanded plane needs at least one acquired frame near it to stand
    in for it, with *frames_per_step* asking for some margin beyond one. A frame is only
    usable if it can also be placed in depth, so the rate that counts is the slower of
    the camera's and the focus controller's, which caps the speed at
    ``abs(step) * limiting_fps / frames_per_step``.

    **Which mode runs.** Under ``mode="auto"`` those same budgets pick it, by comparing
    what each mode would cost: the sweep takes ``span / speed``, while stepping takes
    *est_time_per_step* per plane. A large step with a small blur budget is the case that
    flips it -- the blur cap holds the sweep to a crawl while the step count stays low,
    so stopping at each plane finishes first. An explicit ``"fast"`` or ``"stepped"`` is
    honoured verbatim; only ``"auto"`` is ever overridden, because only ``"auto"`` asked
    to be.

    **The two modes do not measure depth alike, and the choice above does not weigh
    that.** A fast sweep takes its depths from reports issued while the focus was moving,
    so a focus controller reporting with a constant lag shifts every plane of the stack
    against the depth it is labelled with by ``speed * lag``: a quarter of a micron on a
    10 um/s sweep at 25 ms of lag, a whole micron at 100 ms. Stepped mode reads its
    depths at rest and carries no such shift. Two stacks over identical bounds therefore
    disagree by that much when ``"auto"`` sent one down each path, with nothing in either
    result saying so. Callers comparing two stacks against each other are unaffected only
    while both went the same way, which for identical bounds they do.

    **How far the sweep starts before the stack.** A sweep launched from rest at *start*
    spends its first ``speed**2 / (2 * acceleration)`` metres getting up to speed, so the
    planes nearest *start* are exposed during the ramp -- which is exactly the transient
    the knot reduction in :func:`estimate_swept_frame_depths` exists to reconstruct
    depths through. Backing the parking position off by that
    distance, and running the same distance past *stop*, means every frame inside
    ``[start, stop]`` is taken at constant velocity and the overshoot frames are discarded
    by :func:`select_planes`'s range trim. The figure is the textbook ``v**2 / 2a``, times
    :data:`_RUNUP_MARGIN`, because *acceleration* is a model of the controller rather
    than a measurement of it.

    The run-up is at least :data:`_RUNUP_FRAMES` plane steps of travel
    (``_RUNUP_FRAMES * abs(step)``), whatever the acceleration model says, so
    the first and last planes are never taken at the very edge of the sweep. It is the
    larger of that and the ``v**2 / 2a`` figure, and applies in fast mode only.

    Parameters
    ----------
    start: float
        Depth of the first plane, in metres.
    stop: float
        Depth the stack runs toward, in metres; may be above or below *start*.
    step: float
        Distance between adjacent planes, in metres. Its sign is ignored.
    exposure: float
        Camera exposure time in seconds, off the imager. Sets the imaging frame rate, and
        with it both the blur budget and half of the sampling budget.
    position_fps: float
        How many position updates per second the focus device publishes. Frames arriving
        faster than this cannot be told apart in depth, so this is the other half of the
        sampling budget.
    mode: str
        ``"auto"``, ``"fast"`` or ``"stepped"``.
    max_dz_per_frame: float
        Motion-blur budget: the greatest focus travel per exposure, in metres, the sweep
        may incur. Pass ``np.inf`` to waive it and let the sampling budget alone set the
        speed.
    frames_per_step: float
        Roughly how many frames the sweep should acquire per commanded plane. The stack
        returned always has exactly ``len(depths)`` planes regardless; this only says how
        much raw material the selection stage gets to choose from.
    est_time_per_step: float
        Estimated wall-clock cost of one plane in stepped mode -- a move, its settle and
        one exposure -- used only to predict how long stepped mode would take, so that
        ``mode="auto"`` can decide. Stepped mode wins whenever that prediction beats the
        sweep's, which happens for stacks with a very large step size and a small
        *max_dz_per_frame*. Default 1 second.
    acceleration: float
        The focus device's acceleration in m/s², off :attr:`Stage.acceleration`. Used
        only for the run-up. Defaults to :attr:`Stage.defaultAcceleration`.

    Returns
    -------
    ZStackPlan
        The resolved mode, the commanded plane depths, the sweep speed and its run-up.

    Raises
    ------
    ValueError
        If *mode* is not one of the three accepted values, or *step* is zero.
    """
    if mode not in ("auto", "fast", "stepped"):
        raise ValueError(f"Unknown acquisition mode: {mode!r} (expected 'auto', 'fast' or 'stepped')")

    # Called exactly once per stack; every stage downstream consumes this array.
    depths = commanded_depths(start, stop, step)

    imaging_fps = 1.0 / exposure
    # A frame the focus controller could not distinguish in depth from its neighbour is
    # not a second sample of the sweep, so the slower of the two rates is the real one.
    limiting_fps = min(imaging_fps, position_fps)
    blur_budget = max_dz_per_frame * imaging_fps
    sampling_budget = abs(step) * limiting_fps / frames_per_step
    speed = min(blur_budget, sampling_budget)

    estimated_fast_time = abs(stop - start) / speed if speed > 0 else np.inf
    estimated_stepped_time = est_time_per_step * len(depths)
    if mode == "auto":
        mode = "fast" if estimated_fast_time < estimated_stepped_time else "stepped"

    # The ramp distance is only known when the stage reports an acceleration; the
    # frame-based floor applies regardless.
    runup = 0.0
    if mode == "fast":
        runup = _RUNUP_FRAMES * abs(step)
        if np.isfinite(acceleration) and acceleration > 0:
            runup = max(runup, _RUNUP_MARGIN * speed**2 / (2 * acceleration))

    return ZStackPlan(
        mode=mode,
        depths=depths,
        speed=speed,
        runup=runup,
        imaging_fps=imaging_fps,
        limiting_fps=limiting_fps,
        blur_speed=blur_budget,
        sampling_speed=sampling_budget,
        est_fast_time=estimated_fast_time,
        est_stepped_time=estimated_stepped_time,
    )


def acquire_z_stack(
    imager,
    start: float,
    stop: float,
    step: float,
    *,
    # 1. which acquisition mode
    mode: str = "auto",
    # 2. how fast the sweep may run (fast mode only)
    max_dz_per_frame: float = 5e-6,  # m
    frames_per_step: float = 2.0,
    est_time_per_step: float = 1.0,  # s
    # 3. motion policy and plumbing
    hysteresis_correction: bool = True,
    fallback_to_stepped: bool = True,
    device_reservation_timeout: float = 10.0,
    name: str | None = "z stack",
    debug: bool = False,
) -> FrameSequence:
    """Acquire a Z stack from the given imager.

    There are two ways to do it. In **fast** mode the imager records continuously while
    the focus sweeps once from *start* to *stop*, and the frames are afterwards measured,
    selected and stamped onto the commanded planes. In **stepped** mode the focus moves
    to each commanded plane in turn and one frame is taken there. Fast is normally much
    quicker; stepped lands on the commanded depths by construction, and is also the
    fallback when a sweep does not yield a usable frame for every plane.

    :func:`plan_z_stack` makes that choice, and the parameters below are grouped by the
    three things a caller is really deciding: which mode, how fast the sweep may go, and
    motion policy.

    **The stack always has** ``len(commanded_depths(start, stop, step))`` **planes** --
    the same count at any absolute depth, in either direction of travel, in either mode,
    and whether or not a fast attempt fell back to stepped.

    Parameters
    ----------
    imager: Camera
        The imager instance to use for acquisition.
    start: float
        Z position to begin the stack, in metres. A plane always lands exactly here.
    stop: float
        Z position to end the stack, in metres (can be above or below *start*). A plane
        lands on it only when the span is a whole multiple of *step*.
    step: float
        Distance between adjacent planes, in metres. Its sign is ignored; *start* and
        *stop* set the direction of travel.
    mode: str
        ``"fast"`` for one continuous sweep, ``"stepped"`` to stop at each plane, or
        ``"auto"`` to let the estimated durations choose. ``"auto"`` is the only value
        that can be overridden.
    max_dz_per_frame: float
        Motion-blur budget for fast mode: the greatest focus travel per exposure, in
        metres, the sweep may incur. The sweep slows down to stay inside it. ``np.inf``
        waives it, leaving *frames_per_step* to set the speed on its own.
    frames_per_step: float
        Roughly how many frames fast mode should acquire per commanded plane, which is
        the other thing bounding sweep speed. More frames give the selection stage more
        to choose from; the number of planes returned is unaffected. Default 2.0.
    est_time_per_step: float
        Used for deciding when to use stepped rather than fast acquisition (when *mode*
        is ``"auto"``). This value estimates the total time to acquire a single step in
        stepped mode. If the total estimated acquisition time is lower in stepped mode
        than in fast mode, then use stepped. This will happen for stacks with a very
        large step size and small *max_dz_per_frame*. Default is 1 second.
    hysteresis_correction: bool
        If True, the move towards the stack's first plane arrives from the direction the
        stack will travel, overshooting past it first if it would otherwise arrive from
        the wrong side. See :func:`approach_depth`.
    fallback_to_stepped: bool
        If True, and fast acquisition fails to produce a usable frame for every plane,
        retry the whole stack with the slower stepped method.
    device_reservation_timeout: float
        Maximum time to wait for device reservation, in seconds.
    name: str | None
        Label attached to the moves this makes, for logs and the motion planner.
    debug: bool
        If True, attach a :class:`SweepDebug` to the result's ``debug`` attribute: the
        recorded frame times and reported depths, the fit, the linearized depths and which
        frames were selected. Kept in memory only.

    Returns
    -------
    FrameSequence
        A list of Frame, with ``.debug`` set if *debug* was requested and ``.decisions``
        always set to a nested dict of every input, hardware rate and decision made
        (plan, run-up, linearization, selection, result). One frame per commanded plane, with corrected z positions. **Always ascending in
        depth**, whichever mode ran and whichever way round *start* and *stop* were given:
        a descending stack is swept downward but returned low-z to high-z. Consumers
        depend on this ordering, not merely on the count.
    """
    stage = imager.scopeDev.getFocusDevice()
    hardware = {
        "exposure": imager.getParam('exposure'),
        "position_fps": stage.positionUpdatesPerSecond,
        "acceleration": stage.acceleration,
    }
    plan = plan_z_stack(
        start,
        stop,
        step,
        mode=mode,
        max_dz_per_frame=max_dz_per_frame,
        frames_per_step=frames_per_step,
        est_time_per_step=est_time_per_step,
        **hardware,
    )
    decisions = {
        "request": {
            "start": start,
            "stop": stop,
            "step": step,
            "mode": mode,
            "max_dz_per_frame": max_dz_per_frame,
            "frames_per_step": frames_per_step,
            "est_time_per_step": est_time_per_step,
            "hysteresis_correction": hysteresis_correction,
            "fallback_to_stepped": fallback_to_stepped,
        },
        "hardware": hardware,
        "plan": plan.as_dict(),
    }
    # Rebound by the fallback below; plan.mode keeps saying what was planned.
    mode = plan.mode
    # The focus travels from start toward stop, so that is the order the planes are
    # acquired in -- but *not* the order they are returned in. The stack always comes back
    # ascending in depth. Consumers rely on that: acq4_automation's find_pipette_in_z_stack
    # slides a fixed-width window up the stack with `while z[j] - z[i] < window`, which on a
    # descending stack never terminates early and silently widens every window to the whole
    # sweep, corrupting three of its six acceptance criteria.
    travel = plan.depths
    depths = np.sort(travel)
    direction = stop - start
    man = Manager.getManager()
    sweep = None  # the fast attempt's raw record, kept for *debug*
    selected_indices = None
    fell_back = False

    # One reservation around both attempts. Releasing it between a failed fast sweep and
    # the stepped retry would leave a window for another operation to move the stage, and
    # the retry would then start from somewhere the plan knows nothing about.
    with man.reserveDevices(imager.devicesToReserve(), timeout=device_reservation_timeout, reserver="acquire_z_stack"):
        if mode == 'fast':
            # Park short of the stack and sweep past its far end, so the acceleration and
            # deceleration ramps both fall outside [start, stop] and every frame standing
            # for a commanded plane was exposed at constant velocity. The frames taken
            # over the run-up are outside the commanded range and select_planes trims
            # them. See _runup_bounds.
            park, overrun = _runup_bounds(imager, start, stop, plan.runup)
            fast: dict = {"park": park, "overrun": overrun}
            decisions["fast"] = fast
            # One approach for the whole stack: everything after this travels one way.
            approach_depth(imager, park, direction, "fast", hysteresis_correction, f"{name} start")

            # Frames at rest either side of the move give the depth fit its resting
            # depths: three report periods' worth, beyond the frames a stale report spoils.
            rest_frames = 3 * int(np.ceil(max(1.0, plan.imaging_fps / hardware["position_fps"])))
            fast["rest_frames"] = rest_frames
            with imager.ensureRunning(ensureFreshFrames=True):
                frames_fut = imager.acquireFrames()
                try:
                    imager.acquireFrames(rest_frames).wait()
                    _focus_move(imager, overrun, plan.speed, name=f"{name} stop")
                    imager.acquireFrames(rest_frames).wait()
                finally:
                    frames_fut.stop()
            frames = frames_fut.wait(timeout=10)
            fast["n_frames"] = len(frames)
            # A. measure what depth each frame was really exposed at, then B. pick one
            # frame per commanded plane. B is handed the planned depths rather than the
            # bounds, so it cannot arrive at a different number of planes than the plan.
            if debug:
                sweep = {
                    "frames": list(frames),
                    "times": np.array([f.time for f in frames], dtype=float),
                    "reported": np.array([f.depth for f in frames], dtype=float),
                }
                sweep.update(fit=None, linear=sweep["reported"], raw_times=sweep["times"])
            fast["linearization"] = {}
            fast["selection"] = selection = {"range_tol": _RANGE_TOL}
            fast["error"] = None
            try:
                fit = estimate_swept_frame_depths(frames, report=fast["linearization"])
                linear = np.array([f.depth for f in frames], dtype=float)
                if debug:
                    sweep.update(fit=fit, linear=linear, times=fit["frame_times"])
                selection["n_in_range"] = int(np.sum(
                    (linear >= depths[0] - _RANGE_TOL) & (linear <= depths[-1] + _RANGE_TOL)
                ))
                acquired = frames
                frames = select_planes(acquired, depths)
                if debug:
                    index = {id(f): i for i, f in enumerate(acquired)}
                    selected_indices = np.array([index[id(f)] for f in frames])
            except ValueError as exc:
                fast["error"] = str(exc)
                if not fallback_to_stepped:
                    raise
                fell_back = True
                imager.logger.info("Failed to fast-acquire linear z stack. Retrying with stepwise movement.")
                mode = 'stepped'

        if mode == 'stepped':
            # Park focus at the stack beginning. This is the stack's one hysteresis
            # approach in stepped mode too: the steps that follow all travel the same way,
            # so none of them has a reversal to unwind. A fast attempt that fell back to
            # here has already made an approach, but to the run-up position rather than to
            # start, and possibly overshot past stop since -- so the approach is made
            # again rather than assumed.
            approach_depth(imager, start, direction, "fast", hysteresis_correction, f"{name} start")
            # The very planes the fast attempt was planned over, so a fallback cannot
            # land on a different count than the attempt it is replacing.
            frames = _stepped_z_stack(imager, travel, name=name)
            if travel[0] > travel[-1]:
                # Swept downward, so the planes were acquired deep-end-last. The hardware
                # had to move monotonically; the caller gets the stack ascending anyway.
                frames = frames[::-1]

    # C. stamp. Frame i+1 sits one step deeper than frame i in the list being returned,
    # which is what makes the first frame's transform describe the whole stack. The list is
    # ascending, so the step is positive whichever way the focus actually travelled.
    z_step = float(depths[1] - depths[0]) if len(depths) > 1 else abs(step)
    surface_depth = imager.scopeDev.getSurfaceDepth()
    stamp_z_stack_planes(frames, z_step, surface_depth)
    decisions["result"] = {
        "mode": mode,
        "fell_back": fell_back,
        "n_frames": len(frames),
        "depths": np.array([f.depth for f in frames], dtype=float),
        "z_step": z_step,
        "surface_depth": surface_depth,
    }
    result = FrameSequence(frames, decisions=decisions)
    if debug:
        result.debug = SweepDebug.from_acquisition(mode, fell_back, depths, frames, sweep, selected_indices, decisions)
    return result


class SweepDebug:
    """What a z-stack acquisition measured and decided, for plotting.

    Per-frame arrays are in acquisition order and cover every frame the sweep recorded,
    including run-up frames outside the stack. Depths are in metres, times in seconds.

    Parameters
    ----------
    mode: str
        ``"fast"`` or ``"stepped"``: what produced the returned frames.
    fell_back: bool
        True if a fast sweep was attempted and abandoned for stepped acquisition. The
        sweep arrays then describe that abandoned fast attempt.
    commanded_depths: np.ndarray
        The planes the stack asked for, ascending.
    frame_times, reported_depths: np.ndarray
        Each recorded frame's timestamp (after linearization) and the focus position the
        controller had last reported when it was exposed (before linearization).
    obs_times, obs_depths: np.ndarray
        Observations of the focus fitted by the linearization: see :func:`_depth_observations`.
    knot_times, knot_depths: np.ndarray
        Knots of the piecewise-linear depth-against-time fit. Empty if no fit was made
        (stepped acquisition, or a sweep that could not be fitted).
    linear_depths: np.ndarray
        Each recorded frame's depth after linearization (equals *reported_depths* where
        no fit was made).
    selected_indices: np.ndarray | None
        Index into the recorded frames of the frame chosen for each returned plane, or
        None where planes were stepped rather than picked.
    decisions: dict | None
        The acquisition's inputs and decisions; the same dict as ``FrameSequence.decisions``.
    raw_frame_times: np.ndarray | None
        Each recorded frame's timestamp as the camera gave it. Defaults to *frame_times*.
    """

    def __init__(
        self,
        mode: str,
        fell_back: bool,
        commanded_depths: np.ndarray,
        frame_times: np.ndarray,
        reported_depths: np.ndarray,
        obs_times: np.ndarray,
        obs_depths: np.ndarray,
        knot_times: np.ndarray,
        knot_depths: np.ndarray,
        linear_depths: np.ndarray,
        selected_indices: "np.ndarray | None" = None,
        decisions: "dict | None" = None,
        raw_frame_times: "np.ndarray | None" = None,
    ):
        self.mode = mode
        self.fell_back = fell_back
        self.commanded_depths = commanded_depths
        self.frame_times = frame_times
        self.reported_depths = reported_depths
        self.obs_times = obs_times
        self.obs_depths = obs_depths
        self.knot_times = knot_times
        self.knot_depths = knot_depths
        self.linear_depths = linear_depths
        self.selected_indices = selected_indices
        self.decisions = {} if decisions is None else decisions
        self.raw_frame_times = frame_times if raw_frame_times is None else raw_frame_times

    @classmethod
    def from_acquisition(cls, mode, fell_back, commanded_depths, frames, sweep, selected_indices, decisions):
        """Build from what acquire_z_stack recorded; *sweep* is None if no fast sweep ran."""
        if sweep is None:  # stepped from the start: the returned frames are all there is
            times = np.array([f.time for f in frames], dtype=float)
            linear = np.array([f.depth for f in frames], dtype=float)
            sweep = {"times": times, "reported": linear, "linear": linear, "fit": None}
            selected_indices = np.arange(len(frames))
        empty = np.array([])
        fit = sweep["fit"] or {}
        return cls(
            mode=mode,
            fell_back=fell_back,
            commanded_depths=commanded_depths,
            frame_times=sweep["times"],
            reported_depths=sweep["reported"],
            obs_times=fit.get("obs_times", empty),
            obs_depths=fit.get("obs_depths", empty),
            knot_times=fit.get("knot_times", empty),
            knot_depths=fit.get("knot_depths", empty),
            linear_depths=sweep["linear"],
            selected_indices=None if fell_back else selected_indices,
            decisions=decisions,
            raw_frame_times=sweep.get("raw_times"),
        )

    def plot(self) -> Qt.QSplitter:
        """Show the sweep in a new window and return it.

        Left: a tree of :attr:`decisions`. Right, three plots with linked time axes (seconds
        from the first frame): depth against time -- each frame raw (camera time, reported
        depth), time-corrected and time+depth-corrected, joined by a line per frame; the
        observations; the fit curve and its knots; and the selected frames, with a line at
        each commanded plane -- the linearization's depth correction (linearized
        minus reported depth) per frame, and its time correction (corrected minus raw
        timestamp) per frame. The plot widget is at ``.plots``.
        """
        t0 = self.frame_times[0] if len(self.frame_times) else 0.0
        t = self.frame_times - t0
        fitted = len(self.knot_times) > 0
        if self.fell_back:
            error = self.decisions.get("fast", {}).get("error")
            title = f"z stack sweep -- fast sweep failed, fell back to stepped: {error}"
        else:
            title = f"z stack sweep ({self.mode})" + ("" if fitted else " -- no fit made")

        win = Qt.QSplitter(Qt.Qt.Orientation.Horizontal)
        win.setWindowTitle(title)
        tree = pg.DataTreeWidget(data=self.decisions)
        win.addWidget(tree)
        plots = pg.GraphicsLayoutWidget()
        win.addWidget(plots)
        win.plots = plots
        win.setSizes([350, 900])
        win.resize(1250, 700)

        top = plots.addPlot(row=0, col=0, title=title)
        top.addLegend()
        top.setLabel("left", "depth", units="m")
        for z in self.commanded_depths:
            top.addItem(pg.InfiniteLine(z, angle=0, pen=pg.mkPen((128, 128, 128, 70))))
        raw_t = self.raw_frame_times - t0
        # One path per frame, raw -> time-corrected -> fully corrected, NaN-separated.
        n = len(t)
        path_t = np.column_stack((raw_t, t, t, np.full(n, np.nan))).ravel()
        path_z = np.column_stack((self.reported_depths, self.reported_depths, self.linear_depths,
                                  np.full(n, np.nan))).ravel()
        top.plot(path_t, path_z, pen=pg.mkPen((255, 255, 255, 90)), connect="finite")
        # Hollow and larger than the other frame markers, so each stays visible where they coincide.
        top.plot(raw_t, self.reported_depths, pen=None, symbol="o", symbolSize=10,
                 symbolPen=(150, 150, 150), symbolBrush=None, name="raw (camera time, reported depth)")
        top.plot(t, self.reported_depths, pen=None, symbol="d", symbolSize=8,
                 symbolPen=(255, 150, 0), symbolBrush=None, name="time-corrected (reported depth)")
        if len(self.obs_times):
            top.plot(self.obs_times - t0, self.obs_depths, pen=None, symbol="x",
                     symbolSize=8, symbolPen="y", name="observations (report changes)")
        if fitted:
            # np.interp holds the fit flat outside the knots, so extend it to the frames' span.
            curve_t = np.unique(np.concatenate((self.knot_times, self.frame_times)))
            top.plot(curve_t - t0, np.interp(curve_t, self.knot_times, self.knot_depths),
                     pen=pg.mkPen("g", width=2), name="piecewise-linear fit")
            top.plot(self.knot_times - t0, self.knot_depths, pen=None, symbol="o",
                     symbolSize=7, symbolPen="g", symbolBrush=None, name="fit knots")
        top.plot(t, self.linear_depths, pen=None, symbol="+", symbolSize=6,
                 symbolPen=None, symbolBrush="c", name="time + depth corrected")
        if self.selected_indices is not None:
            sel = np.asarray(self.selected_indices, dtype=int)
            top.plot(t[sel], self.linear_depths[sel], pen=None, symbol="s", symbolSize=13,
                     symbolPen="r", symbolBrush=None, name="selected")

        bottom = plots.addPlot(row=1, col=0)
        bottom.setLabel("left", "linearized - reported", units="m")
        bottom.setXLink(top)
        bottom.plot(t, self.linear_depths - self.reported_depths, pen=None, symbol="o",
                    symbolSize=4, symbolPen=None, symbolBrush="c")

        times = plots.addPlot(row=2, col=0)
        times.setLabel("left", "corrected - raw time", units="s")
        times.setLabel("bottom", "time", units="s")
        times.setXLink(top)
        times.plot(t, self.frame_times - self.raw_frame_times, pen=None, symbol="o",
                   symbolSize=4, symbolPen=None, symbolBrush="m")
        for row, stretch in enumerate((2, 1, 1)):
            plots.ci.layout.setRowStretchFactor(row, stretch)
        win.show()
        return win


def stamp_z_stack_planes(frames: list[Frame], z_step: float, surface_depth: "float | None") -> None:
    """Write each finished plane's transform and stack metadata, in one pass.

    The last of the three stages. Selection has already settled which frame is which
    plane and what depth each sits at; all that is left is to say how the stack is
    arranged and where it came from. Doing it here, once, is the point: the transform used
    to be rewritten two or three times over on its way out -- by the depth estimate, again
    by selection restating a depth the frame already had, and again here -- so what a
    frame finally carried depended on which of those had run.

    Two things get written. The **z scale** is set to *z_step* while the transform's z
    direction is left alone, so that the first frame's transform describes the whole stack:
    frame *i* sits *i* steps along it. That is how the stack is saved -- ``saveImage``
    stores the first frame's transform and each ``appendImage`` adds only a position -- so
    a stack whose frames are roughly evenly spaced is fully described by it. The scale is
    signed along the order of the list it is handed, so a caller passing its planes
    deepest-first gets a negative z step. ``acquire_z_stack`` never does: it hands its
    stack over ascending whichever way the focus travelled, so in production the step is
    always positive.

    The **surface depth** is the global z of the plane the sample was cut along, whatever
    the microscope currently reports. Recording it on every frame is what lets downstream
    analysis express a feature's depth below the surface rather than in stage coordinates.

    Parameters
    ----------
    frames: list[Frame]
        The finished planes, in the order they will be returned. Modified in place.
    z_step: float
        Signed distance from one plane to the next in the order *frames* are given, in
        metres.
    surface_depth: float | None
        Global z of the sample surface in metres, or None if no surface has been marked.
    """
    for frame in frames:
        # this xform will be composite, so we can't just do `.scale = ...`
        xform = frame.globalTransform().as_affine()
        m = xform.matrix  # get a copy to modify
        z_vector = m[:, 2]
        m[:, 2] = z_vector / np.linalg.norm(z_vector) * z_step
        xform.matrix = m  # use the setter so the change is stored
        frame.addInfo(transform=xform, surfaceDepth=surface_depth)


class ImageSequencerCtrl(Qt.QWidget):
    """GUI for acquiring z-stacks, timelapse, and mosaic."""

    def __init__(self, cameraMod):
        self.mod = weakref.ref(cameraMod)
        Qt.QWidget.__init__(self)

        self.imager = None
        self._manuallyStopped = False

        self.ui = Qt.importTemplate(".sequencerTemplate")()
        self.ui.setupUi(self)

        self.ui.zStartSpin.setOpts(value=100e-6, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.zEndSpin.setOpts(value=50e-6, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.zSpacingSpin.setOpts(min=1e-9, value=1e-6, suffix="m", siPrefix=True, dec=True, minStep=1e-9, step=0.5)
        self.ui.intervalSpin.setOpts(min=0, value=1, suffix="s", siPrefix=True, dec=True, minStep=1e-3, step=1)
        self.ui.xLeftSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.xRightSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.yTopSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.yBottomSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.mosaicOverlapSpin.setOpts(
            value=50e-6, suffix="m", siPrefix=True, step=1e-6, decimals=6, bounds=(0, float("inf"))
        )

        self.updateDeviceList()
        self.ui.statusLabel.setText("[ stopped ]")

        self._future: Optional[QtFriendlyTask] = None

        self.state = pg.WidgetGroup(self)
        self.state.sigChanged.connect(self.stateChanged)
        cameraMod.sigInterfaceAdded.connect(self.updateDeviceList)
        cameraMod.sigInterfaceRemoved.connect(self.updateDeviceList)
        self.ui.startBtn.clicked.connect(self.startClicked)
        self.ui.setStartBtn.clicked.connect(self.setStartClicked)
        self.ui.setEndBtn.clicked.connect(self.setEndClicked)
        self.ui.setTopLeftBtn.clicked.connect(self.setTopLeftClicked)
        self.ui.setBottomRightBtn.clicked.connect(self.setBottomRightClicked)

    def updateDeviceList(self):
        items = ["Select device.."]
        self.ui.deviceCombo.clear()
        items.extend(k for k, v in self.mod().interfaces.items() if v.canImage)
        self.ui.deviceCombo.setItems(items)
        if len(items) == 2:  # only one real device plus the placeholder
            self.ui.deviceCombo.setCurrentIndex(1)

    def selectedImager(self):
        if self.ui.deviceCombo.currentIndex() < 1:
            return None
        name = self.ui.deviceCombo.currentText()
        return self.mod().interfaces[name].getDevice()

    def _selectedImagerOrComplain(self):
        dev = self.selectedImager()
        if dev is None:
            raise ValueError("Must select an imaging device first.")
        return dev

    def stateChanged(self, name, value):
        if name == "deviceCombo":
            imager = self.selectedImager()
            self.imager = imager
        self.updateStatus()

    def makeProtocol(self):
        """Build a description of everything that needs to be done during the sequence."""
        prot = {"imager": self.selectedImager()}
        if self.ui.zStackGroup.isChecked():
            start = self.ui.zStartSpin.value()
            end = self.ui.zEndSpin.value()
            spacing = self.ui.zSpacingSpin.value()
            prot["z_stack"] = (start, end, spacing)

        if self.ui.timelapseGroup.isChecked():
            count = self.ui.iterationsSpin.cleanText()
            if count == "inf":
                count = float(count)
            else:
                count = int(count)
            prot["count"] = count
            prot["interval"] = self.ui.intervalSpin.value()
        else:
            prot["count"] = 1
            prot["interval"] = 0

        if self.ui.mosaicGroup.isChecked():
            prot["mosaic"] = (
                self.ui.xLeftSpin.value(),
                self.ui.yTopSpin.value(),
                self.ui.xRightSpin.value(),
                self.ui.yBottomSpin.value(),
                self.ui.mosaicOverlapSpin.value(),
            )

        if self.ui.pinCheckbox.isChecked():
            prot["pin"] = lambda f: run_in_gui_thread(self.mod().displayPinnedFrame, f)

        return prot

    def startClicked(self, b):
        if b:
            self.start()
        else:
            self.stop()

    def start(self):
        try:
            if self.selectedImager() is None:
                raise RuntimeError("No imaging device selected.")
            prot = self.makeProtocol()
            dh = Manager.getManager().getCurrentDir().getDir("ImageSequence", create=True, autoIncrement=True)
            dhinfo = prot.copy()
            del dhinfo["imager"]
            if "pin" in dhinfo:
                del dhinfo["pin"]
            if dhinfo["count"] == float("inf"):
                dhinfo["count"] = -1
            dh.setInfo(dhinfo)
            prot["storage_dir"] = dh
            self.setRunning(True)
            self._future = run_image_sequence(**prot)
            self._future.sigFinished.connect(self.threadStopped)
            self._future.sigStateChanged.connect(self.threadMessage)
        except Exception:
            self.threadStopped(self._future)
            raise
        if self._future.is_done:  # probably an immediate error
            self.threadStopped(self._future)

    def stop(self):
        if self._future is not None:
            self.ui.startBtn.setText("Stopping...")
            self.ui.startBtn.setEnabled(False)
            self._future.stop()
            self._manuallyStopped = True

    def threadStopped(self, future):
        try:
            self.ui.startBtn.setText("Start")
            self.ui.startBtn.setChecked(False)
            self.setRunning(False)
            self.updateStatus()
            if self._future is not None:
                fut = self._future
                self._future.sigStateChanged.disconnect(self.threadMessage)
                self._future = None
                if not self._manuallyStopped:
                    fut.wait(timeout=1)  # to raise errors if any happened
        finally:
            self._manuallyStopped = False

    def setRunning(self, b):
        self.ui.startBtn.setEnabled(True)
        self.ui.startBtn.setText("Stop" if b else "Start")
        self.ui.zStackGroup.setEnabled(not b)
        self.ui.mosaicGroup.setEnabled(not b)
        self.ui.timelapseGroup.setEnabled(not b)
        self.ui.deviceCombo.setEnabled(not b)

    def threadMessage(self, future, message):
        self.ui.statusLabel.setText(message)

    def updateStatus(self):
        prot = self.makeProtocol()
        if prot["count"] > 1:
            itermsg = f"iter=0/{prot['count']}"
        else:
            itermsg = "iter=0"

        msg = f"[ stopped  {itermsg} ]"
        self.ui.statusLabel.setText(msg)

    def setStartClicked(self):
        dev = self._selectedImagerOrComplain()
        self.ui.zStartSpin.setValue(dev.getFocusDepth())

    def setEndClicked(self):
        dev = self._selectedImagerOrComplain()
        self.ui.zEndSpin.setValue(dev.getFocusDepth())

    def setTopLeftClicked(self):
        cam = self._selectedImagerOrComplain()
        region = cam.getParam("region")
        bound = cam.globalTransform().map((region[0], region[1], 0))
        self.ui.xLeftSpin.setValue(bound[0])
        self.ui.yTopSpin.setValue(bound[1])

    def setBottomRightClicked(self):
        cam = self._selectedImagerOrComplain()
        region = cam.getParam("region")
        bound = cam.globalTransform().map((region[0] + region[2], region[1] + region[3], 0))
        self.ui.xRightSpin.setValue(bound[0])
        self.ui.yBottomSpin.setValue(bound[1])
