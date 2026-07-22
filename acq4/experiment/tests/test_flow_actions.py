"""Tests for flow actions (GoToNext/RetryCell/Abort) and the Prompt action."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.flow import (
    GoToNextAction,
    RetryCellAction,
    AbortAction,
)
from acq4.experiment.actions.prompt import PromptAction
from acq4.experiment.exceptions import (
    AdvanceToNextCell,
    RetryCurrentCell,
    AbortExperiment,
)
from acq4.experiment.registry import get_action_class


def test_gotonext_raises_advance():
    with pytest.raises(AdvanceToNextCell):
        GoToNextAction().run(ExecutionContext())


def test_retrycell_raises_retry():
    with pytest.raises(RetryCurrentCell):
        RetryCellAction().run(ExecutionContext())


def test_abort_raises_abort():
    with pytest.raises(AbortExperiment):
        AbortAction().run(ExecutionContext())


def test_flow_actions_registered():
    assert get_action_class("GoToNext") is GoToNextAction
    assert get_action_class("RetryCell") is RetryCellAction
    assert get_action_class("Abort") is AbortAction


def test_prompt_logs_and_acknowledges():
    logged = []
    ctx = ExecutionContext(log=logged.append)
    a = PromptAction(params={"message": "Swap the pipette, then continue."})
    assert a.run(ctx) == "acknowledged"
    assert logged == ["Swap the pipette, then continue."]
