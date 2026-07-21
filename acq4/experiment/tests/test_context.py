"""Tests for the ExecutionContext passed to Actions."""
from acq4.experiment.context import ExecutionContext


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
