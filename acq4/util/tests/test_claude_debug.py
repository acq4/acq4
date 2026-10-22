"""Tests for the Claude debugging handoff: context rendering, command resolution, launch."""

import contextlib
import logging
import sys as _sys
import textwrap
import time
from unittest import mock

import pytest

from acq4.util import claude_debug


def make_record(level=logging.ERROR, msg="something went wrong", exc_info=None):
    return logging.LogRecord(
        name="acq4.devices.Pipette",
        level=level,
        pathname="/fake/pipette.py",
        lineno=42,
        msg=msg,
        args=(),
        exc_info=exc_info,
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


@contextlib.contextmanager
def buffer_state(active=False, size=0, count=0, matching_id=None):
    """Patch the ring buffer's live state as build_debug_context will find it."""
    with mock.patch.multiple(
        "acq4.mcp.exception_capture",
        buffer_status=mock.DEFAULT,
        find_buffered_id=mock.DEFAULT,
    ) as patched:
        patched["buffer_status"].return_value = {
            "active": active,
            "size": size,
            "count": count,
        }
        patched["find_buffered_id"].return_value = matching_id
        yield patched


def live_context(**state):
    with buffer_state(**state):
        return claude_debug.build_debug_context(
            make_record(exc_info=real_exc_info()),
            teleprox_address="tcp://127.0.0.1:6666",
        )


def test_buffer_is_checked_rather_than_assumed_off():
    """The brief must report what the buffer actually holds, not hedge about opt-in."""
    with buffer_state(active=True, size=5, count=3, matching_id=2):
        out = claude_debug.build_debug_context(
            make_record(exc_info=real_exc_info()),
            teleprox_address="tcp://127.0.0.1:6666",
        )
    assert "opt-in" not in out
    assert "exception_id=2" in out


def test_buffered_record_names_its_own_exception_id():
    out = live_context(active=True, size=5, count=3, matching_id=7)
    assert "exception_id=7" in out
    assert "get_exception_frame" in out


def test_unmatched_record_is_pointed_at_the_held_exceptions():
    out = live_context(active=True, size=5, count=3, matching_id=None)
    assert "3 other exceptions" in out
    assert "list_exceptions" in out
    assert "exception_id=" not in out


def test_active_but_empty_buffer_is_reported_as_empty():
    out = live_context(active=True, size=5, count=0, matching_id=None)
    assert "empty" in out
    assert "arm_exception_capture" in out


def test_inactive_buffer_says_so_and_offers_the_live_alternative():
    out = live_context(active=False, size=0, count=0, matching_id=None)
    assert "not running" in out
    assert "arm_exception_capture" in out
    assert "--exception-buffer" in out


def test_buffer_is_not_consulted_without_live_inspection():
    """No teleprox server means no MCP call can reach the buffer; don't look."""
    with buffer_state(active=True, size=5, count=3, matching_id=2) as patched:
        claude_debug.build_debug_context(make_record(exc_info=real_exc_info()))
    patched["buffer_status"].assert_not_called()


def test_real_buffer_entry_is_correlated_by_identity():
    """End-to-end against the real buffer: one exception, both paths, one ID.

    acq4's logging callback and the ring buffer are both driven from a single
    excepthook call, so they hold the same exception object. That is what makes
    correlation exact rather than a fuzzy type/message/line comparison.
    """
    from collections import deque
    from types import SimpleNamespace

    from acq4.mcp import exception_capture as ec

    try:
        raise ValueError("pipette pressure out of range")
    except ValueError as exc:
        exc_info = (type(exc), exc, exc.__traceback__)

    saved = ec._exception_buffer
    ec._exception_buffer = deque(maxlen=5)  # bypass start_buffer: no global hook
    try:
        ec._buffer_callback(
            SimpleNamespace(
                exc_type=exc_info[0],
                exc_value=exc_info[1],
                exc_traceback=exc_info[2],
                thread=None,
            )
        )
        expected_id = ec._exception_buffer[0][0]
        out = claude_debug.build_debug_context(
            make_record(exc_info=exc_info), teleprox_address="tcp://127.0.0.1:6666"
        )
    finally:
        ec._exception_buffer = saved

    assert f"exception_id={expected_id}" in out


def test_buffer_is_not_consulted_without_a_traceback():
    with buffer_state(active=True, size=5, count=3) as patched:
        claude_debug.build_debug_context(
            make_record(), teleprox_address="tcp://127.0.0.1:6666"
        )
    patched["buffer_status"].assert_not_called()


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
            assert (
                "{contextFile}" in template
            ), f"{platform}/{name} lacks {{contextFile}}"
            assert "claude" in template, f"{platform}/{name} does not invoke claude"


def test_configured_command_returns_none_when_no_manager():
    """_configuredCommand returns None when no Manager is running (e.g. under pytest)."""
    result = claude_debug._configuredCommand()
    assert result is None


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
    """End-to-end for the part ACQ4 owns: a real subprocess receives the real path.

    Popen is deliberately NOT mocked here -- this is the one test that proves a real
    process is launched and can read what we wrote. The stub is spawned exactly once,
    by invokeClaude itself; we wait for its receipt rather than running it again.
    """
    stub = tmp_path / "stub.py"
    stub.write_text(textwrap.dedent("""
        import sys
        with open(sys.argv[2], "w") as out:
            out.write(sys.argv[1] + "\\n")
            out.write(open(sys.argv[1]).read())
    """))
    receipt = tmp_path / "receipt.txt"
    command = f"{_sys.executable} {stub} {{contextFile}} {receipt}"

    path = claude_debug.invokeClaude("# brief\nlive body", command=command)

    deadline = time.monotonic() + 30
    while not receipt.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert receipt.exists(), "stub process never wrote its receipt"

    written = receipt.read_text()
    assert path in written
    assert "live body" in written


def test_debug_record_passes_address_into_the_context():
    record = make_record(logging.ERROR)
    with mock.patch(
        "acq4.mcp.ensure_teleprox_server", return_value="tcp://127.0.0.1:7777"
    ):
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
