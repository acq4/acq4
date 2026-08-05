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

from acq4_automation.feature_tracking import CellTrackingLost

from acq4.util.imaging.sequencer import run_image_sequence
from acq4.util.task import run_in_gui_thread

from ..exceptions import OrchestrationError


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
        return depth


def cellfie(ctx, height: float = 30e-6, step: float = 1e-6) -> None:
    """Capture the cell "cellfie": focus on the target, save a z-stack into the
    current storage directory, and initialize the cell tracker's reference.

    The z-stack save mirrors ApproachState._maybeTakeACellfie; preset switching
    (e.g. GFP/brightfield) is protocol-specific and left to the caller.
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
        # Initialize the tracker reference used to follow the cell during patching.
        try:
            ctx.cell.initializeTracker(imager, use_cellpose=True)
        except CellTrackingLost as exc:
            # The tracker could not re-find this cell against its own reference
            # stacks, so the stacks are useless: the cell has drifted out of
            # reach or died. That is a question about the tissue, not about this
            # action, and the window is what can answer it. Never returns.
            ctx.tissue_moved(exc.reason or str(exc))


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


def run_task(ctx, store: bool = True, timeout: float = 0.0):
    """Run the sequence already loaded into an open TaskRunner module.

    Finds the TaskRunner module whose docks include this pipette's clamp device
    and runs its loaded sequence to completion (mirroring
    AutomationDebug.autopatch.Autopatcher._autopatchRunTaskRunner).

    TODO: opening the TaskRunner module and loading a specified protocol file are
    still the operator's responsibility; taking that over is deferred.
    """
    with ctx.log_action("Task Runner Sequence") as action_entry:
        man = ctx.manager
        clampName = ctx.pipette.clampDevice.name()
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
        action_entry.set_status("running task runner sequence")
        run_in_gui_thread(taskrunner.runSequence, store=store).wait(timeout=timeout)
