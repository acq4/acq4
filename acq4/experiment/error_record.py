"""Renders a failure to retainable text: the shared rendering behind the
per-action log entry's error fields and the orchestrator's run-level report."""
from __future__ import annotations

import traceback
from dataclasses import dataclass


def describe_exception(exc: BaseException) -> tuple[str, str, str]:
    """Render `exc` to `(type name, message, traceback text)`.

    Text, never the exception itself. Both callers retain what they are given
    for the length of a session -- a finished ActionLogEntry stays in CellPanel's
    per-cell stores, and the run-level record stays in StatusPanel until the next
    run -- and a live exception holds its traceback, which holds every frame,
    which holds those frames' locals: image stacks, device handles, the execution
    context. Formatting here is what stops one failure from pinning a run's worth
    of memory, and keeps this out of the reference-cycle class of bug Autopatch's
    deterministic teardown path exists to avoid.

    The traceback text follows the `__cause__` chain, which is where the frames
    that explain anything live: an orchestrator halt is raised as
    `AbortExperiment(...) from exc`, and the wrapper's own frames say only that
    the orchestrator gave up.
    """
    return (
        type(exc).__name__,
        str(exc),
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )


@dataclass(frozen=True)
class RunErrorRecord:
    """What halted a run, as plain data -- the payload of Orchestrator.sigRunError.

    `cell_repr` is the same token the orchestrator's own log messages carry
    ("...while processing cell %r"), so the operator can paste it into the log
    window's search: teleprox's LogViewer has no select-a-record API, so the UI's
    log link narrows the view but cannot anchor to the entry. None when the
    failure belongs to no cell -- a producer raising during a refill emits no
    sigCellFinished and opens no log_action, so there is neither a cell nor an
    entry to attribute it to.
    """

    exc_type: str
    exc_message: str
    traceback_text: str
    cell_repr: str | None = None

    @classmethod
    def from_exception(cls, exc: BaseException, cell=None) -> "RunErrorRecord":
        exc_type, exc_message, traceback_text = describe_exception(exc)
        return cls(
            exc_type,
            exc_message,
            traceback_text,
            None if cell is None else repr(cell),
        )
