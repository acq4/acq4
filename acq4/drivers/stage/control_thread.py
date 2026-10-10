"""Device-independent control thread for motorized stages.

Each StageDriver has one StageControlThread, the only caller of the driver's backend
(StageBackend) and the only writer of hardware-derived state. Other threads submit requests through its
queue and get futures back, or read snapshots: attributes the control thread rebinds to a new
object that is never mutated afterwards. Rebinding an attribute is atomic in CPython, so a
reader sees the old or the new snapshot, never a mix; no locks are used.
"""
from __future__ import annotations

import itertools
import logging
import queue
import threading
import time

from acq4.util import ptime
from typing import TYPE_CHECKING, Any, Callable

from .futures import MoveCancelled, MoveRequest, MoveState, RequestFuture

if TYPE_CHECKING:
    from .backend import StageBackend
    from .driver import StageDriver

logger = logging.getLogger(__name__)


class StageControlThread:
    """Thread that owns a StageDriver's backend and hardware-derived state.

    Calls the backend (and nothing else does): ``open`` first, then queued requests and a
    poll every *poll_interval* seconds, then ``close``.

    Parameters
    ----------
    driver : StageDriver
        Owner; named in futures and errors.
    backend : StageBackend
        Hardware layer.
    poll_interval : float
        Seconds between polls.
    stop_timeout : float
        Seconds to wait for motion to cease (``backend.stop_before_move`` only) before
        failing the move waiting on it.
    position_change_threshold : float | dict | None
        Per-axis distance the position must move before the position callback fires; a
        dict maps axis -> threshold (missing axes: 0). None fires on every poll.

    Attributes read by other threads
    --------------------------------
    state : str
        'new', then 'running' from :meth:`start`, then 'closed' once shut down (final).
    position : dict | None
        Snapshot from the latest position read; None before the first.
    position_callback : callable | None
        Written by any thread; called on this thread with a copy of each reported position.
    """

    def __init__(self, driver: StageDriver, backend: StageBackend, poll_interval: float,
                 stop_timeout: float, position_change_threshold: float | dict | None):
        self.driver = driver
        self.backend = backend
        self.poll_interval = poll_interval
        self.stop_timeout = stop_timeout
        self.position_change_threshold = position_change_threshold
        # entries (priority, seq, fut, args): cancels (priority 0) overtake other requests,
        # which run in submission order
        self.queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self.state = 'new'
        self.position: dict | None = None
        self.position_callback: Callable[[dict], Any] | None = None
        self.opened = RequestFuture('open', driver, f"connect {type(driver).__name__}")
        self.active_move: MoveRequest | None = None
        self.active_handle = None   # backend handle of active_move
        # stop_before_move only: move waiting for motion to cease, and the handle of the motion ceasing
        self.pending_move: MoveRequest | None = None
        self.stopping = None
        self.stopping_since = 0.0
        self._last_reported_pos: dict | None = None
        self._poll_failing = {}
        self._handlers = {
            'move': self._handle_move,
            'stop': self._handle_stop,
            'cancel': self._handle_cancel,
            'call': self._handle_call,
        }
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name=f"{type(driver).__name__}ControlThread")

    def start(self) -> RequestFuture:
        """Start the thread; returns ``opened``, finished when ``backend.open`` returns or raises."""
        if self.state != 'new':
            raise RuntimeError(f"{self.driver} is already {'connected' if self.state == 'running' else 'closed'}")
        self.state = 'running'
        self.thread.start()
        return self.opened

    def enqueue(self, fut: RequestFuture, **args) -> RequestFuture:
        """Queue *fut* for this thread, or fail it at once if the thread is not running. Any thread.

        *args* are passed to the request's handler as keyword arguments; keys the handler does
        not accept, or missing keys, fail *fut* with a TypeError cause. Cancel requests are
        handled before any request queued earlier; the rest in order.
        """
        if self.state != 'running':
            fut._finish('failed', message="rejected: driver is not connected")
            return fut
        self.queue.put((0 if fut.kind == 'cancel' else 1, next(self._seq), fut, args))
        if self.state == 'closed':
            # shut down since the check above; its final drain may have missed fut
            self._reject_queued()
        return fut

    def quit(self) -> RequestFuture:
        """Queue shutdown and return its future without waiting. Any thread.

        The future finishes after requests queued before it have run and ``backend.close``
        has returned; it fails at once if the thread is not running.
        """
        return self.enqueue(RequestFuture('quit', self.driver, 'close driver'))

    # ---- loop ----

    def _run(self):
        self.opened.start_time = ptime.time()
        try:
            self.backend.open()
        except Exception as exc:
            self._shutdown()
            self.opened._finish('failed', message=f"{self.driver} failed to connect", cause=exc)
            return
        self.opened._finish('done')

        next_poll = time.monotonic()
        quit_fut = None
        while quit_fut is None:
            try:
                timeout = max(0.0, next_poll - time.monotonic())
                try:
                    _, _, fut, args = self.queue.get(timeout=timeout)
                except queue.Empty:
                    fut = None
                if fut is not None:
                    if fut.kind == 'quit':
                        quit_fut = fut
                        quit_fut.start_time = ptime.time()
                    else:
                        self._dispatch(fut, args)

                now = time.monotonic()
                if now >= next_poll and quit_fut is None:
                    self._poll()
                    next_poll += self.poll_interval
                    if next_poll < now:
                        next_poll = now + self.poll_interval
            except Exception:
                logger.exception("Unexpected error in %s; continuing", self.thread.name)
        self._shutdown()
        quit_fut._finish('done')

    def _shutdown(self):
        if self.active_move is not None:
            self.active_move._finish('failed', message="abandoned: driver closed",
                                     final_position=self.position)
        if self.pending_move is not None:
            self.pending_move._finish('failed', message="abandoned: driver closed")
        self.active_move = self.active_handle = self.pending_move = self.stopping = None
        try:
            self.backend.close()
        except Exception:
            logger.exception("Error closing backend")
        self.state = 'closed'
        self._reject_queued()

    def _reject_queued(self):
        """Fail every queued request. Each is taken by one thread only (Queue.get)."""
        while True:
            try:
                fut = self.queue.get_nowait()[2]
            except queue.Empty:
                return
            fut._finish('failed', message="rejected: driver closed")

    def _dispatch(self, fut: RequestFuture, args: dict):
        """Run the handler for *fut* with ``**args``; any exception, including a TypeError from bad keys, fails *fut*."""
        if fut.done():  # move cancelled while queued
            return
        fut.start_time = ptime.time()
        try:
            handler = self._handlers.get(fut.kind)
            if handler is None:
                raise ValueError(f"Unknown request kind {fut.kind!r}")
            handler(fut, **args)
        except Exception as exc:
            fut._finish('failed', cause=exc)

    def _poll(self):
        backend = self.backend
        try:
            pos = backend.read_position()
        except Exception:
            self._log_poll_error('read_position')
        else:
            self._poll_ok('read_position')
            self._update_position(pos)

        try:
            backend.poll_extra()
        except Exception:
            self._log_poll_error('poll_extra')
        else:
            self._poll_ok('poll_extra')

        if self.stopping is not None:
            self._check_stopping()
        if self.active_move is not None:
            self._check_active()

    def _update_position(self, pos: dict):
        pos = dict(pos)
        self.position = pos
        last = self._last_reported_pos
        if last is not None and not self._exceeds_threshold(last, pos):
            return
        self._last_reported_pos = pos
        cb = self.position_callback
        if cb is not None:
            try:
                cb(dict(pos))
            except Exception:
                logger.exception("Error in position callback")

    def _exceeds_threshold(self, last: dict, pos: dict) -> bool:
        thresh = self.position_change_threshold
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
        move, handle = self.active_move, self.active_handle
        try:
            state, reason = self.backend.check_move(handle)
        except Exception as exc:
            self._clear_active()
            move._finish('failed', message="failed while checking status", cause=exc,
                         final_position=self.position)
            return
        if state is MoveState.MOVING:
            return
        self._clear_active()
        if state is MoveState.DONE:
            move._finish('done', final_position=self._read_final_position(move, handle))
        elif state is MoveState.FAILED:
            move._finish('failed', message=reason or 'failed', final_position=self.position)
        else:
            move._finish('failed', message=f"check_move returned invalid state {state!r}",
                         final_position=self.position)

    def _clear_active(self):
        self.active_move = self.active_handle = None

    def _read_final_position(self, move: MoveRequest, handle) -> dict | None:
        """Read and publish the position of completed *move*; the latest known position if the read fails."""
        try:
            pos = self.backend.final_position(handle)
        except Exception:
            logger.exception("Error in final_position for %s; using last known position", move)
            return self.position
        self._update_position(pos)
        return pos

    def _begin_stopping(self, handle):
        """Wait for *handle*'s motion to cease before starting a pending move (stop_before_move only)."""
        if self.backend.stop_before_move:
            self.stopping = handle
            self.stopping_since = time.monotonic()

    def _check_stopping(self):
        try:
            moving = self.backend.is_moving(self.stopping)
        except Exception as exc:
            self.stopping = None
            self._fail_pending("failed waiting for previous motion to stop", cause=exc)
            return
        if moving:
            if time.monotonic() - self.stopping_since > self.stop_timeout:
                self.stopping = None
                self._fail_pending(f"previous motion did not stop within {self.stop_timeout} s")
            return
        self.stopping = None
        if self.pending_move is not None:
            move, self.pending_move = self.pending_move, None
            self._start_move(move)

    def _fail_pending(self, message: str, cause: BaseException | None = None):
        if self.pending_move is not None:
            move, self.pending_move = self.pending_move, None
            move._finish('failed', message=message, cause=cause)

    # ---- request handlers: called as handler(fut, **args) ----

    def _handle_move(self, move: MoveRequest):
        move.status = 'moving'
        moving, handle = self.active_move, self.active_handle
        if moving is not None:
            moving._finish('interrupted', message=f"interrupted by {move}", final_position=self.position)
            self._clear_active()
        if self.pending_move is not None:
            self.pending_move._finish('interrupted', message=f"interrupted by {move}")
            self.pending_move = None

        if self.backend.stop_before_move and moving is not None:
            self.backend.stop(f"interrupted by {move}")
            self._begin_stopping(handle)
        if self.stopping is not None:
            self.pending_move = move
        else:
            self._start_move(move)

    def _start_move(self, move: MoveRequest):
        self.active_move = move
        try:
            self.active_handle = self.backend.start_move(move.target, move.speed, **move.kwds)
        except Exception as exc:
            self._clear_active()
            # start_move may have commanded some axes before raising
            move._finish('failed', message='failed to start', cause=exc, final_position=self.position)

    def _end_motion(self, status: str, reason: str):
        """Send stop and resolve active/pending moves with *status*."""
        active, handle = self.active_move, self.active_handle
        self.backend.stop(reason)
        if active is not None:
            self._begin_stopping(handle)
        message = f"{status}: {reason}"
        if active is not None:
            active._finish(status, message=message, final_position=self.position)
        if self.pending_move is not None:
            self.pending_move._finish(status, message=message)
        self._clear_active()
        self.pending_move = None

    def _handle_stop(self, fut: RequestFuture, *, reason: str):
        self._end_motion('stopped', reason)
        fut._finish('done')

    def _handle_cancel(self, fut: RequestFuture, *, move: MoveRequest):
        if move is self.active_move:
            handle = self.active_handle
            self.backend.stop(fut.reason)
            self._clear_active()
            self._begin_stopping(handle)
            move._finish('cancelled', message='cancelled', final_position=self.position)
        else:
            # queued or waiting on stop_before_move; no-op if already finished
            if move is self.pending_move:
                self.pending_move = None
            move._finish('cancelled', message='cancelled before it started')
        fut._finish('done')

    def _handle_call(self, fut: RequestFuture, *, fn: Callable, args: tuple, interrupt: bool):
        if interrupt and (self.active_move is not None or self.pending_move is not None):
            self._end_motion('interrupted', f"interrupted by {fut.reason or 'device operation'}")
        try:
            result = fn(*args)
        except MoveCancelled as exc:
            fut._finish('cancelled', cause=exc)
            return
        fut._finish('done', result=result)
