# Debug This With Claude — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Debug with Claude" action to ACQ4's error dialog and log window that launches Claude Code primed with the failing record, the rig's identity, and a live connection back into the running process.

**Architecture:** A pure, Qt-free `build_debug_context(record)` renders a markdown brief; `invokeClaude()` writes it to a temp file and spawns a terminal running `claude`, using a config-overridable per-platform command template modelled on `acq4/util/codeEditor.py`. Live inspection works by starting a teleprox `RPCServer` on demand behind a one-time confirmation. Design spec: `docs/superpowers/specs/2026-08-05-claude-debug-handoff-design.md`.

**Tech Stack:** Python 3.9+, PyQt5, pytest, pytest-qt, teleprox, pyqtgraph.

## Global Constraints

- Python interpreter for all commands: `/home/martin/.miniforge3/envs/acq4-gl/bin/python`
- Run tests as `python -m pytest` from the repo root so the root `conftest.py` loads — it pins `PYTEST_QT_API=pyqt5` and `PYQTGRAPH_QT_LIB=PyQt5`. Never invoke a bare `pytest` binary.
- Qt is imported as `from acq4.util import Qt`, never `PyQt5` directly, in new acq4 code.
- Tests live in `acq4/util/tests/` and `acq4/mcp/tests/`, alongside the code they cover.
- Match surrounding style per file: `LogWindow.py` and `codeEditor.py` use `camelCase` for functions and attributes; `acq4/mcp/*` uses `snake_case`. Follow the file you are editing.
- Every file starts with a brief comment or docstring saying what it does.
- No mock hardware and no mock rigs. Where a test needs a `LogRecord`, build a real one with `logging.LogRecord(...)`. Where it needs a subprocess, use a real stub script.
- Never bind a real port in a test. `RPCServer` is always patched.
- Commit after each task with `--author="Martin Chase (claude) <outofculture@gmail.com>"`, conventional-commit subject, and the footer used by this repo:

```
🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>
```

## File Structure

| File | Responsibility |
|---|---|
| `acq4/mcp/__init__.py` (modify) | Teleprox lifecycle: record, discover, and on-demand start of the RPC server. Owns the confirmation and the WARNING. |
| `acq4/__main__.py` (modify) | Registers a `--teleprox`-started server with the accessor; documents on-demand start in argparse help. |
| `acq4/util/claude_debug.py` (create) | Context rendering, command resolution, and launch. No Qt imports. |
| `acq4/util/LogWindow.py` (modify) | The two entry points: `ErrorDialog` button, `DocumentedLogViewer` context menu. |
| `acq4/mcp/tests/test_teleprox_lifecycle.py` (create) | Task 1 coverage. |
| `acq4/util/tests/test_claude_debug.py` (create) | Tasks 2–4 coverage: context, command, launch. |
| `acq4/util/tests/test_logwindow_claude_action.py` (create) | Tasks 5–6 coverage: Qt entry points. |

`claude_debug.py` deliberately imports no Qt so the Phase 2 inline panel can reuse
`build_debug_context` unchanged, and so Tasks 2–4 test without a QApplication.

---

### Task 1: Teleprox lifecycle

**Files:**
- Modify: `acq4/mcp/__init__.py`
- Modify: `acq4/__main__.py` (the `if args.teleprox is not None:` block, and the `--teleprox` argparse help at line 22)
- Test: `acq4/mcp/tests/test_teleprox_lifecycle.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces, all in `acq4.mcp`:
  - `set_teleprox_address(addr: str | bytes) -> None`
  - `get_teleprox_address() -> str | None` — always `str`, decoded
  - `ensure_teleprox_server(confirm: Callable[[], bool] | None = None) -> str | None`
  - `_reset_teleprox_state_for_test() -> None` — clears module state between tests

`RPCServer.address` is `bytes`; both setter and starter decode before storing, so callers
only ever see `str`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/mcp/tests/test_teleprox_lifecycle.py`:

```python
"""Tests for acq4.mcp's teleprox server discovery and on-demand start.
No real port is ever bound; RPCServer is patched throughout.
"""

import logging
from unittest import mock

import pytest

from acq4 import mcp


@pytest.fixture(autouse=True)
def clean_state():
    mcp._reset_teleprox_state_for_test()
    yield
    mcp._reset_teleprox_state_for_test()


def test_no_server_means_no_address():
    assert mcp.get_teleprox_address() is None


def test_set_address_decodes_bytes():
    mcp.set_teleprox_address(b"tcp://127.0.0.1:5555")
    assert mcp.get_teleprox_address() == "tcp://127.0.0.1:5555"


def test_ensure_returns_existing_without_starting_or_asking():
    mcp.set_teleprox_address("tcp://127.0.0.1:5555")
    confirm = mock.Mock(return_value=True)
    with mock.patch("teleprox.RPCServer") as server:
        assert mcp.ensure_teleprox_server(confirm=confirm) == "tcp://127.0.0.1:5555"
    server.assert_not_called()
    confirm.assert_not_called()


def test_ensure_starts_server_when_confirmed():
    with mock.patch("teleprox.RPCServer") as server:
        server.return_value.address = b"tcp://127.0.0.1:6666"
        addr = mcp.ensure_teleprox_server(confirm=lambda: True)
    assert addr == "tcp://127.0.0.1:6666"
    server.assert_called_once_with("tcp://127.0.0.1:*")
    assert mcp.get_teleprox_address() == "tcp://127.0.0.1:6666"


def test_ensure_is_idempotent():
    with mock.patch("teleprox.RPCServer") as server:
        server.return_value.address = b"tcp://127.0.0.1:6666"
        first = mcp.ensure_teleprox_server(confirm=lambda: True)
        second = mcp.ensure_teleprox_server(confirm=lambda: True)
    assert first == second
    assert server.call_count == 1


def test_decline_starts_nothing_and_does_not_reask():
    confirm = mock.Mock(return_value=False)
    with mock.patch("teleprox.RPCServer") as server:
        assert mcp.ensure_teleprox_server(confirm=confirm) is None
        assert mcp.ensure_teleprox_server(confirm=confirm) is None
    server.assert_not_called()
    confirm.assert_called_once()


def test_start_is_logged_at_warning_with_address(caplog):
    with caplog.at_level(logging.WARNING, logger="acq4"):
        with mock.patch("teleprox.RPCServer") as server:
            server.return_value.address = b"tcp://127.0.0.1:6666"
            mcp.ensure_teleprox_server(confirm=lambda: True)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("tcp://127.0.0.1:6666" in r.getMessage() for r in warnings)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_teleprox_lifecycle.py -v
```

