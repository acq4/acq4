"""Tests for device-wrapping Actions (Cellfie, Task) using small fakes."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.device import CellfieAction, TaskAction
from acq4.experiment.exceptions import OrchestrationError
from acq4.experiment.registry import get_action_class


class _FakeCell:
    def __init__(self):
        self.tracker_calls = []

    def initializeTracker(self, imager, **kwargs):
        self.tracker_calls.append((imager, kwargs))


class _FakeCamera:
    pass


class _FakePipette:
    def __init__(self):
        self._imager = _FakeCamera()

    def imagingDevice(self):
        return self._imager


class _FakeManager:
    def __init__(self, result="RESULT"):
        self.result = result
        self.runTask_calls = []

    def runTask(self, cmd):
        self.runTask_calls.append(cmd)
        return self.result


def test_cellfie_initializes_tracker():
    pip = _FakePipette()
    cell = _FakeCell()
    ctx = ExecutionContext(cell=cell, pipette=pip)
    assert CellfieAction().run(ctx) == "captured"
    assert len(cell.tracker_calls) == 1
    imager, kwargs = cell.tracker_calls[0]
    assert imager is pip._imager
    assert kwargs.get("use_cellpose") is True


def test_task_runs_command_and_returns_done():
    mgr = _FakeManager(result={"trace": [1, 2, 3]})
    ctx = ExecutionContext(manager=mgr)
    a = TaskAction(params={"command": '{"protocol": "seal test"}'})
    assert a.run(ctx) == "done"
    assert mgr.runTask_calls == [{"protocol": "seal test"}]
    assert a.results["result"] == {"trace": [1, 2, 3]}


def test_task_invalid_json_raises_orchestration_error():
    mgr = _FakeManager()
    ctx = ExecutionContext(manager=mgr)
    a = TaskAction(params={"command": "{not valid json"})
    with pytest.raises(OrchestrationError):
        a.run(ctx)
    assert mgr.runTask_calls == []


def test_registered():
    assert get_action_class("Cellfie") is CellfieAction
    assert get_action_class("Task") is TaskAction
