"""Tests for device-wrapping Actions (FindTip, Cellfie, Task).

Task is fully headless. FindTip and Cellfie drive real pipette/imaging hardware
(moves, tip-finding, z-stack capture), so only their registration and declared
outcomes/params are checked here; their behavior is verified by live testing.
"""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.device import FindTipAction, CellfieAction, TaskAction
from acq4.experiment.exceptions import OrchestrationError
from acq4.experiment.registry import get_action_class


class _FakeManager:
    def __init__(self, result="RESULT"):
        self.result = result
        self.runTask_calls = []

    def runTask(self, cmd):
        self.runTask_calls.append(cmd)
        return self.result


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


def test_findtip_declares_found_outcome():
    assert FindTipAction.outcomes == ("found",)


def test_cellfie_declares_captured_outcome():
    assert CellfieAction.outcomes == ("captured",)


def test_registered():
    assert get_action_class("FindTip") is FindTipAction
    assert get_action_class("Cellfie") is CellfieAction
    assert get_action_class("Task") is TaskAction
