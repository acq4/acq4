"""Acquire z-stacks, timelapses, and mosaics from an imager, plus the GUI to drive them.
Acquisition runs as gentletask tasks; the pure z-stack math lives in standalone functions."""

from __future__ import annotations

import itertools
import weakref
from dataclasses import dataclass
from typing import Union, Optional, Generator

import numpy as np
from gentletask import asynch
from scipy.optimize import linear_sum_assignment
from skimage.metrics import structural_similarity as ssim

import acq4.Manager as Manager
import pyqtgraph as pg
from acq4.util import Qt, ptime
from acq4.util.DataManager import DirHandle
from acq4.util.task import QtFriendlyTask, check_stop, current_task, set_state, sleep
from acq4.util.imaging import Frame
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


def _depth_observations(depths: np.ndarray, times: np.ndarray, edges: np.ndarray):
    """Infer when the focus passed each depth its controller reported.

    The focus controller publishes its position periodically, and every frame is stamped
    with whichever report was current when that frame was exposed. So a report first
    appearing on frame *e* means the focus crossed that depth at some point between
    frames e-1 and e; this takes the midpoint of those two frames' timestamps as the
    time of the crossing. Each crossing is one observation of the focus.

    Parameters
    ----------
    depths: np.ndarray
        Reported depth of each frame, in metres.
    times: np.ndarray
        Frame timestamps in seconds, non-decreasing.
    edges: np.ndarray
        Indices where *depths* changes, i.e. ``np.flatnonzero(np.diff(depths)) + 1``.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Observation times and the depth observed at each, dropping any that share a time.
    """
    obs_t = 0.5 * (times[edges] + times[edges - 1])
    obs_z = depths[edges]
    keep = np.concatenate(([True], np.diff(obs_t) > 0))
    return obs_t[keep], obs_z[keep]


def _anchor_at_rest(kt: np.ndarray, kz: np.ndarray, first: float, last: float):
    """Add a knot at each end of a depth-against-time fit, where the focus was at rest.

    *kt* and *kz* are the knots of a piecewise-linear fit, which span only the part of
    the sweep the controller reported a changing position over. The controller's first
    changed report arrives after the focus has already left *first*, so those knots
    begin partway into the move and say nothing about when the move began. Extending
    the fit's first segment back to where it reaches *first* dates that departure from
    the motion itself, and extending its last segment forward to *last* does the same
    for the arrival. Interpolating the fit outside the two added knots holds it flat,
    which is what a focus sitting at rest did.

    Parameters
    ----------
    kt: np.ndarray
        Knot times, increasing.
    kz: np.ndarray
        Depth at each knot.
    first: float
        Depth the focus rested at before the sweep, in metres.
    last: float
        Depth it rested at after the sweep, in metres.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        The knots, with a resting knot added at either end where the crossing falls
        within one segment length of it. Unchanged if fewer than two knots were given.
    """
    if len(kt) < 2:
        return kt, kz
    # Cap each extension at the length of the segment being extended. A sweep that
    # starts slowly gives its first segment a shallow slope, which would otherwise place
    # the point where that segment reaches *first* arbitrarily far back in time, and
    # interpolating from there would distort every depth in the sweep.
    lead = trail = None
    span = kt[1] - kt[0]
    rise = kz[1] - kz[0]
    if rise != 0:
        t = kt[0] + (first - kz[0]) * span / rise
        if kt[0] - span <= t < kt[0]:
            lead = t
    span = kt[-1] - kt[-2]
    rise = kz[-1] - kz[-2]
    if rise != 0:
        t = kt[-1] + (last - kz[-1]) * span / rise
        if kt[-1] < t <= kt[-1] + span:
            trail = t
    if lead is not None:
        kt, kz = np.concatenate(([lead], kt)), np.concatenate(([first], kz))
    if trail is not None:
        kt, kz = np.concatenate((kt, [trail])), np.concatenate((kz, [last]))
    return kt, kz


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


