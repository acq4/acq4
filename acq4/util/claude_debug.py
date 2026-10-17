"""Hand off an ACQ4 log record or exception to Claude Code for debugging.

Renders a markdown brief about the record and the rig, then launches Claude primed with it.
"""

import logging
import os
import shutil
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


def _bufferLines(exc):
    """Report what the exception ring buffer holds for *exc*, checked as the brief is built.

    The brief is rendered inside the process that owns the buffer, so it can state
    what is actually there rather than leaving the reader to guess.
    """
    from acq4.mcp import exception_capture

    status = exception_capture.buffer_status()
    if not status["active"]:
        return [
            "The exception ring buffer is not running in this ACQ4, so no frames were "
            "stored for this exception and `list_exceptions` will come back empty. "
            "Work out the mechanism from the traceback text, and if you need live "
            "frames, `arm_exception_capture` will catch a recurrence; a restart with "
            "`--exception-buffer N` keeps every exception from then on.",
        ]

    capacity = f"{status['count']} of {status['size']} slots in use"
    exception_id = exception_capture.find_buffered_id(exc)
    if exception_id is not None:
        return [
            "The exception above is held in the ring buffer as "
            f"exception_id={exception_id} ({capacity}). "
            f"`get_exception_frame(exception_id={exception_id}, frame_index=N)` gives "
            "you a frame's locals and `exec_in_exception_frame` evaluates expressions "
            "against them. Read the frames before theorising; the buffer is a ring, so "
            "do it early.",
        ]

    if status["count"] == 0:
        return [
            f"The exception ring buffer is running (capacity {status['size']}) but "
            "empty, so there are no stored frames for this exception. Work out the "
            "mechanism from the traceback text, and use `arm_exception_capture` if you "
            "want to catch a recurrence live.",
        ]

    return [
        "This exception is not itself in the ring buffer, but the buffer is running "
        f"and holds {status['count']} other exceptions (capacity {status['size']}). Call "
        "`list_exceptions` in case one of them is the same failure caught elsewhere; "
        "`get_exception_frame` and `exec_in_exception_frame` then work against that "
        "entry. Otherwise work from the traceback text.",
    ]


def build_debug_context(record, log_tail=None, teleprox_address=None):
    """Render a markdown debugging brief for *record*.

    Reads live state (rig identity, exception ring buffer) but changes none of it, and
    touches no Qt and no subprocess. The Phase 2 inline panel reuses this.

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
        out += (
            ["## Live frame inspection", ""] + _bufferLines(record.exc_info[1]) + [""]
        )

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
    except Exception as exc:
        logger.debug("configured claudeCommand not consulted: %s", exc)
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


def invokeClaude(context, command=None):
    """Write *context* to a temp markdown file and launch Claude Code on it.

    Returns the path written. The file is deliberately not deleted: the spawned
    process outlives this call and needs to read it, and keeping it lets the
    operator re-read or re-launch. Temp cleanup is the OS's job.
    """
    if command is None:
        command = claudeCommand()
    fd, path = tempfile.mkstemp(prefix="acq4-debug-", suffix=".md", text=True)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
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
