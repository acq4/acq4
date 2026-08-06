"""Tests for the Orchestrator's cell-producer refill hook: the empty-queue
refill trigger, the empty-vs-exhausted distinction, and end-of-run conditions."""
import gc
import weakref
from collections import deque

import pytest

from acq4.experiment.orchestrator import Orchestrator
from acq4.util import Qt
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


def test_refill_discards_a_batch_from_a_producer_cleared_during_the_call(make_pf):
    """The "New slice" hazard: setCellProducer(None) landing between the
    producer being called and its batch being queued must not let that batch
    land anyway. A producer that clears itself and then returns cells
    reproduces the interleaving deterministically -- no thread race needed --
    since _refillQueue reads self._cellProducer into a local before calling
    it, and the clear this producer makes on its own way out is exactly the
    "landed while producer() was running" case that local exists to guard
    against on the way out too."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)

    def clears_then_returns_cells():
        orch.setCellProducer(None)
        return ["c1", "c2"]

    orch.setCellProducer(clears_then_returns_cells)
    statuses = []
    orch.sigStatus.connect(statuses.append)
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    orch.run_sync()  # must end normally, not error

    assert ran == [], "a cell from a batch discarded on the way out was still processed"
    assert list(orch._queue) == [], "the discarded batch was left sitting in the queue"
    assert finished == []
    assert "error" not in statuses


def test_refill_still_queues_a_batch_from_the_still_installed_producer(make_pf):
    """The ordinary path, pinned alongside the discard above: a producer that
    is still installed when it returns must still have its cells enqueued and
    processed -- the new check at the far end of _refillQueue must not turn
    into a blanket discard."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["c1", "c2"], None]))

    orch.run_sync()

    assert ran == ["c1", "c2"]


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
    left the next-cell flag set on four separate raise paths.

    Refill only ever runs against an empty queue, so the moment a producer
    reports exhaustion there is nothing left queued and the run loop ends
    right there -- there is no way to reach a still-queued, still-raising
    cell by driving the producer through the normal refill path. The
    exhausted flag is set directly instead, with a cell already queued from
    before that point, to pin the same invariant: the finally clears it on
    this raise path too, not only when the loop ends by returning."""
    pf = make_pf()

    def run(ctx, **kwargs):
        raise AttributeError("an ordinary bug, mid-cell")

    pf.run = run
    orch = Orchestrator(pf, cellProducer=make_producer([]))
    orch.enqueue("c1")
    orch._producerExhausted = True
    with pytest.raises(AbortExperiment):
        orch.run_sync()
    assert orch._producerExhausted is False


def test_exhaustion_cleared_after_a_cooperative_stop(make_pf):
    """Operator presses Stop after the region is exhausted but while cells
    remain queued, then presses Start again. The remaining cells must be
    worked, and the producer must be re-asked rather than assumed dry.

    Refill only ever runs against an empty queue, so reaching exhaustion
    with cells still queued behind it can't be driven through the normal
    refill path (the moment the producer reports exhaustion, the queue is
    already empty). The exhausted flag is set directly instead, with two
    cells already queued, so the first cell's Stopped ends the run while a
    cell (c2) and the exhausted flag are both still there to check."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "c1":
            raise Stopped("operator pressed stop")

    pf.run = run
    orch = Orchestrator(pf, cellProducer=make_producer([]))
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch._producerExhausted = True
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


def test_nextcell_request_during_refill_of_an_empty_queue_is_discarded(make_pf):
    """A "Next cell" request that arrives while the producer is imaging a tile
    -- itself a slow, seconds-to-minutes operation -- lands on an empty queue:
    nothing was running and nothing was queued for it to advance past. Consuming
    it against the first cell the producer then returns would skip a cell the
    operator never saw, without it ever being attempted, so it must be
    discarded instead."""
    pf = make_pf()
    ran = []
    finished = []
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        if calls["n"] == 1:
            orch.requestNextCell()  # arrives mid-produce, before any cell exists
            return ["c1", "c2"]
        return None

    def run(ctx, **kwargs):
        ran.append(ctx.cell)

    pf.run = run
    orch = Orchestrator(pf, cellProducer=producer)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync()
    assert ran == ["c1", "c2"]
    assert finished == [("c1", "done"), ("c2", "done")]


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
    task = orch.start()
    qtbot.wait(100)
    assert calls["n"] == 0, "producer was asked for a tile while paused"

    orch.resume()
    qtbot.waitUntil(lambda: calls["n"] > 0, timeout=5000)

    released.set()
    task.wait(timeout=5)
    # This wait(updates=False) does raise Timeout on expiry, so it is itself a
    # barrier -- it is wait(updates=True) that returns None instead (the KNOWN
    # DIVERGENCE in acq4/util/task.py). The assertion pins the loop's own
    # completion regardless of which wait a later edit reaches for, so a run
    # that failed to terminate cannot leak a spinning worker thread into every
    # test that follows.
    assert task.is_done, "run loop did not finish before the wait returned"


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


