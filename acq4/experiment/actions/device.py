"""Device-wrapping protocol functions: staged pipette moves (go_*, including the
go_park retraction that gets the tip out of the slice), focusing
(focus_*), a fresh-pipette search+tip-find (new_pipette), tip finding in place
(find_tip), surface detection (find_surface), a pressure-bracketed
sonication of the tip (sonicate), the cell z-stack capture (cellfie), the cell
tracker re-find check (verify_cell), applying a microscope imaging preset
(load_preset), and running a loaded TaskRunner sequence (run_task).

These wrap existing PatchPipette/Pipette/Microscope device APIs and drive real
hardware, so they are exercised by live testing rather than the headless suite.
ctx.pipette is a PatchPipette; the underlying manipulator is ctx.pipette.pipetteDevice.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from acq4.util import Qt
from acq4.util.debug import log_and_ignore_exception
from acq4.util.imaging.sequencer import run_image_sequence
from acq4.util.model_config import segmenter_path
from acq4.util.task import Stopped, check_stop, run_in_gui_thread, sleep

from ..exceptions import OrchestrationError

# Retained trace length per sweep. More than a plot's pixel width, and small
# enough that a 20-sweep sequence costs the pane well under a megabyte per cell
# rather than the 16 MB the undecimated sweeps would. The full data is in the
# saved ProtocolSequence directory either way.
_MAX_TRACE_POINTS = 4000


def _move(ctx, name: str, position: str, speed: str) -> None:
    """Move the pipette to a named position via the global motion planner."""
    with ctx.log_action(name) as action_entry:
        action_entry.set_status(f"moving to {position!r}")
        ctx.pipette.pipetteDevice.moveTo(position, speed).wait()


def go_home(ctx, speed: str = "fast") -> None:
    """Retract the pipette to its home position."""
    _move(ctx, "Pipette To Home", "home", speed)


def go_search(ctx, speed: str = "fast") -> None:
    """Move the pipette to its search position."""
    _move(ctx, "Pipette To Search Position", "search", speed)


def go_approach(ctx, speed: str = "fast") -> None:
    """Move the pipette to the approach position above the target."""
    _move(ctx, "Pipette To Approach Position", "approach", speed)


def go_target(ctx, speed: str = "fast") -> None:
    """Move the pipette to the target position."""
    _move(ctx, "Pipette To Target", "target", speed)


def go_above_target(ctx, speed: str = "fast") -> None:
    """Move the pipette to the position directly above the target."""
    _move(ctx, "Pipette To Above Target", "aboveTarget", speed)


# FSM states that mean the tip is not in the recording chamber: it is out of the
# bath entirely, or bound to a cleaning/refill/collection well somewhere else on
# the rig. Parking one of those would drive it back across to the chamber, and
# putting a well-bound pipette into "bath" would charge it with bath pressure
# where there is no bath. Every other state -- including "broken" and "fouled",
# which is where a failed attempt leaves a tip that is still down in the slice --
# is a state a park applies to.
_OUT_OF_CHAMBER_STATES = frozenset(
    {"out", "clean", "refill", "collect", "home with nucleus"}
)


def _currentStateName(pip) -> str | None:
    """`pip`'s current FSM state name, or None if it has no state running."""
    state = pip.getState()
    return None if state is None else state.stateName


