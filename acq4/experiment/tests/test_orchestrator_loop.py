"""Tests for the Orchestrator queue loop, pause/resume, stop, and next-cell."""
import gc
import weakref

import pytest

from acq4.util.task import Stopped, Event, sleep
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AbortExperiment, RetryCurrentCell
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


def test_requestnextcell_cleared_when_cell_ends_normally_does_not_skip_following_cell(
    make_pf,
):
    """A "Next cell" request must apply to at most the cell it was made
    during. If that cell's protocol simply returns without raising a flow
    signal (e.g. a survey-only protocol with no next_cell(ctx) call), the
    flag must not survive into the next queue iteration -- otherwise the
    following queued cell is skipped without ever being attempted, with no
    error and no indication anything went wrong."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "cell1":
            orch.requestNextCell()
        # returns normally -- no flow signal raised

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    orch.enqueue("cell2")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync()
    assert ran == ["cell1", "cell2"]
    assert finished == [("cell1", "done"), ("cell2", "done")]


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


def test_requestnextcell_mid_poll_swallowed_by_protocol_halts_with_error(
    make_pf, fake_pip_factory
):
    """actions.fsm's poll-loop checkpoint raises AdvanceToNextCell the same
    way a flow action does -- so a protocol with a broad except around an
    FSM action must not be able to swallow a mid-poll abandon invisibly. The
    cell must be reported "error" and the run must halt with
    AbortExperiment, not report a false "done" while the pipette was
    actually abandoned mid-FSM."""
    from acq4.experiment.actions.fsm import patch as fsm_patch

    # No state_sequence: "approach" is not a Patch terminal, so without the
    # mid-poll request this would poll forever.
    pip = fake_pip_factory([])

    def run(ctx, **kwargs):
        # Simulates the operator's "Next cell" button firing before the poll
        # loop's next checkpoint (run_sync is single-threaded, so this simply
        # has to happen before fsm_patch's first check to reproduce it).
        orch.requestNextCell()
        try:
            fsm_patch(ctx)
        except Exception:
            pass  # a protocol author's broad except, swallowing the abandon
        return None

    pf = make_pf()
    pf.run = run

    def contextFactory(cell):
        return ExecutionContext(cell=cell, pipette=pip)

    orch = Orchestrator(pf, contextFactory=contextFactory)
    orch.enqueue("cell1")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    with pytest.raises(AbortExperiment):
        orch.run_sync()

    assert finished == [("cell1", "error")]
    # The FSM job was still safely aborted even though the protocol swallowed
    # the exception -- the orchestrator's detection is independent of that.
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

    # task.wait() is NOT a sufficient barrier here: _TaskCore._finish() (which
    # sets the done event sigFinished waits on) runs inside ThreadTask._run(),
    # which is itself the target of the worker's own threading.Thread --
    # still inside Thread.run()'s try/finally at that point. Thread.run()'s
    # own finally clears self._target/self._args/self._kwargs only AFTER
    # _run() returns, and until that unwind completes, the worker thread's
    # frame keeps task._run (a bound method of task) alive via Thread._args,
    # which keeps task itself alive -- exactly the kind of retainer that
    # makes the refcounting proof below flaky under gc.disable(). There is no
    # public join() on Task/ThreadTask, so join the underlying
    # threading.Thread directly: once it returns, Thread.run()'s finally has
    # already cleared that reference, so no race remains between "sigFinished
    # delivered" and "the worker thread has fully unwound".
    task._thread.join(timeout=5)
    assert not task._thread.is_alive()

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
