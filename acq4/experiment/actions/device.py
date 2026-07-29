"""Device-wrapping Actions and their plain-function equivalents: staged pipette
moves (Go*/go_*), focusing (Focus*/focus_*), a fresh-pipette search+tip-find
(NewPipette/new_pipette), tip finding above the target (FindTip/find_tip),
surface detection (FindSurface/find_surface), the cell z-stack capture
(Cellfie/cellfie), and running a loaded TaskRunner sequence (Task/run_task).

These wrap existing PatchPipette/Pipette/Microscope device APIs and drive real
hardware, so they are exercised by live testing rather than the headless suite.
ctx.pipette is a PatchPipette; the underlying manipulator is ctx.pipette.pipetteDevice.
"""
from __future__ import annotations

from acq4.util.imaging.sequencer import run_image_sequence
from acq4.util.task import run_in_gui_thread

from ..action import Action
from ..registry import register_action
from ..exceptions import OrchestrationError


class _NamedMoveAction(Action):
    """Base for moves to a named pipette position via the global motion planner.

    Subclasses set ``position`` to one of the Pipette's named positions
    (home, search, approach, target, aboveTarget).
    """

    position: str = None
    outcomes = ("moved",)
    paramSpec = ({"name": "speed", "type": "str", "default": "fast"},)

    def run(self, ctx):
        self.setState(f"moving to {self.position!r}")
        ctx.pipette.pipetteDevice.moveTo(self.position, self.paramValue("speed")).wait()
        return "moved"


@register_action(name="GoHome")
class GoHomeAction(_NamedMoveAction):
    """Retract the pipette to its home position."""

    position = "home"


@register_action(name="GoSearch")
class GoSearchAction(_NamedMoveAction):
    """Move the pipette to its search position."""

    position = "search"


@register_action(name="GoApproach")
class GoApproachAction(_NamedMoveAction):
    """Move the pipette to the approach position above the target."""

    position = "approach"


@register_action(name="GoTarget")
class GoTargetAction(_NamedMoveAction):
    """Move the pipette to the target position."""

    position = "target"


@register_action(name="GoAboveTarget")
class GoAboveTargetAction(_NamedMoveAction):
    """Move the pipette to the position directly above the target."""

    position = "aboveTarget"


class _FocusAction(Action):
    """Base for focusing the imaging device on a pipette feature.

    Subclasses set ``focus_on`` to "tip" or "target".
    """

    focus_on: str = None
    outcomes = ("focused",)
    paramSpec = ({"name": "speed", "type": "str", "default": "fast"},)

    def run(self, ctx):
        pip = ctx.pipette
        method = {"tip": pip.focusOnTip, "target": pip.focusOnTarget}[self.focus_on]
        self.setState(f"focusing on {self.focus_on}")
        method(self.paramValue("speed")).wait()
        return "focused"


@register_action(name="FocusTip")
class FocusTipAction(_FocusAction):
    """Focus the imaging device on the pipette tip."""

    focus_on = "tip"


@register_action(name="FocusTarget")
class FocusTargetAction(_FocusAction):
    """Focus the imaging device on the target."""

    focus_on = "target"


@register_action(name="NewPipette")
class NewPipetteAction(Action):
    """Reset per-pipette state and run the search + tip-find calibration for a
    freshly-attached pipette. Mirrors the MultiPatch "New Pipette" button
    (PatchPipette.newPipette)."""

    outcomes = ("ready",)

    def run(self, ctx):
        self.setState("new pipette: search and tip-find")
        try:
            ctx.pipette.newPipette().wait()
        except Exception as e:
            raise OrchestrationError(
                f"{self.name}: new-pipette calibration failed: {e}"
            ) from e
        return "ready"


@register_action(name="FindTip")
class FindTipAction(Action):
    """Move the pipette to just above the target and auto-locate its tip.

    Mirrors the AutomationDebug autopatch tip-finding step: go to the "above
    target" position, auto-set the clamp pipette offset, then iteratively find
    the tip so the pipette position is calibrated before a patch attempt.
    """

    outcomes = ("found",)
    paramSpec = ({"name": "speed", "type": "str", "default": "fast"},)

    def run(self, ctx):
        pip = ctx.pipette
        self.setState("moving above target")
        pip.pipetteDevice.moveTo("aboveTarget", self.paramValue("speed")).wait()
        pip.clampDevice.autoPipetteOffset()
        self.setState("finding pipette tip")
        try:
            pip.pipetteDevice.iterativelyFindTip()
        except Exception as e:
            # Route a tip-finding failure through the orchestrator's exception
            # handling rather than crashing the run loop.
            raise OrchestrationError(f"{self.name}: could not find pipette tip: {e}") from e
        return "found"


