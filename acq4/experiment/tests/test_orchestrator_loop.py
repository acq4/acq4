"""Tests for the Orchestrator queue loop, pause/resume, stop, and next-cell."""
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
    assert "paused" in statuses and "running" in statuses


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
