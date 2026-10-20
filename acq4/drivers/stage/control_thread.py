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
from typing import TYPE_CHECKING, Any, Callable, NamedTuple

from .futures import MoveCancelled, MoveRequest, MoveState, RequestFuture

if TYPE_CHECKING:
    from .backend import StageBackend
    from .driver import StageDriver

logger = logging.getLogger(__name__)


class PositionReport(NamedTuple):
    """A position, when it was read from hardware, and whether a read has failed since.

    Snapshots are never mutated; the control thread rebinds a new one. While ``stale`` is
    true the position is frozen at a reading that is no longer confirmed, and the control
    thread refuses to start new motion.
    """

    position: dict
    time: float     # ptime.time() when *position* was read
    stale: bool

    def age(self) -> float:
        """Seconds since *position* was read from hardware."""
        return ptime.time() - self.time


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
    position_report : PositionReport | None
        Snapshot from the latest position read, with its age and whether a read has failed
        since; None before the first read.
    position : dict | None
        ``position_report``'s position; None before the first read.
    position_callback : callable | None
        Set with :meth:`set_position_callback`; called on this thread with a copy of each
        reported position.
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
        # depends on next(itertools.count()) being atomic, a CPython GIL guarantee: two
        # threads must never get the same sequence number, since heapq would then compare
        # the RequestFutures beside them and they have no ordering.
        self._seq = itertools.count()
        self.state = 'new'
        self.position_report: PositionReport | None = None
        self.position_callback: Callable[[dict], Any] | None = None
        self.opened = RequestFuture('open', driver, f"connect {type(driver).__name__}")
        self.active_move: MoveRequest | None = None
        self.active_handle = None   # backend handle of active_move
        # stop_before_move only: move waiting for motion to cease, and the handle of the motion ceasing
        self.pending_move: MoveRequest | None = None
        self.stopping = None
        self.stopping_since = 0.0
        self._last_reported_pos: dict | None = None
        self._reported_to = None    # callback _last_reported_pos was reported to
        self._poll_failing = {}
        self._handlers = {
            'move': self._handle_move,
            'stop': self._handle_stop,
            'cancel': self._handle_cancel,
            'call': self._handle_call,
        }
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name=f"{type(driver).__name__}ControlThread")

    @property
    def position(self) -> dict | None:
        """The latest position read, or None before the first."""
        report = self.position_report
        return None if report is None else report.position

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

    def set_position_callback(self, cb: Callable[[dict], Any] | None) -> None:
        """Set the position callback. Any thread.

        A new callback is called on the next poll, whatever the threshold.
        """
        self.position_callback = cb

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
                    by = self._superseding() if fut.kind == 'move' else None
                    if fut.kind == 'quit':
                        quit_fut = fut
                        quit_fut.start_time = ptime.time()
                    elif by is not None:
                        # never sent: ends as the superseding request would have ended it
                        if by.kind == 'stop':
                            fut._finish('stopped', message=f"stopped: {by.reason}")
                        elif by.kind == 'call':
                            fut._finish('interrupted', message=f"interrupted by {by.reason or 'device operation'}")
                        else:
                            fut._finish('interrupted', message=f"interrupted by {by}")
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

    def _superseding(self) -> RequestFuture | None:
        """The queued request that would at once end a move about to be dispatched, if any.

        That is the next queued request that is not a cancel, if it is a move, a stop, or
        an interrupting call. Peeks at the queue's heap without dequeuing.
        """
        with self.queue.mutex:
            heap = self.queue.queue
            if heap and heap[0][0] == 1:
                nxt = heap[0]  # no cancel queued
            else:
                nxt = min((e for e in heap if e[0] == 1), default=None)
        if nxt is None or nxt[2].done():  # done: cancelled while queued
            return None
        fut, args = nxt[2], nxt[3]
        if fut.kind in ('move', 'stop') or (fut.kind == 'call' and args.get('interrupt', False)):
            return fut
        return None

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
            self.read_position()
        except Exception:
            self._log_poll_error('read_position')
        else:
            self._poll_ok('read_position')

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

    def read_position(self) -> dict:
        """Read the position from hardware and publish it; returns it. Control thread only.

        Marks the published position stale and re-raises if the read fails, so the caller
        hears about it and no new motion starts until a read succeeds.
        """
        try:
            pos = self.backend.read_position()
        except Exception:
            self._mark_position_stale()
            raise
        self._update_position(pos)
        return dict(pos)

    def _mark_position_stale(self):
        """Record that a position read failed: the published position is no longer confirmed."""
        report = self.position_report
        if report is not None and not report.stale:
            self.position_report = report._replace(stale=True)

    def _position_refused(self) -> str | None:
        """Why new motion must not start, or None if the position is confirmed.

        A position read that failed leaves every axis it could not read frozen at its last
        accepted value, and a move planned from that fiction runs to the wrong place. Stops,
        cancels and device operations are never refused, so a stage whose link has dropped
        for good can still be halted and recovered.
        """
        report = self.position_report
        if report is None or not report.stale:
            return None
        return (f"refused: position reads are failing, so {self.driver} does not know where it is "
                f"(last confirmed position is {report.age():.1f} s old)")

    def _update_position(self, pos: dict):
        pos = dict(pos)
        self.position_report = PositionReport(pos, ptime.time(), False)
        cb = self.position_callback
        if cb is None:
            return
        if cb is not self._reported_to:
            # reset here, not in set_position_callback, so a poll in progress cannot undo it
            self._reported_to = cb
            self._last_reported_pos = None
        last = self._last_reported_pos
        if last is not None and not self._exceeds_threshold(last, pos):
            return
        self._last_reported_pos = pos
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
            self._mark_position_stale()
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
        refused = self._position_refused()
        if refused is not None:
            # before any side effect: an active move must keep its supervision
            move._finish('failed', message=refused)
            return
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
        refused = self._position_refused()
        if refused is not None:
            # reached from _check_stopping: the read failed while the previous motion ceased
            move._finish('failed', message=refused)
            return
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