def test_producer_bound_method_cycle_is_freed_once_the_producer_is_released(
    make_pf, qtbot
):
    """A realistic producer is a bound method of a UI panel that also holds
    the orchestrator: orchestrator -> panel (via the bound method's __self__)
    -> panel._orchestrator -> orchestrator, a QObject reference cycle much
    like the orch<->task cycle test_finished_task_does_not_leave_qobject_cycle
    (test_orchestrator_loop.py) guards against. The existing teardown
    machinery breaks it, but nothing on this branch exercises it with a real
    producer reference in place. This proves that once the producer is
    released, plain refcounting -- cyclic GC disabled -- is enough to free
    both the panel and the orchestrator.
    """
    gate = Event()
    started = Event()

    class FakePanel(Qt.QObject):
        def __init__(self, orchestrator):
            super().__init__()
            self._orchestrator = orchestrator

        def produceCells(self):
            started.set()
            gate.wait()
            return None  # exhausted; nothing more to survey

    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    # A plain lambda, not a bound method of orch, so the orchestrator's own
    # self._contextFactory attribute does not itself create a self-cycle --
    # this test is targeted at the orch<->panel cycle through the producer
    # specifically, same isolation as the orch<->task cycle test.
    orch = Orchestrator(pf, contextFactory=lambda cell: None)
    panel = FakePanel(orch)
    orch.setCellProducer(panel.produceCells)
    orch.enqueue("c1")

    task = orch.start()
    started.wait()  # producer is parked mid-call, definitely not finished

    # Connect to sigFinished BEFORE releasing the gate, so there is no race
    # between the task starting/finishing and us starting to listen.
    with qtbot.waitSignal(task.sigFinished, timeout=5000):
        gate.set()  # let the producer, and the run loop, finish

    # See test_finished_task_does_not_leave_qobject_cycle for why joining the
    # worker thread directly -- not task.wait() -- is the correct barrier here.
    task._thread.join(timeout=5)
    assert not task._thread.is_alive()

    # Release the producer the way real teardown must (P2b/P2c's job, not this
    # branch's -- see the record-only finding on setCellProducer(None)). This
    # is what breaks orch -> panel -> panel._orchestrator -> orch.
    orch.setCellProducer(None)
    panel._orchestrator = None

    panel_ref = weakref.ref(panel)
    orch_ref = weakref.ref(orch)

    gc.disable()
    try:
        del panel
        del orch
        del task
        assert orch_ref() is None, "Orchestrator survived refcounting alone -- a cycle remains"
        assert panel_ref() is None, "Panel survived refcounting alone -- a cycle remains"
    finally:
        gc.collect()
        gc.enable()


def test_surveying_status_is_emitted_around_a_refill(make_pf):
    orch = Orchestrator(make_pf())
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.setCellProducer(make_producer([[object()], None]))

    orch.run_sync()

    assert "surveying" in statuses
    # And it must not be the last word: the run reports back to running for the
    # cell it then works, and waiting once drained.
    assert statuses.index("surveying") < statuses.index("waiting")


def test_current_cell_is_cleared_before_surveying_is_reported(make_pf):
    """sigCurrentCell(None) and sigStatus("surveying") are same-thread direct
    connections, so a UI slot genuinely runs between them -- if the status
    were reported first, that slot would briefly render the just-finished
    cell as "surveying". Recording both signals into one shared, ordered list
    pins that the cell is cleared first."""
    orch = Orchestrator(make_pf())
    events = []
    orch.sigCurrentCell.connect(lambda cell: events.append(("cell", cell)))
    orch.sigStatus.connect(lambda status: events.append(("status", status)))
    orch.setCellProducer(make_producer([[object()], None]))

    orch.run_sync()

    cell_cleared_index = events.index(("cell", None))
    surveying_index = events.index(("status", "surveying"))
    assert cell_cleared_index < surveying_index


