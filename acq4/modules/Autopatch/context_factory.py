"""context_factory: builds the Orchestrator's per-cell ExecutionContext factory,
binding the operator-selected pipette (the engine's default factory does not)."""
from __future__ import annotations

from typing import Callable

from acq4.experiment.context import ExecutionContext


def make_context_factory(
    pipetteGetter: Callable[[], object],
    manager,
    log: Callable[[str], None] | None = None,
) -> Callable[[object], ExecutionContext]:
    def _factory(cell) -> ExecutionContext:
        kwargs = dict(cell=cell, pipette=pipetteGetter(), manager=manager)
        if log is not None:
            kwargs["log"] = log
        return ExecutionContext(**kwargs)

    return _factory
