"""Tests for the Orchestrator calling a ProtocolFile's run() directly."""
import pytest

from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.exceptions import (
    AbortExperiment,
    AdvanceToNextCell,
    RetryCurrentCell,
    OrchestrationError,
)
from acq4.util.task import Stopped


def test_run_called_with_ctx(make_pf):
    pf = make_pf()
    calls = []

    def spy_run(ctx, **kwargs):
        calls.append(ctx)

    pf.run = spy_run
    orch = Orchestrator(pf)
    orch.run_sync_cell("cell1")
    assert len(calls) == 1
    assert calls[0].cell == "cell1"


def test_param_values_passed_as_kwargs_and_reflect_tree_edits(make_pf):
    pf = make_pf(params=[{"name": "power", "type": "float", "default": 1.0}])
    received = {}

    def spy_run(ctx, **kwargs):
        received.update(kwargs)

    pf.run = spy_run
    pf.param_tree.child("power").setValue(2.5)  # an edit made after load()
    Orchestrator(pf).run_sync_cell("cell1")
    assert received == {"power": 2.5}


def test_advance_to_next_cell_is_skipped(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(AdvanceToNextCell("next"))
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("cell1")
    assert finished == [("cell1", "skipped")]


def test_retry_current_cell_retries_then_succeeds(make_pf):
    pf = make_pf()
    calls = {"n": 0}

    def spy_run(ctx, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryCurrentCell("first attempt fails")

    pf.run = spy_run
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("cell1")
    assert calls["n"] == 2  # failed once, retried in place, succeeded
    assert finished == [("cell1", "retry"), ("cell1", "done")]


def test_retry_exhaustion_reports_retry_exhausted(make_pf):
    pf = make_pf()
    calls = {"n": 0}

    def spy_run(ctx, **kwargs):
        calls["n"] += 1
        raise RetryCurrentCell("always fails")

    pf.run = spy_run
    finished = []
    orch = Orchestrator(pf, maxRetries=3)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("cell1")
    assert calls["n"] == 4  # initial attempt + 3 retries, then give up
    assert finished[-1] == ("cell1", "retry-exhausted")


def test_abort_experiment_propagates(make_pf):
    pf = make_pf()

    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(AbortExperiment("operator abort"))
    with pytest.raises(AbortExperiment):
        Orchestrator(pf).run_sync_cell("cell1")


def test_orchestration_error_reports_error_and_raises_abort(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(OrchestrationError("broken"))
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync_cell("cell1")
    assert isinstance(excinfo.value.__cause__, OrchestrationError)
    assert finished == [("cell1", "error")]


def test_unexpected_exception_reports_error_and_raises_abort(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync_cell("cell1")
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert finished == [("cell1", "error")]


def test_stopped_propagates(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(Stopped("stopped"))
    with pytest.raises(Stopped):
        Orchestrator(pf).run_sync_cell("cell1")


def test_current_cell_signal_emits_cell_then_none_after_the_loop(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    seen = []
    orch.sigCurrentCell.connect(seen.append)
    orch.run_sync()
    assert seen == ["cell1", None]


def test_swallowed_flow_signal_halts_instead_of_reporting_done(make_pf):
    """Design §5's safety net: protocol authors write their own try/except by
    design, so `try: ... next_cell(ctx) ... except Exception: pass` is a
    likely mistake, not a theoretical one. A FlowSignal that doesn't
    propagate must be treated as a bug -- logged and halted -- rather than
    quietly reported "done" with a queue that didn't actually advance."""
    from acq4.experiment.actions.flow import next_cell

    pf = make_pf()

    def spy_run(ctx, **kwargs):
        try:
            next_cell(ctx)
        except Exception:
            pass  # the protocol author's own overly-broad try/except

    pf.run = spy_run
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("cell1")
    assert finished == [("cell1", "error")]


def test_unswallowed_flow_signal_still_reports_skipped(make_pf):
    """The safety net must not fire on the ordinary case: a FlowSignal that
    does propagate is handled exactly as before."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(AdvanceToNextCell("next"))
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("cell1")
    assert finished == [("cell1", "skipped")]


def test_requestnextcell_before_a_cell_skips_without_calling_run(make_pf):
    pf = make_pf()
    calls = {"n": 0}
    pf.run = lambda ctx, **kwargs: calls.__setitem__("n", calls["n"] + 1)
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.enqueue("cell1")
    orch.requestNextCell()  # before running: honored at the cell boundary
    orch.run_sync()
    assert calls["n"] == 0
    assert finished == [("cell1", "skipped")]