def test_every_barren_refill_pass_reports_surveying(make_pf):
    # The operator watching a slow, empty stretch of region must see
    # "surveying", not a stale "running" that implies a cell is being patched.
    orch = Orchestrator(make_pf())
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.setCellProducer(make_producer([[], [], None]))

    orch.run_sync()

    assert statuses.count("surveying") == 3


def test_clear_producer_exhausted_lets_an_exhausted_producer_be_asked_again():
    # A producer that reported exhaustion is never asked again for the rest of
    # the run. After a forced rescan there are uncovered tiles once more, so the
    # flag has to be cleared or the loop ends on a queue the producer could
    # have refilled.
    orch = Orchestrator(make_pf())
    orch.setCellProducer(lambda: None)
    orch._producerExhausted = True

    orch.clearProducerExhausted()

    assert orch._producerExhausted is False
    assert orch._shouldRefill() is True


def test_set_cell_producer_still_clears_exhaustion():
    # The extraction must not move behaviour off setCellProducer, which existing
    # callers rely on.
    orch = Orchestrator(make_pf())
    orch._producerExhausted = True
    orch.setCellProducer(lambda: [])
    assert orch._producerExhausted is False


def test_current_cell_is_cleared_before_the_producer_runs(make_pf):
    # sigCurrentCell must not still name the just-finished cell while the
    # producer images: Area 5 would attribute survey time to that cell, and a
    # "Next cell" request arriving during the survey would appear to have a
    # current cell to act against, when none is actually being worked.
    pf = make_pf()
    first = object()
    orch = Orchestrator(pf)
    orch.enqueue(first)

    seen = []
    orch.sigCurrentCell.connect(seen.append)
    statuses = []
    orch.sigStatus.connect(statuses.append)

    def producer():
        # Whatever the orchestrator last announced must not be `first`.
        assert seen[-1] is None, f"still following {seen[-1]!r} while surveying"
        # The status the operator sees at this same moment must already be
        # "surveying", not "running" left over from before the refill.
        assert (
            statuses[-1] == "surveying"
        ), f"status was {statuses[-1]!r} while surveying"
        return None

    orch.setCellProducer(producer)
    orch.run_sync()

    assert first in seen


def test_clear_queue_drops_pending_cells(make_pf):
    orch = Orchestrator(make_pf())
    ran = []
    orch.protocolFile.run = lambda ctx, **kw: ran.append(ctx.cell)
    orch.enqueue(object())
    orch.enqueue(object())

    orch.clearQueue()
    orch.run_sync()

    assert ran == []


def test_clear_queue_leaves_a_later_enqueue_working(make_pf):
    orch = Orchestrator(make_pf())
    ran = []
    orch.protocolFile.run = lambda ctx, **kw: ran.append(ctx.cell)
    orch.enqueue(object())
    orch.clearQueue()
    kept = object()
    orch.enqueue(kept)

    orch.run_sync()

    assert ran == [kept]


def test_clear_queue_leaves_a_running_cell_alone(make_pf):
    """clearQueue()'s docstring promises it leaves a running cell alone: a
    cell already in the middle of its protocol must still complete even
    though the queue behind it is dropped out from under it."""
    orch = Orchestrator(make_pf())
    ran = []

    def run(ctx, **kwargs):
        orch.clearQueue()
        assert orch._nextCellRequested is False
        ran.append(ctx.cell)

    orch.protocolFile.run = run
    queued = object()
    orch.enqueue(queued)
    running = object()

    orch.run_sync_cell(running)

    assert ran == [running]
    assert list(orch._queue) == []


