# acq4/mcp/exception_capture.py — exception capture state and hooks for MCP
# Captures live exceptions in the ACQ4 process for MCP client interrogation.

import datetime
import re
import sys
import threading
import traceback
from collections import deque

from pyqtgraph import exceptionHandling

_lock = threading.Lock()
_captured_exc = None      # the Exception object (keeps __traceback__ alive)
_armed_event = None       # threading.Event, set when a matching exception arrives
_armed_filter = None      # compiled regex or None

_buffer_counter = 0          # monotonically incremented; IDs start at 1
_exception_buffer = None     # None = buffer mode not active; deque of (id, exc, captured_at)


def arm(timeout, include_caught=False, filter_regex=None):
    """Arm a one-shot exception hook and block until an exception fires or timeout.

    include_caught=True installs sys.settrace across all threads, which adds per-call
    overhead to every Python function call for the duration of the wait. Keep the window
    short on a busy rig. Note: threading.settrace only affects threads started after
    arm() is called; pre-existing threads (Qt GUI, device workers) are not covered.
    """
    global _captured_exc, _armed_event, _armed_filter

    with _lock:
        _disarm()  # clears previous capture and unregisters old hooks

        _captured_exc = None
        _armed_event = threading.Event()
        _armed_filter = re.compile(filter_regex) if filter_regex else None

    exceptionHandling.registerCallback(_exception_callback)
    if include_caught:
        sys.settrace(_systrace)
        threading.settrace(_systrace)

    fired = _armed_event.wait(timeout=timeout)
    _disarm()
    return fired  # True = exception captured; False = timed out


def _disarm():
    # called holding _lock or during arm() before the wait
    try:
        exceptionHandling.unregisterCallback(_exception_callback)
    except ValueError:
        pass
    sys.settrace(None)
    threading.settrace(None)


def _matches(exc_info):
    if _armed_filter is None:
        return True
    tb = exc_info.exc_traceback
    filename = tb.tb_frame.f_code.co_filename if tb else ''
    function = tb.tb_frame.f_code.co_name if tb else ''
    msg = ''.join(traceback.format_exception_only(exc_info.exc_type, exc_info.exc_value))
    return bool(_armed_filter.search(f"{filename}:{function}:{msg}"))


def _exception_callback(exc_info):
    global _captured_exc
    if _armed_event is None or _armed_event.is_set():
        return  # already fired or disarmed
    if not _matches(exc_info):
        return
    with _lock:
        if _armed_event.is_set():
            return  # race — second exception; ignore
        _captured_exc = exc_info.exc_value
        _armed_event.set()


def _systrace(frame, event, arg):
    if event == 'exception':
        from types import SimpleNamespace
        exc_type, exc_value, exc_tb = arg
        _exception_callback(SimpleNamespace(
            exc_type=exc_type, exc_value=exc_value, exc_traceback=exc_tb, thread=None
        ))
    return _systrace


def start_buffer(size: int = 5) -> None:
    """Arm the ring buffer. Registers _buffer_callback; returns immediately (non-blocking)."""
    global _exception_buffer
    _exception_buffer = deque(maxlen=size)
    exceptionHandling.registerCallback(_buffer_callback)


def stop_buffer() -> None:
    """Disarm the ring buffer hook. Buffer contents remain readable after stopping."""
    try:
        exceptionHandling.unregisterCallback(_buffer_callback)
    except ValueError:
        pass


def _buffer_callback(exc_info) -> None:
    # Never touches _armed_event — fully independent from one-shot mode.
    global _buffer_counter
    if _exception_buffer is None:
        return
    captured_at = datetime.datetime.now().isoformat()
    with _lock:
        _buffer_counter += 1
        exc_id = _buffer_counter
    _exception_buffer.appendleft((exc_id, exc_info.exc_value, captured_at))


def _get_buffer_entry(exception_id: int):
    """Return (id, exc, captured_at) for exception_id, or None if aged off / not found."""
    if _exception_buffer is None:
        return None
    for entry in _exception_buffer:
        if entry[0] == exception_id:
            return entry
    return None


