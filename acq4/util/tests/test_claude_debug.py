"""Tests for the Claude debugging handoff: context rendering, command resolution, launch."""

import logging

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
            assert (
                "{contextFile}" in template
            ), f"{platform}/{name} lacks {{contextFile}}"
            assert "claude" in template, f"{platform}/{name} does not invoke claude"


def test_configured_command_returns_none_when_no_manager():
    """_configuredCommand returns None when no Manager is running (e.g. under pytest)."""
    result = claude_debug._configuredCommand()
    assert result is None
