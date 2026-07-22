"""Device-wrapping Actions: capture the cell tracker reference stack (Cellfie)
and run a TaskRunner command (Task)."""
from __future__ import annotations

import json

from ..action import Action
from ..registry import register_action
from ..exceptions import OrchestrationError


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
