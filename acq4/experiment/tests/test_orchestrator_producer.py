"""Tests for the Orchestrator's cell-producer refill hook: the queue-depth
target, the empty-vs-exhausted distinction, and end-of-run conditions."""
import pytest

from acq4.experiment.orchestrator import Orchestrator
from acq4.util.task import Stopped, Event, sleep
from acq4.experiment.exceptions import AbortExperiment


def make_producer(batches):
    """A producer returning each of `batches` in turn, recording its calls.

    Each batch is either a list of cells or None (exhausted). Running past the
    end of `batches` is a broken test setup, not an implicit exhaustion, so it
    fails loudly rather than quietly ending the run.
    """
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        if not batches:
            raise AssertionError(
                "producer called after its last declared batch -- the loop "
                "asked again past exhaustion"
            )
        return batches.pop(0)

    producer.calls = calls
    return producer


def test_producer_fills_an_empty_queue_and_cells_are_processed(make_pf):
    """The whole point: a run started with nothing queued must still work
    cells, by asking the producer for them."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["c1", "c2"], None]))
    orch.run_sync()  # nothing enqueued up front
    assert ran == ["c1", "c2"]


def test_run_ends_when_queue_empty_and_producer_exhausted(make_pf):
    pf = make_pf()
    finished = []
    pf.run = lambda ctx, **kwargs: None
    orch = Orchestrator(pf, cellProducer=make_producer([["c1"], None]))
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync()  # must return, not spin
    assert finished == [("c1", "done")]


def test_empty_batch_asks_again_rather_than_ending_the_run(make_pf):
    """An imaged tile with no cells in it returns [] -- "found nothing, ask me
    again" -- which must NOT end the run the way None does. This is the
    distinction the whole survey loop rests on: a barren tile in the middle of
    a region cannot be allowed to stop the experiment."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    producer = make_producer([[], [], ["c1"], None])
    orch = Orchestrator(pf, cellProducer=producer)
    orch.run_sync()
    assert ran == ["c1"]
    assert producer.calls["n"] == 4  # two empty tiles, one productive, then exhausted


def test_queue_is_filled_to_target_depth_before_the_first_cell_runs(make_pf):
    """With a depth target above 1, the loop keeps asking until the queue
    reaches it -- so a producer yielding one cell per tile is asked three times
    before any cell is worked."""
    pf = make_pf()
    callsAtFirstRun = {}

    def run(ctx, **kwargs):
        callsAtFirstRun.setdefault("n", producer.calls["n"])

    pf.run = run
    producer = make_producer([["c1"], ["c2"], ["c3"], None])
    orch = Orchestrator(pf, cellProducer=producer, targetQueueDepth=3)
    orch.run_sync()
    assert callsAtFirstRun["n"] == 3


def test_depth_target_is_read_fresh_so_it_can_change_mid_run(make_pf):
    """The cell-finding config owns this number and an operator may change it
    while a run is in progress, so it must not be snapshotted at start."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        orch.targetQueueDepth = 1  # operator turns it down after the first cell

    pf.run = run
    producer = make_producer([["c1"], ["c2"], ["c3"], None])
    orch = Orchestrator(pf, cellProducer=producer, targetQueueDepth=2)
    orch.run_sync()
    assert ran == ["c1", "c2", "c3"]


def test_no_producer_drains_the_queue_and_ends(make_pf):
    """The unconfigured case -- every existing caller. Behaviour must be
    exactly the pre-producer queue drain, and in particular the loop must end
    rather than spin waiting for a refill that can never come."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    assert ran == ["c1", "c2"]


def test_producer_supplements_cells_seeded_before_start(make_pf):
    """Seeded cells and produced cells are the same queue: the operator's
    hand-added cells are worked first, then the producer's."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["produced"], None]))
    orch.enqueue("seeded")
    orch.run_sync()
    assert ran == ["seeded", "produced"]


def test_setCellProducer_installs_a_producer_after_construction(make_pf):
    """The UI builds the Orchestrator when a protocol is selected, but the
    producer depends on region/finding config chosen later, so it must be
    installable after the fact."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    orch.setCellProducer(make_producer([["c1"], None]))
    orch.run_sync()
    assert ran == ["c1"]


def test_setCellProducer_none_reverts_to_a_plain_queue_drain(make_pf):
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["never asked"], None]))
    orch.setCellProducer(None)
    orch.enqueue("c1")
    orch.run_sync()
    assert ran == ["c1"]


def test_target_queue_depth_below_one_is_rejected(make_pf):
    """A target of 0 would make `len(queue) < target` never true, silently
    disabling the producer -- a misconfiguration that looks like a hung
    survey. Fail at construction instead."""
    pf = make_pf()
    with pytest.raises(ValueError):
        Orchestrator(pf, targetQueueDepth=0)


