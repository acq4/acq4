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
    # Should not be an error dict
    assert "error" not in result


def test_exec_in_frame_returns_error_when_nothing_captured():
    result = ec.exec_in_frame(0, "x")

    assert result == {"error": "no exception captured"}


def test_exec_in_frame_returns_error_for_nonexistent_frame():
    exc = _make_captured_exc()
    ec._captured_exc = exc

    result = ec.exec_in_frame(99, "x")

    assert "error" in result
    assert "99" in result["error"]


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
