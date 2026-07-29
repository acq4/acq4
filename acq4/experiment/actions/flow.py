"""Flow-control actions: they carry no work, only signal the orchestrator to
advance, retry, or abort by raising the matching control-flow signal."""
from __future__ import annotations

from ..exceptions import AdvanceToNextCell, RetryCurrentCell, AbortExperiment


def next_cell(ctx) -> None:
    """Advance the orchestrator to the next cell."""
    raise AdvanceToNextCell("advance to next cell")


def retry_cell(ctx) -> None:
    """Retry the current cell from the start."""
    raise RetryCurrentCell("retry current cell")


def abort(ctx) -> None:
    """Abort the whole experiment run."""
    raise AbortExperiment("abort experiment")