def estimate_swept_frame_depths(frames: list[Frame]) -> None:
    """Re-derive each swept frame's depth by fitting depth against time, in place.

    A frame's depth is whatever position the focus controller had last reported when the
    frame was exposed. Where frames arrive faster than those reports, a run of frames
    all carry one stale report, so their depths advance in steps that can be coarser
    than the z step the stack was asked for. Frame timestamps have no such problem, so
    this fits reported depth against time and reads each frame's depth off the fit.

    The fit is piecewise linear through the fewest reports that keep it within half the
    reporting step measured above, so it follows real changes in speed -- acceleration
    at either end of the sweep, or all through it -- without bending to the staircase
    that stale reports alone produce. It costs no acquisition time.

    Only for a continuous sweep that begins and ends at rest, as acquire_z_stack
    arranges; the fit is extended to reach those two resting depths. Stepwise
    acquisition settles at each depth before exposing, so it needs none of this.

    The frames are left untouched where there is nothing to gain or no basis to act:
    reports keeping pace with frames (each depth being already its own), fewer than two
    frames, missing timestamps, timestamps out of order or tied, or a reported depth
    that never changed.

    Parameters
    ----------
    frames: list[Frame]
        Frames of one continuous sweep, in acquisition order. Their transforms are
        rewritten in place; nothing is returned.
    """
    if len(frames) < 2:
        return
    try:
        depths = np.array([f.depth for f in frames], dtype=float)
        times = np.array([f.time for f in frames], dtype=float)
    except (KeyError, TypeError, ValueError):
        return  # no usable timestamps; what the controller reported is all we have
    if not np.all(np.diff(times) >= 0):
        return  # out-of-order timestamps; the reported depths are all we can trust
    edges = np.flatnonzero(np.diff(depths)) + 1
    if len(edges) == 0:
        return  # depth never changed; there is no motion to fit
    runs = np.diff(np.concatenate(([0], edges, [len(depths)])))
    if np.median(runs) < 2:
        # Reports keep pace with frames, so each depth is already its own observation
        # and the gaps between them measure the sweep, not the reporting granularity.
        return
    obs_t, obs_z = _depth_observations(depths, times, edges)
    if len(obs_t) < 2:
        return
    reported = np.unique(depths)
    quantum = float(np.median(np.diff(reported)))
    knots = _reduce_knots(obs_t, obs_z, 0.5 * quantum)
    knot_t, knot_z = _anchor_at_rest(obs_t[knots], obs_z[knots], depths[0], depths[-1])
    for frame, depth in zip(frames, np.interp(times, knot_t, knot_z)):
        xform = frame.globalTransform().as_affine()
        xform.offset = [xform.offset[0], xform.offset[1], depth]
        frame.addInfo(transform=xform)


#: How far outside the commanded planes a frame may sit and still be counted as part of
#: the stack, in metres. An absolute distance rather than a fraction of the step: what it
#: absorbs is the focus controller's reporting jitter at the two ends of the sweep, which
#: does not scale with the step. Roughly half a typical 1 um z-step. Frames further out
#: than this were exposed while the focus was still settling into, or already overshooting
#: out of, the commanded range, so they stand for no plane.
_RANGE_TOL = 5e-7


