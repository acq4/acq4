"""StageDriver: thread-safe, future-based driver for a motorized stage, built on a StageBackend."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from .backend import StageBackend
from .control_thread import PositionReport, StageControlThread
from .futures import MoveRequest, RequestFailed, RequestFuture

logger = logging.getLogger(__name__)


class StageDriver:
    """Driver for one stage; all hardware access goes through *backend* on the control thread.

    Each driver has one control thread (StageControlThread) for its lifetime: :meth:`connect`
    starts it, :meth:`close` ends it, and a closed driver cannot reconnect. Public methods are
    thread-safe and return immediately, queueing work for the control thread; requests made
    before ``connect`` or after ``close`` fail at once with RequestFailed. Device-specific
    operations are added by subclasses as public wrappers around :meth:`_run`.

    Parameters
    ----------
    backend : StageBackend
        Hardware layer; called only from the control thread once the driver owns it.
    poll_interval : float
        Seconds between polls.
    stop_timeout : float
        Seconds to wait for motion to cease (``backend.stop_before_move`` only) before
        failing the move waiting on it.
    position_change_threshold : float | dict | None
        Per-axis distance the position must move before the position callback fires; a dict
        maps axis -> threshold (missing axes: 0). None fires on every poll.
    """

    def __init__(self, backend: StageBackend, *, poll_interval: float = 0.05, stop_timeout: float = 5.0,
                 position_change_threshold: float | dict | None = None):
        self._backend = backend
        self._ctrl = StageControlThread(self, backend, poll_interval=poll_interval,
                                        stop_timeout=stop_timeout,
                                        position_change_threshold=position_change_threshold)

    @property
    def axes(self) -> tuple:
        """Axis names."""
        return tuple(self._backend.axes)

    @property
    def poll_interval(self) -> float:
        return self._ctrl.poll_interval

    @property
    def position_change_threshold(self):
        return self._ctrl.position_change_threshold

    def get_position(self) -> dict | None:
        """Position from the most recent successful read (no I/O); None before the first."""
        pos = self._ctrl.position
        return None if pos is None else dict(pos)

    def position_report(self) -> PositionReport | None:
        """The latest position with its read time and whether a read has failed since (no I/O).

        None before the first read. ``stale`` means a read failed and the position has not
        been confirmed since; ``age()`` is how long ago it was read. While it is stale the
        driver refuses new moves -- stops, cancels and device operations still run.
        """
        report = self._ctrl.position_report
        return None if report is None else report._replace(position=dict(report.position))

    def read_position(self) -> RequestFuture:
        """Queue a hardware read of every axis; the future's result is the position dict.

        The read also republishes the position (position callback included). It waits behind
        requests already queued, so a long device operation delays it.
        """
        return self._run(self._ctrl.read_position, reason='read position')

    def move_to(self, pos: dict, speed, reason: str = '', **kwds) -> MoveRequest:
        """Queue an absolute move to *pos* (axis -> target; None or absent axes are not moved).

        Supersedes any active move, which completes as 'interrupted'. Extra *kwds* are stored
        on ``MoveRequest.kwds`` and passed to ``backend.start_move``.
        """
        target = {ax: v for ax, v in pos.items() if v is not None}
        return self._enqueue(MoveRequest(self, target, speed, reason, kwds))

    def stop(self, reason: str = 'user') -> RequestFuture:
        """Queue a stop. The active move, if any, completes as 'stopped'.

        The returned future resolves once the stop is sent, not when motion ceases.
        """
        return self._enqueue(RequestFuture('stop', self, reason), reason=reason)

    def cancel_move(self, move: MoveRequest) -> RequestFuture:
        """Queue cancellation of *move*; returns a future for the cancel itself. Thread-safe.

        Handled before requests queued earlier. An active move is stopped on the device; a
        move not yet started is finished without hardware access (it is never sent); a
        finished move is unaffected. *move* ends with status 'cancelled'.
        """
        return self._enqueue(RequestFuture('cancel', self, f"cancel move {move.reason or move.target}"),
                             move=move)

    def set_position_callback(self, cb: Callable[[dict], Any] | None) -> None:
        """Set ``cb(pos_dict)``, called from the control thread when position changes past threshold
        (and once immediately after the callback is set)."""
        self._ctrl.set_position_callback(cb)

    def connect(self) -> None:
        """Start the control thread and run ``backend.open`` on it; polling starts after.

        Blocks until ``open`` returns. If it raises, the driver is closed and that
        exception is re-raised here. RuntimeError if already connected or closed.
        """
        try:
            self._ctrl.start().wait(timeout=None)
        except RequestFailed as exc:
            cause = exc.__cause__
        else:
            return
        raise cause

    def close(self, timeout: float = 10.0) -> None:
        """Stop the control thread (running ``backend.close`` on it) and wait up to *timeout* s for it to exit.

        Requests queued before the close still run; outstanding moves then fail with
        RequestFailed, and no stop is sent to the device. Idempotent; does nothing before
        ``connect``. Called on the control thread, it queues the shutdown and returns at once.
        """
        ctrl = self._ctrl
        ctrl.quit()
        th = ctrl.thread
        if th.ident is None or th is threading.current_thread():
            return
        th.join(timeout)
        if th.is_alive():
            logger.warning("%s still running %s s after close", th.name, timeout)

    def _run(self, fn: Callable, *args, interrupt: bool = False, reason: str = '') -> RequestFuture:
        """Queue ``fn(*args)`` to run on the control thread; thread-safe.

        With *interrupt*, any active or pending move first ends as 'interrupted' (a stop is
        sent). The future's result is fn's return value; if fn raises MoveCancelled the
        future ends 'cancelled', any other exception fails it (``__cause__`` = the
        exception). *reason* names the request in its repr and errors. Polling pauses while
        fn runs. Not cancellable.
        """
        return self._enqueue(RequestFuture('call', self, reason), fn=fn, args=args, interrupt=interrupt)

    def _enqueue(self, fut: RequestFuture, **args) -> RequestFuture:
        return self._ctrl.enqueue(fut, **args)

    def __repr__(self):
        return f"<{type(self).__name__} {self._backend!r}>"
