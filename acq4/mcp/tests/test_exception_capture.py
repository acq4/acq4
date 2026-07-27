# acq4/mcp/tests/test_exception_capture.py — tests for exception_capture module
# Tests the MCP exception capture state and query functions without pyqtgraph hooks.

import sys
import types
from types import SimpleNamespace
from unittest import mock

import pytest

# Mock pyqtgraph.exceptionHandling before importing the module under test
_mock_eh = mock.MagicMock()
sys.modules.setdefault('pyqtgraph', mock.MagicMock())
sys.modules.setdefault('pyqtgraph.exceptionHandling', _mock_eh)

# Patch the attribute that exception_capture imports via `from pyqtgraph import exceptionHandling`
with mock.patch.dict(sys.modules, {'pyqtgraph': mock.MagicMock(exceptionHandling=_mock_eh)}):
    import acq4.mcp.exception_capture as ec


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module globals before each test."""
    ec._captured_exc = None
    ec._armed_event = None
    ec._armed_filter = None
    yield
    ec._captured_exc = None
    ec._armed_event = None
    ec._armed_filter = None


def _make_captured_exc():
    """Raise and catch a real exception so it has a live __traceback__."""
    try:
        raise ValueError("test error")
    except ValueError as e:
        return e


# --- get_summary ---

def test_get_summary_returns_none_when_nothing_captured():
    assert ec.get_summary() is None


def test_get_summary_returns_correct_shape():
    exc = _make_captured_exc()
    ec._captured_exc = exc

    result = ec.get_summary()

    assert result is not None
    assert result["timed_out"] is False
    assert result["exception_type"] == "ValueError"
    assert result["message"] == "test error"
    assert isinstance(result["traceback"], str)
    assert "ValueError" in result["traceback"]
    assert isinstance(result["frames"], list)
    assert len(result["frames"]) >= 1
    frame = result["frames"][0]
    assert "index" in frame
    assert "file" in frame
    assert "line" in frame
    assert "function" in frame


# --- get_frame_locals ---

def test_get_frame_locals_returns_correct_shape():
    exc = _make_captured_exc()
    ec._captured_exc = exc

    result = ec.get_frame_locals(0)

    assert result is not None
    assert result["frame_index"] == 0
    assert "file" in result
    assert "line" in result
    assert "function" in result
    assert isinstance(result["locals"], dict)


def test_get_frame_locals_returns_none_for_nonexistent_frame():
    exc = _make_captured_exc()
    ec._captured_exc = exc

    result = ec.get_frame_locals(99)

    assert result is None


def test_get_frame_locals_returns_none_when_nothing_captured():
    result = ec.get_frame_locals(0)
    assert result is None


# --- exec_in_frame ---

def test_exec_in_frame_returns_namespace_dict():
    exc = _make_captured_exc()
    ec._captured_exc = exc

    result = ec.exec_in_frame(0, "x")

    assert isinstance(result, dict)
    # Errors are raised as RuntimeError, so any returned dict is a namespace dict.


def test_exec_in_frame_raises_when_nothing_captured():
    with pytest.raises(RuntimeError, match="no exception captured"):
        ec.exec_in_frame(0, "x")


def test_exec_in_frame_raises_for_nonexistent_frame():
    exc = _make_captured_exc()
    ec._captured_exc = exc

    with pytest.raises(RuntimeError, match="99"):
        ec.exec_in_frame(99, "x")


# --- arm ---

def test_arm_with_short_timeout_returns_false():
    # arm() with a timeout so short no exception can fire should return False.
    fired = ec.arm(0.001)
    assert fired is False


# --- _matches ---

def test_matches_returns_true_when_filter_is_none():
    ec._armed_filter = None
    exc_info = SimpleNamespace(
        exc_type=ValueError,
        exc_value=ValueError("boom"),
        exc_traceback=None,
        thread=None,
    )
    assert ec._matches(exc_info) is True


def test_matches_applies_regex_correctly_match():
    ec._armed_filter = __import__('re').compile(r"ValueError")
    try:
        raise ValueError("specific message")
    except ValueError as e:
        import sys
        tb = sys.exc_info()[2]
        exc_info = SimpleNamespace(
            exc_type=ValueError,
            exc_value=e,
            exc_traceback=tb,
            thread=None,
        )
    assert ec._matches(exc_info) is True


def test_matches_applies_regex_correctly_no_match():
    ec._armed_filter = __import__('re').compile(r"ZeroDivisionError")
    try:
        raise ValueError("different error")
    except ValueError as e:
        import sys
        tb = sys.exc_info()[2]
        exc_info = SimpleNamespace(
            exc_type=ValueError,
            exc_value=e,
            exc_traceback=tb,
            thread=None,
        )
    assert ec._matches(exc_info) is False


# --- ring buffer ---

from collections import deque  # noqa: E402


@pytest.fixture(autouse=True)
def reset_buffer_state():
    """Reset buffer globals before/after each test."""
    ec._buffer_counter = 0
    ec._exception_buffer = None
    yield
    if ec._exception_buffer is not None:
        ec.stop_buffer()
    ec._buffer_counter = 0
    ec._exception_buffer = None


def _capture_to_buffer():
    """Helper: start buffer, fire a real exception into it, stop buffer."""
    ec.start_buffer(size=5)
    try:
        def inner(data):
            error = ValueError("an inner error")  # noqa: F841
            raise KeyError("missing_key")
        inner({"x": 1})
    except KeyError as exc:
        ec._buffer_callback(SimpleNamespace(
            exc_type=type(exc), exc_value=exc,
            exc_traceback=exc.__traceback__, thread=None,
        ))
    return ec._exception_buffer[0][0]  # return the exception_id


def test_start_buffer_creates_deque():
    ec.start_buffer(size=3)
    assert ec._exception_buffer is not None
    assert ec._exception_buffer.maxlen == 3


def test_start_buffer_registers_callback():
    ec.start_buffer(size=5)
    _mock_eh.registerCallback.assert_called_with(ec._buffer_callback)


def test_stop_buffer_unregisters_callback():
    ec.start_buffer(size=5)
    ec.stop_buffer()
    _mock_eh.unregisterCallback.assert_called_with(ec._buffer_callback)


def test_stop_buffer_tolerates_not_registered():
    _mock_eh.unregisterCallback.side_effect = ValueError("not registered")
    ec.stop_buffer()  # must not raise
    _mock_eh.unregisterCallback.side_effect = None


def test_buffer_callback_appends_entry():
    ec.start_buffer(size=5)
    exc_id = _capture_to_buffer()
    assert len(ec._exception_buffer) == 1
    stored_id, stored_exc, captured_at = ec._exception_buffer[0]
    assert stored_id == exc_id
    assert isinstance(stored_exc, KeyError)
    assert captured_at  # non-empty ISO string


def test_buffer_callback_assigns_monotonic_ids():
    ec.start_buffer(size=5)
    ids = []
    for msg in ["first", "second", "third"]:
        try:
            raise RuntimeError(msg)
        except RuntimeError as exc:
            ec._buffer_callback(SimpleNamespace(
                exc_type=type(exc), exc_value=exc,
                exc_traceback=exc.__traceback__, thread=None,
            ))
            ids.append(ec._exception_buffer[0][0])
    assert ids[0] < ids[1] < ids[2]


def test_buffer_drops_oldest_when_full():
    ec.start_buffer(size=2)
    ids = []
    for msg in ["a", "b", "c"]:
        try:
            raise RuntimeError(msg)
        except RuntimeError as exc:
            ec._buffer_callback(SimpleNamespace(
                exc_type=type(exc), exc_value=exc,
                exc_traceback=exc.__traceback__, thread=None,
            ))
            ids.append(ec._exception_buffer[0][0])
    # Only last 2 should remain
    held_ids = {entry[0] for entry in ec._exception_buffer}
    assert ids[0] not in held_ids
    assert ids[1] in held_ids
    assert ids[2] in held_ids


def test_list_buffer_returns_empty_when_not_active():
    assert ec.list_buffer() == []


def test_list_buffer_returns_summaries_most_recent_first():
    exc_id = _capture_to_buffer()
    entries = ec.list_buffer()
    assert len(entries) == 1
    e = entries[0]
    assert e["exception_id"] == exc_id
    assert e["exception_type"] == "KeyError"
    assert "missing_key" in e["message"]
    assert e["function"]  # non-empty
    assert e["captured_at"]


def test_get_buffer_frame_locals_returns_locals():
    exc_id = _capture_to_buffer()
    result = ec.get_buffer_frame_locals(exc_id, 0)
    assert result is not None
    assert "locals" in result
    assert result["function"]


def test_get_buffer_frame_locals_raises_for_aged_off_id():
    ec.start_buffer(size=1)
    # Capture two exceptions so the first ages off
    ids = []
    for msg in ["first", "second"]:
        try:
            raise RuntimeError(msg)
        except RuntimeError as exc:
            ec._buffer_callback(SimpleNamespace(
                exc_type=type(exc), exc_value=exc,
                exc_traceback=exc.__traceback__, thread=None,
            ))
            ids.append(ec._exception_buffer[0][0])
    with pytest.raises(RuntimeError, match=str(ids[0])):
        ec.get_buffer_frame_locals(ids[0], 0)


def test_exec_in_buffer_frame_returns_namespace():
    exc_id = _capture_to_buffer()
    ns = ec.exec_in_buffer_frame(exc_id, 0, "1+1")
    assert isinstance(ns, dict)


def test_exec_in_buffer_frame_raises_for_aged_off():
    ec.start_buffer(size=1)
    ids = []
    for msg in ["first", "second"]:
        try:
            raise RuntimeError(msg)
        except RuntimeError as exc:
            ec._buffer_callback(SimpleNamespace(
                exc_type=type(exc), exc_value=exc,
                exc_traceback=exc.__traceback__, thread=None,
            ))
            ids.append(ec._exception_buffer[0][0])
    with pytest.raises(RuntimeError, match="oldest held"):
        ec.exec_in_buffer_frame(ids[0], 0, "1+1")
