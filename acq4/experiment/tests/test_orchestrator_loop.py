"""Tests for the Orchestrator queue loop, pause/resume, stop, and next-cell."""
import gc
import weakref

import pytest

from acq4.util.task import Stopped, Event
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
