"""context_factory: builds the Orchestrator's per-cell ExecutionContext factory,
binding the operator-selected pipette (the engine's default factory does not)
and tagging each cell's log callback so the UI can scope log lines per cell."""
from __future__ import annotations

from functools import partial
from typing import Callable

from acq4.experiment.context import ExecutionContext


def make_context_factory(
    pipetteGetter: Callable[[], object],
    manager,
    log: Callable[[object, str], None] | None = None,
    onLogAction: Callable[[object, object], None] | None = None,
    tissueMoved: Callable[[object, object, str], None] | None = None,
) -> Callable[[object], ExecutionContext]:
    def _factory(cell) -> ExecutionContext:
        kwargs = dict(cell=cell, pipette=pipetteGetter(), manager=manager)
        if log is not None:
            # ExecutionContext.log is a single-arg (message) callable; bind this
            # cell so the UI-side sink (log) knows which cell a line belongs to.
            kwargs["log"] = partial(log, cell)
        if onLogAction is not None:
            # ExecutionContext.on_log_action is a single-arg (entry) callable;
            # bind this cell the same way, so the UI-side sink (onLogAction)
            # knows which cell an ActionLogEntry belongs to.
            kwargs["on_log_action"] = partial(onLogAction, cell)
        if tissueMoved is not None:
            # Only the cell is bound in. ExecutionContext.tissue_moved passes
            # itself at call time, so the context is never captured in a closure
            # it also owns -- that would be a self-reference the cyclic GC alone
            # could break.
            kwargs["tissue_moved_hook"] = partial(tissueMoved, cell)
        return ExecutionContext(**kwargs)

    return _factory
