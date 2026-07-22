"""Device-wrapping Actions: find the pipette tip above the target (FindTip),
capture and save the cell z-stack (Cellfie), and run a TaskRunner command (Task).

These wrap existing PatchPipette/Pipette device APIs. They run against real
hardware, so they are exercised by live testing rather than the headless suite.
"""
from __future__ import annotations

import json

from acq4.util.imaging.sequencer import run_image_sequence

from ..action import Action
from ..registry import register_action
from ..exceptions import OrchestrationError


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
    """Run a TaskRunner command (a JSON object in the `command` param) headless via
    Manager.runTask. Loading a saved protocol file into a command dict is a later
    concern; this action takes the command directly.

    TODO: the real implementation should drive an already-open TaskRunner module
    instance (loading the specified task and taking over the run), rather than
    calling Manager.runTask with a raw command dict. See
    acq4.modules.AutomationDebug.autopatch.Autopatcher._autopatchRunTaskRunner for
    the pattern to take over. Deferred to a later stage of this work.
    """

    outcomes = ("done",)
    paramSpec = ({"name": "command", "type": "text", "default": "{}"},)

    def run(self, ctx):
        raw = self.paramValue("command") or "{}"
        try:
            command = json.loads(raw)
        except ValueError as e:
            # Route malformed command JSON through the orchestrator's exception
            # handling (catch-all "Exception") rather than crashing the run loop.
            raise OrchestrationError(f"{self.name}: invalid command JSON: {e}") from e
        self.results["result"] = ctx.manager.runTask(command)
        return "done"