def select_planes(frames: list[Frame], depths: np.ndarray, *, interpolate: bool = False) -> list[Frame]:
    """Turn the frames a sweep acquired into exactly one frame per commanded plane.

    This is the middle of the three stages a swept stack passes through.
    :func:`estimate_swept_frame_depths` has already established what depth each frame was
    really exposed at; this decides which of those frames -- or which blend of them --
    stands in for each plane the caller asked for; :func:`stamp_z_stack_planes` then writes
    the result. Nothing here re-derives the planes: *depths* is handed in, normally
    straight off ``ZStackPlan.depths``, and ``len(depths)`` is the length of what comes
    back. That is what makes the frame count a property of the request rather than of
    whichever path happened to run -- a promise two callers already carry defenses against
    not being kept.

    **Two ways to fill a plane.** By default each plane is the acquired frame nearest its
    commanded depth, keeping its own measured depth: a real exposure, at approximately the
    right place. Matching is done over the whole stack at once rather than plane by plane,
    because that is what keeps the assignment one-to-one -- a nearest-neighbour pass would
    happily hand one frame to two adjacent planes and leave a third unfilled. With
    *interpolate*, each plane is instead blended from the two frames bracketing it, landing
    on the commanded depth exactly, at the cost of every plane being a mixture of two
    exposures rather than one real frame.

    **What gets rejected.** Frames outside the commanded range by more than ``_RANGE_TOL``
    are dropped before anything else: they were exposed while the focus was still settling
    into or overshooting out of the range, so they stand for no plane. What survives must
    describe one monotonic sweep, and there must be at least one frame per plane;
    interpolation asks for more besides, since blending cannot manufacture structure the
    sweep never sampled. Every one of those is a ``ValueError``, which is the signal
    ``acquire_z_stack`` takes as its cue to fall back to stepped acquisition.

    A plane is only ever filled from *this* sweep; nothing is invented. Nor is anything
    repeated, save in the one case the nearest-frame path tolerates deliberately: where
    several frames share a depth, the sweep genuinely resolved fewer depths than the stack
    asked for, and the stack still comes back full, of the frames the sweep really took.
    Interpolation refuses that same stack, because a blend between two frames at one depth
    would be a fiction.

    Parameters
    ----------
    frames: list[Frame]
        Acquired frames, in acquisition order, each carrying the depth measured for it.
        Neither sorted nor distinct by depth; both are handled here.
    depths: np.ndarray
        The commanded plane depths, in the order the planes should be returned -- usually
        order of travel, so a descending stack comes back descending.
    interpolate: bool
        Blend each plane from its two bracketing frames instead of picking the nearest.

    Returns
    -------
    list[Frame]
        Exactly ``len(depths)`` frames, one per entry of *depths*, in that order. On the
        nearest-frame path they are the acquired frames themselves, untouched, still at
        their own measured depths; on the interpolated path they are new frames sitting
        exactly on *depths*.

    Raises
    ------
    ValueError
        If *depths* is empty; if fewer frames than planes lie inside the commanded range;
        if the frames inside it are not monotonic in depth; or, when interpolating, if
        they hold fewer than two distinct depths, fewer distinct depths than there are
        planes, or fall more than one plane short of either end.
    """
    depths = np.asarray(depths, dtype=float)
    if depths.ndim != 1 or len(depths) == 0:
        raise ValueError("Cannot select planes: no commanded depths were given.")
    low, high = float(depths.min()), float(depths.max())

    # Trim first, so that neither the count nor the monotonic check is decided by frames
    # that were never part of the stack to begin with.
    kept = [f for f in frames if low - _RANGE_TOL <= f.depth <= high + _RANGE_TOL]
    if len(kept) < len(depths):
        raise ValueError(
            f"Insufficient frames to have one frame per step: {len(kept)} of {len(frames)} "
            f"acquired frames lie within the commanded {low * 1e6:.3f}..{high * 1e6:.3f} um, "
            f"but {len(depths)} planes were asked for."
        )

    have = np.array([f.depth for f in kept], dtype=float)
    deltas = np.diff(have)
    if not (np.all(deltas >= 0) or np.all(deltas <= 0)):
        raise ValueError(
            "Frames are not monotonic by depth. Cannot enforce linear stack: a sweep that "
            "doubles back does not have one frame standing for each plane."
        )

    # The one sort the pipeline does. Both paths want depth order -- the blend to find its
    # brackets, the assignment to return its picks in plane order -- and a stable sort
    # leaves frames that tie in the order they were acquired.
    order = np.argsort(have, kind="stable")
    have = have[order]
    kept = [kept[i] for i in order]

    if interpolate:
        return _blend_onto_depths(kept, have, depths)
    return _assign_nearest(kept, have, depths)


def _assign_nearest(frames: list[Frame], have: np.ndarray, depths: np.ndarray) -> list[Frame]:
    """Give each commanded depth its own acquired frame, minimising total depth error.

    Hungarian assignment over ``|commanded - measured|``. Solving the whole stack at once
    is what makes the result one-to-one, and it also lets a frame go to a neighbouring
    plane when that costs the stack as a whole less than giving it to its own nearest.

    Frames come back exactly as they arrived, still at their own measured depths: the plane
    a frame was chosen for says where it was *wanted*, not where it was.
    """
    cost = np.abs(depths[:, None] - have[None, :])
    rows, cols = linear_sum_assignment(cost)
    picks = np.full(len(depths), -1, dtype=int)
    picks[rows] = cols
    assert np.all(picks >= 0), "Hungarian assignment left a plane unfilled"
    return [frames[j] for j in picks]