def test_exhaustion_does_not_outlive_the_run(make_pf):
    """The scar-tissue test. A producer that exhausted during one run must not
    leave the orchestrator permanently convinced there is nothing to find: the
    operator draws a second survey region, presses Start, and the new
    producer has to actually be asked. This is the same class of leak as the
    "Next cell" flag surviving its run and silently skipping an unrelated
    cell."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["c1"], None]))
    orch.run_sync()
    assert ran == ["c1"]
    assert orch._producerExhausted is False  # cleared on the way out

    second = make_producer([["c2"], None])
    orch.setCellProducer(second)
    orch.run_sync()
    assert ran == ["c1", "c2"]  # the second region was actually surveyed
    assert second.calls["n"] == 2


def test_exhaustion_cleared_when_the_run_ends_by_raising(make_pf):
    """_runLoopBody can leave by raising as well as returning (an
    OrchestrationError from a cell re-raised as AbortExperiment). The clear
    belongs in the finally, not on the return path -- the same mistake that
    left the next-cell flag set on four separate raise paths."""
    pf = make_pf()

    def run(ctx, **kwargs):
        raise AttributeError("an ordinary bug, mid-cell")

    pf.run = run
    orch = Orchestrator(pf, cellProducer=make_producer([["c1"], None]))
    with pytest.raises(AbortExperiment):
        orch.run_sync()
    assert orch._producerExhausted is False


def test_exhaustion_cleared_after_a_cooperative_stop(make_pf):
    """Operator presses Stop after the region is exhausted but while cells
    remain queued, then presses Start again. The remaining cells must be
    worked, and the producer must be re-asked rather than assumed dry."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "c1":
            raise Stopped("operator pressed stop")

    pf.run = run
    producer = make_producer([["c1", "c2"], None])
    orch = Orchestrator(pf, cellProducer=producer)
    orch.run_sync()  # a cooperative stop ends the run normally
    assert ran == ["c1"]
    assert orch._producerExhausted is False
    assert list(orch._queue) == ["c2"]  # a stop is not a queue drain


def test_producer_exception_surfaces_as_error_and_aborts(make_pf):
    """A bug in the producer (a detection crash, a stage move that throws)
    must not quietly end the survey and let the run report itself complete."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None

    def exploding_producer():
        raise RuntimeError("detection crashed")

    statuses = []
    orch = Orchestrator(pf, cellProducer=exploding_producer)
    orch.sigStatus.connect(statuses.append)
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync()
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "error" in statuses


def test_producer_stopped_ends_the_run_normally(make_pf):
    """Stop pressed while the producer is imaging a tile: check_stop() inside
    the producer raises Stopped, which is a normal end to the run, not a
    raise the caller must catch."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None

    def stopping_producer():
        raise Stopped("operator pressed stop mid-survey")

    orch = Orchestrator(pf, cellProducer=stopping_producer)
    orch.run_sync()  # must not raise


def test_producer_abort_propagates_without_double_wrapping(make_pf):
    """A producer that raises AbortExperiment means it. It must propagate as
    itself rather than being caught by the broad clause and re-wrapped in a
    second AbortExperiment whose __cause__ is the first."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    sentinel = AbortExperiment("region is unusable")

    def aborting_producer():
        raise sentinel

    orch = Orchestrator(pf, cellProducer=aborting_producer)
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync()
    assert excinfo.value is sentinel


def test_pause_is_honored_before_refilling(make_pf, qtbot):
    """Pause means "start nothing new", and imaging a tile is very much
    something new -- an operator who pauses must not have the stage move to
    another tile underneath them."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    calls = {"n": 0}
    released = Event()

    def slow_producer():
        calls["n"] += 1
        sleep(0.005)  # paces tiles out so pause can land between them
        return [] if not released.is_set() else None

    orch = Orchestrator(pf, cellProducer=slow_producer)
    orch.pause()
    orch.start()
    qtbot.wait(100)
    assert calls["n"] == 0, "producer was asked for a tile while paused"

    orch.resume()
    qtbot.waitUntil(lambda: calls["n"] > 0, timeout=5000)

    released.set()
    orch.wait(timeout=5)


def test_stop_between_tiles_ends_a_barren_survey(make_pf, qtbot):
    """A producer returning [] forever is a wedged survey by construction.
    check_stop() between refills is what makes it interruptible, so the
    operator's Stop must end it."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    calls = {"n": 0}

    def barren_producer():
        calls["n"] += 1
        sleep(0.005)
        return []  # never exhausts

    orch = Orchestrator(pf, cellProducer=barren_producer)
    task = orch.start()
    qtbot.waitUntil(lambda: calls["n"] >= 2, timeout=5000)
    orch.stop("test stop")
    task.wait(timeout=5)  # a cooperative stop is a normal end, not a raise
    countAtStop = calls["n"]
    qtbot.wait(100)
    assert calls["n"] == countAtStop  # genuinely stopped asking
    assert orch._producerExhausted is False