def go_park(ctx, speed: str = "fast", center=None, radius: float | None = None,
            height: float | None = None) -> None:
    """Get the pipette out of the slice the moment it is no longer needed there.

    A tip left down in the tissue between cells is two problems at once: it keeps
    leaking internal into the slice, and it sits in the light path over cells the
    next steps are about to image (the tracker's own z-stack for the next cell,
    or a survey tile). Neither is visible as a failure -- the run simply works the
    next cell through a pipette-shaped shadow.

    Where it parks is Pipette.parkPosition(): just above the sample surface, and
    retracted back along its own axis until it is clear of an *occlusion circle*
    in the horizontal plane. `center` and `radius` name that circle explicitly;
    with neither given the circle is asked of the context (`ctx.occlusion_circle`,
    which the Orchestrator binds to the cells still to be worked). A context that
    answers None has nothing left to stay out of, and the tip goes home instead --
    the end of a run, where there is no reason to leave it hovering over the
    slice.

    The pipette is put into "bath" first, so the retraction happens under a
    defined state rather than out from under whatever was still running (an
    interrupted approach or cell detect drives the pipette itself, and would
    otherwise be moving it at the same time as this). That is skipped, along with
    the move, for a tip that is already clear -- see Pipette.isParked -- which is
    what makes this safe to call from a protocol and from the orchestrator's
    end-of-cell safety net without the second one costing a second move.

    A stopped run parks nothing and says so rather than raising. The natural
    place to call this from a protocol is a finally, which is exactly where a
    stop unwinds through, and a park that raised Stopped from there would replace
    whatever actually ended the pass. The operator has asked the rig to stop
    moving; every move from here would fail its own check_stop() in any case, and
    the FSM has already been put into its state's declared fallback by the abort
    handling in actions.fsm.
    """
    with ctx.log_action("Park Pipette") as action_entry:
        try:
            check_stop()
        except Stopped:
            action_entry.set_status("not parking: the run was stopped")
            return
        pip = ctx.pipette
        dev = pip.pipetteDevice
        stateName = _currentStateName(pip)
        if stateName in _OUT_OF_CHAMBER_STATES:
            action_entry.set_status(f"nothing to do: pipette is {stateName!r}")
            return
        if center is None and radius is None:
            circle = ctx.occlusion_circle()
            if circle is None:
                if _atHome(dev):
                    action_entry.set_status("nothing to do: pipette is already home")
                    return
                action_entry.set_status("retracting home; nothing left to stay clear of")
                _bathBeforeRetracting(pip, action_entry)
                dev.moveTo("home", speed).wait()
                return
            center, radius = circle
        if dev.isParked(center=center, radius=radius, height=height):
            action_entry.set_status("nothing to do: pipette is already clear")
            return
        _bathBeforeRetracting(pip, action_entry)
        action_entry.set_status("parking clear of the slice")
        dev.goPark(speed=speed, center=center, radius=radius, height=height).wait()


# How far from its home position the tip may be and still count as home, for the
# only question go_park asks of it: "is there a retraction left to make". Loose
# because nothing downstream depends on the tip being at home to the micron --
# a tip within a tenth of a millimetre of home is not in the slice, which is the
# whole of what this decides.
_HOME_TOLERANCE = 100e-6


def _atHome(dev) -> bool:
    """True if `dev`'s tip is already at (or within _HOME_TOLERANCE of) home.

    False rather than raising for a manipulator with no home position defined:
    that is a rig that cannot answer the question, and the honest response is to
    make the move and let it fail there with its own message, not to refuse the
    park over it.
    """
    try:
        home = np.asarray(dev.homePosition(), dtype=float)
    except Exception:
        return False
    return bool(np.linalg.norm(np.asarray(dev.globalPosition(), dtype=float) - home) <= _HOME_TOLERANCE)


def _bathBeforeRetracting(pip, action_entry) -> None:
    """Put `pip` into the "bath" state before its tip is pulled out of the slice.

    Two things at once. It stops whatever state job was running: approach, cell
    detect, contact cell and clean all drive the manipulator themselves, and a
    retraction made while one of them is still stepping the tip is two callers
    moving one device. And it leaves the pipette somewhere defined -- pressure
    on, test pulse running, resistance watched -- which is what "bath" means and
    what the tip above the surface actually is, rather than a seal state still
    reasoning about a cell the tip has just been pulled off.

    It does end a live whole-cell recording. That is the intended trade and not
    an accident: by the time anything asks for a park, the protocol is done with
    that cell, and the alternative on the rig today is the tip staying on the
    cell -- in the slice, in the light path -- until the *next* cell's clean
    cycle gets around to retracting it.
    """
    stateName = _currentStateName(pip)
    if stateName == "bath":
        return
    action_entry.set_status(f"leaving {stateName!r} for 'bath' before retracting")
    try:
        pip.setState("bath")
    except Exception as e:
        raise OrchestrationError(
            f"{action_entry.name}: could not put {pip.name()} into 'bath' before "
            f"retracting: {e}"
        ) from e


def _focus(ctx, name: str, focus_on: str, speed: str) -> None:
    """Focus the imaging device on a pipette feature ("tip" or "target")."""
    with ctx.log_action(name) as action_entry:
        pip = ctx.pipette
        method = {"tip": pip.focusOnTip, "target": pip.focusOnTarget}[focus_on]
        action_entry.set_status(f"focusing on {focus_on}")
        method(speed).wait()


def focus_tip(ctx, speed: str = "fast") -> None:
    """Focus the imaging device on the pipette tip."""
    _focus(ctx, "Focus On Pipette Tip", "tip", speed)


