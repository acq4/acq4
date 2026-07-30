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
