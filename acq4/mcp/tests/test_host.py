"""Unit tests for acq4.mcp.host: the ACQ4-side code-execution and inspection helpers.

These run without a live Manager or GUI; they exercise namespace seeding, output
capture, exception reporting, and GUI-thread dispatch in isolation.
"""

import pytest

from acq4.mcp import host


def test_execute_persists_variables_across_calls():
    host.reset_namespace()
    host.execute("persisted_value = 123")
    result = host.execute("persisted_value * 2")
    assert result["result"] == "246"


def test_reset_namespace_clears_state():
    host.execute("scratch = 'gone soon'")
    host.reset_namespace()
    result = host.execute("'scratch' in dir()")
    assert result["result"] == "False"


def test_reset_namespace_returns_confirmation():
    assert host.reset_namespace() == {"reset": True}


def test_namespace_reheals_man_once_manager_exists(monkeypatch):
    import acq4

    host.reset_namespace()
    # First build: no Manager yet -> man is None.
    monkeypatch.setattr(
        acq4, "getManager", lambda: (_ for _ in ()).throw(RuntimeError("none"))
    )
    assert host.execute("man is None")["result"] == "True"
    host.execute("user_var = 7")  # user state that must survive the heal
    # Manager appears.
    sentinel = object()
    monkeypatch.setattr(acq4, "getManager", lambda: sentinel)
    assert host.execute("man is not None")["result"] == "True"
    assert host.execute("user_var")["result"] == "7"


def test_execute_returns_last_expression_repr():
    host.reset_namespace()
    result = host.execute("1 + 1")
    assert result["result"] == "2"
    assert result["traceback"] is None


def test_execute_captures_stdout():
    result = host.execute("print('hello world')")
    assert "hello world" in result["stdout"]
    # print() returns None, so there is no trailing-expression value
    assert result["result"] is None


def test_execute_multi_statement_with_trailing_expression():
    result = host.execute("x = 5\nx * 2")
    assert result["result"] == "10"


def test_execute_no_trailing_expression_has_no_result():
    result = host.execute("y = 41\ny += 1")
    assert result["result"] is None
    assert result["traceback"] is None


def test_execute_reports_exception_traceback():
    result = host.execute("raise ValueError('boom')")
    assert result["result"] is None
    assert "ValueError: boom" in result["traceback"]


def test_execute_captures_stdout_before_exception():
    result = host.execute("print('partial')\nraise RuntimeError('later')")
    assert "partial" in result["stdout"]
    assert "RuntimeError: later" in result["traceback"]


def test_execute_seeds_acq4_module():
    host.reset_namespace()
    result = host.execute("acq4.__name__")
    assert result["result"] == "'acq4'"


def test_execute_seeds_man_as_none_without_manager():
    # Without a running Manager, `man` is seeded as None rather than raising NameError.
    host.reset_namespace()
    result = host.execute("man is None")
    assert result["result"] == "True"
    assert result["traceback"] is None


def test_execute_gui_thread_dispatches_through_run_in_gui_thread(monkeypatch):
    from acq4.util import task

    calls = []

    def fake_run_in_gui_thread(fn, *args, **kwargs):
        calls.append(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr(task, "run_in_gui_thread", fake_run_in_gui_thread)

    result = host.execute("2 * 3", gui_thread=True)

    assert calls, "expected gui_thread=True to route through run_in_gui_thread"
    assert result["result"] == "6"


def test_execute_default_does_not_use_gui_thread(monkeypatch):
    from acq4.util import task

    def boom(*args, **kwargs):
        raise AssertionError(
            "run_in_gui_thread must not be called when gui_thread=False"
        )

    monkeypatch.setattr(task, "run_in_gui_thread", boom)

    result = host.execute("4 + 4")
    assert result["result"] == "8"


# ---------------------------------------------------------------------------
# Hot reload
# ---------------------------------------------------------------------------


def test_reload_libraries_runs_on_gui_thread_and_summarizes(monkeypatch):
    import pyqtgraph.reload as reload
    from acq4.util import task

    calls = []
    monkeypatch.setattr(
        task,
        "run_in_gui_thread",
        lambda fn, *a, **k: (calls.append(fn) or fn(*a, **k)),
    )

    def fake_reload_all(debug=False):
        print("Reloading acq4.foo")
        return {
            "acq4.foo": (True, None),
            "acq4.bar": (True, None),
            "os": (False, "code has not changed since compile"),
        }

    monkeypatch.setattr(reload, "reloadAll", fake_reload_all)

    result = host.reload_libraries()
    assert calls, "reload must run on the GUI thread, like the Reload button"
    assert result["reloaded"] == ["acq4.bar", "acq4.foo"]
    assert result["skipped"] == 1
    assert result["error"] is None
    assert "Reloading acq4.foo" in result["output"]


def test_reload_libraries_reports_partial_failure(monkeypatch):
    import pyqtgraph.reload as reload
    from acq4.util import task

    monkeypatch.setattr(task, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))

    def fake_reload_all(debug=False):
        # pyqtgraph.reload.reloadAll reloads what it can, then raises if any module
        # failed -- so the return dict is lost but the debug log survives.
        print("Reloading acq4.broken")
        raise Exception("Some modules failed to reload: acq4.broken")

    monkeypatch.setattr(reload, "reloadAll", fake_reload_all)

    result = host.reload_libraries()
    assert result["reloaded"] is None
    assert result["skipped"] is None
    assert "acq4.broken" in result["error"]
    assert "Reloading acq4.broken" in result["output"]