Expected: every test fails with `AttributeError: module 'acq4.mcp' has no attribute '_reset_teleprox_state_for_test'`.

- [ ] **Step 3: Implement the accessors**

Append to `acq4/mcp/__init__.py`, keeping its existing module docstring and adding to it:

```python
import logging

logger = logging.getLogger("acq4")

# Teleprox lifecycle. A teleprox RPC server is what lets an MCP client reach into
# this process. It may be started at launch by `--teleprox`, or on demand by a
# feature that needs it (see acq4/util/claude_debug.py).
#
# CONTRACT: starting this server opens a loopback port that permits arbitrary code
# execution inside ACQ4 for the remainder of the session. teleprox's own docs state
# plainly that RPCServer is not a secure server. On-demand starts therefore go
# through a confirmation and are logged at WARNING.
_teleprox_server = None      # server this module started, if any
_teleprox_address = None     # address of whichever server is serving; str or None
_teleprox_declined = False   # operator said no; do not ask again this session


def set_teleprox_address(addr):
    """Record the address of a server started elsewhere (e.g. by ``--teleprox``)."""
    global _teleprox_address
    _teleprox_address = addr.decode() if isinstance(addr, bytes) else addr


def get_teleprox_address():
    """Return the address of the running teleprox server, or None if there is none."""
    return _teleprox_address


def ensure_teleprox_server(confirm=None):
    """Return a teleprox address, starting a server if none is running.

    Idempotent. Returns None if no server is running and *confirm* declines; the
    refusal is remembered for the session so the operator is asked only once.

    confirm : callable returning bool, or None
        Asked before opening a port. None means do not start one.
    """
    global _teleprox_server, _teleprox_declined
    if _teleprox_address is not None:
        return _teleprox_address
    if _teleprox_declined or confirm is None:
        return None
    if not confirm():
        _teleprox_declined = True
        return None

    import teleprox

    _teleprox_server = teleprox.RPCServer("tcp://127.0.0.1:*")
    set_teleprox_address(_teleprox_server.address)
    logger.warning(
        "Started teleprox server on %s for AI-assisted debugging. This port allows "
        "code execution in this ACQ4 process until it exits.",
        _teleprox_address,
    )
    return _teleprox_address


def _reset_teleprox_state_for_test():
    """Clear module-level teleprox state. For tests only."""
    global _teleprox_server, _teleprox_address, _teleprox_declined
    _teleprox_server = None
    _teleprox_address = None
    _teleprox_declined = False
```

`RPCServer.__init__` defaults to `run_thread=True`, so it starts its own daemon thread
and needs no `run_forever()` call — which is why `__main__.py` never calls one either.

Note the test patches `teleprox.RPCServer`, so the import must stay inside the function.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp/tests/test_teleprox_lifecycle.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Register the startup server and document the contract**

In `acq4/__main__.py`, extend the existing block:

```python
if args.teleprox is not None:
    from teleprox import RPCServer
    if args.teleprox == 0:
        addr = 'tcp://127.0.0.1:*'
    else:
        addr = f'tcp://127.0.0.1:{args.teleprox}'
    teleprox_debug_server = RPCServer(addr)
    print(f"Teleprox server listening on {teleprox_debug_server.address}")
    from acq4 import mcp as _mcp
    _mcp.set_teleprox_address(teleprox_debug_server.address)
```

And amend the `--teleprox` help string at line 22 to end with:

```
"A server may also be started on demand (with confirmation) by AI-assisted debugging."
```

- [ ] **Step 6: Verify nothing else broke**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/mcp -v
```

Expected: all pass, including the pre-existing MCP tests.

- [ ] **Step 7: Commit**

```bash
git add acq4/mcp/__init__.py acq4/mcp/tests/test_teleprox_lifecycle.py acq4/__main__.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: discover or start teleprox on demand

Adds set/get/ensure accessors for the teleprox address so features needing
live process access can find an existing server or open one, rather than
requiring --teleprox to have been passed before the failure.

On-demand starts require confirmation and are logged at WARNING, since the
port permits code execution in the ACQ4 process for the rest of the session.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>
EOF
)"
```

### Task 2: Context builder

**Files:**
- Create: `acq4/util/claude_debug.py`
- Test: `acq4/util/tests/test_claude_debug.py`

**Interfaces:**
- Consumes: nothing at runtime. The *caller* resolves the address via
  `acq4.mcp.ensure_teleprox_server()` from Task 1 and passes it in; this keeps the
  builder pure and testable without patching.
- Produces:
  - `build_debug_context(record, log_tail=None, teleprox_address=None) -> str`
  - `TASK_ERROR`, `TASK_WARNING`, `TASK_INFO` — module-level template strings, so tests
    assert against the constant rather than a copied sentence.

`record` is a `logging.LogRecord`. `log_tail` is a list of `LogRecord` or None.

- [ ] **Step 1: Write the failing tests**

Create `acq4/util/tests/test_claude_debug.py`:

```python
"""Tests for the Claude debugging handoff: context rendering, command resolution, launch."""

import logging

import pytest

from acq4.util import claude_debug


def make_record(level=logging.ERROR, msg="something went wrong", exc_info=None):
    return logging.LogRecord(
        name="acq4.devices.Pipette", level=level, pathname="/fake/pipette.py",
        lineno=42, msg=msg, args=(), exc_info=exc_info,
    )


def real_exc_info():
    """A genuine exc_info triple, so the traceback rendered is a real one."""
    try:
        raise ValueError("pipette pressure out of range")
    except ValueError:
        import sys
        return sys.exc_info()


def test_error_record_gets_error_task():
    out = claude_debug.build_debug_context(make_record(logging.ERROR))
    assert claude_debug.TASK_ERROR in out
    assert claude_debug.TASK_WARNING not in out
    assert claude_debug.TASK_INFO not in out


def test_warning_record_gets_warning_task():
    out = claude_debug.build_debug_context(make_record(logging.WARNING))
    assert claude_debug.TASK_WARNING in out
    assert claude_debug.TASK_ERROR not in out


def test_info_record_gets_info_task():
    out = claude_debug.build_debug_context(make_record(logging.INFO))
    assert claude_debug.TASK_INFO in out
    assert claude_debug.TASK_ERROR not in out


