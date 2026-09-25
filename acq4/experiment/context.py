"""ExecutionContext: the per-run bundle (cell, pipette, manager, log) handed to
every protocol run() and action function."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, Callable, NoReturn

from .exceptions import (
    AbortExperiment,
    AdvanceToNextCell,
    FlowSignal,
    RetryCurrentCell,
    TrackingLost,
)
from .log_entry import ActionLogEntry


def _noop_log(_message: str) -> None:
    return None


def _no_next_cell_requested() -> bool:
    return False


def _noop_checkpoint() -> None:
    return None


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
    # The pause seam: called at each boundary where the orchestrator may hold
    # the run before the next thing starts. Blocks while paused and returns
    # when resumed (or raises Stopped, since the orchestrator's pause event is
    # stop-aware). The Orchestrator binds this per cell; a headless context, or
    # one a contextFactory built without it, simply never pauses.
    #
    # It is a field on the context rather than a check written inline wherever
    # a boundary happens to be, because "may the run hold here" is a control
    # decision and needs somewhere honestly named to live. log_action() calls
    # it, but only because opening an action entry is where the boundaries are
    # today -- that is a trigger, not a home. See
    # docs/superpowers/specs/2026-09-04-autopatch-pause-granularity-friction.md
    # for why the two are kept apart, and for what would mean this is no longer
    # enough. A protocol author wanting an explicit hold point mid-action calls
    # this directly.
    checkpoint: Callable[[], None] = field(default=_noop_checkpoint)
    # Supplied by the Autopatch window's context factory: the capability to
    # react to a cell the tracker could not re-find. Called as hook(ctx, reason)
    # -- the context is passed at call time rather than bound into the hook,
    # because a stored closure over this object would make it reference itself,
    # and a cycle here is only reclaimable by the cyclic GC. The engine holds no
    # slice knowledge; this is how the window lends it some.
    tissue_moved_hook: Callable[[Any, str], None] | None = field(
        default=None, repr=False
    )
    # Set by next_cell/retry_cell/abort to the FlowSignal each is about to
    # raise, before raising it -- so the orchestrator can tell, on the
    # success path of a protocol run(), whether a flow signal was raised and
    # then swallowed by the protocol's own try/except rather than actually
    # propagating. A fresh context is built per attempt, so this never needs
    # resetting between retries.
    pending_flow_signal: FlowSignal | None = field(default=None, repr=False)

    def next_cell(self) -> None:
        """Abandon this cell and advance the orchestrator's queue."""
        self._raise_flow_signal(AdvanceToNextCell("advance to next cell"))

    def retry_cell(self) -> None:
        """Restart this cell's protocol from the top."""
        self._raise_flow_signal(RetryCurrentCell("retry current cell"))

    def abort(self) -> None:
        """Stop the whole experiment run."""
        self._raise_flow_signal(AbortExperiment("abort experiment"))

    def tissue_moved(self, reason: str) -> NoReturn:
        """Report that the tracker could not re-find this cell. Never returns.

        With a hook bound, the window prompts the operator and ends the cell,
        which leaves this call by way of a FlowSignal. With no hook -- headless,
        or a context built directly by a test -- a re-find failure is the plain
        TrackingLost error it is, and the orchestrator's catch-all halts the run.

        The fall-through raise is not dead code: a hook that returns instead of
        ending the cell would otherwise let the protocol carry on against a
        coordinate we have just established is stale.
        """
        if self.tissue_moved_hook is not None:
            self.tissue_moved_hook(self, reason)
        raise TrackingLost(reason)

    def _raise_flow_signal(self, exc: FlowSignal) -> None:
        """Record `exc` on pending_flow_signal, then raise it.

        The single place a FlowSignal is ever raised from: next_cell,
        retry_cell, abort, and actions.fsm's poll-loop checkpoint (via
        next_cell) all go through this rather than raising directly, so a
        future new raise site can't repeat the omission of recording the
        signal -- which is what lets the orchestrator's success-path
        swallow-net (Orchestrator._processCell) tell a genuinely-returned
        run() apart from one that raised a flow signal the protocol's own
        try/except then caught and suppressed.
        """
        self.pending_flow_signal = exc
        raise exc

    @contextlib.contextmanager
    def log_action(self, name: str, pausable: bool = True):
        """Track one action for the UI: yields an ActionLogEntry, notifies the UI
        hook if attached, and records the outcome on exit. Never suppresses.

        Also the run's pause boundary: `checkpoint()` is called on entry, so a
        pause requested mid-cell is honored here rather than waiting for the
        cell to end. `pausable=False` withholds that for a boundary the rig
        cannot safely hold at -- a pipette parked at the target in tissue, say
        -- and withholds only that: the entry is still opened and reported.

        The checkpoint runs before the entry is built, so a pause honored here
        leaves no Area 5 row for an action that has not started; a row
        announced and then parked would read as running while nothing is.
        """
        if pausable:
            self.checkpoint()
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