def list_buffer() -> list:
    """Return one-line summaries for all buffered exceptions, most-recent first.

    Returns [] when buffer mode is not active.
    Each entry: {exception_id, exception_type, message, file, line, function, captured_at}.
    """
    if _exception_buffer is None:
        return []
    result = []
    for exc_id, exc, captured_at in _exception_buffer:
        tb = exc.__traceback__
        while tb and tb.tb_next:
            tb = tb.tb_next
        result.append({
            "exception_id": exc_id,
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "file": tb.tb_frame.f_code.co_filename if tb else "",
            "line": tb.tb_lineno if tb else 0,
            "function": tb.tb_frame.f_code.co_name if tb else "",
            "captured_at": captured_at,
        })
    return result


def get_buffer_frame_locals(exception_id: int, frame_index: int) -> dict:
    """Return locals for a buffered exception's frame. Same shape as get_frame_locals().

    Raises RuntimeError if exception_id has aged off or frame_index is out of range.
    """
    entry = _get_buffer_entry(exception_id)
    if entry is None:
        _raise_buffer_error(exception_id)
    _, exc, _ = entry
    tb = exc.__traceback__
    for _ in range(frame_index):
        if tb is None:
            raise RuntimeError(f"frame {frame_index} not found")
        tb = tb.tb_next
    if tb is None:
        raise RuntimeError(f"frame {frame_index} not found")
    frame = tb.tb_frame
    return {
        "frame_index": frame_index,
        "file": frame.f_code.co_filename,
        "line": frame.f_lineno,
        "function": frame.f_code.co_name,
        "locals": {k: repr(v) for k, v in frame.f_locals.items()},
    }


def exec_in_buffer_frame(exception_id: int, frame_index: int, code: str) -> dict:
    """Return namespace dict for exec in a buffered exception's frame.

    Raises RuntimeError if exception_id has aged off or frame_index is out of range.
    Execution with stdout/stderr capture happens in host.py (same contract as exec_in_frame).
    """
    entry = _get_buffer_entry(exception_id)
    if entry is None:
        _raise_buffer_error(exception_id)
    _, exc, _ = entry
    tb = exc.__traceback__
    for _ in range(frame_index):
        if tb is None:
            raise RuntimeError(f"frame {frame_index} not found")
        tb = tb.tb_next
    if tb is None:
        raise RuntimeError(f"frame {frame_index} not found")
    frame = tb.tb_frame
    return {**frame.f_globals, **frame.f_locals}


def _raise_buffer_error(exception_id: int) -> None:
    """Raise a RuntimeError naming the oldest held ID (or noting buffer is inactive)."""
    if _exception_buffer is None:
        raise RuntimeError(
            f"exception {exception_id} not found: buffer not active "
            f"(start ACQ4 with --exception-buffer N)"
        )
    if _exception_buffer:
        oldest_id = _exception_buffer[-1][0]
        raise RuntimeError(
            f"exception {exception_id} is no longer in buffer (oldest held: {oldest_id})"
        )
    raise RuntimeError(f"exception {exception_id} not found: buffer is empty")


def get_summary():
    exc = _captured_exc
    if exc is None:
        return None
    tb = exc.__traceback__
    frames = []
    idx = 0
    while tb is not None:
        frames.append({
            "index": idx,
            "file": tb.tb_frame.f_code.co_filename,
            "line": tb.tb_lineno,
            "function": tb.tb_frame.f_code.co_name,
        })
        tb = tb.tb_next
        idx += 1
    return {
        "timed_out": False,
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback": ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        "frames": frames,
    }


def get_frame_locals(frame_index):
    exc = _captured_exc
    if exc is None:
        return None
    tb = exc.__traceback__
    for i in range(frame_index):
        if tb is None:
            return None
        tb = tb.tb_next
    if tb is None:
        return None
    frame = tb.tb_frame
    return {
        "frame_index": frame_index,
        "file": frame.f_code.co_filename,
        "line": frame.f_lineno,
        "function": frame.f_code.co_name,
        "locals": {k: repr(v) for k, v in frame.f_locals.items()},
    }


def exec_in_frame(frame_index, code):
    exc = _captured_exc
    if exc is None:
        raise RuntimeError("no exception captured")
    tb = exc.__traceback__
    for i in range(frame_index):
        if tb is None:
            raise RuntimeError(f"frame {frame_index} not found")
        tb = tb.tb_next
    if tb is None:
        raise RuntimeError(f"frame {frame_index} not found")
    frame = tb.tb_frame
    ns = {**frame.f_globals, **frame.f_locals}
    # (caller executes code in ns; stdout/stderr capture happens in host.py)
    return ns