def test_exception_on_info_record_still_gets_error_task():
    """exc_info wins over level: a traceback is a breakage regardless of level."""
    out = claude_debug.build_debug_context(
        make_record(logging.INFO, exc_info=real_exc_info())
    )
    assert claude_debug.TASK_ERROR in out


def test_traceback_section_present_only_with_exc_info():
    with_exc = claude_debug.build_debug_context(make_record(exc_info=real_exc_info()))
    assert "## Traceback" in with_exc
    assert "pipette pressure out of range" in with_exc

    without = claude_debug.build_debug_context(make_record())
    assert "## Traceback" not in without


def test_connect_instruction_present_with_address():
    out = claude_debug.build_debug_context(
        make_record(), teleprox_address="tcp://127.0.0.1:6666"
    )
    assert "connect_acq4(port=6666)" in out


def test_unavailable_sentence_present_without_address():
    out = claude_debug.build_debug_context(make_record(), teleprox_address=None)
    assert "connect_acq4" not in out
    assert "Live inspection is not available" in out


def test_thread_caveat_present_when_connectable():
    out = claude_debug.build_debug_context(
        make_record(), teleprox_address="tcp://127.0.0.1:6666"
    )
    assert "teleprox thread" in out


def test_list_exceptions_hint_only_when_connectable_and_traceback():
    both = claude_debug.build_debug_context(
        make_record(exc_info=real_exc_info()), teleprox_address="tcp://127.0.0.1:6666"
    )
    assert "list_exceptions" in both

    no_conn = claude_debug.build_debug_context(make_record(exc_info=real_exc_info()))
    assert "list_exceptions" not in no_conn

    no_tb = claude_debug.build_debug_context(
        make_record(), teleprox_address="tcp://127.0.0.1:6666"
    )
    assert "list_exceptions" not in no_tb


def test_log_tail_section_present_only_when_supplied():
    tail = [make_record(logging.INFO, msg="approaching cell")]
    with_tail = claude_debug.build_debug_context(make_record(), log_tail=tail)
    assert "## Recent log" in with_tail
    assert "approaching cell" in with_tail

    assert "## Recent log" not in claude_debug.build_debug_context(make_record())


def test_throughline_rendered_when_present():
    record = make_record()
    record.throughline = ["patch cell 3", "seal"]
    out = claude_debug.build_debug_context(record)
    assert "patch cell 3 > seal" in out


def test_no_empty_section_headers():
    """Every '## Heading' must be followed by content, not another heading."""
    out = claude_debug.build_debug_context(make_record())
    lines = [ln for ln in out.splitlines() if ln.strip()]
    for i, line in enumerate(lines[:-1]):
        if line.startswith("## "):
            assert not lines[i + 1].startswith("#"), f"empty section: {line}"


def test_message_and_level_always_present():
    out = claude_debug.build_debug_context(make_record(msg="headstage stalled"))
    assert "headstage stalled" in out
    assert "ERROR" in out
    assert "acq4.devices.Pipette" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_claude_debug.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'acq4.util.claude_debug'`.

- [ ] **Step 3: Implement the builder**

Create `acq4/util/claude_debug.py`:

```python
"""Hand off an ACQ4 log record or exception to Claude Code for debugging.
Renders a markdown brief about the record and the rig, then launches Claude primed with it.
"""

import logging
import os
import socket
import subprocess
import sys
import tempfile
import traceback

logger = logging.getLogger(__name__)

TASK_ERROR = (
    "Why did this break? Work out the failure mechanism from the traceback and "
    "the code, then confirm it against live state if inspection is available."
)
TASK_WARNING = (
    "This looks suspicious. What is going on here -- is it benign, or the first "
    "sign of a real problem?"
)
TASK_INFO = (
    "Explain what this message means in the context of this rig, and offer "
    "possible next steps."
)

GUIDANCE = (
    "Prefer inspection tools (get_log, list_devices, manager_state, health_series, "
    "get_exception_frame) to build understanding first. This is a live scientific "
    "instrument: ask me before running anything that could change device state."
)


def _taskFor(record):
    if record.exc_info or record.levelno >= logging.ERROR:
        return TASK_ERROR
    if record.levelno >= logging.WARNING:
        return TASK_WARNING
    return TASK_INFO


def _rigIdentity():
    """Describe this rig. Degrades to whatever is available; never raises."""
    lines = [f"- Hostname: {socket.gethostname()}"]
    try:
        import acq4
        lines.append(f"- ACQ4 version: {acq4.__version__}")
    except Exception:
        pass
    try:
        from acq4 import getManager
        lines.append(f"- Data directory: {getManager().getBaseDir().name()}")
    except Exception:
        pass  # no Manager running (e.g. under test)
    return lines


def _formatRecord(record):
    lines = [
        f"- Level: {record.levelname}",
        f"- Logger: {record.name}",
        f"- Time: {logging.Formatter().formatTime(record)}",
        f"- Source: {record.pathname}:{record.lineno}",
    ]
    throughline = getattr(record, "throughline", None)
    if throughline:
        lines.append(f"- Throughline: {' > '.join(str(n) for n in throughline)}")
    lines.append("")
    lines.append(f"```\n{record.getMessage()}\n```")
    return lines


