"""Tests for the Script action (reload-on-run .py files)."""
import textwrap
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.script import ScriptAction
from acq4.experiment.exceptions import ScriptError


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
