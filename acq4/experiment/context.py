"""ExecutionContext: the per-run bundle (cell, pipette, manager, log) handed to
every protocol run() and action function."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, Callable

from .log_entry import ActionLogEntry


def _noop_log(_message: str) -> None:
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

    @contextlib.contextmanager
    def log_action(self, name: str):
        """Track one action for the UI: yields an ActionLogEntry, notifies the UI
        hook if attached, and records the outcome on exit. Never suppresses."""
        entry = ActionLogEntry(name)
        if self.on_log_action is not None:
            self.on_log_action(entry)
        exc_seen = None
        try:
            yield entry
        except BaseException as exc:
            exc_seen = exc
            raise
        finally:
            entry._finish(exc_seen)
