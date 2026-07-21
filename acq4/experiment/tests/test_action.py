"""Tests for the Action base class."""
import pytest

from acq4.experiment.action import Action
from acq4.experiment.context import ExecutionContext


class _Demo(Action):
    outcomes = ("done",)
    paramSpec = (
        {"name": "pressure", "type": "float", "default": 5000.0, "suffix": "Pa"},
    )

    def run(self, ctx):
        self.setState("running demo")
        self.results["p"] = self.paramValue("pressure")
        return "done"


def test_default_name_is_class_name():
    assert _Demo().name == "_Demo"


def test_explicit_name():
    assert _Demo(name="node1").name == "node1"


def test_param_default_and_override():
    assert _Demo().paramValue("pressure") == 5000.0
    assert _Demo(params={"pressure": 1234.0}).paramValue("pressure") == 1234.0


def test_unknown_param_raises():
    with pytest.raises(KeyError):
        _Demo(params={"nope": 1})


def test_run_returns_outcome_and_sets_results():
    a = _Demo()
    assert a.run(ExecutionContext()) == "done"
    assert a.results["p"] == 5000.0


def test_setstate_emits_signal(qtbot):
    a = _Demo()
    with qtbot.waitSignal(a.sigStateChanged, timeout=1000) as blocker:
        a.setState("hi")
    assert blocker.args == [a, "hi"]


def test_base_run_not_implemented():
    with pytest.raises(NotImplementedError):
        Action().run(ExecutionContext())


def test_safeabort_and_show_defaults():
    a = _Demo()
    assert a.safeAbort(ExecutionContext()) is None
    assert a.show() is None
