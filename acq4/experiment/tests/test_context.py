"""Tests for the ExecutionContext passed to Actions."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import (
    AdvanceToNextCell,
    RetryCurrentCell,
    AbortExperiment,
)


def test_context_defaults():
    ctx = ExecutionContext()
    assert ctx.cell is None
    assert ctx.pipette is None
    assert ctx.manager is None
    # log is callable and a no-op by default
    assert ctx.log("hello") is None


def test_context_fields():
    seen = []
    ctx = ExecutionContext(cell="c", pipette="p", manager="m", log=seen.append)
    assert (ctx.cell, ctx.pipette, ctx.manager) == ("c", "p", "m")
    ctx.log("line")
    assert seen == ["line"]


# -- flow control -----------------------------------------------------------


def test_next_cell_raises_advance():
    with pytest.raises(AdvanceToNextCell):
        ExecutionContext().next_cell()


def test_retry_cell_raises_retry():
    with pytest.raises(RetryCurrentCell):
        ExecutionContext().retry_cell()


def test_abort_raises_abort():
    with pytest.raises(AbortExperiment):
        ExecutionContext().abort()


# -- recording the signal so the orchestrator can detect a swallow ----------


def test_next_cell_records_the_signal_on_ctx_before_raising():
    ctx = ExecutionContext()
    try:
        ctx.next_cell()
    except AdvanceToNextCell as exc:
        assert ctx.pending_flow_signal is exc


def test_retry_cell_records_the_signal_on_ctx_before_raising():
    ctx = ExecutionContext()
    try:
        ctx.retry_cell()
    except RetryCurrentCell as exc:
        assert ctx.pending_flow_signal is exc


def test_abort_records_the_signal_on_ctx_before_raising():
    ctx = ExecutionContext()
    try:
        ctx.abort()
    except AbortExperiment as exc:
        assert ctx.pending_flow_signal is exc


# -- tissue_moved hook -------------------------------------------------------


def test_tissue_moved_raises_trackinglost_when_no_hook_is_bound():
    # Headless and in tests there is no window to prompt, so a re-find failure
    # is the plain error it is and the catch-all halts the run. Safe default.
    from acq4.experiment.context import ExecutionContext
    from acq4.experiment.exceptions import TrackingLost

    ctx = ExecutionContext()
    with pytest.raises(TrackingLost, match="no features"):
        ctx.tissue_moved("no features")


def test_tissue_moved_passes_the_context_and_reason_to_the_hook():
    from acq4.experiment.context import ExecutionContext
    from acq4.experiment.exceptions import AdvanceToNextCell

    seen = []

    def hook(ctx, reason):
        seen.append((ctx, reason))
        ctx.next_cell()

    ctx = ExecutionContext(tissue_moved_hook=hook)
    with pytest.raises(AdvanceToNextCell):
        ctx.tissue_moved("tissue drifted")
    assert seen == [(ctx, "tissue drifted")]


def test_tissue_moved_never_returns_normally_even_if_the_hook_does():
    # The contract is that this call does not come back. A hook that forgets to
    # end the cell must not leave the protocol running against a stale
    # coordinate; falling through to the safe default is what stops that.
    from acq4.experiment.context import ExecutionContext
    from acq4.experiment.exceptions import TrackingLost

    ctx = ExecutionContext(tissue_moved_hook=lambda ctx, reason: None)
    with pytest.raises(TrackingLost):
        ctx.tissue_moved("hook returned")


def test_tissue_moved_hook_is_not_stored_as_a_bound_partial():
    # A hook closing over the context would make the context reference itself.
    # Assert the field holds exactly what was passed in.
    from acq4.experiment.context import ExecutionContext

    def hook(ctx, reason):
        ctx.next_cell()

    ctx = ExecutionContext(tissue_moved_hook=hook)
    assert ctx.tissue_moved_hook is hook
