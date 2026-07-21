"""ExecutionContext: the per-run bundle (cell, pipette, manager, log) handed to
every Action's run() and safeAbort()."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


def _noop_log(_message: str) -> None:
    return None


@dataclass
class ExecutionContext:
    cell: Any = None
    pipette: Any = None
    manager: Any = None
    log: Callable[[str], None] = field(default=_noop_log)
