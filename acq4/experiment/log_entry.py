"""ActionLogEntry: a per-action record used by ctx.log_action() to track status,
timing, and the live detail widget for the UI log/timeline view."""
from __future__ import annotations

import time
from typing import Any, Callable

from acq4.util.task import Stopped

from .error_record import describe_exception
from .exceptions import FlowSignal


class ActionLogEntry:
    """Tracks one action's execution: name, status, timing, details widget.

    UI layers attach callbacks (on_status, on_widget, on_finish) to drive
    widgets; in headless mode these are all None and the entry is plain data.
    """

    def __init__(self, name: str):
        self.name = name
        self.start_time: float = time.time()
        self.end_time: float | None = None
        self.status: str = ""
        self.outcome: str | None = None
        self.details_widget: Any = None
        # Retained counterpart to details_widget: a GUI-free description of what
        # this action found, which outlives the action (see set_details).
        self.details_kind: str | None = None
        self.details_payload: Any = None
        # Populated by _finish() for an error outcome only, and never with the
        # exception itself -- see error_record.describe_exception. A finished
        # entry is retained for the session in CellPanel's per-cell stores, so
        # what it holds is what one failure costs in memory.
        self.exc_type: str | None = None
        self.exc_message: str | None = None
        self.traceback_text: str | None = None
        self.on_status: Callable | None = None
        self.on_widget: Callable | None = None
        self.on_details: Callable | None = None
        self.on_finish: Callable | None = None

    def set_status(self, message: str) -> None:
        self.status = message
        if self.on_status is not None:
            self.on_status(self)

    def set_details_widget(self, widget) -> None:
        """Hand the UI a live widget for this action (e.g. a plot updated as the
        action progresses), stored and passed to on_widget(entry, widget).

        ctx.log_action() is opened from whatever thread is running the
        protocol/action function -- typically the orchestrator's worker
        thread, not the GUI thread. A widget is a GUI object: if the caller
        constructs one here, it must build it via run_in_gui_thread (from
        acq4.util.task) rather than instantiating it directly, since a widget
        built off the GUI thread is not safe to parent into the GUI tree.
        """
        self.details_widget = widget
        if self.on_widget is not None:
            self.on_widget(self, widget)

    def set_details(self, kind: str, payload) -> None:
        """Hand the UI a retained description of what this action found, stored
        and passed to on_details(entry, kind, payload).

        The counterpart to set_details_widget(), and different from it in the one
        way that matters: what is passed here *outlives the action*. CellPanel
        keeps it for the rest of the session so the operator can re-read a
        finished action's results, which is why `payload` must be plain data --
        numpy arrays, strings, numbers, and dicts/lists of those -- and never a
        Qt object, a Cell, an exception, or a file handle. What a payload holds
        is what one action costs in memory for the rest of the run; see
        error_record.describe_exception for the same rule applied to tracebacks.

        `kind` selects how the UI renders the payload. An unrecognized kind
        renders as plain text rather than raising.

        **Must be called before this entry finishes.** CellPanel resolves an
        entry to its timeline row through bookkeeping that the entry's finish
        tears down, so a payload set afterwards has no row to attach to. Actions
        satisfy this by calling from a try/finally *inside* the
        `with ctx.log_action(...)` block, which runs before the context
        manager's __exit__.
        """
        self.details_kind = kind
        self.details_payload = payload
        if self.on_details is not None:
            self.on_details(self, kind, payload)

    def _finish(self, exc: BaseException | None) -> None:
        self.end_time = time.time()
        if exc is None:
            self.outcome = "done"
        elif isinstance(exc, Stopped):
            self.outcome = "stopped"
        elif isinstance(exc, FlowSignal):
            # A flow signal is control flow, not a failure -- that's why this
            # isn't "error". But an action whose block a flow signal escaped
            # was abandoned partway, not completed, so it isn't "done" either.
            self.outcome = "abandoned"
        else:
            self.outcome = "error"
            self.exc_type, self.exc_message, self.traceback_text = describe_exception(exc)
        # Set before on_finish, not after: the UI's "finished" slot renders the
        # error block straight from these fields, and it is reached through this
        # callback.
        if self.on_finish is not None:
            self.on_finish(self)
