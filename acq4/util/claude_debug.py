"""Hand off an ACQ4 log record or exception to Claude Code for debugging.

Renders a markdown brief about the record and the rig, then launches Claude primed with it.
"""

import logging
import shutil
import socket
import sys
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


# `claude` is a TUI, so it needs a terminal to live in. Each entry is
# (executable to look for, command template). First one present on the system wins.
# Every template must contain {contextFile}; see claudeCommand().
_POINTER = 'claude "Read {contextFile} and help me debug it"'

terminalCommands = {
    "linux": [
        ("wezterm", "wezterm start -- " + _POINTER),
        ("kitty", "kitty " + _POINTER),
        ("gnome-terminal", "gnome-terminal -- " + _POINTER),
        ("konsole", "konsole -e " + _POINTER),
        ("alacritty", "alacritty -e " + _POINTER),
        ("xterm", "xterm -e " + _POINTER),
    ],
    # UNVERIFIED: no Windows rig has run Claude Code from a command line yet.
    # Override with `misc: claudeCommand` if these are wrong.
    "win32": [
        ("wt", 'wt.exe new-tab --title "ACQ4 debug" ' + _POINTER),
        ("cmd", 'start "ACQ4 debug" cmd /k ' + _POINTER),
    ],
    # UNVERIFIED, and lower priority than Windows.
    "darwin": [
        (
            "osascript",
            """osascript -e 'tell application "Terminal" to do script """
            """"claude \\"Read {contextFile} and help me debug it\\""' """
            """-e 'tell application "Terminal" to activate'""",
        ),
    ],
}


def _configuredCommand():
    """Return the operator's configured command, or None if unset or no Manager."""
    try:
        from acq4 import getManager

        return getManager().config.get("misc", {}).get("claudeCommand", None)
    except Exception:
        logger.debug("No ACQ4 Manager running; configured claudeCommand not consulted")
        return None


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
