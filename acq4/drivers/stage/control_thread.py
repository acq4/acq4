"""Device-independent control thread and request futures for motorized stages."""
from __future__ import annotations

import logging
import queue
import threading
import time
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MoveState(Enum):
    """Result of :meth:`StageDriver._check_move`."""
    MOVING = auto()
    DONE = auto()
    FAILED = auto()


class RequestError(Exception):
    """Base class for every exception raised by :meth:`RequestFuture.wait` (except TimeoutError)."""


class RequestFailed(RequestError):
    """The request failed: hardware/hook error, failure reported by ``_check_move``, or driver closed.

    ``__cause__`` is the original exception, when there was one.
    """


class MoveInterrupted(RequestError):
    """The move was superseded by a newer move request. Not an error of the device."""


class MoveStopped(RequestError):
    """The move was ended by :meth:`StageDriver.stop`."""


class MoveCancelled(MoveStopped):
    """The move was ended by :meth:`MoveRequest.cancel`."""


_status_errors = {
    'failed': RequestFailed,
    'interrupted': MoveInterrupted,
    'stopped': MoveStopped,
    'cancelled': MoveCancelled,
}


class RequestFuture:
    """Pending result of a request handled by the control thread.

    ``status`` is 'pending', then one terminal value: 'done' or 'failed'
    ('stopped', 'interrupted', 'cancelled' are also possible for moves).
    """

    def __init__(self, kind: str, driver: StageDriver | None = None):
        self.kind = kind
        self.driver = driver
        self.status = 'pending'
        self.result = None
        self.error: BaseException | None = None
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._callbacks: list[Callable] = []

    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: float | None = 10.0) -> Any:
        """Block until finished and return the result.

        Raises TimeoutError if *timeout* elapses, otherwise the RequestError subclass
        matching ``status`` (RequestFailed, MoveInterrupted, MoveStopped, MoveCancelled).
        """
        if not self._done.wait(timeout=timeout):
            raise TimeoutError(f"Timed out waiting for {self}")
        if self.error is not None:
            # fresh instance so repeated waits do not accumulate tracebacks
            raise type(self.error)(*self.error.args) from self.error.__cause__
        return self.result

    def set_callback(self, cb: Callable[[RequestFuture], Any]) -> None:
        """Call ``cb(self)`` when finished; immediately (in this thread) if already finished.

        Otherwise it runs in whichever thread finishes the request, usually the control thread.
        """
        with self._lock:
            if not self._done.is_set():
                self._callbacks.append(cb)
                return
        self._run_callback(cb)

    def cancel(self) -> RequestFuture:
        raise TypeError(f"Cannot cancel a {self.kind!r} request")

    def _finish(self, status: str, result=None, message: str | None = None, cause: BaseException | None = None,
                only_if: tuple[str, ...] | None = None) -> bool:
        """Move to terminal *status* unless already finished (or not in *only_if*). Returns True if it did."""
        with self._lock:
            if self._done.is_set() or (only_if is not None and self.status not in only_if):
                return False
            self.status = status
            self.result = result
            if status in _status_errors:
                err = _status_errors[status](message or f"{self} {status}")
                err.__cause__ = cause
                self.error = err
            self._done.set()
            callbacks, self._callbacks = self._callbacks, []
        for cb in callbacks:
            self._run_callback(cb)
        return True

    def _set_status(self, status: str, only_if: tuple[str, ...]) -> bool:
        """Change non-terminal status if currently in *only_if*."""
        with self._lock:
            if self._done.is_set() or self.status not in only_if:
                return False
            self.status = status
            return True

    def _run_callback(self, cb):
        try:
            cb(self)
        except Exception:
            logger.exception("Error in callback for %s", self)

    def __repr__(self):
        return f"<{type(self).__name__} {self.kind} {self.status}>"


