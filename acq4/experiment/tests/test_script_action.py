"""Tests for the Script action (reload-on-run .py files)."""
import textwrap
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.script import ScriptAction
from acq4.experiment.exceptions import ScriptError
from acq4.experiment.protocol import Protocol
from acq4.experiment.orchestrator import Orchestrator


def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


def test_script_runs_loaded_action(tmp_path):
    path = _write(tmp_path, "good.py", """
        from acq4.experiment.action import Action

        class MyAction(Action):
            outcomes = ("ok",)
            def run(self, ctx):
                ctx.log("script ran")
                return "ok"
    """)
    logged = []
    a = ScriptAction(params={"path": path})
    assert a.run(ExecutionContext(log=logged.append)) == "ok"
    assert logged == ["script ran"]


def test_script_reloads_on_each_run(tmp_path):
    path = _write(tmp_path, "mut.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("v1",)
            def run(self, ctx): return "v1"
    """)
    a = ScriptAction(params={"path": path})
    assert a.run(ExecutionContext()) == "v1"
    # edit the file; a fresh run must pick up the change
    _write(tmp_path, "mut.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("v2",)
            def run(self, ctx): return "v2"
    """)
    assert a.run(ExecutionContext()) == "v2"


def test_import_error_becomes_scripterror(tmp_path):
    path = _write(tmp_path, "bad.py", "this is not valid python !!!")
    with pytest.raises(ScriptError):
        ScriptAction(params={"path": path}).run(ExecutionContext())


def test_no_action_subclass_raises(tmp_path):
    path = _write(tmp_path, "empty.py", "x = 1\n")
    with pytest.raises(ScriptError):
        ScriptAction(params={"path": path}).run(ExecutionContext())


def test_script_exposes_inner_outcomes(tmp_path):
    path = _write(tmp_path, "oc.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("weird",)
            def run(self, ctx): return "weird"
    """)
    a = ScriptAction(params={"path": path})
    result = a.run(ExecutionContext())
    assert result == "weird"
    # The wrapper adopts the inner action's outcomes so the orchestrator's
    # `result in action.outcomes` validation passes for non-"done" outcomes.
    assert a.outcomes == ("weird",)
    assert result in a.outcomes


def test_script_routes_through_orchestrator(tmp_path, recording_cls):
    # Regression: a ScriptAction whose inner action returns a non-"done" outcome
    # must route through the orchestrator rather than raising "unknown outcome".
    recording_cls.ran.clear()
    path = _write(tmp_path, "route.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("weird",)
            def run(self, ctx): return "weird"
    """)
    script = ScriptAction(name="s", params={"path": path})
    after = recording_cls(name="after")
    p = Protocol(nodes={"s": script, "after": after},
                 edges={("s", "weird"): "after"}, entry="s")
    Orchestrator(p).run_sync_cell("cell1")
    assert recording_cls.ran == ["after"]


def test_script_safeabort_delegates_to_inner(tmp_path):
    path = _write(tmp_path, "ab.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("ok",)
            def run(self, ctx): return "ok"
            def safeAbort(self, ctx): ctx.log("inner aborted")
    """)
    logged = []
    a = ScriptAction(params={"path": path})
    a.run(ExecutionContext(log=logged.append))
    a.safeAbort(ExecutionContext(log=logged.append))
    assert "inner aborted" in logged


def test_script_safeabort_before_run_is_noop():
    # No inner action loaded yet -> must not raise.
    ScriptAction(params={"path": ""}).safeAbort(ExecutionContext())


def test_multiple_action_subclasses_raises(tmp_path):
    path = _write(tmp_path, "two.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("ok",)
            def run(self, ctx): return "ok"
        class B(Action):
            outcomes = ("ok",)
            def run(self, ctx): return "ok"
    """)
    with pytest.raises(ScriptError):
        ScriptAction(params={"path": path}).run(ExecutionContext())
