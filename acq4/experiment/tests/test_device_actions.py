"""Tests for device-wrapping Actions (GoTo, Cellfie, Task) using small fakes."""
import numpy as np

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.device import GoToAction, CellfieAction, TaskAction
from acq4.experiment.registry import get_action_class


class _FakeFuture:
    def wait(self, *a, **k):
        return None


class _FakePosition:
    def __init__(self, coords):
        self.coordinates = np.asarray(coords, dtype=float)


class _FakeCell:
    def __init__(self, coords=(1e-3, 2e-3, 3e-3)):
        self.position = _FakePosition(coords)
        self.tracker_calls = []

    def initializeTracker(self, imager, **kwargs):
        self.tracker_calls.append((imager, kwargs))


class _FakeCamera:
    pass


class _FakeMovePipette:
    def __init__(self):
        self.target = None
        self.moveTo_calls = []
        self._imager = _FakeCamera()

    def setTarget(self, target):
        self.target = target

    def moveTo(self, position, speed, **kwds):
        self.moveTo_calls.append((position, speed))
        return _FakeFuture()

    def imagingDevice(self):
        return self._imager


class _FakeManager:
    def __init__(self, result="RESULT"):
        self.result = result
        self.runTask_calls = []

    def runTask(self, cmd):
        self.runTask_calls.append(cmd)
        return self.result


def test_goto_moves_to_cell_target():
    pip = _FakeMovePipette()
    cell = _FakeCell((5e-3, 6e-3, 7e-3))
    ctx = ExecutionContext(cell=cell, pipette=pip)
    assert GoToAction().run(ctx) == "arrived"
    assert np.allclose(pip.target, [5e-3, 6e-3, 7e-3])
    assert pip.moveTo_calls == [("target", "fast")]


def test_cellfie_initializes_tracker():
    pip = _FakeMovePipette()
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


def test_registered():
    assert get_action_class("GoTo") is GoToAction
    assert get_action_class("Cellfie") is CellfieAction
    assert get_action_class("Task") is TaskAction