class MoveRequest(RequestFuture):
    """Future for an absolute move.

    Attributes
    ----------
    target : dict
        Axis name -> target position in driver units. Axes not present are not moved.
    speed :
        As passed to :meth:`StageDriver.move_to`; interpretation is up to the driver.
    reason : str
        Caller's description, used in log and error messages.
    kwds : dict
        Extra keyword arguments to ``move_to`` (e.g. acceleration), for ``_send_move``.
    status : str
        'pending' | 'moving' | 'done' | 'failed' | 'stopped' | 'interrupted' | 'cancelled'.
    """

    def __init__(self, driver: StageDriver, target: dict, speed, reason: str = '', kwds: dict | None = None):
        super().__init__('move', driver)
        self.target = target
        self.speed = speed
        self.reason = reason
        self.kwds = kwds or {}

    def cancel(self) -> RequestFuture:
        """End this move with status 'cancelled'; returns a future for the cancel itself.

        A move not yet started is resolved immediately with no hardware access. An active
        move is stopped on the device. Already-finished moves are unaffected.
        """
        if self._finish('cancelled', message=f"{self} cancelled", only_if=('pending',)):
            fut = RequestFuture('cancel', self.driver)
            fut._finish('done')
            return fut
        if self.done():
            fut = RequestFuture('cancel', self.driver)
            fut._finish('done')
            return fut
        return self.driver._enqueue(RequestFuture('cancel', self.driver), move=self)

    def __repr__(self):
        reason = f" ({self.reason})" if self.reason else ''
        return f"<MoveRequest to {self.target}{reason} {self.status}>"


