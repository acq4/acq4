# Exception Ring Buffer

**Status:** Spec — ready to implement
**Branch:** new branch off _reviewed

## Context

The one-shot `arm_exception_capture` tool requires the MCP client to be watching when an exception fires. For debugging sporadic or already-occurred exceptions, a persistent ring buffer is needed: ACQ4 keeps the last N exceptions in memory, and the client can list and inspect them at any time after the fact.

## Goals

- ACQ4 accumulates the last N unhandled exceptions automatically when started with a flag.
- MCP client can list buffered exceptions, search by regex, and inspect any live frame.
- Exception identity is stable: each capture gets a unique monotonic ID so a new exception arriving between `list_exceptions` and `get_exception_frame` cannot silently redirect inspection to the wrong frame.

## Non-goals

- Catching handled (caught) exceptions in buffer mode — unhandled only, via `pyqtgraph.exceptionHandling`.
- Persisting the buffer across ACQ4 restarts.
- Changing the existing one-shot `arm_exception_capture` semantics.

---

## ACQ4 Startup Flag

```
acq4 --exception-buffer N
```

`N` is the ring buffer size (e.g. 5). When `N > 0`, ACQ4 calls
`acq4.mcp.exception_capture.start_buffer(N)` early in startup (before the
event loop, after the Manager is created). Default: off (0).

The flag is added to ACQ4's argument parser in `acq4/__main__.py`.

---

## exception_capture.py additions

### New globals

```python
_buffer_counter = 0          # monotonically incremented on every buffer capture
_exception_buffer: deque | None = None  # None = buffer mode not active
                             # entries: (exception_id: int, exc: Exception, captured_at: str)
```

### New functions

```python
def start_buffer(size: int = 5) -> None:
    """Arm the ring buffer. Registers _buffer_callback; does not block."""

def stop_buffer() -> None:
    """Disarm the ring buffer hook. Buffer contents remain readable."""

def _buffer_callback(exc_info) -> None:
    """Appends to _exception_buffer. Never sets _armed_event (independent of one-shot)."""

def _get_buffer_entry(exception_id: int) -> tuple:
    """Return the (id, exc, captured_at) tuple for exception_id.

    Returns None if exception_id has aged off. Callers translate None to the
    appropriate error dict (host.py is responsible for this translation).
    """

def list_buffer() -> list[dict]:
    """Return one-line summaries for all buffered exceptions, most-recent first.

    Each entry: {exception_id, exception_type, message, file, line, function, captured_at}.
    No traceback — callers use get_exception_frame for details.
    Returns [] if buffer mode is not active.
    """

def get_buffer_frame_locals(exception_id: int, frame_index: int) -> dict | None:
    """Return frame locals for a buffered exception. Same shape as get_frame_locals().
    Returns None if exception_id has aged off or frame_index is OOB."""

def exec_in_buffer_frame(exception_id: int, frame_index: int, code: str):
    """Return namespace dict for exec (success) or raise RuntimeError (failure).
    Same contract as exec_in_frame() — RuntimeError is caught by host.py."""
```

### Coexistence

One-shot mode (`arm()` / `_captured_exc`) and buffer mode (`_exception_buffer`) are fully
independent. Both can be active simultaneously. They share no state and use separate
registered callbacks.

---

## host.py additions

### New function

```python
def list_exceptions(filter_regex=None):
    """Return one-line summaries of buffered exceptions, optionally filtered.

    filter_regex is applied to "exception_type:message:file:function".
    Returns [] if buffer mode is not active.
    """
```

### Extended functions

```python
def get_exception_frame(frame_index, exception_id=None):
    """Return locals for a frame.

    exception_id=None → use one-shot _captured_exc (existing behaviour).
    exception_id=N    → use buffered exception N; error if N has aged off.
    """

def exec_in_exception_frame(frame_index, code, gui_thread=False, exception_id=None):
    """Execute code in a frame namespace.

    exception_id=None → one-shot _captured_exc (existing behaviour).
    exception_id=N    → buffered exception N; error if N has aged off.
    """
```

---

## connection.py additions

One new public+private pair mirroring the existing pattern:

```python
def list_exceptions(self, filter_regex=None, port=None, host=None)
def _list_exceptions(self, filter_regex, port, host)
```

Existing `get_exception_frame` and `exec_in_exception_frame` wrappers gain an
`exception_id=None` keyword argument that passes through to the host.

---

## server.py additions and changes

### New tool

```python
@server.tool()
def list_exceptions(
    filter: Optional[str] = None,
    port: Optional[int] = None,
    host: Optional[str] = None,
) -> str:
    """List buffered exceptions (most-recent first), optionally filtered by regex.

    ACQ4 must have been started with --exception-buffer N. Returns a JSON array
    of one-line summaries. Each entry includes exception_id — pass that to
    get_exception_frame or exec_in_exception_frame to inspect a specific exception.

    filter is a regex applied to "type:message:file:function".
    """
```

### Extended tools

`get_exception_frame` and `exec_in_exception_frame` each gain:

```python
exception_id: Optional[int] = None,
```

When `exception_id` is provided it takes precedence over the one-shot capture.
If the exception has aged off the buffer, the tool returns a clear error string.

---

## Error responses

| Situation | Response |
|-----------|----------|
| `exception_id` provided but aged off | `{"error": "exception 37 is no longer in buffer (oldest held: 40)"}` |
| `exception_id` provided but buffer not active | `{"error": "exception buffer is not active (start ACQ4 with --exception-buffer N)"}` |
| `list_exceptions` called, buffer not active | `[]` (empty list — tool docstring documents the `--exception-buffer` precondition) |

---

## File touch-list

| File | Change |
|------|--------|
| `acq4/__main__.py` | Add `--exception-buffer N` arg, call `start_buffer(N)` |
| `acq4/mcp/exception_capture.py` | Add buffer globals, `start_buffer`, `stop_buffer`, `_buffer_callback`, `_get_buffer_entry`, `list_buffer`, `get_buffer_summary`, `get_buffer_frame_locals`, `exec_in_buffer_frame` |
| `acq4/mcp/host.py` | Add `list_exceptions`; extend `get_exception_frame` and `exec_in_exception_frame` with `exception_id` |
| `acq4/mcp/connection.py` | Add `list_exceptions` wrapper pair; extend existing wrappers with `exception_id` |
| `acq4/mcp/server.py` | Add `list_exceptions` tool; extend existing tools with `exception_id` |
| `acq4/mcp/tests/test_exception_capture.py` | Tests for new buffer functions |
| `acq4/mcp/tests/test_host.py` | Tests for new/extended host functions |
| `acq4/mcp/tests/test_connection.py` | Tests for new/extended wrappers |
| `acq4/mcp/tests/test_server.py` | Tests for new/extended tools |
