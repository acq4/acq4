"""Device-wrapping Actions: move the pipette to a cell (GoTo), capture the cell
tracker reference stack (Cellfie), and run a TaskRunner command (Task)."""
from __future__ import annotations

import json

from ..action import Action
from ..registry import register_action


@register_action(name="GoTo")
class GoToAction(Action):
    """Move the pipette to the current cell's position (planned move to target)."""

    outcomes = ("arrived",)
    paramSpec = ({"name": "speed", "type": "str", "default": "fast"},)

    def run(self, ctx):
        pip = ctx.pipette
        pip.setTarget(ctx.cell.position.coordinates)
        pip.moveTo("target", self.paramValue("speed")).wait()
        return "arrived"


@register_action(name="Cellfie")
class CellfieAction(Action):
    """Capture the cell tracker's reference stack (the "cellfie")."""

    outcomes = ("captured",)

    def run(self, ctx):
        imager = ctx.pipette.imagingDevice()
        ctx.cell.initializeTracker(imager, use_cellpose=True)
        return "captured"


@register_action(name="Task")
class TaskAction(Action):
    """Run a TaskRunner command (a JSON object in the `command` param) headless via
    Manager.runTask. Loading a saved protocol file into a command dict is a later
    concern; this action takes the command directly."""

    outcomes = ("done",)
    paramSpec = ({"name": "command", "type": "text", "default": "{}"},)

    def run(self, ctx):
        command = json.loads(self.paramValue("command") or "{}")
        self.results["result"] = ctx.manager.runTask(command)
        return "done"
