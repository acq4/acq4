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


class ScriptError(OrchestrationError):
    typeName = "ScriptError"


class FlowSignal(Exception):
    """Base for control-flow signals raised by flow actions."""


class AdvanceToNextCell(FlowSignal):
    """Abandon the current cell and move to the next queued cell."""


class RetryCurrentCell(FlowSignal):
    """Restart the protocol from the top for the current cell."""


class AbortExperiment(FlowSignal):
    """Stop the whole experiment."""


# Maps an abnormal FSM state name to an exception class. Consumed by the FSM
# watcher in the P0b plan; defined here so the taxonomy lives in one place.
ABNORMAL_STATE_EXCEPTIONS: dict[str, type[OrchestrationError]] = {
    "broken": BrokenPipette,
    "fouled": Fouled,
}
