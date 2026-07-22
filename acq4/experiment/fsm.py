"""FSM-wrapping Actions: drive acq4's PatchPipette state machine to a declared
terminal state, mapping unexpected abnormal states to orchestration exceptions."""
from __future__ import annotations

from acq4.util.task import check_stop, sleep

from .action import Action
from .registry import register_action
from .exceptions import ABNORMAL_STATE_EXCEPTIONS


class FsmCompositeAction(Action):
    """Drive the PatchPipette FSM from ``entry_state`` and finish when it reaches one
    of this action's declared ``outcomes`` (FSM terminal state names). The reached
    state name is the outcome the protocol graph routes on.

    If the FSM lands on an abnormal state (see ABNORMAL_STATE_EXCEPTIONS) that is not
    one of the declared outcomes, the mapped OrchestrationError is raised so the
    orchestrator's exception handling takes over. Subclasses set ``entry_state`` and
    ``outcomes`` (and optionally ``entry_config``/``poll_interval``).
    """

    entry_state: str = None
    entry_config: dict = {}
    poll_interval: float = 0.1  # seconds between FSM state polls

    def run(self, ctx) -> str:
        if self.entry_state is None:
            raise ValueError(f"{self.name}: entry_state is not set")
        pip = ctx.pipette
        self.setState(f"driving FSM from {self.entry_state!r}")
        pip.setState(self.entry_state, **self.entry_config)
        while True:
            check_stop()
            state = pip.getState().stateName
            if state in self.outcomes:
                self.setState(f"reached {state!r}")
                self.results["final_state"] = state
                return state
            exc_cls = ABNORMAL_STATE_EXCEPTIONS.get(state)
            if exc_cls is not None:
                raise exc_cls(f"{self.name}: pipette entered {state!r} state")
            sleep(self.poll_interval)

    def safeAbort(self, ctx) -> None:
        pip = getattr(ctx, "pipette", None)
        if pip is None:
            return
        # Best-effort retract to a safe holding state.
        try:
            pip.setState("bath")
        except Exception:
            pass


@register_action(name="Patch")
class PatchAction(FsmCompositeAction):
    """Drive cell detection through sealing/break-in to a resting terminal state."""

    entry_state = "cell detect"
    outcomes = ("whole cell", "cell attached", "bath", "broken", "fouled")


@register_action(name="Reseal")
class ResealAction(FsmCompositeAction):
    """Reseal from whole-cell toward an outside-out patch, else fall back to whole cell."""

    entry_state = "reseal"
    outcomes = ("outside out", "whole cell")
