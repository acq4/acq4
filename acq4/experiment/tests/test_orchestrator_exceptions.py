"""Tests for the Orchestrator's handling of flow signals and the
uncaught-exception catch-all net (no exception-handler dispatch: that feature
is gone -- a protocol author who wants to recover writes try/except in run())."""
import pytest

from acq4.experiment.protocol_file import ProtocolFile
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.exceptions import AbortExperiment, BrokenPipette, RetryCurrentCell


def _make_pf(tmp_path, name="protocol.py"):
    """A minimally valid ProtocolFile, loaded from a real file on disk; tests
    overwrite pf.run afterward with whatever behavior they need to exercise."""
    path = tmp_path / name
    path.write_text("def run(ctx, **kwargs):\n    return None\n")
    pf = ProtocolFile(str(path))
    pf.load()
    return pf


def test_unhandled_orchestration_error_aborts(tmp_path):
    pf = _make_pf(tmp_path)
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(BrokenPipette("broken"))
    with pytest.raises(AbortExperiment):
        Orchestrator(pf).run_sync_cell("c1")


def test_status_returns_to_running_after_retry(tmp_path):
    pf = _make_pf(tmp_path)
    calls = {"n": 0}

    def flaky_run(ctx, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryCurrentCell("first attempt fails")

    pf.run = flaky_run
    statuses = []
    orch = Orchestrator(pf)
    orch.sigStatus.connect(statuses.append)
    orch.run_sync_cell("c1")
    # "running" is re-emitted for the retry attempt (status must not stay
    # stuck on anything from the failed first attempt)
    assert statuses == ["running", "running"]


def test_retry_cap_exhausts_and_finishes_cell(tmp_path):
    # A protocol that always retries an always-failing action must not loop
    # forever; after maxRetries it finishes the cell as "retry-exhausted".
    pf = _make_pf(tmp_path)
    calls = {"n": 0}

    def always_fails(ctx, **kwargs):
        calls["n"] += 1
        raise RetryCurrentCell("always fails")

    pf.run = always_fails
    finished = []
    orch = Orchestrator(pf, maxRetries=3)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert finished[-1] == ("c1", "retry-exhausted")
    assert calls["n"] == 4  # initial attempt + 3 retries, then give up


def test_unexpected_exception_is_surfaced_not_swallowed(tmp_path):
    """A plain (non-OrchestrationError) exception -- an ordinary bug -- must
    not vanish silently. It must be surfaced via sigStatus/sigCellFinished as
    an error and abort the run, rather than let the loop carry on as though
    nothing happened."""
    pf = _make_pf(tmp_path)
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(
        AttributeError("boom: an ordinary bug, not an OrchestrationError")
    )
    statuses = []
    finished = []
    orch = Orchestrator(pf)
    orch.sigStatus.connect(statuses.append)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")

    assert "error" in statuses
    assert finished == [("c1", "error")]