def _blend_onto_depths(frames: list[Frame], have: np.ndarray, depths: np.ndarray) -> list[Frame]:
    """Build a new frame at each of *depths* by blending the two acquired frames around it.

    Each frame returned is a fresh linear blend of the two input frames whose depths
    bracket the depth wanted, so it sits at exactly that depth instead of wherever an input
    frame happened to land. The blend weight rises strictly with the wanted depth, so no
    two frames returned are identical.

    Frames sharing a depth are collapsed to one first: a blend between two frames at the
    same depth is undefined, and a run of them says the sweep resolved one depth where the
    stack wanted several. Depths past either end of what the frames span are extrapolated
    off the nearest bracket rather than clamped, which would repeat one end image -- but
    only about as far as one plane, beyond which the sweep is judged to have missed the
    stack rather than merely fallen short of it.

    Parameters
    ----------
    frames: list[Frame]
        Acquired frames, sorted by depth. Duplicates by depth are dropped here.
    have: np.ndarray
        Depth of each entry of *frames*, non-decreasing.
    depths: np.ndarray
        Depths to produce a frame at, in the order they should be returned. Need not be
        sorted; a descending stack asks for its planes descending.

    Returns
    -------
    list[Frame]
        One new frame per entry of *depths*, in that order, each carrying that depth and a
        blended timestamp.

    Raises
    ------
    ValueError
        If the frames hold fewer than two distinct depths, fewer distinct depths than
        *depths* asks for planes, or fall more than one plane short of either end.
    """
    keep = np.concatenate(([True], np.diff(have) > 0))
    have = have[keep]
    frames = [f for f, k in zip(frames, keep) if k]
    if len(frames) < 2:
        raise ValueError("Need at least two distinct frame depths to interpolate.")
    if len(frames) < len(depths):
        raise ValueError(
            f"Only {len(frames)} distinct frame depths for {len(depths)} requested planes: "
            f"interpolating would invent planes the sweep never sampled."
        )
    # Depth estimates stop at the last report, so frames can fall short of the commanded
    # ends. Extrapolate off the end bracket; clamping would repeat the same end image.
    reach = max(have[0] - depths.min(), depths.max() - have[-1], 0.0)
    # One plane's worth of extrapolation is fine. A lone plane has no spacing of its own.
    limit = float(np.max(np.abs(np.diff(depths)))) if len(depths) > 1 else float(np.max(np.diff(have)))
    if reach > limit:
        raise ValueError(
            f"Acquired frames span {have[0] * 1e6:.3f}..{have[-1] * 1e6:.3f} um, too far "
            f"inside the requested {depths.min() * 1e6:.3f}..{depths.max() * 1e6:.3f} um to "
            f"interpolate (short by {reach * 1e6:.3f} um, limit {limit * 1e6:.3f} um)."
        )
    out = []
    hi_idx = np.clip(np.searchsorted(have, depths, side="left"), 1, len(have) - 1)
    for depth, hi in zip(depths, hi_idx):
        lo = hi - 1
        weight = (depth - have[lo]) / (have[hi] - have[lo])
        low, high = frames[lo], frames[hi]
        data = low.data() * (1.0 - weight) + high.data() * weight
        if np.issubdtype(low.data().dtype, np.integer):
            data = np.rint(data).astype(low.data().dtype)
        else:
            data = data.astype(low.data().dtype)
        info = dict(low.info())
        xform = low.globalTransform().as_affine()
        xform.offset = [xform.offset[0], xform.offset[1], float(depth)]
        info["transform"] = xform
        info["time"] = low.time * (1.0 - weight) + high.time * weight
        out.append(Frame(data, info))
    return out


