"""Tests for the Orchestrator's cell-producer refill hook: the queue-depth
target, the empty-vs-exhausted distinction, and end-of-run conditions."""
import pytest

from acq4.experiment.orchestrator import Orchestrator


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
