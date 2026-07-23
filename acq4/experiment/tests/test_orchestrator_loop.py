"""Tests for the Orchestrator queue loop, pause/resume, stop, and next-cell."""
import gc
import weakref

import pytest

from acq4.util.task import Stopped, Event
from acq4.experiment.action import Action
from acq4.experiment.registry import register_action
from acq4.experiment.protocol import Protocol
from acq4.experiment.orchestrator import Orchestrator


def test_run_sync_processes_whole_queue(recording_cls):
    recording_cls.ran.clear()
    p = Protocol(nodes={"a": recording_cls(name="a")}, edges={}, entry="a")
    orch = Orchestrator(p)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    assert recording_cls.ran == ["a", "a"]  # ran once per cell


def test_requestnextcell_skips_current(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a")
    p = Protocol(nodes={"a": a}, edges={}, entry="a")
    orch = Orchestrator(p)
    finished = []
    orch.sigCellFinished.connect(lambda cell, status: finished.append((cell, status)))
    orch.enqueue("c1")
    orch.requestNextCell()  # before running: first boundary check skips c1
    orch.run_sync()
    assert recording_cls.ran == []            # action never ran
    assert finished == [("c1", "skipped")]


def test_pause_resume_toggle_status():
    p = Protocol()
    orch = Orchestrator(p)
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.pause()
    assert orch._pauseEvent.is_set() is False
    orch.resume()
    assert orch._pauseEvent.is_set() is True


@register_action(name="Blocking")
class _BlockingAction(Action):
    """Blocks on a shared Event until released, so the async loop can be stopped
    mid-action. `gate` is set by the test; `started` signals arrival."""

    outcomes = ("done",)
    gate: Event = None
    started: Event = None
    aborted: list = []

    def run(self, ctx):
        if _BlockingAction.started is not None:
            _BlockingAction.started.set()
        if _BlockingAction.gate is not None:
            _BlockingAction.gate.wait()  # stop-aware; raises Stopped on stop()
        return "done"

    def safeAbort(self, ctx):
        _BlockingAction.aborted.append(self.name)


def test_stop_aborts_running_action(qtbot):
    _BlockingAction.gate = Event()       # never set -> run() blocks
    _BlockingAction.started = Event()
    _BlockingAction.aborted = []
    p = Protocol(nodes={"a": _BlockingAction(name="a")}, edges={}, entry="a")
    orch = Orchestrator(p)
    orch.enqueue("c1")
    task = orch.start()
    _BlockingAction.started.wait()       # wait until the action is running
    orch.stop("test stop")
    with pytest.raises(Stopped):
        task.wait(timeout=5)
    assert _BlockingAction.aborted == ["a"]  # safeAbort ran on stop


def test_finished_task_does_not_leave_qobject_cycle(qtbot):
    """Regression test for the exit-segfault root cause: Orchestrator and its
    QtFriendlyTask are both QObjects, so a permanent orch<->task reference cycle
    can only be reclaimed by Python's cyclic GC -- non-deterministically, off
    Qt's safe teardown path. Once a run has finished, plain refcounting alone
    (cyclic GC disabled) must be enough to free both.
    """
    _BlockingAction.gate = Event()
    _BlockingAction.started = Event()
    _BlockingAction.aborted = []
    p = Protocol(nodes={"a": _BlockingAction(name="a")}, edges={}, entry="a")
    # A plain function, not a bound method of orch, so the orchestrator's own
    # self._contextFactory attribute does not itself create a self-cycle --
    # this test is targeted at the orch<->task cycle specifically.
    orch = Orchestrator(p, contextFactory=lambda cell: None)
    orch.enqueue("c1")
    task = orch.start()
    _BlockingAction.started.wait()  # action is parked in run(), definitely not finished

    # Connect to sigFinished BEFORE releasing the gate, so there is no race
    # between the task starting/finishing and us starting to listen.
    with qtbot.waitSignal(task.sigFinished, timeout=5000):
        _BlockingAction.gate.set()  # let the action, and the run loop, finish

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
