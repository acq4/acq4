"""Device-independent control thread for motorized stages.

Each StageDriver has one StageControlThread, which performs all of the driver's hardware I/O
and is the only writer of hardware-derived state. Other threads submit requests through its
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

from .futures import MoveRequest, MoveState, RequestFuture

if TYPE_CHECKING:
    from .driver import StageDriver

logger = logging.getLogger(__name__)


class StageControlThread:
    """Thread that owns a StageDriver's hardware link and hardware-derived state.

    Runs the driver's hooks (and nothing else does): ``_open_link`` first, then queued
    requests and a poll every ``driver.poll_interval`` seconds, then ``_close_link``.

    Attributes read by other threads
    --------------------------------
    state : str
        'new', then 'running' from :meth:`start`, then 'closed' once shut down (final).
    position : dict | None
        Snapshot from the latest position read; None before the first.
    position_callback : callable | None
        Written by any thread; called on this thread with a copy of each reported position.
    """

    def __init__(self, driver: StageDriver):
        self.driver = driver
        # entries (priority, seq, fut, args): cancels (priority 0) overtake other requests,
        # which run in submission order
        self.queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self.state = 'new'
        self.position: dict | None = None
        self.position_callback: Callable[[dict], Any] | None = None
        self.opened = RequestFuture('open', driver, f"connect {type(driver).__name__}")
        self.active_move: MoveRequest | None = None
        # stop_before_move only: move waiting for motion to cease, and the move whose motion is ceasing
        self.pending_move: MoveRequest | None = None
        self.stopping: MoveRequest | None = None
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
        """Start the thread; returns ``opened``, finished when ``_open_link`` returns or raises."""
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

        The future finishes after requests queued before it have run and ``_close_link`` has
        returned; it fails at once if the thread is not running.
        """
        return self.enqueue(RequestFuture('quit', self.driver, 'close driver'))

    # ---- loop ----

    def _run(self):
        self.opened.start_time = ptime.time()
        try:
            self.driver._open_link()
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
                    next_poll += self.driver.poll_interval
                    if next_poll < now:
                        next_poll = now + self.driver.poll_interval
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
        self.active_move = self.pending_move = self.stopping = None
        try:
            self.driver._close_link()
        except Exception:
            logger.exception("Error in _close_link")
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
            move._finish('failed', message="failed while checking status", cause=exc,
                         final_position=self.position)
            return
        if state is MoveState.MOVING:
            return
        self.active_move = None
        if state is MoveState.DONE:
            move._finish('done', final_position=self._read_final_position(move))
        elif state is MoveState.FAILED:
            move._finish('failed', message=reason or 'failed', final_position=self.position)
        else:
            move._finish('failed', message=f"_check_move returned invalid state {state!r}",
                         final_position=self.position)

    def _read_final_position(self, move: MoveRequest) -> dict | None:
        """Read and publish the position of completed *move*; the latest known position if the read fails."""
        try:
            pos = self.driver._read_final_position(move)
        except Exception:
            logger.exception("Error in _read_final_position for %s; using last known position", move)
            return self.position
        self._update_position(pos)
        return pos

    def _check_stopping(self):
        try:
            state, _ = self.driver._check_move(self.stopping)
        except Exception as exc:
            self.stopping = None
            self._fail_pending("failed waiting for previous motion to stop", cause=exc)
            return
        if state is MoveState.MOVING:
            if time.monotonic() - self.stopping_since > self.driver.stop_timeout:
                self.stopping = None
                self._fail_pending(f"previous motion did not stop within {self.driver.stop_timeout} s")
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
        moving = self.active_move
        if moving is not None:
            moving._finish('interrupted', message=f"interrupted by {move}", final_position=self.position)
            self.active_move = None
        if self.pending_move is not None:
            self.pending_move._finish('interrupted', message=f"interrupted by {move}")
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
            # _send_move may have commanded some axes before raising
            move._finish('failed', message='failed to start', cause=exc, final_position=self.position)

    def _end_motion(self, status: str, reason: str):
        """Send stop and resolve active/pending moves with *status*."""
        active = self.active_move
        self.driver._send_stop(reason)
        if active is not None and self.driver.stop_before_move:
            self.stopping = active
            self.stopping_since = time.monotonic()
        message = f"{status}: {reason}"
        if active is not None:
            active._finish(status, message=message, final_position=self.position)
        if self.pending_move is not None:
            self.pending_move._finish(status, message=message)
        self.active_move = self.pending_move = None

    def _handle_stop(self, fut: RequestFuture, *, reason: str):
        self._end_motion('stopped', reason)
        fut._finish('done')

    def _handle_cancel(self, fut: RequestFuture, *, move: MoveRequest):
        if move is self.active_move:
            self.driver._send_stop(fut.reason)
            self.active_move = None
            if self.driver.stop_before_move:
                self.stopping = move
                self.stopping_since = time.monotonic()
            move._finish('cancelled', message='cancelled', final_position=self.position)
        else:
            # queued or waiting on stop_before_move; no-op if already finished
            if move is self.pending_move:
                self.pending_move = None
            move._finish('cancelled', message='cancelled before it started')
        fut._finish('done')

    def _handle_call(self, fut: RequestFuture, *, fn: Callable, args: tuple, kwds: dict):
        fut._finish('done', result=fn(*args, **kwds))
