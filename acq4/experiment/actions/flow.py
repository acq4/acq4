"""Flow-control actions: they carry no work, only signal the orchestrator to
advance, retry, or abort by raising the matching control-flow signal."""
from __future__ import annotations

from ..action import Action
from ..registry import register_action
from ..exceptions import AdvanceToNextCell, RetryCurrentCell, AbortExperiment


@register_action(name="GoToNext")
class GoToNextAction(Action):
    outcomes = ()

    def run(self, ctx):
        raise AdvanceToNextCell(f"{self.name}: advance to next cell")


@register_action(name="RetryCell")
class RetryCellAction(Action):
    outcomes = ()

    def run(self, ctx):
        raise RetryCurrentCell(f"{self.name}: retry current cell")


@register_action(name="Abort")
class AbortAction(Action):
    outcomes = ()

    def run(self, ctx):
        raise AbortExperiment(f"{self.name}: abort experiment")
