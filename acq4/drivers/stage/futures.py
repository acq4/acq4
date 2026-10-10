"""Request futures, their errors, and MoveState, shared by StageDriver and StageControlThread.

Timestamps on futures (``created_time``, ``start_time``, ``finish_time``) are
``acq4.util.ptime.time()`` seconds, the wall clock used throughout ACQ4.
"""
from __future__ import annotations

import logging
import threading
from acq4.util import ptime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .driver import StageDriver

logger = logging.getLogger(__name__)


class MoveState(Enum):
    """Result of :meth:`StageBackend.check_move`."""
    MOVING = auto()
    DONE = auto()
    FAILED = auto()


class RequestError(Exception):
    """Base class for every exception raised by :meth:`RequestFuture.wait` (except TimeoutError).

    A plain RequestError (not a subclass) is also what ``RequestFuture.error`` holds when a
    request ended without an underlying exception; it describes how the request ended.
    """


class RequestFailed(RequestError):
    """The request failed: backend error, failure reported by ``check_move``, or driver closed."""


class MoveInterrupted(RequestError):
    """The move was superseded by a newer move request. Not an error of the device."""


class MoveStopped(RequestError):
    """The move was ended by :meth:`StageDriver.stop`."""


class MoveCancelled(MoveStopped):
    """The request was cancelled (:meth:`MoveRequest.cancel`, or declined before it started).

    A function run by ``StageDriver._run`` may raise it to end its request as 'cancelled'.
    """


_status_errors = {
    'failed': RequestFailed,
    'interrupted': MoveInterrupted,
    'stopped': MoveStopped,
    'cancelled': MoveCancelled,
}


class RequestFuture:
    """Pending result of a request handled by the control thread (StageControlThread).

    ``status`` is 'pending', then one terminal value: 'done' or 'failed'
    ('stopped', 'interrupted', 'cancelled' are also possible for moves). Finished by a
    single thread: the control thread, or the thread that rejects the request.

    Attributes
    ----------
    reason : str
        Caller's description of the request, used in its repr and every error message.
    error : BaseException | None
        Set when the request ends other than 'done': the underlying exception (backend
        error, LimitError, CommutationError, ...) if there was one, else a plain
        RequestError saying how it ended. Never raised itself; :meth:`wait` raises a new
        exception chained from it.
    created_time : float
        When the future was created (normally just before it was queued).
    start_time : float | None
        When the control thread began handling the request; None if it never did (rejected,
        or cancelled while queued).
    finish_time : float | None
        When the request reached its terminal status; None while pending.
    """

    def __init__(self, kind: str, driver: StageDriver | None = None, reason: str = ''):
        self.kind = kind
        self.driver = driver
        self.reason = reason
        self.status = 'pending'
        self.result = None
        self.error: BaseException | None = None
        self.created_time = ptime.time()
        self.start_time: float | None = None
        self.finish_time: float | None = None
        self._message = ''
        self._done = threading.Event()
        self._callbacks: list[Callable] = []

    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: float | None = 10.0) -> Any:
        """Block until finished and return the result.

        Raises TimeoutError if *timeout* elapses, otherwise the RequestError subclass
        matching ``status`` (RequestFailed, MoveInterrupted, MoveStopped, MoveCancelled),
        with ``__cause__`` = :attr:`error`.
        """
        if not self._done.wait(timeout=timeout):
            raise TimeoutError(f"Timed out after {timeout} s waiting for {self}")
        if self.error is not None:
            raise _status_errors[self.status](f"{self}: {self._message}") from self.error
        return self.result

    def add_callback(self, cb: Callable[[RequestFuture], Any]) -> None:
        """Add *cb*, called once as ``cb(self)`` when finished; immediately (in this thread) if already finished.

        Otherwise it runs in the thread that finishes the request, usually the control thread.
        Callbacks added by different threads may run concurrently and in any order.
        """
        self._callbacks.append(cb)
        # _finish sets _done before draining, so a cb appended after its drain is seen here
        if self._done.is_set():
            self._run_callbacks()

    def _finish(self, status: str, result=None, message: str | None = None,
                cause: BaseException | None = None) -> bool:
        """Move to terminal *status* unless already finished. Returns True if it did.

        *message* says how the request ended (without naming the request); for a status
        other than 'done', defaults to *cause* as text, else *status*.
        """
        if self._done.is_set():
            return False
        self.finish_time = ptime.time()
        self.status = status
        self.result = result
        if status in _status_errors:
            if message is None:
                message = status if cause is None else f"{type(cause).__name__}: {cause}"
            elif cause is not None:
                message = f"{message}: {type(cause).__name__}: {cause}"
            self._message = message
            self.error = cause if cause is not None else RequestError(message)
        self._done.set()
        self._run_callbacks()
        return True

    def _run_callbacks(self):
        # list.pop is atomic, so each callback runs once even if two threads drain the list
        callbacks = self._callbacks
        while True:
            try:
                cb = callbacks.pop(0)
            except IndexError:
                return
            try:
                cb(self)
            except Exception:
                logger.exception("Error in callback for %s", self)

    def __repr__(self):
        reason = f" {self.reason!r}" if self.reason else ''
        return f"<{type(self).__name__} {self.kind}{reason} {self.status}>"


class MoveRequest(RequestFuture):
    """Future for an absolute move.

    Attributes
    ----------
    target : dict
        Axis name -> target position in driver units. Axes not present are not moved.
    speed :
        As passed to :meth:`StageDriver.move_to`; interpretation is up to the driver.
    kwds : dict
        Extra keyword arguments to ``move_to`` (e.g. acceleration), for ``backend.start_move``.
    status : str
        'pending' | 'moving' | 'done' | 'failed' | 'stopped' | 'interrupted' | 'cancelled'.
    final_position : dict | None
        Axis -> position (driver units) when the move finished, set before callbacks run.
        For 'done', from :meth:`StageBackend.final_position`; otherwise the latest
        position the control thread had read, which may precede motion ceasing. None if the
        move was never sent to the device (rejected, cancelled or interrupted before it
        started).
    """

    def __init__(self, driver: StageDriver, target: dict, speed, reason: str = '', kwds: dict | None = None):
        super().__init__('move', driver, reason)
        self.target = target
        self.speed = speed
        self.kwds = kwds or {}
        self.final_position: dict | None = None

    def cancel(self) -> RequestFuture:
        """See :meth:`StageDriver.cancel_move`."""
        return self.driver.cancel_move(self)

    def _finish(self, status: str, result=None, message: str | None = None,
                cause: BaseException | None = None, final_position: dict | None = None) -> bool:
        if self._done.is_set():
            return False
        self.final_position = None if final_position is None else dict(final_position)
        return super()._finish(status, result, message, cause)

    def __repr__(self):
        reason = f" ({self.reason})" if self.reason else ''
        return f"<MoveRequest to {self.target}{reason} {self.status}>"
