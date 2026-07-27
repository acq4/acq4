# Exception Ring Buffer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent ring buffer to ACQ4's MCP server that accumulates the last N unhandled exceptions (indexed by stable monotonic ID) for post-hoc inspection.

**Architecture:** A new `--exception-buffer N` startup flag arms a continuous callback in `exception_capture.py` that appends exceptions to a bounded deque. Each entry carries a monotonic integer ID so MCP tools address exceptions stably even as new ones push old ones off. Three existing MCP tools (`list_exceptions` new, `get_exception_frame` extended, `exec_in_exception_frame` extended) expose the buffer. One-shot `arm_exception_capture` is completely unchanged.

**Tech Stack:** Python stdlib (`collections.deque`, `datetime`, `threading`), pyqtgraph `exceptionHandling`, FastMCP, teleprox.

## Global Constraints

- Python: `/home/martin/.miniforge3/envs/acq4-gl/bin/python`
- Working directory / git root: `/home/martin/src/acq4/acq4/.claude/worktrees/mcp-exception-interrogation`
- Run tests with: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest <path> -v`
- Commit author: `--author="Martin Chase <outofculture@gmail.com>"`
- Commit footer: `🤖 Generated with [Claude Code](https://claude.ai/code)`
- All files start with a 2-line `# path — purpose` comment header
- No `--no-verify` on commits
- TDD: write failing test → confirm failure → implement → confirm pass → commit
- `exception_id=0` is never a valid ID (counter starts at 1); treat 0 as "not provided"
- Buffer mode and one-shot mode share `_lock` but are otherwise independent
- `_buffer_callback` must never set `_armed_event` (one-shot state)

---

## File Touch-List

| File | Change |
|------|--------|
| `acq4/mcp/exception_capture.py` | Add buffer globals, `start_buffer`, `stop_buffer`, `_buffer_callback`, `_get_buffer_entry`, `list_buffer`, `get_buffer_frame_locals`, `exec_in_buffer_frame` |
| `acq4/__main__.py` | Add `--exception-buffer N` arg; call `start_buffer(N)` when N > 0 |
| `acq4/mcp/host.py` | Add `list_exceptions`; extend `get_exception_frame` and `exec_in_exception_frame` with `exception_id=None` |
| `acq4/mcp/connection.py` | Add `list_exceptions` public+private pair; extend existing two wrappers with `exception_id=None` |
| `acq4/mcp/server.py` | Add `list_exceptions` tool; extend `get_exception_frame` and `exec_in_exception_frame` tools with `exception_id` |
| `acq4/mcp/tests/test_exception_capture.py` | Extend with buffer tests |
| `acq4/mcp/tests/test_host.py` | Extend with buffer host tests |
| `acq4/mcp/tests/test_connection.py` | Extend with buffer wrapper tests |
| `acq4/mcp/tests/test_server.py` | No change needed (pure helper tests only) |

---

## Task 1: Buffer core in exception_capture.py

**Files:**
- Modify: `acq4/mcp/exception_capture.py`
- Test: `acq4/mcp/tests/test_exception_capture.py`

**Interfaces:**
- Consumes: existing `_lock`, `exceptionHandling`
- Produces:
  - `start_buffer(size: int = 5) -> None`
  - `stop_buffer() -> None`
  - `list_buffer() -> list[dict]` — each dict: `{exception_id, exception_type, message, file, line, function, captured_at}`
  - `get_buffer_frame_locals(exception_id: int, frame_index: int) -> dict` — raises `RuntimeError` on failure
  - `exec_in_buffer_frame(exception_id: int, frame_index: int, code: str) -> dict` — returns namespace dict or raises `RuntimeError`

- [ ] **Step 1: Write failing tests**

Add to `acq4/mcp/tests/test_exception_capture.py` after the existing `reset_state` fixture. The mock setup at the top of the file already patches `exceptionHandling`; `_mock_eh` is the mock object.

```python
from collections import deque


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
        from types import SimpleNamespace
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
            from types import SimpleNamespace
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
            from types import SimpleNamespace
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
            from types import SimpleNamespace
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
            from types import SimpleNamespace
            ec._buffer_callback(SimpleNamespace(
                exc_type=type(exc), exc_value=exc,
                exc_traceback=exc.__traceback__, thread=None,
            ))
            ids.append(ec._exception_buffer[0][0])
    with pytest.raises(RuntimeError, match="oldest held"):
        ec.exec_in_buffer_frame(ids[0], 0, "1+1")
```

- [ ] **Step 2: Confirm tests fail**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_exception_capture.py -v -k "buffer"
```
Expected: multiple errors — `AttributeError: module has no attribute '_buffer_counter'` etc.

- [ ] **Step 3: Implement buffer additions in exception_capture.py**

Add to the imports section (after `import traceback`):
```python
import datetime
from collections import deque
```

Add after the existing globals (`_armed_filter = None`):
```python
_buffer_counter = 0          # monotonically incremented; IDs start at 1
_exception_buffer = None     # None = buffer mode not active; deque of (id, exc, captured_at)
```

Add these functions after `_systrace` (before `get_summary`):
```python
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
```

- [ ] **Step 4: Confirm tests pass**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_exception_capture.py -v
```
Expected: all tests pass (existing + new buffer tests).

- [ ] **Step 5: Commit**

```bash
git add acq4/mcp/exception_capture.py acq4/mcp/tests/test_exception_capture.py
git commit --author="Martin Chase <outofculture@gmail.com>" -m "feat: add ring buffer to exception_capture module

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

## Task 2: ACQ4 startup flag

**Files:**
- Modify: `acq4/__main__.py`

**Interfaces:**
- Consumes: `exception_capture.start_buffer(size)` from Task 1
- Produces: `--exception-buffer N` CLI flag; `start_buffer` called before event loop

**Note:** No automated test is practical for this task (it requires a full ACQ4 process). Verify manually by inspection after implementing.

- [ ] **Step 1: Add the argument to the parser**

In `acq4/__main__.py`, add this line immediately after the `--teleprox` argument definition:

```python
control_arg_parser.add_argument(
    "--exception-buffer", type=int, default=0, metavar="N",
    help="Keep a ring buffer of the last N unhandled exceptions for MCP inspection. "
         "0 (default) disables the buffer.",
)
```

- [ ] **Step 2: Call start_buffer after installExceptionHandler**

In `acq4/__main__.py`, add this block immediately after the `installExceptionHandler()` call (around line 88):

```python
if args.exception_buffer > 0:
    from acq4.mcp import exception_capture as _exc_capture
    _exc_capture.start_buffer(args.exception_buffer)
    print(f"Exception ring buffer active (size={args.exception_buffer})")
```

- [ ] **Step 3: Verify the file parses correctly**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "
import sys; sys.argv = ['acq4', '--help']
try:
    import acq4.__main__
except SystemExit:
    pass
" 2>&1 | grep "exception-buffer"
```
Expected: `--exception-buffer N   Keep a ring buffer ...`

- [ ] **Step 4: Commit**

```bash
git add acq4/__main__.py
git commit --author="Martin Chase <outofculture@gmail.com>" -m "feat: add --exception-buffer startup flag to ACQ4

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

## Task 3: host.py additions and extensions

**Files:**
- Modify: `acq4/mcp/host.py`
- Test: `acq4/mcp/tests/test_host.py`

**Interfaces:**
- Consumes from Task 1: `list_buffer()`, `get_buffer_frame_locals(exc_id, frame_idx)`, `exec_in_buffer_frame(exc_id, frame_idx, code)`
- Produces:
  - `list_exceptions(filter_regex=None) -> list`
  - `get_exception_frame(frame_index, exception_id=None) -> dict` — extended signature
  - `exec_in_exception_frame(frame_index, code, gui_thread=False, exception_id=None) -> dict` — extended signature

- [ ] **Step 1: Write failing tests**

Add to `acq4/mcp/tests/test_host.py`:

```python
import acq4.mcp.exception_capture as _ec


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
    result = host.get_exception_frame(0, exception_id=buffer_with_exception)
    assert "locals" in result
    assert result["function"] in ("inner", "_buffer_callback")


def test_get_exception_frame_aged_off_returns_error():
    _ec.start_buffer(size=1)
    from types import SimpleNamespace
    import pyqtgraph.exceptionHandling as _eh
    _eh.registerCallback = lambda cb: None
    _eh.unregisterCallback = lambda cb: None
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


def test_exec_in_exception_frame_with_exception_id(buffer_with_exception):
    result = host.exec_in_exception_frame(0, "1 + 1", exception_id=buffer_with_exception)
    assert result.get("result") == "2"


def test_exec_in_exception_frame_exception_id_none_still_works():
    """Original one-shot path must be unaffected."""
    host.reset_namespace()
    _ec._captured_exc = None
    result = host.exec_in_exception_frame(0, "1+1")
    assert "error" in result  # no captured exc
```

- [ ] **Step 2: Confirm tests fail**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host.py -v -k "buffer or exception_id or list_exception"
```
Expected: errors about missing `list_exceptions`, missing `exception_id` params.

- [ ] **Step 3: Implement list_exceptions in host.py**

Add after `exec_in_exception_frame` (at end of file):

```python
def list_exceptions(filter_regex=None):
    """Return one-line summaries of buffered exceptions, optionally filtered by regex.

    filter_regex is applied to "exception_type:message:file:function".
    Returns [] when the buffer is not active (ACQ4 not started with --exception-buffer).
    """
    import re as _re
    from acq4.mcp import exception_capture
    entries = exception_capture.list_buffer()
    if not filter_regex:
        return entries
    pat = _re.compile(filter_regex)
    return [
        e for e in entries
        if pat.search(f"{e['exception_type']}:{e['message']}:{e['file']}:{e['function']}")
    ]
```

- [ ] **Step 4: Extend get_exception_frame with exception_id**

Replace the existing `get_exception_frame` function body:

```python
def get_exception_frame(frame_index, exception_id=None):
    """Return locals for the given frame of a captured exception.

    exception_id=None uses the one-shot _captured_exc (existing behaviour).
    exception_id=N uses the ring-buffer exception with that ID; returns an error
    dict if the exception has aged off the buffer.

    Returns a dict with frame_index, file, line, function, and locals (name->repr).
    Returns {"error": "no exception captured"} if no exception is available.
    """
    from acq4.mcp import exception_capture
    if exception_id is not None:
        try:
            return exception_capture.get_buffer_frame_locals(exception_id, frame_index)
        except RuntimeError as exc:
            return {"error": str(exc)}
    result = exception_capture.get_frame_locals(frame_index)
    if result is None:
        return {"error": "no exception captured"}
    return result
```

- [ ] **Step 5: Extend exec_in_exception_frame with exception_id**

Replace the existing `exec_in_exception_frame` function body:

```python
def exec_in_exception_frame(frame_index, code, gui_thread=False, exception_id=None):
    """Execute code in the namespace of a captured exception's frame.

    CPython does not write exec results back into the live frame's locals —
    use this for inspection (print(x), type(obj)) not mutation.

    exception_id=None uses the one-shot _captured_exc (existing behaviour).
    exception_id=N uses the ring-buffer exception with that ID.

    Returns the same dict shape as execute(): stdout, stderr, result, traceback.
    Returns {"error": "..."} if no exception is available or the ID has aged off.
    """
    from acq4.mcp import exception_capture
    if exception_id is not None:
        try:
            ns = exception_capture.exec_in_buffer_frame(exception_id, frame_index, code)
        except RuntimeError as exc:
            return {"error": str(exc)}
    else:
        try:
            ns = exception_capture.exec_in_frame(frame_index, code)
        except RuntimeError as exc:
            return {"error": str(exc)}

    def run():
        return _exec_and_capture(code, ns)

    if gui_thread:
        from acq4.util import task
        return task.run_in_gui_thread(run)
    return run()
```

- [ ] **Step 6: Confirm tests pass**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_host.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add acq4/mcp/host.py acq4/mcp/tests/test_host.py
git commit --author="Martin Chase <outofculture@gmail.com>" -m "feat: add list_exceptions and exception_id support to host methods

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

## Task 4: connection.py additions and extensions

**Files:**
- Modify: `acq4/mcp/connection.py`
- Test: `acq4/mcp/tests/test_connection.py`

**Interfaces:**
- Consumes from Task 3: `host.list_exceptions(filter_regex)`, `host.get_exception_frame(frame_index, exception_id)`, `host.exec_in_exception_frame(frame_index, code, gui_thread, exception_id)`
- Produces:
  - `ConnectionManager.list_exceptions(filter_regex=None, port=None, host=None)`
  - `ConnectionManager.get_exception_frame(frame_index, exception_id=None, port=None, host=None)` — extended
  - `ConnectionManager.exec_in_exception_frame(frame_index, code, gui_thread=False, timeout=30.0, exception_id=None, port=None, host=None)` — extended

- [ ] **Step 1: Write failing tests**

Add to `acq4/mcp/tests/test_connection.py`. Read that file first for the `_FakeHostModule` pattern — it's a class with `__call__` that returns canned values, and it records kwargs so tests can assert on them.

Add these tests (check how `_FakeHostModule` is currently structured — these tests follow the same pattern):

```python
def test_list_exceptions_calls_host():
    mgr = ConnectionManager(host_module_provider=lambda h, p: _fake_host({"list_exceptions": []}), serialize=False)
    mgr._active = ("127.0.0.1", 9999)
    result = mgr.list_exceptions(filter_regex="KeyError")
    # Verify it called through (result is the canned [])
    assert result == []


def test_list_exceptions_raises_not_connected():
    mgr = ConnectionManager(serialize=False)
    with pytest.raises(NotConnectedError):
        mgr.list_exceptions()


def test_get_exception_frame_passes_exception_id():
    calls = {}
    def fake_provider(h, p):
        mod = mock.MagicMock()
        def get_frame(*args, **kwargs):
            calls["kwargs"] = kwargs
            return {"frame_index": 0, "locals": {}}
        mod.get_exception_frame.side_effect = get_frame
        return mod
    mgr = ConnectionManager(host_module_provider=fake_provider, serialize=False)
    mgr._active = ("127.0.0.1", 9999)
    mgr.get_exception_frame(frame_index=0, exception_id=42)
    assert calls["kwargs"].get("exception_id") == 42 or 42 in calls["kwargs"].values()


def test_exec_in_exception_frame_passes_exception_id():
    calls = {}
    def fake_provider(h, p):
        mod = mock.MagicMock()
        def exec_frame(*args, **kwargs):
            calls["kwargs"] = kwargs
            return {"stdout": "", "stderr": "", "result": "2", "traceback": None}
        mod.exec_in_exception_frame.side_effect = exec_frame
        return mod
    mgr = ConnectionManager(host_module_provider=fake_provider, serialize=False)
    mgr._active = ("127.0.0.1", 9999)
    mgr.exec_in_exception_frame(frame_index=0, code="1+1", exception_id=7)
    assert calls["kwargs"].get("exception_id") == 7 or 7 in calls["kwargs"].values()
```

- [ ] **Step 2: Confirm tests fail**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_connection.py -v -k "list_exceptions or exception_id"
```
Expected: `AttributeError` — `ConnectionManager` has no `list_exceptions`.

- [ ] **Step 3: Add list_exceptions pair to connection.py**

Append to `ConnectionManager` (after `exec_in_exception_frame` pair, before end of class):

```python
def list_exceptions(self, filter_regex=None, port=None, host=None):
    """Return one-line summaries of buffered exceptions, filtered by optional regex."""
    return self._run(self._list_exceptions, filter_regex, port, host)

def _list_exceptions(self, filter_regex, port, host):
    host, port = self._resolve(host, port)
    return self._host_module(host, port).list_exceptions(
        filter_regex, _return_type="value"
    )
```

- [ ] **Step 4: Extend get_exception_frame pair with exception_id**

Replace the existing `get_exception_frame` and `_get_exception_frame` methods:

```python
def get_exception_frame(self, frame_index, exception_id=None, port=None, host=None):
    """Return locals for the given frame of a captured exception."""
    return self._run(self._get_exception_frame, frame_index, exception_id, port, host)

def _get_exception_frame(self, frame_index, exception_id, port, host):
    host, port = self._resolve(host, port)
    return self._host_module(host, port).get_exception_frame(
        frame_index, exception_id, _return_type="value"
    )
```

- [ ] **Step 5: Extend exec_in_exception_frame pair with exception_id**

Replace the existing `exec_in_exception_frame` and `_exec_in_exception_frame` methods:

```python
def exec_in_exception_frame(self, frame_index, code, gui_thread=False, timeout=30.0, exception_id=None, port=None, host=None):
    """Execute code in the namespace of a captured exception's frame."""
    return self._run(self._exec_in_exception_frame, frame_index, code, gui_thread, timeout, exception_id, port, host)

def _exec_in_exception_frame(self, frame_index, code, gui_thread, timeout, exception_id, port, host):
    host, port = self._resolve(host, port)
    return self._host_module(host, port).exec_in_exception_frame(
        frame_index, code, gui_thread, exception_id, _return_type="value", _timeout=timeout
    )
```

- [ ] **Step 6: Confirm tests pass**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_connection.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add acq4/mcp/connection.py acq4/mcp/tests/test_connection.py
git commit --author="Martin Chase <outofculture@gmail.com>" -m "feat: add list_exceptions wrapper and exception_id to ConnectionManager

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

## Task 5: server.py additions and extensions

**Files:**
- Modify: `acq4/mcp/server.py`
- Test: `acq4/mcp/tests/test_server.py`

**Interfaces:**
- Consumes from Task 4: `ConnectionManager.list_exceptions`, extended `get_exception_frame`, extended `exec_in_exception_frame`
- Produces: `list_exceptions` MCP tool; `get_exception_frame` and `exec_in_exception_frame` tools extended with `exception_id`

- [ ] **Step 1: Write failing tests**

Add to `acq4/mcp/tests/test_server.py`:

```python
def test_list_exceptions_empty_serializes():
    import json
    result = json.dumps([], indent=2)
    assert result == "[]"


def test_aged_off_error_serializes():
    import json
    result = json.dumps(
        {"error": "exception 37 is no longer in buffer (oldest held: 40)"},
        indent=2,
    )
    assert '"exception 37' in result
```

- [ ] **Step 2: Confirm tests pass immediately** (these are pure data tests)

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_server.py -v
```
Expected: all pass (these tests don't exercise the server tools themselves).

- [ ] **Step 3: Add list_exceptions tool to server.py**

Add inside `build_server()`, after the `exec_in_exception_frame` tool and before `return server`:

```python
@server.tool()
def list_exceptions(
    filter: Optional[str] = None,
    port: Optional[int] = None,
    host: Optional[str] = None,
) -> str:
    """List buffered exceptions (most-recent first), optionally filtered by regex.

    ACQ4 must have been started with --exception-buffer N. Returns a JSON array
    of one-line summaries; each entry includes exception_id — pass that to
    get_exception_frame or exec_in_exception_frame to inspect a specific exception.

    filter is a regex applied to "exception_type:message:file:function".
    Returns [] if the buffer is not active.
    """
    try:
        result = _get_connection().list_exceptions(filter_regex=filter, port=port, host=host)
    except NotConnectedError as exc:
        return f"Not connected: {exc}"
    return json.dumps(result, indent=2, default=str)
```

- [ ] **Step 4: Extend get_exception_frame tool with exception_id**

Replace the existing `get_exception_frame` tool inside `build_server()`:

```python
@server.tool()
def get_exception_frame(
    frame_index: int,
    exception_id: Optional[int] = None,
    port: Optional[int] = None,
    host: Optional[str] = None,
) -> str:
    """Return local variables for one frame of a captured exception.

    exception_id: use an ID from list_exceptions to address a ring-buffer exception.
    Omit (or pass None) to address the most recent one-shot arm_exception_capture result.

    frame_index corresponds to the "index" field in the frames list returned by
    arm_exception_capture (0 = outermost/call-site, last = raise site).

    Returns a dict with file, line, function, and locals (name -> repr string).
    Returns an error string if no exception is available or the ID has aged off.
    """
    try:
        result = _get_connection().get_exception_frame(
            frame_index=frame_index,
            exception_id=exception_id,
            port=port,
            host=host,
        )
    except NotConnectedError as exc:
        return f"Not connected: {exc}"
    return json.dumps(result, indent=2, default=str)
```

- [ ] **Step 5: Extend exec_in_exception_frame tool with exception_id**

Replace the existing `exec_in_exception_frame` tool inside `build_server()`:

```python
@server.tool()
def exec_in_exception_frame(
    frame_index: int,
    code: str,
    gui_thread: bool = False,
    timeout: float = 30.0,
    exception_id: Optional[int] = None,
    port: Optional[int] = None,
    host: Optional[str] = None,
) -> str:
    """Execute code in the namespace of a captured exception's frame.

    exception_id: use an ID from list_exceptions to address a ring-buffer exception.
    Omit (or pass None) to address the most recent one-shot arm_exception_capture result.

    Runs code with the captured frame's locals merged over its globals as the
    execution namespace. Returns stdout, stderr, result (repr of trailing expression),
    and traceback — same format as execute_code.

    CPython does not write exec results back into the live frame's locals — use this
    for inspection (print(x), type(obj)) not mutation.

    gui_thread follows identical semantics to execute_code.
    """
    try:
        result = _get_connection().exec_in_exception_frame(
            frame_index=frame_index,
            code=code,
            gui_thread=gui_thread,
            timeout=timeout,
            exception_id=exception_id,
            port=port,
            host=host,
        )
    except NotConnectedError as exc:
        return f"Not connected: {exc}"
    if isinstance(result, dict) and "error" in result:
        return result["error"]
    return _format_execute(result)
```

- [ ] **Step 6: Run full test suite**

```
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/ -v
```
Expected: all tests pass (81 pre-existing + new buffer tests).

- [ ] **Step 7: Commit**

```bash
git add acq4/mcp/server.py acq4/mcp/tests/test_server.py
git commit --author="Martin Chase <outofculture@gmail.com>" -m "feat: add list_exceptions tool and exception_id to MCP server tools

🤖 Generated with [Claude Code](https://claude.ai/code)"
```
