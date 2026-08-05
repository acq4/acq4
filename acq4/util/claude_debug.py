"""Hand off an ACQ4 log record or exception to Claude Code for debugging.

Renders a markdown brief about the record and the rig, then launches Claude primed with it.
"""

import logging
import socket
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
