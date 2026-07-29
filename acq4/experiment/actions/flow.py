"""Flow-control actions: they carry no work, only signal the orchestrator to
advance, retry, or abort by raising the matching control-flow signal."""
from __future__ import annotations

from ..exceptions import AdvanceToNextCell, RetryCurrentCell, AbortExperiment


def next_cell(ctx) -> None:
    """Advance the orchestrator to the next cell."""
    exc = AdvanceToNextCell("advance to next cell")
    ctx.pending_flow_signal = exc
    raise exc


def retry_cell(ctx) -> None:
    """Retry the current cell from the start."""
    exc = RetryCurrentCell("retry current cell")
    ctx.pending_flow_signal = exc
    raise exc


def abort(ctx) -> None:
    """Abort the whole experiment run."""
    exc = AbortExperiment("abort experiment")
    ctx.pending_flow_signal = exc
    raise exc
