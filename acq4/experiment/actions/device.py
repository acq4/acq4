"""Device-wrapping protocol functions: staged pipette moves (go_*), focusing
(focus_*), a fresh-pipette search+tip-find (new_pipette), tip finding above the
target (find_tip), surface detection (find_surface), the cell z-stack capture
(cellfie), applying a microscope imaging preset (load_preset), and running a
loaded TaskRunner sequence (run_task).

These wrap existing PatchPipette/Pipette/Microscope device APIs and drive real
hardware, so they are exercised by live testing rather than the headless suite.
ctx.pipette is a PatchPipette; the underlying manipulator is ctx.pipette.pipetteDevice.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from acq4.util import Qt
from acq4.util.imaging.sequencer import run_image_sequence
from acq4.util.model_config import segmenter_path
from acq4.util.task import run_in_gui_thread

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


def find_tip(ctx, speed: str = "fast") -> None:
    """Move the pipette to just above the target and auto-locate its tip.

    Mirrors the AutomationDebug autopatch tip-finding step: go to the "above
    target" position, auto-set the clamp pipette offset, then iteratively find
    the tip so the pipette position is calibrated before a patch attempt.
    """
    with ctx.log_action("Find Pipette Tip") as action_entry:
        pip = ctx.pipette
        action_entry.set_status("moving above target")
        pip.pipetteDevice.moveTo("aboveTarget", speed).wait()
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
    if the tracker exposes one. Shared by cellfie's success and tracking-lost
    paths so a recorded stack is always shown, whichever one runs."""
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
    """Capture the cell "cellfie": focus on the target, save a z-stack into the
    current storage directory, and initialize the cell tracker's reference.

    The z-stack save mirrors ApproachState._maybeTakeACellfie; preset switching
    (e.g. GFP/brightfield) is protocol-specific and left to the caller.

    Retains the tracker's cropped object stack as this action's Area 5 details.
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
        # Imported here, not at module scope: acq4_automation lives in an internal
        # repository, and a top-level import would stop every test under
        # acq4/experiment from collecting where it is absent. AutomationDebug's
        # feature_tracking reaches acq4_automation at its own module scope, so
        # importing DEFORMATION_TOLERANCE from it carries the same cost and is
        # deferred for the same reason.
        from acq4.modules.AutomationDebug.feature_tracking import DEFORMATION_TOLERANCE
        from acq4_automation.feature_tracking import CellTrackingLost

        # Initialize the tracker reference used to follow the cell during patching.
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
            # it. A stack was still recorded above (a fresh reference, or the
            # prior pass's reference on a re-verify) -- attach it before
            # tissue_moved raises, so the operator sees what was captured
            # instead of nothing, distinctly titled so they aren't misled into
            # thinking the reference verified.
            _attachStackDetails(action_entry, ctx.cell, "Cellfie (reference did not match)")
            ctx.tissue_moved(exc.reason or str(exc))
        # Retained for Area 5: the cube around the cell, which is what an
        # operator reads to judge a cellfie. The full acquired z-stack stays on
        # disk in the cellfie/ directory saved above.
        _attachStackDetails(action_entry, ctx.cell, "Cellfie")


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