def focus_target(ctx, speed: str = "fast") -> None:
    """Focus the imaging device on the target."""
    _focus(ctx, "Focus On Target", "target", speed)


def new_pipette(ctx) -> None:
    """Reset per-pipette state and run the search + tip-find calibration for a
    freshly-attached pipette. Mirrors the MultiPatch "New Pipette" button
    (PatchPipette.newPipette)."""
    with ctx.log_action("New Pipette Calibration") as action_entry:
        action_entry.set_status("new pipette: search and tip-find")
        try:
            ctx.pipette.newPipette().wait()
        except Exception as e:
            raise OrchestrationError(f"{action_entry.name}: new-pipette calibration failed: {e}") from e


def find_tip(ctx) -> None:
    """Auto-set the clamp pipette offset, then iteratively locate the pipette tip.

    Calibrates wherever the pipette already is, and never moves it:
    Pipette.iterativelyFindTip walks the *scope* focus over the tip and writes
    what it converges on to the tip offset. Position the pipette first with
    whichever go_* action puts the tip in the field you want it found in --
    go_search for a wide field with the tip centered, go_above_target for the
    position an approach starts from.
    """
    with ctx.log_action("Find Pipette Tip") as action_entry:
        pip = ctx.pipette
        pip.clampDevice.autoPipetteOffset()
        action_entry.set_status("finding pipette tip")
        try:
            pip.pipetteDevice.iterativelyFindTip()
        except Exception as e:
            # Route a tip-finding failure through the orchestrator's exception
            # handling rather than crashing the run loop.
            raise OrchestrationError(f"{action_entry.name}: could not find pipette tip: {e}") from e


def find_surface(ctx):
    """Detect the sample surface depth by focusing the scope through a z-range
    (Microscope.findSurfaceDepth). Returns the detected depth."""
    with ctx.log_action("Find Sample Surface") as action_entry:
        pip = ctx.pipette
        scope = pip.scopeDevice()
        imager = pip.imagingDevice()
        action_entry.set_status("detecting surface")
        try:
            depth = scope.findSurfaceDepth(imager)
        except ValueError as e:
            raise OrchestrationError(f"{action_entry.name}: {e}") from e
        action_entry.set_details(
            "text", {"lines": [f"surface detected at {pg.siFormat(depth, suffix='m')}"]}
        )
        return depth


# Upper bound on how long to wait for a sonication task. Sonicator.doProtocol
# already bounds the crystal drive itself (its own wait is the protocol's
# computed duration x1.3), so this only has to cover that plus the DAQ task
# setup around it -- generously, since the configured protocols run on the
# order of seconds and overshooting here costs nothing on a healthy rig. It
# exists so a sonicator that never reports finished fails the action instead of
# parking the run forever with the regulator charged.
_SONICATION_TIMEOUT = 120.0