def build_debug_context(record, log_tail=None, teleprox_address=None):
    """Render a markdown debugging brief for *record*.

    Pure: no Qt, no subprocess, no global state. The Phase 2 inline panel reuses this.

    record : logging.LogRecord
    log_tail : list of LogRecord, or None
        Records preceding *record*, for context. Section omitted when None or empty.
    teleprox_address : str or None
        Address of a running teleprox server, from acq4.mcp.ensure_teleprox_server().
        None means live inspection is unavailable and the brief says so.
    """
    out = ["# ACQ4 debugging brief", ""]

    out += ["## Rig", ""] + _rigIdentity() + [""]

    out += ["## Live inspection", ""]
    if teleprox_address:
        port = teleprox_address.rsplit(":", 1)[-1]
        out += [
            f"This ACQ4 is running and reachable. Start with `connect_acq4(port={port})`, "
            "then use the acq4 MCP tools to inspect it.",
            "",
            "Note: MCP calls execute on the teleprox thread, not the Qt GUI thread. "
            "Do not touch Qt objects; inspect devices, state, and data instead.",
            "",
        ]
    else:
        out += [
            "Live inspection is not available for this session, so work from the "
            "information below rather than trying to connect.",
            "",
        ]

    out += ["## Log record", ""] + _formatRecord(record) + [""]

    if record.exc_info:
        formatted = "".join(traceback.format_exception(*record.exc_info))
        out += ["## Traceback", "", f"```python\n{formatted.rstrip()}\n```", ""]

    if record.exc_info and teleprox_address:
        out += [
            "## Live frame inspection",
            "",
            "Call `list_exceptions` and look for the entry matching the traceback above. "
            "If you find it, `get_exception_frame` gives you that frame's locals and "
            "`exec_in_exception_frame` lets you evaluate against them.",
            "",
            "The exception ring buffer is opt-in, so an empty list just means ACQ4 was "
            "started without `--exception-buffer N`. That is expected; carry on from the "
            "traceback text.",
            "",
        ]

    if log_tail:
        rendered = "\n".join(
            f"{r.levelname:8} {r.name} | {r.getMessage()}" for r in log_tail
        )
        out += ["## Recent log", "", f"```\n{rendered}\n```", ""]

    out += ["## Your task", "", _taskFor(record), "", GUIDANCE, ""]

    return "\n".join(out)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_claude_debug.py -v
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add acq4/util/claude_debug.py acq4/util/tests/test_claude_debug.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: render a Claude debugging brief from a log record

build_debug_context turns a LogRecord into a markdown brief describing the
rig, the record, its traceback, and how to reach the live process. Pure and
Qt-free so a later in-ACQ4 panel can reuse it unchanged.

The task text is keyed off level and exc_info: errors ask why it broke,
warnings ask whether it is benign, everything else asks for an explanation.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>
EOF
)"
```

### Task 3: Command resolution

**Files:**
- Modify: `acq4/util/claude_debug.py`
- Test: `acq4/util/tests/test_claude_debug.py` (append)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `claudeCommand() -> str` — a format string containing `{contextFile}`
  - `suggestTerminal() -> str` — platform default; raises `Exception` if none found
  - `terminalCommands: dict[str, list[tuple[str, str]]]` — platform → ordered
    (executable, template) pairs, first available wins

Mirrors `codeEditorCommand` / `suggestCodeEditor` / `editorCommands` in
`acq4/util/codeEditor.py`, including the single-substitution format-string contract.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/util/tests/test_claude_debug.py`:

```python
from unittest import mock


def test_config_command_returned_verbatim():
    custom = 'myterm -e claude "Read {contextFile}"'
    with mock.patch.object(claude_debug, "_configuredCommand", return_value=custom):
        assert claude_debug.claudeCommand() == custom


def test_falls_back_to_platform_default_when_unconfigured():
    with mock.patch.object(claude_debug, "_configuredCommand", return_value=None):
        with mock.patch.object(claude_debug, "suggestTerminal", return_value="stub"):
            assert claude_debug.claudeCommand() == "stub"


def test_suggest_terminal_picks_first_available():
    with mock.patch.object(claude_debug.sys, "platform", "linux"):
        # kitty missing, gnome-terminal present -> gnome-terminal wins over later entries
        def which(name):
            return "/usr/bin/" + name if name == "gnome-terminal" else None
        with mock.patch("shutil.which", side_effect=which):
            cmd = claude_debug.suggestTerminal()
    assert cmd.startswith("gnome-terminal")
    assert "{contextFile}" in cmd


def test_suggest_terminal_raises_when_nothing_found():
    with mock.patch.object(claude_debug.sys, "platform", "linux"):
        with mock.patch("shutil.which", return_value=None):
            with pytest.raises(Exception, match="No terminal emulator"):
                claude_debug.suggestTerminal()


def test_suggest_terminal_raises_on_unsupported_platform():
    with mock.patch.object(claude_debug.sys, "platform", "sunos5"):
        with pytest.raises(Exception, match="not yet supported"):
            claude_debug.suggestTerminal()


def test_every_template_carries_the_substitution():
    for platform, entries in claude_debug.terminalCommands.items():
        for name, template in entries:
            assert "{contextFile}" in template, f"{platform}/{name} lacks {{contextFile}}"
            assert "claude" in template, f"{platform}/{name} does not invoke claude"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_claude_debug.py -k "command or terminal or template" -v
```

Expected: `AttributeError: module 'acq4.util.claude_debug' has no attribute '_configuredCommand'`.

- [ ] **Step 3: Implement command resolution**

Add to `acq4/util/claude_debug.py` (it already imports `os`, `sys`, `subprocess`,
`tempfile`; add `import shutil`):

```python
# `claude` is a TUI, so it needs a terminal to live in. Each entry is
# (executable to look for, command template). First one present on the system wins.
# Every template must contain {contextFile}; see claudeCommand().
_POINTER = 'claude "Read {contextFile} and help me debug it"'

terminalCommands = {
    'linux': [
        ('wezterm', 'wezterm start -- ' + _POINTER),
        ('kitty', 'kitty ' + _POINTER),
        ('gnome-terminal', 'gnome-terminal -- ' + _POINTER),
        ('konsole', 'konsole -e ' + _POINTER),
        ('alacritty', 'alacritty -e ' + _POINTER),
        ('xterm', 'xterm -e ' + _POINTER),
    ],
    # UNVERIFIED: no Windows rig has run Claude Code from a command line yet.
    # Override with `misc: claudeCommand` if these are wrong.
    'win32': [
        ('wt', 'wt.exe new-tab --title "ACQ4 debug" ' + _POINTER),
        ('cmd', 'start "ACQ4 debug" cmd /k ' + _POINTER),
    ],
    # UNVERIFIED, and lower priority than Windows.
    'darwin': [
        ('osascript',
         """osascript -e 'tell application "Terminal" to do script """
         """"claude \\"Read {contextFile} and help me debug it\\""' """
         """-e 'tell application "Terminal" to activate'"""),
    ],
}


def _configuredCommand():
    """Return the operator's configured command, or None if unset or no Manager."""
    try:
        from acq4 import getManager
        return getManager().config.get('misc', {}).get('claudeCommand', None)
    except Exception:
        return None  # no Manager running (e.g. under test)


def suggestTerminal():
    """Return a command format string using the first terminal found on this system."""
    entries = terminalCommands.get(sys.platform)
    if entries is None:
        raise Exception(
            f"Launching Claude is not yet supported on this platform ({sys.platform}). "
            "Set `misc: claudeCommand` in the acq4 config to a command containing "
            "{contextFile}."
        )
    for name, template in entries:
        if shutil.which(name) is not None:
            return template
    raise Exception(
        "No terminal emulator found to run `claude` in (looked for: "
        + ", ".join(name for name, _ in entries)
        + "). Set `misc: claudeCommand` in the acq4 config to a command containing "
        "{contextFile}."
    )


def claudeCommand():
    """Return a format string that generates a command to launch Claude Code.

    The format string must contain a ``{contextFile}`` variable, which is replaced
    with the path to the debugging brief.

    By default this looks for a terminal emulator present on the system. The return
    value can also be set by the acq4 configuration::

        <default.cfg>:
            misc:
                claudeCommand: 'wezterm start -- claude "Read {contextFile}"'
    """
    return _configuredCommand() or suggestTerminal()
```

