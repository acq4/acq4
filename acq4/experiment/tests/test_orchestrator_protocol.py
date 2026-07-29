"""Tests for the Orchestrator calling a ProtocolFile's run() directly."""
import pytest

from acq4.experiment.protocol_file import ProtocolFile
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.exceptions import (
    AbortExperiment,
    AdvanceToNextCell,
    RetryCurrentCell,
    OrchestrationError,
)
from acq4.util.task import Stopped


def _make_pf(tmp_path, params=None, name="protocol.py"):
    """A minimally valid ProtocolFile, loaded from a real file on disk so
    param_values()/param_tree behave like the genuine article. Tests that need
    run() to do something in particular overwrite pf.run afterward with a
    sentinel, per the plan's fixture recipe -- load() only needs a real
    callable to accept."""
    params = params or []
    path = tmp_path / name
    path.write_text(
        f"PARAMS = {params!r}\n\n\ndef run(ctx, **kwargs):\n    return None\n"
    )
    pf = ProtocolFile(str(path))
    pf.load()
    return pf


def test_run_called_with_ctx(tmp_path):
    pf = _make_pf(tmp_path)
    calls = []

    def spy_run(ctx, **kwargs):
        calls.append(ctx)

    pf.run = spy_run
    orch = Orchestrator(pf)
    orch.run_sync_cell("cell1")
    assert len(calls) == 1
    assert calls[0].cell == "cell1"


def test_param_values_passed_as_kwargs_and_reflect_tree_edits(tmp_path):
    pf = _make_pf(tmp_path, params=[{"name": "power", "type": "float", "default": 1.0}])
    received = {}

    def spy_run(ctx, **kwargs):
        received.update(kwargs)

    pf.run = spy_run
    pf.param_tree.child("power").setValue(2.5)  # an edit made after load()
    Orchestrator(pf).run_sync_cell("cell1")
    assert received == {"power": 2.5}


def test_advance_to_next_cell_is_skipped(tmp_path):
    pf = _make_pf(tmp_path)
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(AdvanceToNextCell("next"))
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("cell1")
    assert finished == [("cell1", "skipped")]


def test_retry_current_cell_retries_then_succeeds(tmp_path):
    pf = _make_pf(tmp_path)
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


def test_retry_exhaustion_reports_retry_exhausted(tmp_path):
    pf = _make_pf(tmp_path)
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


def test_abort_experiment_propagates(tmp_path):
    pf = _make_pf(tmp_path)

    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(AbortExperiment("operator abort"))
    with pytest.raises(AbortExperiment):
        Orchestrator(pf).run_sync_cell("cell1")


def test_orchestration_error_reports_error_and_raises_abort(tmp_path):
    pf = _make_pf(tmp_path)
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(OrchestrationError("broken"))
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync_cell("cell1")
    assert isinstance(excinfo.value.__cause__, OrchestrationError)
    assert finished == [("cell1", "error")]


def test_unexpected_exception_reports_error_and_raises_abort(tmp_path):
    pf = _make_pf(tmp_path)
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync_cell("cell1")
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert finished == [("cell1", "error")]


def test_stopped_propagates(tmp_path):
    pf = _make_pf(tmp_path)
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(Stopped("stopped"))
    with pytest.raises(Stopped):
        Orchestrator(pf).run_sync_cell("cell1")


def test_current_cell_signal_emits_cell_then_none_after_the_loop(tmp_path):
    pf = _make_pf(tmp_path)
    pf.run = lambda ctx, **kwargs: None
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    seen = []
    orch.sigCurrentCell.connect(seen.append)
    orch.run_sync()
    assert seen == ["cell1", None]


def test_requestnextcell_before_a_cell_skips_without_calling_run(tmp_path):
    pf = _make_pf(tmp_path)
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