def sonicate(
    ctx, protocol: str = "", pressure: float | None = None, settle: float = 0.0
) -> None:
    """Run one of the sonicator's configured protocols on the pipette tip.

    `protocol` names an entry in the Sonicator device's `protocols` config (e.g.
    "clean", "quick clean", "expel"). None or empty is a no-op, so a protocol
    file can leave the step unconfigured -- the same convention `load_preset`
    follows for imaging presets, and what lets a rig whose sonicator has no such
    protocol run the same protocol file unedited.

    `pressure` (Pa), when given, is held from the regulator for the duration of
    the sonication and for `settle` seconds after it, then the source and
    setpoint that were in force beforehand are restored. Positive pressure while
    the crystal runs is what carries loosened debris out of the tip instead of
    letting it settle back, and `settle` keeps expelling for a moment after the
    drive stops. Neither is defaulted here: they are rig numbers, and a protocol
    asking for pressure at the tip should say so at its own call site where an
    operator reading the protocol can see the value -- the same reason `clean`
    leaves `only_if_needed` to its caller.

    The restore is in a `finally`, so a stopped run or a failed sonication
    cannot leave the regulator charged, and the drive is stopped before that
    restore runs, so neither it nor the park that follows a failed action moves
    hardware around a tip that is still sonicating.

    Sonicate only with the tip well clear of the bath. The device applies its
    own `Sonicator.safeToSonicate` check, and on a tip that still looks like it
    is in a recording chamber that check *prompts the operator* -- which stalls
    an unattended run until someone answers. `go_search` parks the tip a
    configured height above the surface and is the intended place to call this
    from; near the target is not.

    Records nothing: there is no readout an operator interprets off a
    sonication, so like `clean` it gets a status line and no details payload.
    """
    if not protocol:
        return
    with ctx.log_action("Sonicate Pipette") as action_entry:
        pip = ctx.pipette
        sonicator = getattr(pip, "sonicatorDevice", None)
        if sonicator is None:
            raise OrchestrationError(
                f"{action_entry.name}: no sonicatorDevice is configured on {pip.name()}"
            )
        # Checked here rather than left to the device: doProtocol falls back to
        # treating an unrecognized name as a literal protocol *definition*, so a
        # misspelled name would reach the DAQ as a malformed stimulus instead of
        # saying which names exist. Mirrors load_preset's unknown-preset error.
        available = getattr(sonicator, "protocols", None) or {}
        if protocol not in available:
            if available:
                names = f"available: {', '.join(sorted(available))}"
            else:
                names = "no protocols are configured on this device"
            raise OrchestrationError(
                f"{action_entry.name}: unknown sonication protocol {protocol!r} ({names})"
            )
        pressureDev = getattr(pip, "pressureDevice", None)
        if pressure is not None and pressureDev is None:
            raise OrchestrationError(
                f"{action_entry.name}: pressure was requested but no pressureDevice "
                f"is configured on {pip.name()}"
            )
        restore = None
        try:
            if pressure is not None:
                # Read before the write, so the restore returns the pipette to
                # whatever its current FSM state left it holding rather than to
                # a hard-coded resting pressure.
                restore = (pressureDev.getSource(), pressureDev.getPressure())
                action_entry.set_status(
                    f"applying {pg.siFormat(pressure, suffix='Pa')}"
                )
                pressureDev.setPressure(source="regulator", pressure=pressure)
            action_entry.set_status(f"sonicating: {protocol!r}")
            sonication = sonicator.doProtocol(protocol)
            try:
                sonication.wait(timeout=_SONICATION_TIMEOUT)
            except Exception:
                # Giving up on the wait does not end the sonication; the crystal runs
                # on. Everything from here moves hardware around a live tip, so the drive
                # is stopped first, with wait=True: a requested stop is not a stop.
                sonication.stop("sonication did not finish", wait=True)
                raise
            if settle > 0:
                action_entry.set_status(f"expelling for {pg.siFormat(settle, suffix='s')}")
                sleep(settle)
        finally:
            if restore is not None:
                # Ignored rather than raised: this runs on the way out of a
                # failure or a stop, and a restore that itself fails must not
                # replace the original exception with its own.
                with log_and_ignore_exception(
                    Exception, "Error restoring pressure after sonication"
                ):
                    source, previous = restore
                    pressureDev.setPressure(source=source, pressure=previous)


def _trackerStack(cell):
    """The 3D stack a cell's tracker holds, oriented for display, or None.

    Reads the same attribute chain AutomationDebug's cell stack view does, and
    swaps rows/cols the same way so the stack displays in the same orientation
    as the Camera module. Returns None rather than raising for a cell whose
    tracker never exposed one: this feeds a display payload, and an action must
    not fail on the orchestrator's worker thread over what the pane can show.
    """
    tracker = getattr(cell, "_tracker", None)
    if tracker is None:
        return None
    try:
        stack = tracker.motion_estimator.original_object_stack.data
        if stack is None:
            return None
        stack = np.asarray(stack)
        if stack.ndim >= 2:
            stack = np.swapaxes(stack, -2, -1)
        return stack
    except Exception:
        return None


def _attachStackDetails(action_entry, cell, title: str) -> None:
    """Attach the cell tracker's stack to `action_entry` as image_stack details,
    if the tracker exposes one. Shared by verify_cell's success and
    tracking-lost paths so a recorded stack is always shown, whichever one
    runs."""
    stack = _trackerStack(cell)
    if stack is not None:
        action_entry.set_details(
            "image_stack",
            {
                "stack": stack,
                "center_index": (
                    stack.shape[0] // 2
                    if stack.ndim >= 3 and stack.shape[0] > 1
                    else None
                ),
                "title": title,
            },
        )


