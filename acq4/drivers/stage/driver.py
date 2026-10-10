"""StageDriver: base class for motorized stage drivers built on StageControlThread."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from .control_thread import StageControlThread
from .futures import MoveRequest, MoveState, RequestFailed, RequestFuture

logger = logging.getLogger(__name__)


class StageDriver:
    """Base for stage device drivers.

    Each driver has one control thread (StageControlThread) for its lifetime: :meth:`connect`
    starts it, :meth:`close` ends it, and a closed driver cannot reconnect. Public methods are
    thread-safe and return immediately, queueing work for the control thread; requests made
    before ``connect`` or after ``close`` fail at once with RequestFailed. Underscore hooks
    run only on the control thread, one at a time and never reentrantly; they may block on I/O.

    Subclasses call ``super().__init__()`` and implement the hooks (``_open_link`` and
    ``_close_link`` open and close the hardware link). Device-specific work runs on the
    control thread via :meth:`_submit`.

    Attributes (class defaults; may be overridden per instance before ``connect``)
    ----------
    poll_interval : float
        Seconds between polls.
    stop_before_move : bool
        If True, a move superseding an active move first sends a stop and waits until
        ``_check_move`` on the old move stops returning MOVING.
    stop_timeout : float
        Seconds to wait for motion to cease (stop_before_move only) before failing the new move.
    position_change_threshold : float | dict | None
        Per-axis distance the position must move before the position callback fires; a dict
        maps axis -> threshold (missing axes: 0). None fires on every poll.
    """

    poll_interval: float = 0.05
    stop_before_move: bool = False
    stop_timeout: float = 5.0
    position_change_threshold: float | dict | None = None

    def __init__(self):
        self._ctrl = StageControlThread(self)

    # ---- public, final ----

    def get_position(self) -> dict | None:
        """Position from the most recent successful read (no I/O); None before the first."""
        pos = self._ctrl.position
        return None if pos is None else dict(pos)

    def move_to(self, pos: dict, speed, reason: str = '', **kwds) -> MoveRequest:
        """Queue an absolute move to *pos* (axis -> target; None or absent axes are not moved).

        Supersedes any active move, which completes as 'interrupted'. Extra *kwds* are stored
        on ``MoveRequest.kwds`` for ``_send_move``.
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
        """Set ``cb(pos_dict)``, called from the control thread when position changes past threshold."""
        self._ctrl.position_callback = cb

    # ---- public, extendable ----

    def connect(self) -> None:
        """Start the control thread and run ``_open_link`` on it; polling starts after.

        Blocks until ``_open_link`` returns. If it raises, the driver is closed and that
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
        """Stop the control thread (running ``_close_link`` on it) and wait up to *timeout* s for it to exit.

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

    # ---- for subclasses ----

    def _submit(self, fn: Callable, *args, reason: str = '', **kwds) -> RequestFuture:
        """Queue ``fn(*args, **kwds)`` to run on the control thread; thread-safe.

        The future's result is fn's return value; an exception fails it with RequestFailed
        (``__cause__`` = the exception). *reason* names the request in its repr and errors.
        Polling and move checks pause while fn runs. Not cancellable.
        """
        return self._enqueue(RequestFuture('call', self, reason), fn=fn, args=args, kwds=kwds)

    def _enqueue(self, fut: RequestFuture, **args) -> RequestFuture:
        return self._ctrl.enqueue(fut, **args)

    def _interrupt_motion(self, reason: str) -> None:
        """End any active or pending move as interrupted (sends a stop). Control thread only."""
        ctrl = self._ctrl
        if ctrl.active_move is not None or ctrl.pending_move is not None:
            ctrl._end_motion('interrupted', f'interrupted by {reason}')

    def _publish_position(self, pos: dict) -> None:
        """Update the cached position and fire the position callback outside the regular poll.

        Control thread only.
        """
        self._ctrl._update_position(pos)

    # ---- hooks ----

    def _open_link(self) -> None:
        """Open the hardware link; runs first on the control thread. Raising aborts ``connect``."""

    def _close_link(self) -> None:
        """Close the hardware link; runs last on the control thread, also after ``_open_link`` fails."""

    def _read_position(self) -> dict:
        """Read position from hardware (axis -> value). Called every poll."""
        raise NotImplementedError()

    def _read_final_position(self, req: MoveRequest) -> dict:
        """Return the position (axis -> value) once *req* is done; becomes ``req.final_position``.

        Called once, right after ``_check_move`` returns DONE, and the result is published as
        the cached position. Default: a fresh ``_read_position()``, since the poll's read
        precedes ``_check_move``. If it raises, the last polled position is used.
        """
        return self._read_position()

    def _send_move(self, req: MoveRequest) -> None:
        """Command the move in *req*. Must re-issue speed if the device zeroes it on stop."""
        raise NotImplementedError()

    def _send_stop(self, reason: str) -> None:
        """Command a stop. Need not wait for motion to cease."""
        raise NotImplementedError()

    def _check_move(self, req: MoveRequest) -> tuple[MoveState, str | None]:
        """Return (state, failure reason) for *req*. Called once per poll while a move is active."""
        raise NotImplementedError()

    def _poll_extra(self) -> None:
        """Optional extra per-poll hardware reads. Exceptions are logged and ignored."""