@register_action(name="FindSurface")
class FindSurfaceAction(Action):
    """Detect the sample surface depth by focusing the scope through a z-range
    (Microscope.findSurfaceDepth) and store it on the results."""

    outcomes = ("found",)

    def run(self, ctx):
        pip = ctx.pipette
        scope = pip.scopeDevice()
        imager = pip.imagingDevice()
        self.setState("detecting surface")
        try:
            depth = scope.findSurfaceDepth(imager)
        except ValueError as e:
            raise OrchestrationError(f"{self.name}: {e}") from e
        self.results["surface_depth"] = depth
        return "found"


@register_action(name="Cellfie")
class CellfieAction(Action):
    """Capture the cell "cellfie": focus on the target, save a z-stack into the
    current storage directory, and initialize the cell tracker's reference.

    The z-stack save mirrors ApproachState._maybeTakeACellfie; preset switching
    (e.g. GFP/brightfield) is protocol-specific and left to the caller.
    """

    outcomes = ("captured",)
    paramSpec = (
        {"name": "height", "type": "float", "default": 30e-6},
        {"name": "step", "type": "float", "default": 1e-6},
    )

    def run(self, ctx):
        pip = ctx.pipette
        imager = pip.imagingDevice()
        self.setState("focusing on target for cellfie")
        pip.focusOnTarget("fast").wait()
        height = self.paramValue("height")
        target_z = pip.pipetteDevice.targetPosition()[2]
        start = target_z - height / 2
        end = start + height
        storage = ctx.manager.getCurrentDir().getDir("cellfie", create=True)
        self.setState("saving cellfie z-stack")
        run_image_sequence(
            imager,
            z_stack=(start, end, self.paramValue("step")),
            storage_dir=storage,
            name="cellfie",
        ).wait()
        # Initialize the tracker reference used to follow the cell during patching.
        ctx.cell.initializeTracker(imager, use_cellpose=True)
        return "captured"


@register_action(name="Task")
class TaskAction(Action):
    """Run the sequence already loaded into an open TaskRunner module.

    Finds the TaskRunner module whose docks include this pipette's clamp device
    and runs its loaded sequence to completion (mirroring
    AutomationDebug.autopatch.Autopatcher._autopatchRunTaskRunner).

    TODO: opening the TaskRunner module and loading a specified protocol file are
    still the operator's responsibility; taking that over is deferred.
    """

    outcomes = ("done",)
    paramSpec = (
        {"name": "store", "type": "bool", "default": True},
        {"name": "timeout", "type": "float", "default": 0.0},  # 0 -> auto from sequence length
    )

    def run(self, ctx):
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
                f"{self.name}: no task runner module found using clamp {clampName!r}"
            )
        info = taskrunner.sequenceInfo
        expected_duration = info["period"] * info["totalParams"]
        timeout = self.paramValue("timeout") or max(30, expected_duration * 20)
        self.setState("running task runner sequence")
        run_in_gui_thread(
            taskrunner.runSequence, store=self.paramValue("store")
        ).wait(timeout=timeout)
        return "done"


def _move(ctx, name: str, position: str, speed: str) -> None:
    """Move the pipette to a named position via the global motion planner."""
    with ctx.log_action(name) as entry:
        entry.set_status(f"moving to {position!r}")
        ctx.pipette.pipetteDevice.moveTo(position, speed).wait()


def go_home(ctx, speed: str = "fast") -> None:
    """Retract the pipette to its home position."""
    _move(ctx, "GoHome", "home", speed)


def go_search(ctx, speed: str = "fast") -> None:
    """Move the pipette to its search position."""
    _move(ctx, "GoSearch", "search", speed)


def go_approach(ctx, speed: str = "fast") -> None:
    """Move the pipette to the approach position above the target."""
    _move(ctx, "GoApproach", "approach", speed)


def go_target(ctx, speed: str = "fast") -> None:
    """Move the pipette to the target position."""
    _move(ctx, "GoTarget", "target", speed)


def go_above_target(ctx, speed: str = "fast") -> None:
    """Move the pipette to the position directly above the target."""
    _move(ctx, "GoAboveTarget", "aboveTarget", speed)