def cellfie(ctx, height: float = 30e-6, step: float = 1e-6) -> None:
    """Capture the cell "cellfie": focus on the target and save a z-stack into
    the current storage directory.

    The z-stack save mirrors ApproachState._maybeTakeACellfie; preset switching
    (e.g. GFP/brightfield) is protocol-specific and left to the caller.

    This records imaging for the operator and does nothing else. The cell
    tracker's reference-and-re-find check is a separate action (verify_cell),
    because the tracker acquires its own stack rather than reading this one.
    """
    with ctx.log_action("Cellfie") as action_entry:
        pip = ctx.pipette
        imager = pip.imagingDevice()
        action_entry.set_status("focusing on target for cellfie")
        pip.focusOnTarget("fast").wait()
        target_z = pip.pipetteDevice.targetPosition()[2]
        start = target_z - height / 2
        end = start + height
        storage = ctx.manager.getCurrentDir().getDir("cellfie", create=True)
        action_entry.set_status("saving cellfie z-stack")
        run_image_sequence(
            imager,
            z_stack=(start, end, step),
            storage_dir=storage,
            name="cellfie",
        ).wait()


def verify_cell(ctx) -> None:
    """Check the cell is still findable where its tracker expects it, seeding
    that tracker's reference on the first pass.

    Cell.initializeTracker has two branches: a cell with no tracker yet gets one
    built and its reference verified, and a cell that already carries one --
    which every cell found by a tile scan does -- is re-found against that
    reference instead. Either way a cell the tracker cannot find goes to the
    tissue_moved hook, and the tracker's cropped object stack is retained as
    this action's Area 5 details.

    The tracker acquires its own z-stack at the cell, under whatever imaging
    preset is loaded when this runs, so run it under the same imaging the
    approach will track the cell in: a reference taken under fluorescence is no
    use for following that cell in brightfield.

    That acquisition moves the imager itself, so no prior focus is needed -- but
    it does want the pipette parked clear of the light path.
    """
    with ctx.log_action("Verify Cell") as action_entry:
        imager = ctx.pipette.imagingDevice()
        # Imported here, not at module scope: acq4_automation lives in an internal
        # repository, and a top-level import would stop every test under
        # acq4/experiment from collecting where it is absent. AutomationDebug's
        # feature_tracking reaches acq4_automation at its own module scope, so
        # importing DEFORMATION_TOLERANCE from it carries the same cost and is
        # deferred for the same reason.
        from acq4.modules.AutomationDebug.feature_tracking import DEFORMATION_TOLERANCE
        from acq4_automation.feature_tracking import CellTrackingLost

        # Initialize (or re-check) the tracker reference used to follow the cell
        # during patching.
        action_entry.set_status("checking the cell against its tracker reference")
        try:
            ctx.cell.initializeTracker(
                imager,
                use_cellpose=True,
                deformation_tolerance=DEFORMATION_TOLERANCE,
                segmenter=segmenter_path(),
            )
        except CellTrackingLost as exc:
            # The tracker could not re-find this cell against its own reference
            # stacks, so the stacks are useless for tracking: the cell has
            # drifted out of reach or died. That is a question about the
            # tissue, not about this action, and the window is what can answer
            # it. The tracker still holds a stack (a fresh reference it just
            # acquired, or the prior pass's reference on a re-verify) -- attach
            # it before tissue_moved raises, so the operator sees what was
            # captured instead of nothing, distinctly titled so they aren't
            # misled into thinking the reference verified.
            _attachStackDetails(
                action_entry, ctx.cell, "Cell Tracker Reference (did not match)"
            )
            ctx.tissue_moved(exc.reason or str(exc))
        # Retained for Area 5: the cube around the cell, which is what an
        # operator reads to judge whether the tracker is looking at the right
        # thing. This action is entirely about that reference, so the stack
        # shown is always the one the check above ran against -- a fresh
        # reference on the first pass, the carried-over one on a re-verify.
        _attachStackDetails(action_entry, ctx.cell, "Cell Tracker Reference")


def load_preset(ctx, preset: str | None = None) -> None:
    """Apply a configured microscope imaging preset (e.g. "GFP", "brightfield").
    A preset of None or empty is a no-op, so a protocol can leave it unconfigured."""
    if not preset:
        return
    with ctx.log_action("Load Imaging Preset") as action_entry:
        scope = ctx.pipette.scopeDevice()
        action_entry.set_status(f"loading preset {preset!r}")
        try:
            scope.loadPreset(preset)
        except KeyError as e:
            if scope.presets:
                available = f"available: {', '.join(sorted(scope.presets))}"
            else:
                available = "no presets are configured on this device"
            raise OrchestrationError(
                f"{action_entry.name}: unknown preset {preset!r} ({available})"
            ) from e