Note `'cmd'` is looked up with `shutil.which('cmd')`, which resolves `cmd.exe` on
Windows and nothing elsewhere — so the fallback is self-gating.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_claude_debug.py -v
```

Expected: 19 passed (13 from Task 2 plus 6 here).

- [ ] **Step 5: Commit**

```bash
git add acq4/util/claude_debug.py acq4/util/tests/test_claude_debug.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: resolve a terminal command for launching Claude

Follows the codeEditor.py pattern: a `misc: claudeCommand` config override,
falling back to the first terminal emulator found on the system. Windows and
macOS templates are marked unverified; the config override is the escape hatch.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>
EOF
)"
```

---

### Task 4: Launch

**Files:**
- Modify: `acq4/util/claude_debug.py`
- Test: `acq4/util/tests/test_claude_debug.py` (append)

**Interfaces:**
- Consumes: `claudeCommand()` from Task 3.
- Produces:
  - `invokeClaude(context, command=None) -> str` — returns the temp file path it wrote
  - `debugRecordWithClaude(record, log_tail=None, confirm=None) -> None` — the single
    call site both Qt entry points use in Tasks 5–6. Resolves the teleprox address via
    `acq4.mcp.ensure_teleprox_server(confirm=confirm)`, builds the context, launches.

This is the end-to-end tier: the stub-script test exercises context assembly, temp file
creation, command formatting, and process spawn — stopping exactly where the external
process begins. Driving a real `claude` TUI is not automatable and is verified by hand
(see Manual Verification at the end of this plan).

- [ ] **Step 1: Write the failing tests**

Append to `acq4/util/tests/test_claude_debug.py`:

```python
import sys as _sys
import textwrap


def test_invoke_writes_context_to_a_temp_file():
    with mock.patch("subprocess.Popen") as popen:
        path = claude_debug.invokeClaude("# brief\nbody", command="true {contextFile}")
    popen.assert_called_once()
    with open(path) as fh:
        assert fh.read() == "# brief\nbody"


def test_invoke_substitutes_the_context_path():
    with mock.patch("subprocess.Popen") as popen:
        path = claude_debug.invokeClaude("x", command="myterm claude {contextFile}")
    launched = popen.call_args[0][0]
    assert launched == f"myterm claude {path}"


def test_invoke_spawns_the_real_command(tmp_path):
    """End-to-end for the part ACQ4 owns: a real subprocess receives the real path."""
    stub = tmp_path / "stub.py"
    stub.write_text(textwrap.dedent("""
        import sys
        with open(sys.argv[2], "w") as out:
            out.write(sys.argv[1] + "\\n")
            out.write(open(sys.argv[1]).read())
    """))
    receipt = tmp_path / "receipt.txt"
    command = f'{_sys.executable} {stub} {{contextFile}} {receipt}'

    path = claude_debug.invokeClaude("# brief\nlive body", command=command)

    import subprocess as sp
    sp.run(command.format(contextFile=path), shell=True, check=True, timeout=30)
    written = receipt.read_text()
    assert path in written
    assert "live body" in written


def test_debug_record_passes_address_into_the_context():
    record = make_record(logging.ERROR)
    with mock.patch("acq4.mcp.ensure_teleprox_server", return_value="tcp://127.0.0.1:7777"):
        with mock.patch.object(claude_debug, "invokeClaude") as invoke:
            claude_debug.debugRecordWithClaude(record)
    context = invoke.call_args[0][0]
    assert "connect_acq4(port=7777)" in context


def test_debug_record_still_launches_when_teleprox_declined():
    record = make_record(logging.ERROR)
    with mock.patch("acq4.mcp.ensure_teleprox_server", return_value=None):
        with mock.patch.object(claude_debug, "invokeClaude") as invoke:
            claude_debug.debugRecordWithClaude(record)
    context = invoke.call_args[0][0]
    assert "Live inspection is not available" in context


def test_debug_record_forwards_the_confirm_callable():
    confirm = mock.Mock(return_value=True)
    with mock.patch("acq4.mcp.ensure_teleprox_server", return_value=None) as ensure:
        with mock.patch.object(claude_debug, "invokeClaude"):
            claude_debug.debugRecordWithClaude(make_record(), confirm=confirm)
    assert ensure.call_args.kwargs["confirm"] is confirm
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_claude_debug.py -k "invoke or debug_record" -v
```

Expected: `AttributeError: module 'acq4.util.claude_debug' has no attribute 'invokeClaude'`.

- [ ] **Step 3: Implement the launcher**

Add to `acq4/util/claude_debug.py`:

```python
def invokeClaude(context, command=None):
    """Write *context* to a temp markdown file and launch Claude Code on it.

    Returns the path written. The file is deliberately not deleted: the spawned
    process outlives this call and needs to read it, and keeping it lets the
    operator re-read or re-launch. Temp cleanup is the OS's job.
    """
    if command is None:
        command = claudeCommand()
    fd, path = tempfile.mkstemp(prefix="acq4-debug-", suffix=".md", text=True)
    with os.fdopen(fd, "w") as fh:
        fh.write(context)
    launched = command.format(contextFile=path)
    logger.info("Launching Claude for debugging: %s", launched)
    subprocess.Popen(launched, shell=True)
    return path


def debugRecordWithClaude(record, log_tail=None, confirm=None):
    """Hand *record* to a fresh Claude Code session.

    Starts a teleprox server if one is not already running and *confirm* agrees, so
    the session can inspect this live process. Without one, the brief is text-only.
    """
    from acq4 import mcp

    address = mcp.ensure_teleprox_server(confirm=confirm)
    context = build_debug_context(record, log_tail=log_tail, teleprox_address=address)
    invokeClaude(context)