class StageControlThread:
    """Sole owner of a StageDriver's hardware link.

    Runs the driver's hook methods (and nothing else does), dispatching queued requests and
    polling position every ``driver.poll_interval`` seconds.
    """

    def __init__(self, driver: StageDriver):
        self.driver = driver
        self.queue: queue.Queue = queue.Queue()
        self.active_move: MoveRequest | None = None
        # stop_before_move: move waiting for motion to cease, and the request whose motion we wait on
        self.pending_move: MoveRequest | None = None
        self.stopping: MoveRequest | None = None
        self.stopping_since = 0.0
        self._last_reported_pos: dict | None = None
        self._poll_failing = {}
        self._running = False
        self._run_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name=f"{type(driver).__name__}ControlThread")

    def start(self):
        with self._run_lock:
            self._running = True
        self.thread.start()

    def enqueue(self, fut: RequestFuture, **args) -> RequestFuture:
        with self._run_lock:
            if self._running:
                self.queue.put((fut, args))
                return fut
        fut._finish('failed', message=f"{fut} rejected: driver is not connected")
        return fut

    def quit(self, timeout: float = 10.0):
        fut = self.enqueue(RequestFuture('quit', self.driver))
        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout)
        return fut

    # ---- loop ----

    def _run(self):
        next_poll = time.monotonic()
        quitting = False
        while not quitting:
            try:
                timeout = max(0.0, next_poll - time.monotonic())
                try:
                    fut, args = self.queue.get(timeout=timeout)
                except queue.Empty:
                    fut = None
                if fut is not None:
                    if fut.kind == 'quit':
                        quitting = True
                    else:
                        self._dispatch(fut, args)

                now = time.monotonic()
                if now >= next_poll and not quitting:
                    self._poll()
                    next_poll += self.driver.poll_interval
                    if next_poll < now:
                        next_poll = now + self.driver.poll_interval
            except Exception:
                logger.exception("Unexpected error in %s; continuing", self.thread.name)
        self._shutdown(fut)

    def _shutdown(self, quit_fut):
        with self._run_lock:
            self._running = False
        for move in (self.active_move, self.pending_move):
            if move is not None:
                move._finish('failed', message=f"{move} abandoned: driver closed")
        self.active_move = self.pending_move = self.stopping = None
        while True:
            try:
                fut, _ = self.queue.get_nowait()
            except queue.Empty:
                break
            fut._finish('failed', message=f"{fut} rejected: driver closed")
        quit_fut._finish('done')

    def _dispatch(self, fut: RequestFuture, args: dict):
        try:
            if fut.kind == 'move':
                self._handle_move(fut)
            elif fut.kind == 'stop':
                self._handle_stop(fut, args['reason'])
            elif fut.kind == 'cancel':
                self._handle_cancel(fut, args['move'])
            elif fut.kind == 'call':
                fut._finish('done', result=args['fn'](*args['args'], **args['kwds']))
            else:
                raise ValueError(f"Unknown request kind {fut.kind!r}")
        except Exception as exc:
            fut._finish('failed', message=f"{fut} failed: {exc}", cause=exc)

    def _poll(self):
        drv = self.driver
        try:
            pos = drv._read_position()
        except Exception:
            self._log_poll_error('_read_position')
        else:
            self._poll_ok('_read_position')
            self._update_position(pos)

        try:
            drv._poll_extra()
        except Exception:
            self._log_poll_error('_poll_extra')
        else:
            self._poll_ok('_poll_extra')

        if self.stopping is not None:
            self._check_stopping()
        if self.active_move is not None:
            self._check_active()

    def _update_position(self, pos: dict):
        pos = dict(pos)
        with self.driver._pos_lock:
            self.driver._position = pos
        last = self._last_reported_pos
        if last is not None and not self._exceeds_threshold(last, pos):
            return
        self._last_reported_pos = pos
        cb = self.driver._position_callback
        if cb is not None:
            try:
                cb(dict(pos))
            except Exception:
                logger.exception("Error in position callback")

    def _exceeds_threshold(self, last: dict, pos: dict) -> bool:
        thresh = self.driver.position_change_threshold
        if thresh is None:
            return True
        if set(last) != set(pos):
            return True
        for ax, val in pos.items():
            t = thresh.get(ax, 0) if isinstance(thresh, dict) else thresh
            if abs(val - last[ax]) > t:
                return True
        return False

    def _log_poll_error(self, name):
        # log the first failure of a run only, to avoid flooding at the poll rate
        if not self._poll_failing.get(name):
            logger.exception("Error in %s during poll (suppressing repeats until it succeeds)", name)
        self._poll_failing[name] = True

    def _poll_ok(self, name):
        if self._poll_failing.get(name):
            logger.info("%s succeeded again", name)
            self._poll_failing[name] = False

    def _check_active(self):
        move = self.active_move
        try:
            state, reason = self.driver._check_move(move)
        except Exception as exc:
            self.active_move = None
            move._finish('failed', message=f"{move} failed while checking status: {exc}", cause=exc)
            return
        if state is MoveState.MOVING:
            return
        self.active_move = None
        if state is MoveState.DONE:
            move._finish('done')
        elif state is MoveState.FAILED:
            move._finish('failed', message=reason or f"{move} failed")
        else:
            move._finish('failed', message=f"_check_move returned invalid state {state!r}")

    def _check_stopping(self):
        try:
            state, _ = self.driver._check_move(self.stopping)
        except Exception as exc:
            self.stopping = None
            if self.pending_move is not None:
                move, self.pending_move = self.pending_move, None
                move._finish('failed', message=f"{move} failed waiting for previous motion to stop: {exc}",
                             cause=exc)
            return
        if state is MoveState.MOVING:
            if time.monotonic() - self.stopping_since > self.driver.stop_timeout:
                self.stopping = None
                if self.pending_move is not None:
                    move, self.pending_move = self.pending_move, None
                    move._finish('failed', message=f"{move} failed: previous motion did not stop within "
                                                   f"{self.driver.stop_timeout} s")
            return
        self.stopping = None
        if self.pending_move is not None:
            move, self.pending_move = self.pending_move, None
            self._start_move(move)

    # ---- request handlers ----

    def _handle_move(self, move: MoveRequest):
        if not move._set_status('moving', only_if=('pending',)):
            return  # cancelled before dispatch
        moving = self.active_move
        if moving is not None:
            moving._finish('interrupted', message=f"{moving} interrupted by {move}")
            self.active_move = None
        if self.pending_move is not None:
            self.pending_move._finish('interrupted', message=f"{self.pending_move} interrupted by {move}")
            self.pending_move = None

        if self.driver.stop_before_move and moving is not None:
            self.driver._send_stop(f"interrupted by {move}")
            self.stopping = moving
            self.stopping_since = time.monotonic()
        if self.stopping is not None:
            self.pending_move = move
        else:
            self._start_move(move)

    def _start_move(self, move: MoveRequest):
        self.active_move = move
        try:
            self.driver._send_move(move)
        except Exception as exc:
            self.active_move = None
            move._finish('failed', message=f"{move} failed to start: {exc}", cause=exc)

    def _end_motion(self, status: str, reason: str):
        """Send stop and resolve active/pending moves with *status*."""
        active = self.active_move
        self.driver._send_stop(reason)
        if active is not None and self.driver.stop_before_move:
            self.stopping = active
            self.stopping_since = time.monotonic()
        for move in (active, self.pending_move):
            if move is not None:
                move._finish(status, message=f"{move} {status}: {reason}")
        self.active_move = self.pending_move = None

    def _handle_stop(self, fut: RequestFuture, reason: str):
        self._end_motion('stopped', reason)
        fut._finish('done')

    def _handle_cancel(self, fut: RequestFuture, move: MoveRequest):
        if move is self.active_move:
            self._end_motion('cancelled', 'cancelled')
        elif move is self.pending_move:
            self.pending_move = None
            move._finish('cancelled', message=f"{move} cancelled")
        else:
            move._finish('cancelled', message=f"{move} cancelled")
        fut._finish('done')


