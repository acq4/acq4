# acq4/mcp/exception_capture.py — exception capture state and hooks for MCP
# Captures live exceptions in the ACQ4 process for MCP client interrogation.

import re
import sys
import threading
import traceback

from pyqtgraph import exceptionHandling

_lock = threading.Lock()
_captured_exc = None      # the Exception object (keeps __traceback__ alive)
_armed_event = None       # threading.Event, set when a matching exception arrives
_armed_filter = None      # compiled regex or None


def arm(timeout, include_caught=False, filter_regex=None):
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
        return {"error": "no exception captured"}
    tb = exc.__traceback__
    for i in range(frame_index):
        if tb is None:
            return {"error": f"frame {frame_index} not found"}
        tb = tb.tb_next
    if tb is None:
        return {"error": f"frame {frame_index} not found"}
    frame = tb.tb_frame
    ns = {**frame.f_globals, **frame.f_locals}
    # (caller executes code in ns; stdout/stderr capture happens in host.py)
    return ns
