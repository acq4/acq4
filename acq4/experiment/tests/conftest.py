"""Shared fake Actions and fixtures for acq4.experiment tests."""
import pytest

from acq4.util.task import Stopped
from acq4.experiment.action import Action
from acq4.experiment.registry import register_action
from acq4.experiment import exceptions as exc


@register_action(name="Recording")
class RecordingAction(Action):
    """Records that it ran (by name) and returns the value of its `next` param."""

    outcomes = ("done", "left", "right")
    paramSpec = ({"name": "next", "type": "str", "default": "done"},)
    ran: list = []

    def run(self, ctx):
        RecordingAction.ran.append(self.name)
        return self.paramValue("next")


@register_action(name="Raising")
class RaisingAction(Action):
    """Raises the OrchestrationError subclass whose typeName matches `exc`."""

    outcomes = ()
    paramSpec = ({"name": "exc", "type": "str", "default": "Exception"},)

    def run(self, ctx):
        name = self.paramValue("exc")
        for cls in _orchestration_error_subclasses():
            if cls.typeName == name:
                raise cls(f"raised {name}")
        raise exc.OrchestrationError(f"raised {name}")


@register_action(name="Stop")
class StopAction(Action):
    """Simulates a cooperative stop mid-action and records the safeAbort call."""

    outcomes = ("done",)
    aborted: list = []

    def run(self, ctx):
        raise Stopped("stopped")

    def safeAbort(self, ctx):
        StopAction.aborted.append(self.name)


def _orchestration_error_subclasses():
    seen = [exc.OrchestrationError]
    stack = [exc.OrchestrationError]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub not in seen:
                seen.append(sub)
                stack.append(sub)
    return seen


@pytest.fixture
def recording_cls():
    return RecordingAction


@pytest.fixture
def raising_cls():
    return RaisingAction


@pytest.fixture
def stop_cls():
    return StopAction


class FakeStateJob:
    """Stand-in for a PatchPipetteState job: exposes .stateName."""

    def __init__(self, name):
        self.stateName = name


class FakePatchPipette:
    """Minimal fake of PatchPipette for FSM-action tests.

    ``state_sequence`` is the list of state names ``getState()`` reports on successive
    polls (simulating the FSM self-driving). ``setState`` records its calls and sets the
    current state to the requested entry state.
    """

    def __init__(self, state_sequence=()):
        self._seq = list(state_sequence)
        self._current = "out"
        self.setState_calls = []

    def setState(self, state, **config):
        self.setState_calls.append((state, config))
        self._current = state
        return FakeStateJob(state)

    def getState(self):
        if self._seq:
            self._current = self._seq.pop(0)
        return FakeStateJob(self._current)


@pytest.fixture
def fake_pip_factory():
    def make(state_sequence):
        return FakePatchPipette(state_sequence)

    return make