def _focus(ctx, name: str, focus_on: str, speed: str) -> None:
    """Focus the imaging device on a pipette feature ("tip" or "target")."""
    with ctx.log_action(name) as entry:
        pip = ctx.pipette
        method = {"tip": pip.focusOnTip, "target": pip.focusOnTarget}[focus_on]
        entry.set_status(f"focusing on {focus_on}")
        method(speed).wait()


def focus_tip(ctx, speed: str = "fast") -> None:
    """Focus the imaging device on the pipette tip."""
    _focus(ctx, "FocusTip", "tip", speed)


def focus_target(ctx, speed: str = "fast") -> None:
    """Focus the imaging device on the target."""
    _focus(ctx, "FocusTarget", "target", speed)


def new_pipette(ctx) -> None:
    """Reset per-pipette state and run the search + tip-find calibration for a
    freshly-attached pipette. Mirrors the MultiPatch "New Pipette" button
    (PatchPipette.newPipette)."""
    with ctx.log_action("NewPipette") as entry:
        entry.set_status("new pipette: search and tip-find")
        try:
            ctx.pipette.newPipette().wait()
        except Exception as e:
            raise OrchestrationError(f"new-pipette calibration failed: {e}") from e


def find_tip(ctx, speed: str = "fast") -> None:
    """Move the pipette to just above the target and auto-locate its tip.

    Mirrors the AutomationDebug autopatch tip-finding step: go to the "above
    target" position, auto-set the clamp pipette offset, then iteratively find
    the tip so the pipette position is calibrated before a patch attempt.
    """
    with ctx.log_action("FindTip") as entry:
        pip = ctx.pipette
        entry.set_status("moving above target")
        pip.pipetteDevice.moveTo("aboveTarget", speed).wait()
        pip.clampDevice.autoPipetteOffset()
        entry.set_status("finding pipette tip")
        try:
            pip.pipetteDevice.iterativelyFindTip()
        except Exception as e:
            # Route a tip-finding failure through the orchestrator's exception
            # handling rather than crashing the run loop.
            raise OrchestrationError(f"could not find pipette tip: {e}") from e


def find_surface(ctx):
    """Detect the sample surface depth by focusing the scope through a z-range
    (Microscope.findSurfaceDepth). Returns the detected depth."""
    with ctx.log_action("FindSurface") as entry:
        pip = ctx.pipette
        scope = pip.scopeDevice()
        imager = pip.imagingDevice()
        entry.set_status("detecting surface")
        try:
            depth = scope.findSurfaceDepth(imager)
        except ValueError as e:
            raise OrchestrationError(str(e)) from e
        return depth


def cellfie(ctx, height: float = 30e-6, step: float = 1e-6) -> None:
    """Capture the cell "cellfie": focus on the target, save a z-stack into the
    current storage directory, and initialize the cell tracker's reference.

    The z-stack save mirrors ApproachState._maybeTakeACellfie; preset switching
    (e.g. GFP/brightfield) is protocol-specific and left to the caller.
    """
    with ctx.log_action("Cellfie") as entry:
        pip = ctx.pipette
        imager = pip.imagingDevice()
        entry.set_status("focusing on target for cellfie")
        pip.focusOnTarget("fast").wait()
        target_z = pip.pipetteDevice.targetPosition()[2]
        start = target_z - height / 2
        end = start + height
        storage = ctx.manager.getCurrentDir().getDir("cellfie", create=True)
        entry.set_status("saving cellfie z-stack")
        run_image_sequence(
            imager,
            z_stack=(start, end, step),
            storage_dir=storage,
            name="cellfie",
        ).wait()
        # Initialize the tracker reference used to follow the cell during patching.
        ctx.cell.initializeTracker(imager, use_cellpose=True)


def run_task(ctx, store: bool = True, timeout: float = 0.0):
    """Run the sequence already loaded into an open TaskRunner module.

    Finds the TaskRunner module whose docks include this pipette's clamp device
    and runs its loaded sequence to completion (mirroring
    AutomationDebug.autopatch.Autopatcher._autopatchRunTaskRunner).

    TODO: opening the TaskRunner module and loading a specified protocol file are
    still the operator's responsibility; taking that over is deferred.
    """
    with ctx.log_action("Task") as entry:
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
                f"no task runner module found using clamp {clampName!r}"
            )
        info = taskrunner.sequenceInfo
        expected_duration = info["period"] * info["totalParams"]
        timeout = timeout or max(30, expected_duration * 20)
        entry.set_status("running task runner sequence")
        run_in_gui_thread(taskrunner.runSequence, store=store).wait(timeout=timeout)
