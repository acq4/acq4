"""Sanity tests for the shared fake actions in conftest."""
import pytest

from acq4.util.task import Stopped
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import BrokenPipette


def test_recording_action_records_and_returns(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a")
    assert a.run(ExecutionContext()) == "done"
    assert recording_cls.ran == ["a"]


def test_recording_action_custom_next(recording_cls):
    a = recording_cls(name="b", params={"next": "left"})
    assert a.run(ExecutionContext()) == "left"


def test_raising_action_raises_mapped_exception(raising_cls):
    a = raising_cls(params={"exc": "BrokenPipette"})
    with pytest.raises(BrokenPipette):
        a.run(ExecutionContext())


def test_stop_action_raises_stopped(stop_cls):
    with pytest.raises(Stopped):
        stop_cls().run(ExecutionContext())
