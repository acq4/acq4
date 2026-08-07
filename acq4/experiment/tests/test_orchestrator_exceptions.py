"""Tests for the Orchestrator's handling of flow signals and the
uncaught-exception catch-all net (no exception-handler dispatch: that feature
is gone -- a protocol author who wants to recover writes try/except in run())."""
import pytest

from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AbortExperiment, AdvanceToNextCell, BrokenPipette, RetryCurrentCell


def test_unhandled_orchestration_error_aborts(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(BrokenPipette("broken"))
    with pytest.raises(AbortExperiment):
        Orchestrator(pf).run_sync_cell("c1")


def test_status_returns_to_running_after_retry(make_pf):
    pf = make_pf()
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


def test_retry_cap_exhausts_and_finishes_cell(make_pf):
    # A protocol that always retries an always-failing action must not loop
    # forever; after maxRetries it finishes the cell as "retry-exhausted".
    pf = make_pf()
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


def test_unexpected_exception_is_surfaced_not_swallowed(make_pf):
    """A plain (non-OrchestrationError) exception -- an ordinary bug -- must
    not vanish silently. It must be surfaced via sigStatus/sigCellFinished as
    an error and abort the run, rather than let the loop carry on as though
    nothing happened."""
    pf = make_pf()
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


def _record_signals(orch):
    """Collect sigRunError payloads and sigStatus values into one ordered list,
    so a test can assert not just what was emitted but in what order."""
    events = []
    orch.sigRunError.connect(lambda rec: events.append(("error-record", rec)))
    orch.sigStatus.connect(lambda status: events.append(("status", status)))
    return events


def test_unexpected_exception_reports_a_run_error_record(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    orch = Orchestrator(pf)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    records = [payload for kind, payload in events if kind == "error-record"]
    assert len(records) == 1
    assert records[0].exc_type == "RuntimeError"
    assert records[0].exc_message == "boom"
    assert "RuntimeError: boom" in records[0].traceback_text
    assert records[0].cell_repr == "'c1'"


def test_orchestration_error_reports_a_run_error_record(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(BrokenPipette("tip gone"))
    orch = Orchestrator(pf)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    records = [payload for kind, payload in events if kind == "error-record"]
    assert [r.exc_type for r in records] == ["BrokenPipette"]
    assert records[0].exc_message == "tip gone"


def test_run_error_is_reported_before_the_error_status(make_pf):
    # A slot reacting to "error" must already have the record to render.
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    orch = Orchestrator(pf)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    flattened = [
        payload if kind == "status" else "error-record" for kind, payload in events
    ]
    assert flattened == ["running", "error-record", "error"]


def test_swallowed_flow_signal_reports_the_signal_as_the_error(make_pf):
    # A protocol that catches its own ctx.next_cell() is a bug; the record must
    # name the signal, since that is what the halt is about.
    pf = make_pf()

    def swallowing_run(ctx, **kwargs):
        try:
            ctx.next_cell()
        except AdvanceToNextCell:
            pass

    pf.run = swallowing_run
    orch = Orchestrator(pf, contextFactory=lambda cell: ExecutionContext(cell=cell))
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    records = [payload for kind, payload in events if kind == "error-record"]
    assert [r.exc_type for r in records] == ["AdvanceToNextCell"]
    assert records[0].cell_repr == "'c1'"


def test_producer_failure_reports_a_run_error_record_with_no_cell(make_pf):
    # A producer raising during a refill is attributed to no cell -- the case
    # the run-level record exists for.
    pf = make_pf()
    orch = Orchestrator(pf)

    def exploding_producer():
        raise RuntimeError("camera is unplugged")

    orch.setCellProducer(exploding_producer)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync()
    records = [payload for kind, payload in events if kind == "error-record"]
    assert [r.exc_type for r in records] == ["RuntimeError"]
    assert records[0].exc_message == "camera is unplugged"
    assert records[0].cell_repr is None


def test_the_error_status_does_not_stick_after_a_halt(make_pf):
    # Measured, not assumed: _runLoopBody's finally emits "waiting"
    # unconditionally, and AbortExperiment is a FlowSignal so it propagates
    # straight through. This is why StatusPanel's error band keys off having a
    # last-error record rather than off sigStatus("error") -- gating visibility
    # on the status would show the band and hide it within the same run.
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    statuses = []
    orch.sigStatus.connect(statuses.append)
    with pytest.raises(AbortExperiment):
        orch.run_sync()
    assert statuses == ["running", "running", "error", "waiting"]