def test_clear_queue_race_between_check_and_pop_ends_the_run_cleanly(make_pf):
    """clearQueue() runs on the GUI thread while _runLoopBody runs on the
    worker thread. If clearQueue() lands between _runLoopBody deciding the
    queue is non-empty and it actually popping a cell, that pop must not
    raise -- an operator clearing the queue mid-run gets a cleanly finished
    run, not a crashed one.

    Deterministic rather than timing-dependent: RaceyQueue's __bool__ is the
    same truthiness check the loop body makes on this deque wherever it asks
    "is there anything left", and it wipes the deque's own contents the first
    time it is consulted while non-empty -- exactly as a concurrent
    clearQueue() would. It then keeps reporting that emptied state as truthy
    for the rest of the pass, because that is what any later consult in the
    same iteration actually observes once a clear has landed: a deque that
    reads as empty when measured by length, but whose iteration is still
    mid-flight on the assumption a cell is there to take.
    """

    class RaceyQueue(deque):
        def __init__(self, *args):
            super().__init__(*args)
            self._raced = False

        def __bool__(self):
            if len(self) > 0:
                self._raced = True
                self.clear()
            return self._raced or len(self) > 0

    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None

    def poison_producer():
        raise AssertionError(
            "producer asked after the race already emptied the queue -- the "
            "run should have ended instead of trying to refill"
        )

    orch = Orchestrator(pf, cellProducer=poison_producer)
    orch._queue = RaceyQueue([object()])

    completed_without_raising = False
    orch.run_sync()
    completed_without_raising = True

    assert completed_without_raising, "run_sync() must end the run cleanly, not raise"
    assert list(orch._queue) == []


def test_producer_cleared_between_shouldrefill_and_refill_ends_the_run_cleanly(make_pf):
    """setCellProducer(None) runs on the GUI thread (a "New slice" mid-run,
    say) while this loop runs on the worker thread, so "there is a producer"
    (_shouldRefill's check) and "call the producer" (_refillQueue, a separate
    step later) cannot be treated as one atomic check-then-act. A clear
    landing in between must not turn a legitimate operator action into a
    TypeError out of calling None -- the run should simply find nothing left
    to do and end normally, the same as if no producer had ever been asked.

    Deterministic rather than timing-dependent: sigStatus always emits
    "surveying" between _shouldRefill()'s check and _refillQueue()'s call (see
    _runLoopBody), so a slot connected to that signal clears the producer at
    exactly that point on this same thread -- standing in for the concurrent
    clear the same way RaceyQueue stands in for a concurrent clearQueue()
    above."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    producer = make_producer([["c1"], None])
    orch = Orchestrator(pf, cellProducer=producer)
    statuses = []
    orch.sigStatus.connect(statuses.append)

    def clear_producer_when_surveying_starts(status):
        if status == "surveying":
            orch.setCellProducer(None)

    orch.sigStatus.connect(clear_producer_when_surveying_starts)

    orch.run_sync()  # must not raise

    assert "error" not in statuses
    assert (
        producer.calls["n"] == 0
    ), "producer was called after it had already been cleared"


def test_no_producer_never_reports_surveying(make_pf):
    """A plain queue drain (no producer configured) must never emit
    "surveying" -- an operator would misread it as the system looking for
    more cells when it is not."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    statuses = []
    orch = Orchestrator(pf)
    orch.sigStatus.connect(statuses.append)
    orch.enqueue("c1")
    orch.enqueue("c2")

    orch.run_sync()

    assert "surveying" not in statuses
    orch.enqueue("c1")
    orch.enqueue("c2")

    orch.run_sync()

    assert "surveying" not in statuses


def test_clear_producer_exhausted_lets_an_exhausted_producer_be_asked_again(make_pf):
    # A producer that reported exhaustion is never asked again for the rest of
    # the run. After a forced rescan there are uncovered tiles once more, so the
    # flag has to be cleared or the loop ends on a queue the producer could
    # have refilled.
    orch = Orchestrator(make_pf())
    orch.setCellProducer(lambda: None)
    orch._producerExhausted = True

    orch.clearProducerExhausted()

    assert orch._producerExhausted is False
    assert orch._shouldRefill() is True


def test_set_cell_producer_still_clears_exhaustion(make_pf):
    # The extraction must not move behaviour off setCellProducer, which existing
    # callers rely on.
    orch = Orchestrator(make_pf())
    orch._producerExhausted = True
    orch.setCellProducer(lambda: [])
    assert orch._producerExhausted is False
