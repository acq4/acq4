"""Unit tests for acq4.mcp.host: the ACQ4-side code-execution and inspection helpers.

These run without a live Manager or GUI; they exercise namespace seeding, output
capture, exception reporting, and GUI-thread dispatch in isolation.
"""

import pytest

import acq4.mcp.exception_capture as _ec
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


# ---------------------------------------------------------------------------
# Exception interrogation
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_exception():
    """Inject a real captured exception into exception_capture and clean up after."""
    import acq4.mcp.exception_capture as ec
    try:
        raise ValueError("test exception for mcp interrogation")
    except ValueError as e:
        exc = e
        ec._captured_exc = exc
    yield exc
    ec._captured_exc = None


def test_get_exception_frame_returns_error_when_no_capture():
    import acq4.mcp.exception_capture as ec
    ec._captured_exc = None
    result = host.get_exception_frame(0)
    assert result == {"error": "no exception captured"}


def test_exec_in_exception_frame_returns_error_when_no_capture():
    import acq4.mcp.exception_capture as ec
    ec._captured_exc = None
    result = host.exec_in_exception_frame(0, "1+1")
    assert result == {"error": "no exception captured"}


def test_arm_exception_capture_returns_timed_out_on_short_timeout():
    result = host.arm_exception_capture(0.01)
    assert result == {"timed_out": True}


def test_get_exception_frame_returns_locals_dict_when_captured(captured_exception):
    result = host.get_exception_frame(0)
    assert "locals" in result
    assert result["frame_index"] == 0
    assert "file" in result
    assert "function" in result


def test_exec_in_exception_frame_evaluates_expression_in_frame(captured_exception):
    result = host.exec_in_exception_frame(0, "1+1")
    assert result["result"] == "2"
    assert result["traceback"] is None


def test_exec_in_exception_frame_frame_with_error_local():
    """A frame local named 'error' must not be mistaken for the error sentinel."""
    import acq4.mcp.exception_capture as ec

    def inner():
        error = "I am a local named error"  # noqa: F841
        raise ValueError("test")

    try:
        inner()
    except ValueError as e:
        ec._captured_exc = e

    try:
        # Frame 0 is inner(), which has a local named 'error'.
        # Before the fix, exec_in_frame returned {"error": "I am a local named error"}
        # and exec_in_exception_frame treated it as an error sentinel, refusing to
        # execute the code.
        result = host.exec_in_exception_frame(0, "1 + 1")
        assert "result" in result, f"Got error instead of result: {result}"
        assert result["result"] == "2"
    finally:
        ec._captured_exc = None


# ---------------------------------------------------------------------------
# Ring-buffer exception interrogation
# ---------------------------------------------------------------------------


@pytest.fixture
def buffer_with_exception():
    """Start buffer, inject an exception, yield its exception_id, then clean up."""
    import sys
    from types import SimpleNamespace

    # Patch exceptionHandling so start_buffer doesn't touch real pyqtgraph hooks
    import pyqtgraph.exceptionHandling as _eh
    orig_reg = _eh.registerCallback
    orig_unreg = _eh.unregisterCallback
    _eh.registerCallback = lambda cb: None
    _eh.unregisterCallback = lambda cb: None

    _ec._buffer_counter = 0
    _ec._exception_buffer = None
    _ec.start_buffer(size=5)

    def inner(data):
        error = ValueError("an error local")  # noqa: F841
        raise KeyError("buffer_test_key")

    try:
        inner({"x": 1})
    except KeyError as exc:
        _ec._buffer_callback(SimpleNamespace(
            exc_type=type(exc), exc_value=exc,
            exc_traceback=exc.__traceback__, thread=None,
        ))
        exc_id = _ec._exception_buffer[0][0]

    yield exc_id

    _ec._exception_buffer = None
    _ec._buffer_counter = 0
    _eh.registerCallback = orig_reg
    _eh.unregisterCallback = orig_unreg


def test_list_exceptions_returns_empty_when_buffer_inactive():
    _ec._exception_buffer = None
    result = host.list_exceptions()
    assert result == []


def test_list_exceptions_returns_entries(buffer_with_exception):
    result = host.list_exceptions()
    assert len(result) == 1
    assert result[0]["exception_type"] == "KeyError"
    assert "exception_id" in result[0]


def test_list_exceptions_filter_matches(buffer_with_exception):
    result = host.list_exceptions(filter_regex="KeyError")
    assert len(result) == 1


def test_list_exceptions_filter_no_match(buffer_with_exception):
    result = host.list_exceptions(filter_regex="ValueError")
    assert result == []


def test_get_exception_frame_with_exception_id(buffer_with_exception):
    # frame 0 is the fixture's try-block; frame 1 is the inner() function where
    # the KeyError was raised — that's the more informative innermost frame.
    result = host.get_exception_frame(1, exception_id=buffer_with_exception)
    assert "locals" in result
    assert result["function"] == "inner"


def test_get_exception_frame_aged_off_returns_error():
    import pyqtgraph.exceptionHandling as _eh
    from types import SimpleNamespace
    orig_reg = _eh.registerCallback
    orig_unreg = _eh.unregisterCallback
    _eh.registerCallback = lambda cb: None
    _eh.unregisterCallback = lambda cb: None

    _ec._buffer_counter = 0
    _ec._exception_buffer = None
    _ec.start_buffer(size=1)
    ids = []
    for msg in ["first", "second"]:
        try:
            raise RuntimeError(msg)
        except RuntimeError as exc:
            _ec._buffer_callback(SimpleNamespace(
                exc_type=type(exc), exc_value=exc,
                exc_traceback=exc.__traceback__, thread=None,
            ))
            ids.append(_ec._exception_buffer[0][0])
    result = host.get_exception_frame(0, exception_id=ids[0])
    assert "error" in result
    _ec._exception_buffer = None
    _ec._buffer_counter = 0
    _eh.registerCallback = orig_reg
    _eh.unregisterCallback = orig_unreg


def test_exec_in_exception_frame_with_exception_id(buffer_with_exception):
    result = host.exec_in_exception_frame(0, "1 + 1", exception_id=buffer_with_exception)
    assert result.get("result") == "2"


def test_exec_in_exception_frame_exception_id_none_still_works():
    """Original one-shot path must be unaffected."""
    host.reset_namespace()
    _ec._captured_exc = None
    result = host.exec_in_exception_frame(0, "1+1")
    assert "error" in result  # no captured exc