def _decimate(times, values, maxPoints: int = _MAX_TRACE_POINTS):
    """(times, values, factor) reduced to at most `maxPoints` samples.

    A factor of 1 means nothing was dropped. The factor is returned rather than
    swallowed so the pane can say what it is not showing.
    """
    times = np.asarray(times)
    values = np.asarray(values)
    if len(values) <= maxPoints:
        return times, values, 1
    factor = int(np.ceil(len(values) / maxPoints))
    return times[::factor], values[::factor], factor


def _sequenceDirName(taskrunner) -> str:
    """The short name of the directory the sequence saved into, or "" if it did
    not save one (store=False, or a run that never got that far)."""
    sequenceDir = getattr(taskrunner, "lastSequenceDir", None)
    return "" if sequenceDir is None else sequenceDir.shortName()


def run_task(ctx, store: bool = True, timeout: float = 0.0):
    """Run the sequence already loaded into an open TaskRunner module.

    Finds the TaskRunner module whose docks include this pipette's clamp device
    and runs its loaded sequence to completion (mirroring
    AutomationDebug.autopatch.Autopatcher._autopatchRunTaskRunner). Each sweep's
    primary trace is collected, decimated to a plottable size, and retained --
    together with the saved sequence directory -- as a "task_results" details
    payload.

    TODO: opening the TaskRunner module and loading a specified protocol file are
    still the operator's responsibility; taking that over is deferred.
    """
    with ctx.log_action("Task Runner Sequence") as action_entry:
        man = ctx.manager
        clampName = ctx.pipette.clampDevice.name()
        try:
            # 'primary' is a current recording only in voltage clamp; in IC or
            # I=0 it is a membrane potential. Mirrors neuroanalysis
            # TestPulse.plot_units, adjusted for getMode()'s upper-case values.
            units = "A" if ctx.pipette.clampDevice.getMode() == "VC" else "V"
        except Exception:
            # This is a display label, not the sequence itself -- a clamp that
            # cannot report its mode must not fail the action over it.
            units = "A"
        taskrunner = None
        for modName in man.listInterfaces("taskRunnerModule"):
            mod = man.getModule(modName)
            if clampName in mod.docks:
                taskrunner = mod
                break
        if taskrunner is None:
            raise OrchestrationError(
                f"{action_entry.name}: no task runner module found using clamp {clampName!r}"
            )
        info = taskrunner.sequenceInfo
        expected_duration = info["period"] * info["totalParams"]
        timeout = timeout or max(30, expected_duration * 20)
        traces = []
        decimation = 1
        failed_frames = 0

        def onNewFrame(frame):
            """Collect one sweep's clamp trace. Reads the result the way
            MultiClamp's own task GUI does: result['primary'] against
            result.xvals('Time')."""
            nonlocal decimation, failed_frames
            result = frame.get("result", {}).get(clampName)
            if result is None:
                return
            try:
                times, values, factor = _decimate(
                    result.xvals("Time"), result["primary"]
                )
            except Exception:
                # A device whose result is not shaped like a clamp recording is
                # not a reason to fail the sequence; the data is saved on disk
                # regardless of whether the pane can plot it. Counted rather
                # than logged here so that a sequence of many failing sweeps
                # produces one summary line, not one per frame.
                failed_frames += 1
                return
            traces.append((times, values))
            decimation = max(decimation, factor)

        # Connected on the GUI thread, where sigNewFrame is emitted: PyQt gives
        # a plain callable slot the affinity of the thread that called
        # connect(), and this action runs on a gentletask ThreadTask with no Qt
        # event loop -- connecting from here directly would queue every frame to
        # a thread that never pumps events, so no sweep would ever be collected.
        run_in_gui_thread(taskrunner.sigNewFrame.connect, onNewFrame)
        action_entry.set_status("running task runner sequence")
        try:
            run_in_gui_thread(taskrunner.runSequence, store=store).wait(timeout=timeout)
        finally:
            Qt.disconnect(taskrunner.sigNewFrame, onNewFrame)
            if decimation > 1:
                ctx.log(
                    f"{action_entry.name}: plotting sweeps decimated {decimation}x; "
                    f"full data saved on disk"
                )
            if failed_frames:
                ctx.log(
                    f"{action_entry.name}: {failed_frames} sweep(s) could not be "
                    f"read for plotting; full data saved on disk"
                )
            action_entry.set_details(
                "task_results",
                {
                    "traces": traces,
                    "sequence_dir": _sequenceDirName(taskrunner),
                    "decimation": decimation,
                    "units": units,
                },
            )
