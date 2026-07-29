"""ExecutionContext: the per-run bundle (cell, pipette, manager, log) handed to
every protocol run() and action function."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, Callable

from .exceptions import FlowSignal
from .log_entry import ActionLogEntry


def _noop_log(_message: str) -> None:
    return None


def _no_next_cell_requested() -> bool:
    return False


@dataclass
class ExecutionContext:
    cell: Any = None
    pipette: Any = None
    manager: Any = None
    log: Callable[[str], None] = field(default=_noop_log)
    on_log_action: Callable[[ActionLogEntry], None] | None = field(
        default=None, repr=False
    )
    # Polled by actions.fsm's poll loop next to check_stop(): True once the
    # orchestrator's operator-facing "Next cell" request should be honored at
    # the next cooperative checkpoint. The Orchestrator sets this to a closure
    # over its own request flag when building each cell's context; a headless
    # ExecutionContext (as built directly by tests, or a contextFactory that
    # doesn't set it) simply never requests one.
    next_cell_requested: Callable[[], bool] = field(default=_no_next_cell_requested)
    # Set by a flow action (next_cell/retry_cell/abort, in actions/flow.py)
    # to the FlowSignal it is about to raise, before raising it -- so the
    # orchestrator can tell, on the success path of a protocol run(), whether
    # a flow signal was raised and then swallowed by the protocol's own
    # try/except rather than actually propagating. A fresh context is built
    # per attempt, so this never needs resetting between retries.
    pending_flow_signal: FlowSignal | None = field(default=None, repr=False)

    def raise_flow_signal(self, exc: FlowSignal) -> None:
        """Record `exc` on pending_flow_signal, then raise it.

        The single place a FlowSignal is ever raised from: both the flow
        actions (actions/flow.py's next_cell/retry_cell/abort) and
        actions.fsm's poll-loop checkpoint go through this rather than
        raising directly, so a future third raise site can't repeat the
        omission of recording the signal -- which is what lets the
        orchestrator's success-path swallow-net (Orchestrator._processCell)
        tell a genuinely-returned run() apart from one that raised a flow
        signal the protocol's own try/except then caught and suppressed.
        """
        self.pending_flow_signal = exc
        raise exc

    @contextlib.contextmanager
    def log_action(self, name: str):
        """Track one action for the UI: yields an ActionLogEntry, notifies the UI
        hook if attached, and records the outcome on exit. Never suppresses."""
        action_entry = ActionLogEntry(name)
        if self.on_log_action is not None:
            self.on_log_action(action_entry)
        exc_seen = None
        try:
            yield action_entry
        except BaseException as exc:
            exc_seen = exc
            raise
        finally:
            action_entry._finish(exc_seen)