```

`debugRecordWithClaude` imports `acq4.mcp` inside the function, matching how the tests
patch `acq4.mcp.ensure_teleprox_server` and keeping module import cheap.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_claude_debug.py -v
```

Expected: 25 passed.

- [ ] **Step 5: Commit**

```bash
git add acq4/util/claude_debug.py acq4/util/tests/test_claude_debug.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: launch Claude Code on a debugging brief

invokeClaude writes the brief to a temp markdown file and spawns the resolved
terminal command; debugRecordWithClaude wires it to teleprox discovery so the
session can inspect the live process when a server is available.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>
EOF
)"
```

### Task 5: Error dialog button

**Files:**
- Modify: `acq4/util/LogWindow.py` (`ErrorDialog`, lines 51–150)
- Test: `acq4/util/tests/test_logwindow_claude_action.py`

**Interfaces:**
- Consumes: `acq4.util.claude_debug.debugRecordWithClaude` from Task 4.
- Produces:
  - `confirmTeleproxServer(parent=None) -> bool` — module-level in `LogWindow.py`; the
    Qt confirmation passed as `confirm=` into `debugRecordWithClaude`. Lives here, not in
    `claude_debug.py`, which stays Qt-free.
  - `ErrorDialog.currentRecord` — the `LogRecord` on display
  - `ErrorDialog.records` — queued `LogRecord`s (replaces `ErrorDialog.messages`, which
    held pre-rendered HTML and so could not be handed to the context builder)

**Refactor note:** `show()` currently renders HTML immediately and queues *strings* in
`self.messages`. The button needs the record, so queueing moves to records and rendering
moves into the display path. `self.messages` is only read inside `ErrorDialog`, so this is
contained.

- [ ] **Step 1: Write the failing tests**

Create `acq4/util/tests/test_logwindow_claude_action.py`:

```python
"""Tests for the "Debug with Claude" entry points in the error dialog and log window."""

import logging
from unittest import mock

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def make_record(level=logging.ERROR, msg="boom"):
    return logging.LogRecord(
        name="acq4.devices.Pipette", level=level, pathname="/fake/p.py",
        lineno=7, msg=msg, args=(), exc_info=None,
    )


def test_dialog_has_a_claude_button(qapp, qtbot):
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    assert dlg.claudeBtn.text() == "Debug with Claude"


def test_dialog_button_sends_the_displayed_record(qapp, qtbot):
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    record = make_record(msg="headstage stalled")
    dlg.show(record)

    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    debug.assert_called_once()
    assert debug.call_args[0][0] is record


def test_dialog_button_follows_the_queue(qapp, qtbot):
    """Stepping to the next queued error re-points the button at that record."""
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    first, second = make_record(msg="first"), make_record(msg="second")
    dlg.show(first)
    dlg.show(second)  # dialog is visible, so this queues
    assert dlg.currentRecord is first

    dlg.nextMessage()
    assert dlg.currentRecord is second

    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    assert debug.call_args[0][0] is second


def test_dialog_button_forwards_the_confirmation(qapp, qtbot):
    from acq4.util import LogWindow

    dlg = LogWindow.ErrorDialog()
    qtbot.addWidget(dlg)
    dlg.show(make_record())

    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    assert debug.call_args.kwargs["confirm"] is not None


def test_button_does_nothing_without_a_record(qapp, qtbot):
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    debug.assert_not_called()


def test_confirmation_defaults_to_no(qapp, qtbot):
    """The teleprox confirmation must not be accept-by-default."""
    from acq4.util.LogWindow import confirmTeleproxServer

    with mock.patch.object(Qt.QMessageBox, "exec_", return_value=Qt.QMessageBox.No):
        assert confirmTeleproxServer() is False
    with mock.patch.object(Qt.QMessageBox, "exec_", return_value=Qt.QMessageBox.Yes):
        assert confirmTeleproxServer() is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_logwindow_claude_action.py -v
```

Expected: `AttributeError: 'ErrorDialog' object has no attribute 'claudeBtn'`, and an
`ImportError` for `confirmTeleproxServer`.

- [ ] **Step 3: Add the confirmation helper**

In `acq4/util/LogWindow.py`, after the existing `get_error_dialog()`:

```python
def confirmTeleproxServer(parent=None):
    """Ask permission to open a teleprox port so Claude can inspect this process.

    Starting a teleprox server permits arbitrary code execution in this ACQ4 for the
    rest of the session, so this is asked explicitly rather than assumed. Declining
    still produces a text-only handoff.
    """
    box = Qt.QMessageBox(parent)
    box.setIcon(Qt.QMessageBox.Warning)
    box.setWindowTitle("Allow live debugging access?")
    box.setText("Open a local debugging port so Claude can inspect this ACQ4?")
    box.setInformativeText(
        "This opens a loopback port that allows code to run inside this ACQ4 process "
        "until it exits, which is what lets Claude read device and task state directly.\n\n"
        "Decline and Claude still gets the log record and traceback, just not live access."
    )
    box.setStandardButtons(Qt.QMessageBox.Yes | Qt.QMessageBox.No)
    box.setDefaultButton(Qt.QMessageBox.No)
    return box.exec_() == Qt.QMessageBox.Yes
```

- [ ] **Step 4: Add the button and switch the queue to records**

In `ErrorDialog.__init__`, after the existing `self.logBtn` lines:

```python
        self.claudeBtn = Qt.QPushButton("Debug with Claude")
        self.btnLayout.addWidget(self.claudeBtn)
        self.claudeBtn.clicked.connect(self.claudeClicked)
```

Replace `self.messages = []` with:

```python
        self.records = []        # queued LogRecords not yet displayed
        self.currentRecord = None  # the record on display, for the Claude handoff
```

Replace `show()`, `nextMessage()`, and the two reset sites:

```python
    def show(self, entry: LogRecord):
        if self.disableCheck.isChecked():
            return False
        if self.isVisible():
            self.records.append(entry)
            self.nextBtn.show()
            self.nextBtn.setEnabled(True)
            self.nextBtn.setText("Show next error (%d more)" % len(self.records))
        else:
            w = Qt.QApplication.activeWindow()
            self.nextBtn.hide()
            self._displayRecord(entry)
            self.open()
            if w is not None:
                cp = w.geometry().center()
                self.setGeometry(
                    int(cp.x() - self.width() / 2.0),
                    int(cp.y() - self.height() / 2.0),
                    self.width(),
                    self.height(),
                )
        self.raise_()

    def _displayRecord(self, entry: LogRecord):
        """Show *entry* and remember it, so the Claude button has something to send."""
        self.currentRecord = entry
        self.msgLabel.setText(self._renderRecord(entry))

    def _renderRecord(self, entry: LogRecord):
        msgLines = []
        if entry.getMessage():
            msgLines.append(self.cleanText(entry.getMessage()))
        if entry.exc_info:
            msgLines.append(self.cleanText(str(entry.exc_info[1])))
        return "<br/>".join(msgLines)

    def nextMessage(self):
        self._displayRecord(self.records.pop(0))
        self.nextBtn.setText("Show next error (%d more)" % len(self.records))
        if len(self.records) == 0:
            self.nextBtn.setEnabled(False)

    def claudeClicked(self):
        if self.currentRecord is None:
            return
        from acq4.util import claude_debug

        claude_debug.debugRecordWithClaude(
            self.currentRecord, confirm=lambda: confirmTeleproxServer(self)
        )
```

In `closeEvent`, `okClicked`, and `logClicked`, replace `self.messages = []` with
`self.records = []`. Leave `currentRecord` alone — the dialog may be reopened on the same
record, and clearing it would silently disable the button.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_logwindow_claude_action.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Verify the existing LogWindow tests still pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests -v
```

Expected: all pass, including `test_logwindow_throughline.py`.

- [ ] **Step 7: Commit**

```bash
git add acq4/util/LogWindow.py acq4/util/tests/test_logwindow_claude_action.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add "Debug with Claude" to the error dialog

The error dialog now queues LogRecords rather than pre-rendered HTML, so the
new button can hand the displayed record to Claude. Live access is gated by a
confirmation that defaults to No and explains what the port allows.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>
EOF
)"
```

---

### Task 6: Log window context menu

**Files:**
- Modify: `acq4/util/LogWindow.py` (`DocumentedLogViewer`)
- Test: `acq4/util/tests/test_logwindow_claude_action.py` (append)

**Interfaces:**
- Consumes: `debugRecordWithClaude` (Task 4), `confirmTeleproxServer` (Task 5).
- Produces on `DocumentedLogViewer`:
  - `_recordAtIndex(index) -> LogRecord | None`
  - `_logTailForIndex(index, count=LOG_TAIL_COUNT) -> list[LogRecord]`
  - `_buildRowContextMenu(index) -> Qt.QMenu`
  - `_debugRowWithClaude()` — triggered handler, reads `self.sender().selectedIndex`
  - `LOG_TAIL_COUNT = 50` — module-level constant

**Why reimplement rather than extend:** teleprox's `LogViewer._show_row_context_menu`
builds its `QMenu` as a local and calls `menu.popup()`, which is non-blocking. There is no
reference to append to after `super()` returns, so the override rebuilds the menu —
including the base's "Copy" action. The test below asserts "Copy" survives, so dropping it
is caught rather than silently shipped.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/util/tests/test_logwindow_claude_action.py`:

```python
from teleprox.log.logviewer.constants import ItemDataRole


def _model_with_records(records):
    """A DocumentedLogModel whose top-level rows carry *records*."""
    from acq4.util.LogWindow import DocumentedLogModel

    model = DocumentedLogModel()
    for record in records:
        item = Qt.QStandardItem(record.getMessage())
        item.setData(record, ItemDataRole.LOG_RECORD)
        model.appendRow([item])
    return model


def test_menu_keeps_copy_and_adds_claude(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.menu")
    qtbot.addWidget(viewer)
    with mock.patch.object(viewer, "_recordAtIndex", return_value=make_record()):
        menu = viewer._buildRowContextMenu(Qt.QModelIndex())
    labels = [a.text() for a in menu.actions()]
    assert "Copy" in labels
    assert "Debug with Claude" in labels


def test_menu_omits_claude_without_a_record(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.menu2")
    qtbot.addWidget(viewer)
    with mock.patch.object(viewer, "_recordAtIndex", return_value=None):
        menu = viewer._buildRowContextMenu(Qt.QModelIndex())
    assert "Debug with Claude" not in [a.text() for a in menu.actions()]


def test_record_at_index_walks_up_to_the_top_level_row(qapp, qtbot):
    """Right-clicking a child detail row must resolve to its parent's record."""
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.walk")
    qtbot.addWidget(viewer)
    record = make_record(msg="parent row")
    model = _model_with_records([record])
    child = Qt.QStandardItem("a detail row")
    model.item(0, 0).appendRow([child])

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        assert viewer._recordAtIndex(model.indexFromItem(child)) is record


def test_log_tail_returns_preceding_records_only(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.tail")
    qtbot.addWidget(viewer)
    records = [make_record(msg=f"r{i}") for i in range(5)]
    model = _model_with_records(records)

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        tail = viewer._logTailForIndex(model.index(3, 0))
    assert [r.getMessage() for r in tail] == ["r0", "r1", "r2"]


def test_log_tail_is_capped(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer, LOG_TAIL_COUNT

    viewer = DocumentedLogViewer(logger="test.claude.cap")
    qtbot.addWidget(viewer)
    records = [make_record(msg=f"r{i}") for i in range(LOG_TAIL_COUNT + 10)]
    model = _model_with_records(records)

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        tail = viewer._logTailForIndex(model.index(LOG_TAIL_COUNT + 5, 0))
    assert len(tail) == LOG_TAIL_COUNT
    assert tail[-1].getMessage() == f"r{LOG_TAIL_COUNT + 4}"


def test_menu_action_sends_record_and_tail(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.send")
    qtbot.addWidget(viewer)
    records = [make_record(msg=f"r{i}") for i in range(3)]
    model = _model_with_records(records)

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        menu = viewer._buildRowContextMenu(model.index(2, 0))
        action = next(a for a in menu.actions() if a.text() == "Debug with Claude")
        with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
            action.trigger()

    assert debug.call_args[0][0] is records[2]
    tail = debug.call_args.kwargs["log_tail"]
    assert [r.getMessage() for r in tail] == ["r0", "r1"]
    assert debug.call_args.kwargs["confirm"] is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_logwindow_claude_action.py -k "menu or record_at or log_tail" -v
```

Expected: `AttributeError: 'DocumentedLogViewer' object has no attribute '_buildRowContextMenu'`.

