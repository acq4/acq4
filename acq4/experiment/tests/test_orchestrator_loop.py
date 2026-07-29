"""Tests for the Orchestrator queue loop, pause/resume, stop, and next-cell."""
import gc
import weakref

import pytest

from acq4.util.task import Stopped, Event, sleep
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import RetryCurrentCell
from acq4.experiment.orchestrator import Orchestrator


def test_run_sync_processes_whole_queue(make_pf):
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    assert ran == ["c1", "c2"]  # ran once per cell, in queue order


def test_requestnextcell_skips_current(make_pf):
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    finished = []
    orch.sigCellFinished.connect(lambda cell, status: finished.append((cell, status)))
    orch.enqueue("c1")
    orch.requestNextCell()  # before running: the cell boundary check skips c1
    orch.run_sync()
    assert ran == []                          # run() never called
    assert finished == [("c1", "skipped")]


def test_pause_resume_toggle_status(make_pf):
    pf = make_pf()
    orch = Orchestrator(pf)
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.pause()
    assert orch._pauseEvent.is_set() is False
    orch.resume()
    assert orch._pauseEvent.is_set() is True


def test_stop_aborts_running_action(make_pf, qtbot):
    gate = Event()       # never set -> run() blocks
    started = Event()
    aborted = []

    pf = make_pf()

    def blocking_run(ctx, **kwargs):
        started.set()
        try:
            gate.wait()  # stop-aware; raises Stopped on stop()
        finally:
            aborted.append("a")

    pf.run = blocking_run
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    task = orch.start()
    started.wait()       # wait until the protocol function is running
    orch.stop("test stop")
    with pytest.raises(Stopped):
        task.wait(timeout=5)
    assert aborted == ["a"]  # the protocol's own try/finally ran on stop


def test_pause_is_honored_across_a_retry(make_pf, qtbot):
    """A protocol retrying against a persistent failure restarts from the top
    of _processCell's own retry loop, not through _runLoopBody -- so Pause
    (checked only in _runLoopBody until this fix) must also be checked at the
    top of that retry loop, or a persistently-retrying protocol ignores
    Pause completely."""
    pf = make_pf()
    calls = {"n": 0}

    def run(ctx, **kwargs):
        calls["n"] += 1
        sleep(0.005)  # paces retries out so pause/resume can be observed
        raise RetryCurrentCell("always fails")

    pf.run = run
    orch = Orchestrator(pf, maxRetries=100_000)
    orch.enqueue("cell1")

    orch.start()
    qtbot.waitUntil(lambda: calls["n"] >= 2, timeout=5000)

    orch.pause()
    qtbot.wait(20)  # let any in-flight attempt finish and hit the retry loop's top
    countAtPause = calls["n"]
    qtbot.wait(100)
    assert calls["n"] == countAtPause, "retries continued after pause()"

    orch.resume()
    qtbot.waitUntil(lambda: calls["n"] > countAtPause, timeout=5000)

    orch.stop("test cleanup")
    with pytest.raises(Stopped):
        orch.wait(timeout=5)


def test_requestnextcell_mid_poll_abandons_cell_and_advances_queue(
    make_pf, fake_pip_factory, qtbot
):
    """The operator flow: requesting the next cell while a protocol is parked
    inside actions.fsm's poll loop (where a cell spends nearly all its
    wall-clock) must abandon the current cell as "skipped" and let the queue
    advance to the next one -- not be silently dropped, as it was when the
    flag was only ever checked (and cleared) between whole cells."""
    from acq4.experiment.actions.fsm import patch as fsm_patch

    # No state_sequence: getState() reports whatever setState() last set
    # ("approach", not a Patch terminal) forever, so without the mid-poll
    # request this would never return on its own.
    pip = fake_pip_factory([])
    entered = Event()

    def run(ctx, **kwargs):
        if ctx.cell == "cell1":
            entered.set()
            fsm_patch(ctx)
        return None

    pf = make_pf()
    pf.run = run

    def contextFactory(cell):
        return ExecutionContext(cell=cell, pipette=pip)

    orch = Orchestrator(pf, contextFactory=contextFactory)
    orch.enqueue("cell1")
    orch.enqueue("cell2")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    orch.start()
    entered.wait(timeout=5)
    qtbot.wait(50)  # let a few poll iterations actually happen
    orch.requestNextCell()
    # sigCellFinished is emitted from the worker thread and queued to the GUI
    # thread; waitUntil both pumps the event loop and polls, so the queued
    # deliveries actually arrive rather than sitting unprocessed while the
    # main thread blocks in a plain (non-pumping) orch.wait().
    qtbot.waitUntil(lambda: len(finished) == 2, timeout=5000)

    assert finished == [("cell1", "skipped"), ("cell2", "done")]
    # The pipette's in-flight FSM job was told to stop, not left running
    # underneath the cell the orchestrator already moved on from.
    assert len(pip.stop_calls) == 1


def test_finished_task_does_not_leave_qobject_cycle(make_pf, qtbot):
    """Regression test for the exit-segfault root cause: Orchestrator and its
    QtFriendlyTask are both QObjects, so a permanent orch<->task reference cycle
    can only be reclaimed by Python's cyclic GC -- non-deterministically, off
    Qt's safe teardown path. Once a run has finished, plain refcounting alone
    (cyclic GC disabled) must be enough to free both.
    """
    gate = Event()
    started = Event()

    pf = make_pf()

    def blocking_run(ctx, **kwargs):
        started.set()
        gate.wait()

    pf.run = blocking_run
    # A plain function, not a bound method of orch, so the orchestrator's own
    # self._contextFactory attribute does not itself create a self-cycle --
    # this test is targeted at the orch<->task cycle specifically.
    orch = Orchestrator(pf, contextFactory=lambda cell: None)
    orch.enqueue("c1")
    task = orch.start()
    started.wait()  # protocol function is parked in run(), definitely not finished

    # Connect to sigFinished BEFORE releasing the gate, so there is no race
    # between the task starting/finishing and us starting to listen.
    with qtbot.waitSignal(task.sigFinished, timeout=5000):
        gate.set()  # let the protocol function, and the run loop, finish

    task_ref = weakref.ref(task)
    orch_ref = weakref.ref(orch)

    gc.disable()
    try:
        del task
        del orch
        assert orch_ref() is None, "Orchestrator survived refcounting alone -- a cycle remains"
        assert task_ref() is None, "Task survived refcounting alone -- a cycle remains"
    finally:
        gc.collect()
        gc.enable()