# ---------------------------------------------------------------------------
# Read-only inspection helpers
# ---------------------------------------------------------------------------


class _FakeDir:
    def __init__(self, path):
        self._path = path

    def name(self):
        return self._path


class _FakeManager:
    def __init__(self):
        self._devices = {"cam": object(), "stage": object()}
        self.config = {"devices": {}, "storageDir": "/data", "misc": 1}

    def listDevices(self):
        return list(self._devices)

    def getDevice(self, name):
        return self._devices[name]

    def listModules(self):
        return ["Camera", "MultiPatch"]

    def listDefinedModules(self):
        return {"Camera": {}, "Console": {}}

    def getBaseDir(self):
        return _FakeDir("/data/base")

    def getCurrentDir(self):
        return _FakeDir("/data/base/2026.07.03")


@pytest.fixture
def fake_manager(monkeypatch):
    import acq4

    man = _FakeManager()
    monkeypatch.setattr(acq4, "getManager", lambda: man)
    return man


def test_list_devices_maps_name_to_type(fake_manager):
    devices = host.list_devices()
    # each device object's class name is "object"
    assert devices == {"cam": "object", "stage": "object"}


def test_list_modules_reports_loaded_and_defined(fake_manager):
    modules = host.list_modules()
    assert modules["loaded"] == ["Camera", "MultiPatch"]
    assert sorted(modules["defined"]) == ["Camera", "Console"]


def test_manager_state_reports_dirs_and_counts(fake_manager):
    state = host.manager_state()
    assert state["base_dir"] == "/data/base"
    assert state["current_dir"] == "/data/base/2026.07.03"
    assert state["device_count"] == 2
    assert "storageDir" in state["config_keys"]
    # manager_state must not embed the module list (that is list_modules' job)
    assert "modules" not in state


def test_manager_state_handles_unset_current_dir(fake_manager, monkeypatch):
    def raise_unset():
        raise RuntimeError("Storage directory has not been set.")

    monkeypatch.setattr(fake_manager, "getCurrentDir", raise_unset)
    state = host.manager_state()
    assert state["current_dir"] is None
    assert state["base_dir"] == "/data/base"


def test_get_log_tails_file(monkeypatch, tmp_path):
    import types

    import acq4.logging_config as lc

    log = tmp_path / "acq4.log"
    log.write_text("".join(f"line {i}\n" for i in range(100)))
    monkeypatch.setattr(
        lc, "log_file_handler", types.SimpleNamespace(baseFilename=str(log))
    )

    result = host.get_log(lines=5)
    assert result["path"] == str(log)
    assert result["text"].splitlines() == [
        "line 95",
        "line 96",
        "line 97",
        "line 98",
        "line 99",
    ]


def test_get_log_returns_only_last_n_lines(monkeypatch, tmp_path):
    import types

    import acq4.logging_config as lc

    log = tmp_path / "acq4.log"
    log.write_text("".join(f"line {i}\n" for i in range(10)))
    monkeypatch.setattr(
        lc, "log_file_handler", types.SimpleNamespace(baseFilename=str(log))
    )

    result = host.get_log(lines=2)
    assert result["path"] == str(log)
    assert result["text"].splitlines() == ["line 8", "line 9"]


def test_get_log_zero_lines_returns_empty_text(monkeypatch, tmp_path):
    # lines=0 means "no lines": empty text, not the whole file (a plain [-0:] slice
    # would return everything).
    import types

    import acq4.logging_config as lc

    log = tmp_path / "acq4.log"
    log.write_text("".join(f"line {i}\n" for i in range(10)))
    monkeypatch.setattr(
        lc, "log_file_handler", types.SimpleNamespace(baseFilename=str(log))
    )

    result = host.get_log(lines=0)
    assert result["path"] == str(log)
    assert result["text"] == ""


def test_get_log_without_handler_reports_no_file(monkeypatch):
    import acq4.logging_config as lc

    monkeypatch.setattr(lc, "log_file_handler", None)
    result = host.get_log()
    assert result["path"] is None
    assert "no log file" in result["text"].lower()


def test_instance_info_without_manager(monkeypatch):
    import acq4

    def raise_no_manager():
        raise RuntimeError("No manager created yet")

    monkeypatch.setattr(acq4, "getManager", raise_no_manager)
    info = host.instance_info()
    assert info["has_manager"] is False
    assert info["device_count"] is None
    assert "hostname" in info


def test_instance_info_with_manager(fake_manager):
    info = host.instance_info()
    assert info["has_manager"] is True
    assert info["device_count"] == 2
    assert info["base_dir"] == "/data/base"
