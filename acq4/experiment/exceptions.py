"""Exception taxonomy for exceptional states routed to handlers, plus control-flow
signals raised by flow actions and consumed by the orchestrator loop."""
from __future__ import annotations


class OrchestrationError(Exception):
    """Base for exceptional states routed to exception handlers.

    `typeName` is the key used to look up a handler; unmatched types fall back to
    the catch-all 'Exception' handler.
    """

    typeName = "Exception"


class BrokenPipette(OrchestrationError):
    typeName = "BrokenPipette"


class Fouled(OrchestrationError):
    typeName = "Fouled"


class Uncleanable(OrchestrationError):
    typeName = "Uncleanable"


class NoSolution(OrchestrationError):
    typeName = "NoSolution"


class FlowSignal(Exception):
    """Base for control-flow signals raised by flow actions."""


class AdvanceToNextCell(FlowSignal):
    """Abandon the current cell and move to the next queued cell."""


class RetryCurrentCell(FlowSignal):
    """Restart the protocol from the top for the current cell."""


class AbortExperiment(FlowSignal):
    """Stop the whole experiment."""


ABNORMAL_STATE_EXCEPTIONS: dict[str, type[OrchestrationError]] = {
    "broken": BrokenPipette,
    "fouled": Fouled,
}


def raise_if_abnormal(state: str, expected, context: str = "") -> None:
    """Raise the ``ABNORMAL_STATE_EXCEPTIONS``-mapped exception for ``state``,
    unless ``state`` is one of the caller's declared terminal states in
    ``expected``. States that are neither expected nor mapped are internal FSM
    hops and pass through without raising."""
    if state in expected:
        return
    exc_cls = ABNORMAL_STATE_EXCEPTIONS.get(state)
    if exc_cls is not None:
        raise exc_cls(f"{context}: pipette state is {state!r}" if context else f"pipette state is {state!r}")