class StageDriver:
    """Base for stage device drivers.

    Public methods are thread-safe and return immediately, queueing work for the control
    thread. Underscore hooks are called only by the control thread, one at a time and never
    reentrantly; they need no locking and may block on I/O.

    Subclasses call ``super().__init__()``, implement the hooks, and extend ``connect``/
    ``close`` (open the link before ``super().connect()``; close it after ``super().close()``).
    Device-specific work runs on the control thread via :meth:`_submit`.

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
        self._pos_lock = threading.Lock()
        self._position: dict | None = None
        self._position_callback: Callable[[dict], Any] | None = None
        self._ctrl: StageControlThread | None = None

    # ---- public, final ----

    def get_position(self) -> dict | None:
        """Position from the most recent successful poll (no I/O); None before the first."""
        with self._pos_lock:
            return None if self._position is None else dict(self._position)

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
        return self._enqueue(RequestFuture('stop', self), reason=reason)

    def set_position_callback(self, cb: Callable[[dict], Any] | None) -> None:
        """Set ``cb(pos_dict)``, called from the control thread when position changes past threshold."""
        self._position_callback = cb

    # ---- public, extendable ----

    def connect(self) -> None:
        """Start the control thread. Polling begins immediately."""
        if self._ctrl is not None and self._ctrl.thread.is_alive():
            raise RuntimeError(f"{self} is already connected")
        self._ctrl = StageControlThread(self)
        self._ctrl.start()

    def close(self) -> None:
        """Stop the control thread and wait for it to exit.

        Outstanding moves fail with RequestFailed; no stop is sent to the device. Idempotent.
        """
        ctrl = self._ctrl
        if ctrl is None:
            return
        ctrl.quit()

    # ---- for subclasses ----

    def _submit(self, fn: Callable, *args, **kwds) -> RequestFuture:
        """Queue ``fn(*args, **kwds)`` to run on the control thread; thread-safe.

        The future's result is fn's return value; an exception fails it with RequestFailed
        (``__cause__`` = the exception). Polling and move checks pause while fn runs.
        Not cancellable.
        """
        return self._enqueue(RequestFuture('call', self), fn=fn, args=args, kwds=kwds)

    def _enqueue(self, fut: RequestFuture, **args) -> RequestFuture:
        ctrl = self._ctrl
        if ctrl is None:
            fut._finish('failed', message=f"{fut} rejected: driver is not connected")
            return fut
        return ctrl.enqueue(fut, **args)

    def _interrupt_motion(self, reason: str) -> None:
        """End any active or pending move as interrupted (sends a stop). Control thread only."""
        ctrl = self._ctrl
        if ctrl is not None and (ctrl.active_move is not None or ctrl.pending_move is not None):
            ctrl._end_motion('interrupted', f'interrupted by {reason}')

    def _publish_position(self, pos: dict) -> None:
        """Update the cached position and fire the position callback outside the regular poll."""
        ctrl = self._ctrl
        if ctrl is not None:
            ctrl._update_position(pos)
        else:
            with self._pos_lock:
                self._position = dict(pos)

    @property
    def _active_move(self) -> MoveRequest | None:
        """The move currently in progress. Read from the control thread only."""
        return None if self._ctrl is None else self._ctrl.active_move

    # ---- hooks ----

    def _read_position(self) -> dict:
        """Read position from hardware (axis -> value). Called every poll."""
        raise NotImplementedError()

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