def enforce_linear_z_stack(
    frames: list[Frame], start: float, stop: float, step: float, interpolate: bool = False
) -> list[Frame]:
    """Select one frame per commanded plane for a stack swept over ``[start, stop]``.

    A back-compatible spelling of :func:`select_planes` for callers holding the bounds
    rather than the planes: it asks :func:`commanded_depths` what planes those bounds want
    and hands them over. The bounds are sorted first, so the stack comes back ascending in
    depth whichever way round they were given. That is the one difference from calling
    :func:`select_planes` directly with a plan's depths, where the planes arrive in order
    of travel and come back in it.

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
    interpolate: bool
        Blend each plane from its two bracketing frames instead of picking the nearest.

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
    return select_planes(frames, commanded_depths(start, stop, step), interpolate=interpolate)


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


def _set_focus_depth(
    imager,
    depth: float,
    direction: float,
    speed: Union[float, str],
    hysteresis_correction: bool = True,
    name: str | None = None,
):
    if depth is None:
        return

    if isinstance(speed, str):
        speed = imager.getFocusDevice()._interpretSpeed(speed)
    dz = depth - imager.getFocusDepth()
    timeout = max(10, 3 * abs(dz) / speed)

    # Avoid hysteresis:
    hysteresis_correction_distance = imager.getFocusDevice().hysteresisCorrection
    if hysteresis_correction_distance == 0:
        hysteresis_correction = False

    if hysteresis_correction and direction < 0 and dz > 0:
        # stack goes downward
        move = imager.setFocusDepth(depth + hysteresis_correction_distance, speed, name=f"{name} hysteresis correction")
    elif hysteresis_correction and direction > 0 and dz < 0:
        # stack goes upward
        move = imager.setFocusDepth(depth - hysteresis_correction_distance, speed, name=f"{name} hysteresis correction")
    else:
        move = imager.setFocusDepth(depth, speed, name=f"redundant {name}")

    move.wait(timeout=timeout)

    move = imager.setFocusDepth(depth, speed, name=name)  # maybe redundant
    move.wait(timeout=timeout)


def _stepped_z_stack(imager, depths: np.ndarray, name) -> list[Frame]:
    """Acquire one frame at each of *depths*, stopping the focus at every one.

    Takes the planned depths rather than ``(start, stop, step)`` so that it cannot
    disagree with the fast path about how many planes a stack has: as the fast attempt's
    fallback it must return exactly the stack the attempt it replaces would have, and the
    only way to guarantee that is for both to be handed the same array. See
    :func:`commanded_depths`.

    *depths* is in order of travel, so every step after the first approaches from the
    same direction and the overall direction is all the hysteresis correction needs.
    """
    direction = np.sign(depths[-1] - depths[0])
    frames = []
    with imager.ensureRunning(ensureFreshFrames=True):
        for z in depths:
            check_stop()
            _set_focus_depth(imager, z, direction, speed="slow", name=f"{name} step")
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
        back, whichever mode ran, whether or not frames were interpolated, and whether
        or not a fast attempt fell back to stepped. Later stages consume this array
        rather than re-deriving anything from ``(start, stop, step)``, which is what
        makes that promise structural instead of something several separate roundings
        have to agree about -- they did not, and two callers still carry defenses
        against it.
    speed: float
        Sweep speed in metres per second. It governs the fast path; the stepped path
        moves at the focus device's own "slow" speed. It is computed either way because
        choosing between the two modes is a comparison of how long each would take, and
        the fast estimate is a function of this speed.
    """

    mode: str
    depths: np.ndarray
    speed: float


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

    Returns
    -------
    ZStackPlan
        The resolved mode, the commanded plane depths, and the sweep speed.

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

    if mode == "auto":
        estimated_fast_time = abs(stop - start) / speed
        estimated_stepped_time = est_time_per_step * len(depths)
        mode = "fast" if estimated_fast_time < estimated_stepped_time else "stepped"

    return ZStackPlan(mode=mode, depths=depths, speed=speed)


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
    # 3. how acquired frames become the returned planes
    interpolate_frames: bool = False,
    # 4. motion policy and plumbing
    hysteresis_correction: bool = True,
    fallback_to_stepped: bool = True,
    device_reservation_timeout: float = 10.0,
    name: str | None = "z stack",
) -> list[Frame]:
    """Acquire a Z stack from the given imager.

    There are two ways to do it. In **fast** mode the imager records continuously while
    the focus sweeps once from *start* to *stop*, and the frames are afterwards measured,
    selected and stamped onto the commanded planes. In **stepped** mode the focus moves
    to each commanded plane in turn and one frame is taken there. Fast is normally much
    quicker; stepped lands on the commanded depths by construction, and is also the
    fallback when a sweep does not yield a usable frame for every plane.

    :func:`plan_z_stack` makes that choice, and the parameters below are grouped by the
    four things a caller is really deciding: which mode, how fast the sweep may go, what
    becomes of the frames afterwards, and motion policy.

    **The stack always has** ``len(commanded_depths(start, stop, step))`` **planes** --
    the same count at any absolute depth, in either direction of travel, in either mode,
    with or without interpolation, and whether or not a fast attempt fell back to
    stepped.

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
    interpolate_frames: bool
        Blend each plane from the two acquired frames bracketing its commanded depth
        instead of picking the nearest real frame. Trades sharpness for exact,
        reproducible depths. Ignored on the stepped path, which already lands on the
        commanded depths.
    hysteresis_correction: bool
        If True, approach each z position from the same direction to avoid hysteresis.
    fallback_to_stepped: bool
        If True, and fast acquisition fails to produce a usable frame for every plane,
        retry the whole stack with the slower stepped method. If False, that failure
        propagates as the ``ValueError`` it was raised as.
    device_reservation_timeout: float
        Maximum time to wait for device reservation, in seconds.
    name: str | None
        Label attached to the moves this makes, for logs and the motion planner.

    Returns
    -------
    list[Frame]
        One frame per commanded plane, in order of travel -- so a descending stack comes
        back descending -- with corrected z positions, whichever mode ran.
    """
    stage = imager.scopeDev.getFocusDevice()
    plan = plan_z_stack(
        start,
        stop,
        step,
        exposure=imager.getParam('exposure'),
        position_fps=stage.positionUpdatesPerSecond,
        mode=mode,
        max_dz_per_frame=max_dz_per_frame,
        frames_per_step=frames_per_step,
        est_time_per_step=est_time_per_step,
    )
    # Rebound by the fallback below; plan.mode keeps saying what was planned.
    mode = plan.mode
    depths = plan.depths
    direction = stop - start
    man = Manager.getManager()

    # One reservation around both attempts. Releasing it between a failed fast sweep and
    # the stepped retry would leave a window for another operation to move the stage, and
    # the retry would then start from somewhere the plan knows nothing about.
    with man.reserveDevices(imager.devicesToReserve(), timeout=device_reservation_timeout, reserver="acquire_z_stack"):
        if mode == 'fast':
            # Park focus at the stack beginning
            _set_focus_depth(imager, start, direction, "fast", hysteresis_correction, f"{name} start")

            with imager.ensureRunning(ensureFreshFrames=True):
                frames_fut = imager.acquireFrames()
                try:
                    imager.acquireFrames(1).wait()  # just to be sure the camera's recording
                    _set_focus_depth(imager, stop, direction, plan.speed, hysteresis_correction=False, name=f"{name} stop")
                    imager.acquireFrames(1).wait()  # just to be sure the camera caught up
                finally:
                    frames_fut.stop()
            frames = frames_fut.wait(timeout=10)
            # A. measure what depth each frame was really exposed at, then B. pick one
            # frame per commanded plane. B is handed the planned depths rather than the
            # bounds, so it cannot arrive at a different number of planes than the plan.
            estimate_swept_frame_depths(frames)
            try:
                frames = select_planes(frames, depths, interpolate=interpolate_frames)
            except ValueError:
                if not fallback_to_stepped:
                    raise
                imager.logger.info("Failed to fast-acquire linear z stack. Retrying with stepwise movement.")
                mode = 'stepped'

        if mode == 'stepped':
            # Park focus at the stack beginning
            _set_focus_depth(imager, start, direction, "fast", hysteresis_correction, f"{name} start")
            # The very planes the fast attempt was planned over, so a fallback cannot
            # land on a different count than the attempt it is replacing.
            frames = _stepped_z_stack(imager, depths, name=name)

    # C. stamp. The planes are spaced by one signed step along the direction of travel,
    # which is what makes the first frame's transform describe the whole stack.
    z_step = float(depths[1] - depths[0]) if len(depths) > 1 else abs(step)
    stamp_z_stack_planes(frames, z_step, imager.scopeDev.getSurfaceDepth())
    return frames


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
    signed along the direction of travel, so a descending stack gets a negative z step and
    stays consistent with the order its frames come back in.

    The **surface depth** is the global z of the plane the sample was cut along, whatever
    the microscope currently reports. Recording it on every frame is what lets downstream
    analysis express a feature's depth below the surface rather than in stage coordinates.

    Parameters
    ----------
    frames: list[Frame]
        The finished planes, in the order they will be returned. Modified in place.
    z_step: float
        Signed distance from one plane to the next along the direction of travel, in
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
