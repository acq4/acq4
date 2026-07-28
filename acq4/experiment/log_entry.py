"""ActionLogEntry: a per-action record used by ctx.log_action() to track status,
timing, and the live detail widget for the UI log/timeline view."""
from __future__ import annotations

import time
from typing import Any, Callable

from acq4.util.task import Stopped

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
        self.on_status: Callable | None = None
        self.on_widget: Callable | None = None
        self.on_finish: Callable | None = None

    def set_status(self, message: str) -> None:
        self.status = message
        if self.on_status is not None:
            self.on_status(self)

    def set_details_widget(self, widget) -> None:
        self.details_widget = widget
        if self.on_widget is not None:
            self.on_widget(self, widget)

    def _finish(self, exc: BaseException | None) -> None:
        self.end_time = time.time()
        if exc is None:
            self.outcome = "done"
        elif isinstance(exc, Stopped):
            self.outcome = "stopped"
        elif isinstance(exc, FlowSignal):
            # Flow signals are control flow, not failure.
            self.outcome = "done"
        else:
            self.outcome = "error"
        if self.on_finish is not None:
            self.on_finish(self)