- [ ] **Step 3: Implement the context menu**

Add `LOG_TAIL_COUNT = 50` next to the existing `LOG_UI = None` / `ERROR_DIALOG = None`
module globals in `acq4/util/LogWindow.py`, then add these methods to
`DocumentedLogViewer`:

```python
    def _recordAtIndex(self, index):
        """Return the LogRecord for the top-level row containing *index*, or None.

        Child rows are detail items belonging to a record, so walk up to the row that
        actually carries one (mirroring the base viewer's clipboard handler).
        """
        if not index.isValid():
            return None
        while index.parent().isValid():
            index = index.parent()
        source = self.map_index_to_model(index)
        item = self.model.item(source.row(), 0)
        if item is None:
            return None
        return item.data(ItemDataRole.LOG_RECORD)

    def _logTailForIndex(self, index, count=LOG_TAIL_COUNT):
        """Return up to *count* records immediately preceding the row at *index*."""
        if not index.isValid():
            return []
        while index.parent().isValid():
            index = index.parent()
        row = self.map_index_to_model(index).row()
        tail = []
        for r in range(max(0, row - count), row):
            item = self.model.item(r, 0)
            if item is None:
                continue
            record = item.data(ItemDataRole.LOG_RECORD)
            if record is not None:
                tail.append(record)
        return tail

    def _show_row_context_menu(self, position):
        """Show the row context menu, with the Claude handoff added.

        Reimplements rather than extends the base: it builds its menu as a local and
        pops it up non-blocking, so there is nothing to append to afterwards.
        """
        index = self.tree.indexAt(position)
        if not index.isValid():
            return
        menu = self._buildRowContextMenu(index)
        menu.popup(self.tree.mapToGlobal(position))

    def _buildRowContextMenu(self, index):
        menu = Qt.QMenu(self)

        copy_action = Qt.QAction("Copy", self)
        copy_action.selectedIndex = index
        copy_action.triggered.connect(self._copy_record_to_clipboard)
        menu.addAction(copy_action)

        if self._recordAtIndex(index) is not None:
            claude_action = Qt.QAction("Debug with Claude", self)
            claude_action.selectedIndex = index
            claude_action.triggered.connect(self._debugRowWithClaude)
            menu.addAction(claude_action)

        return menu

    def _debugRowWithClaude(self):
        index = self.sender().selectedIndex
        record = self._recordAtIndex(index)
        if record is None:
            return
        from acq4.util import claude_debug

        claude_debug.debugRecordWithClaude(
            record,
            log_tail=self._logTailForIndex(index),
            confirm=lambda: confirmTeleproxServer(self),
        )
```

`ItemDataRole` is already imported at the top of `LogWindow.py`. `Qt.QAction` and
`Qt.QMenu` come through acq4's Qt shim; do not import `PyQt5` directly.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_logwindow_claude_action.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Run the whole suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util acq4/mcp -v
```

Expected: all pass. Test output must be clean — no unexpected warnings or tracebacks.

- [ ] **Step 6: Format**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m black acq4/util/claude_debug.py acq4/util/tests/test_claude_debug.py acq4/util/tests/test_logwindow_claude_action.py acq4/mcp/tests/test_teleprox_lifecycle.py
```

Do **not** run black over `LogWindow.py`, `acq4/mcp/__init__.py`, or `__main__.py` — they
predate it and reformatting them would bury the change in noise.

- [ ] **Step 7: Commit**

```bash
git add acq4/util/LogWindow.py acq4/util/tests/test_logwindow_claude_action.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add "Debug with Claude" to the log window context menu

Any log record can now be handed to Claude, not just exceptions, along with
the 50 records preceding it. The override reimplements the base viewer's row
menu because it pops up a local QMenu with no handle to extend.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: WOZCODE <contact@withwoz.com>
EOF
)"
```

---

## Manual verification

Automated tests stop where the external process begins. These steps cover the rest and
should be done once on Linux before calling the feature done, and once per platform for
the unverified templates.

- [ ] **Linux, no teleprox.** Start ACQ4 with no flags. Trigger an error. Click "Debug with
  Claude". Expect: confirmation appears defaulted to No; choosing No opens a terminal with
  a brief that says live inspection is unavailable.
- [ ] **Linux, on-demand teleprox.** Same, but choose Yes. Expect: a WARNING with the
  address appears in the log window; the brief contains `connect_acq4(port=N)`; Claude
  connects and `list_devices` returns the rig's devices.
- [ ] **Linux, pre-started teleprox.** Start with `--teleprox`. Expect: no confirmation at
  all, and the brief carries the startup server's port.
- [ ] **Linux, with the exception buffer.** Start with `--teleprox --exception-buffer 5`.
  Trigger an exception, hand it over, and confirm Claude can reach frame locals via
  `list_exceptions` then `get_exception_frame`.
- [ ] **Log window, non-exception record.** Right-click an INFO row. Expect the explain-and-
  suggest task text, no traceback section, and a populated Recent log section.
- [ ] **Windows.** Verify `wt.exe` template, then the `cmd /k` fallback. Record what actually
  works in the spec's open questions. If Claude Code is only available under WSL there,
  expect live inspection to fail (teleprox binds `127.0.0.1` inside the WSL VM) — note it
  and treat teleprox binding as separate work.
- [ ] **macOS.** Verify the `osascript` template if any macOS rig matters; otherwise leave it
  marked unverified.

## Self-review notes

Checked against the spec:

- Every spec section maps to a task: teleprox lifecycle and its contract → Task 1; context
  blob, templates, and the no-correlation decision → Task 2; config surface and per-platform
  defaults → Task 3; temp-file payload and the e2e boundary → Task 4; both entry points and
  the confirmation → Tasks 5–6. Phase 2 is explicitly deferred and has no task, by design.
- Names are consistent across tasks: `ensure_teleprox_server`, `build_debug_context`,
  `claudeCommand`, `invokeClaude`, `debugRecordWithClaude`, `confirmTeleproxServer`,
  `LOG_TAIL_COUNT`. `snake_case` in `acq4/mcp`, `camelCase` in `acq4/util`, matching each
  file's existing style.
- Two spec details that became explicit here: `build_debug_context` receives the teleprox
  address rather than resolving it (keeps it pure and Qt-free, so Tasks 2–4 need no
  QApplication), and `ErrorDialog.messages` had to become `records` because the queue held
  pre-rendered HTML the context builder cannot use.



