from __future__ import annotations

import logging
import queue
import sys
import threading
import time

import numpy as np
from teleprox.proxy import ObjectProxy

from .motionsynergy_api import get_motionsynergyapi, initialize, check, MotionSynergyException

logger = logging.getLogger(__name__)


#: Rate (Hz) the control loop aims to poll and report stage position at, by default.
#:
#: GetActualPosition costs ~4ms per axis at rest and ~9ms on every axis once any one of
#: them is moving, so a three-axis loop carries ~30-40ms of work before it waits. 20Hz
#: is a rate that holds while moving; idle the loop can manage nearer 30Hz.
DEFAULT_TARGET_UPDATE_RATE = 20.0


class SmartStageControlThread:
    """Monitor position, initiate and track move status

    This thread is used by the main SmartStage class; it has no user-facing API
    other than the SmartStageRequestFuture objects it returns.
    """

    #: Weight given to the newest loop period in the running average behind
    #: :meth:`loop_rate`; 0.05 averages over roughly the last 20 iterations.
    LOOP_RATE_SMOOTHING = 0.05

    def __init__(
        self,
        pos_callback,
        target_update_rate,
        callback_threshold,
        move_complete_threshold,
        enabled_poll_interval,
    ):
        self.pos_callback = pos_callback
        self.target_update_rate = target_update_rate
        self.callback_threshold = callback_threshold
        self.move_complete_threshold = move_complete_threshold
        self.enabled_poll_interval = enabled_poll_interval

        self.motionsynergy, self.instrument_settings = get_motionsynergyapi()
        initialize()
        self.product = self.motionsynergy.GetFirstProduct()
        self.productType = self.product.ProductType
        # TODO: all available axes; may need splitting up if there are multiple devices
        self.axes = list(self.motionsynergy.AxisList)

        self.last_enabled_state = None
        self.enable_state_callback = None
        # perf_counter of the last GetIsEnabled sweep, or None if it has never run
        self.last_enabled_poll = None
        self.last_known_pos = None
        self.last_reported_pos = None
        # running average of the loop period (s); None until two iterations have run.
        # Written by the control thread, read unlocked by anyone.
        self.mean_loop_period = None
        # perf_counter the current iteration should finish waiting at; see _poll_timeout
        self._next_poll_deadline = time.perf_counter()
        self.quit_request: SmartStageRequestFuture | None = None
        self.current_move: SmartStageRequestFuture | None = None
        self.request_queue = queue.Queue()

        self.thread = None
        self.start_thread()

    def set_callback(self, cb):
        """Set the callable invoked with a new position whenever the stage has moved.

        An ObjectProxy callback is switched to fire-and-forget (``sync='off'``); a
        blocking round trip costs ~7ms in every poll iteration. Exceptions raised by
        such a callback are logged in the callback's own process, not raised here.
        """
        if isinstance(cb, ObjectProxy):
            cb._set_proxy_options(sync='off')
        self.pos_callback = cb

    def set_enabled_callback(self, cb):
        # if cb not in self.enable_state_callbacks:
        self.enable_state_callback = cb

    def start_thread(self):
        if self.is_running():
            raise RuntimeError('Thread is already running')
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    def request(self, req, **kwds):
        if self.thread is None or not self.thread.is_alive():
            raise RuntimeError('SmartStage control thread is not running')
        fut = SmartStageRequestFuture(self, req, kwds)
        self.request_queue.put(fut)
        return fut

    def loop_rate(self):
        """Return the measured rate (Hz) at which this loop polls the stage position.

        A ceiling on the rate position callbacks arrive at: a stage moving slower than
        ``callback_threshold`` per loop period reports on only some iterations. Returns
        ``target_update_rate`` until two iterations have been timed.
        """
        period = self.mean_loop_period
        if period is None:
            return self.target_update_rate
        return 1.0 / period

    def _poll_timeout(self):
        """Return how long to wait for a request before polling the stage again.

        Whatever is left of the target period after this iteration's work. The deadline
        advances by whole periods rather than from now, so that an overshooting wait
        (~10ms on Windows) is absorbed by the next one instead of accumulating. An
        iteration outlasting its period returns 0; the missed slot is given up, not
        chased.
        """
        now = time.perf_counter()
        period = 1.0 / self.target_update_rate
        self._next_poll_deadline = max(self._next_poll_deadline + period, now)
        return self._next_poll_deadline - now

    def _run(self):
        last_loop_start = None
        self._next_poll_deadline = time.perf_counter()
        while self.quit_request is None:
            now = time.perf_counter()
            if last_loop_start is not None:
                self._record_loop_period(now - last_loop_start)
            last_loop_start = now

            try:
                self._check_position()
            except MotionSynergyException:
                logger.exception("Error checking position")
            try:
                self._check_move_status()
            except MotionSynergyException:
                logger.exception("Error checking move status")
            try:
                self._check_enabled_state()
            except MotionSynergyException:
                logger.exception("Error checking enabled state")

            try:
                req = self.request_queue.get(timeout=self._poll_timeout())
            except queue.Empty:
                req = None

            # Drain: re-aims arrive faster than ~20 Hz; each costs only ~0.3ms.
            while req is not None:
                try:
                    self._handle_request(req)
                except MotionSynergyException:
                    logger.exception(f"Error handling request {req.request}({req.kwds})")
                if self.quit_request is not None:
                    break
                try:
                    req = self.request_queue.get_nowait()
                except queue.Empty:
                    req = None

        self.quit_request.set_result(None)

    def _record_loop_period(self, period):
        """Fold one iteration's *period* (seconds) into the average behind :meth:`loop_rate`."""
        if self.mean_loop_period is None:
            self.mean_loop_period = period
        else:
            w = self.LOOP_RATE_SMOOTHING
            self.mean_loop_period = (1 - w) * self.mean_loop_period + w * period

    def _check_position(self):
        """Read the position, invoking ``pos_callback`` if any axis moved further than
        ``callback_threshold`` since it was last invoked."""
        pos = self._get_pos()

        moved_enough = self.last_reported_pos is None or bool(
            np.any(np.abs(pos - self.last_reported_pos) > self.callback_threshold)
        )
        if self.pos_callback is not None and moved_enough:
            try:
                self.pos_callback(pos)
                self.last_reported_pos = pos
            except Exception:
                # the loop is this stage's only supervisor; a bad callback must not end it
                logger.exception("Error in position callback")
        self.last_known_pos = pos

    def _check_move_status(self):
        """Complete the current move once every axis it commanded has come to rest."""
        if self.current_move is None:
            return
        if all(task.IsCompleted for task in self.current_move.tasks):
            alerts = [
                f"{task.Result.Alert.UserDescription}; {task.Result.Alert.Description}"
                for task in self.current_move.tasks
                if not task.Result.Success
            ]

            if len(alerts) == 0:
                logger.debug(f"Move {self.current_move.label} completed successfully.")
                self.current_move.set_result(None)
            else:
                logger.warning(f"Move {self.current_move.label} failed: {', '.join(alerts)}")
                self.current_move.fail(f"Move {self.current_move.label} failed: {', '.join(alerts)}")
            self.current_move = None

    def _check_enabled_state(self, force=False):
        """Re-read the per-axis enabled state, at most once per ``enabled_poll_interval``.

        Costs one GetIsEnabled call per axis: ~9ms at rest, over 20ms while a move keeps
        the API busy. An external change (the MotionSynergy tray menu) can go unseen for
        up to one interval. Pass *force* to poll regardless.
        """
        now = time.perf_counter()
        if (
            not force
            and self.last_enabled_poll is not None
            and now - self.last_enabled_poll < self.enabled_poll_interval
        ):
            return
        self.last_enabled_poll = now

        enabled_state = self._get_enabled_state()
        if enabled_state == self.last_enabled_state:
            return
        self.last_enabled_state = enabled_state
        if self.enable_state_callback is not None:
            try:
                self.enable_state_callback(enabled_state)
            except Exception as exc:
                logger.exception("Error in enabled state callback")

    def _handle_request(self, fut: SmartStageRequestFuture):
        cmd = fut.request
        try:
            if cmd == 'stop':
                self._handle_stop()
                fut.set_result(None)
            elif cmd == 'position':
                fut.set_result(self._get_pos())
            elif cmd == 'move':
                self._handle_move(fut)
            elif cmd == 'quit':
                self.quit_request = fut
            elif cmd == 'cancel':
                self._handle_cancel(fut)
            elif cmd == 'disable':
                self._handle_disable(fut)
            elif cmd == 'enable':
                self._handle_enable(fut)
            elif cmd == 'disable_axis':
                self._handle_disable_axis(fut)
            elif cmd == 'enable_axis':
                self._handle_enable_axis(fut)
            elif cmd == 'enabled_state':
                fut.set_result(self._get_enabled_state())
            else:
                raise ValueError(f'unrecognized request {cmd}')

        except Exception:
            fut.set_exc_info(sys.exc_info())

    def _handle_move(self, fut):
        """Re-aim the stage at a new target, replacing any move already running.

        ``MoveContinuous`` redirects an axis in flight without halting it (~1.3ms for
        three axes vs ~230ms through ``Stop()``). The replaced request fails without
        halting the hardware.
        """
        superseded = self.current_move
        if superseded is not None:
            superseded.fail(
                f'Move {superseded.label} superseded by new move request {fut.label}.'
            )
            self.current_move = None
        logger.debug(f"Starting move {fut.label} to pos={fut.kwds['pos']} speed={fut.kwds['speed']}.")
        fut.tasks, fut.axes_commanded = self._move(
            pos=fut.kwds['pos'],
            speed=fut.kwds['speed'],
            acceleration=fut.kwds['acceleration'],
            moving=superseded.axes_commanded if superseded is not None else frozenset(),
        )
        self.current_move = fut

    def _stop(self, reason):
        results = [axis.Stop() for axis in self.axes]
        if self.current_move is not None:
            self.current_move.fail(reason)
            self.current_move = None
        for result in results:
            check(result)

    def _handle_stop(self):
        self._stop(reason='Stopped by request.')

    def _handle_cancel(self, fut):
        move_req = fut.kwds['move_req']
        if move_req is self.current_move and not move_req.done():
            self._stop(f"Move {move_req.label} was cancelled.")
        fut.set_result(None)

    def _handle_disable(self, fut):
        # TODO: cancel any current move
        self._stop(reason='Motors disabled by request.')
        for axis in self.axes:
            if axis.GetIsEnabled().Value is not False:
                check(axis.Disable(), error_msg="Error disabling axis: ")
        self._check_enabled_state(force=True)
        fut.set_result(None)

    def _handle_enable(self, fut):
        for axis in self.axes:
            if axis.GetIsEnabled().Value is not True:
                check(axis.Enable(), error_msg="Error enabling axis: ")
        self._check_enabled_state(force=True)
        fut.set_result(None)

    def _handle_disable_axis(self, fut):
        axis_index = fut.kwds['axis_index']
        axis = self.axes[axis_index]
        if axis.GetIsEnabled().Value is not False:
            check(axis.Disable(), error_msg=f"Error disabling axis {axis_index}: ")
        self._check_enabled_state(force=True)
        fut.set_result(None)

    def _handle_enable_axis(self, fut):
        axis_index = fut.kwds['axis_index']
        axis = self.axes[axis_index]
        if axis.GetIsEnabled().Value is not True:
            check(axis.Enable(), error_msg=f"Error enabling axis {axis_index}: ")
        self._check_enabled_state(force=True)
        fut.set_result(None)

    def _get_enabled_state(self):
        states = tuple(axis.GetIsEnabled().Value for axis in self.axes)
        return states

    def _get_pos(self):
        results = [check(axis.GetActualPosition(), error_msg="Error getting axis position: ") for axis in self.axes]
        return np.array([float(result.Value) for result in results])

    def _move(self, pos, speed, acceleration, moving=frozenset()):
        """Command a move, re-aiming any axis that is already running one.

        Speed and acceleration are split across the axes in proportion to the distance
        each has left, so travel is close to linear.

        Parameters
        ----------
        pos : sequence
            Target position (mm) per axis; None leaves that axis uncommanded, and stops
            it if it is in *moving*.
        speed : float
            Speed (mm/s) along the path.
        acceleration : float
            Acceleration and deceleration (mm/s^2) along the path.
        moving : collection of int
            Indices of the axes the superseded move commanded.

        Returns
        -------
        tasks : list
            One per commanded axis, completing when that axis comes to rest.
        commanded : frozenset of int
            Indices of the axes commanded.
        """
        assert len(pos) == len(self.axes), f"Expected {len(self.axes)} coordinates, got {len(pos)}"
        pos = list(pos)
        # Cached from the poll loop, not a fresh read: reading three axes costs ~83ms
        # while any is moving.
        current_pos = self.last_known_pos
        if current_pos is None:
            current_pos = self._get_pos()
        target_pos = np.array([current_pos[i] if x is None else x for i, x in enumerate(pos)])
        diff = target_pos - current_pos
        dist = np.linalg.norm(diff)
        scale_per_axis = np.abs(diff) / dist if dist > 0 else np.zeros(len(diff))
        speed_per_axis = speed * scale_per_axis
        accel_per_axis = acceleration * scale_per_axis

        tasks = []
        commanded = set()
        for i, axis in enumerate(self.axes):
            if pos[i] is None:
                if i in moving:
                    # unchecked: Stop() itself returns in ~0.04ms, awaiting its task 143ms
                    axis.Stop()
                continue
            if abs(diff[i]) < self.move_complete_threshold and i not in moving:
                continue
            spd = max(1e-6, speed_per_axis[i])
            acc = max(.1, accel_per_axis[i])
            # MoveContinuous(position, acceleration, velocity, deceleration)
            check(
                axis.MoveContinuous(pos[i], acc, spd, acc),
                error_msg="Error starting axis move: ",
            )
            # after the command: on an axis at rest this Task completes immediately
            tasks.append(axis.WaitForContinuousMoveToComplete())
            commanded.add(i)
        return tasks, frozenset(commanded)


class SmartStageRequestFuture:
    """Represents a future result to be generated following a request to the control thread.
    """

    class FutureError(Exception):
        pass

    def __init__(self, ctrl_thread, req, kwds):
        self.thread: SmartStageControlThread = ctrl_thread
        self.request = req
        self.name = kwds.pop('name', None)
        self.kwds = kwds
        self._callback = None
        self._cb_lock = threading.Lock()
        self._done = threading.Event()
        self.result = None
        self.exc_info = None
        self.error = None
        self.tasks = []
        #: indices of the axes this request commanded; a superseding request re-commands
        #: them even where it would otherwise leave them alone
        self.axes_commanded = frozenset()

    @property
    def label(self):
        """Human-readable identifier for this request, for use in log messages."""
        if self.name:
            return f"'{self.name}'"
        if self.request == 'move':
            pos = self.kwds.get('pos')
            return f"move(pos={pos})"
        return f"{self.request}"

    def done(self):
        """Return True if the request has finished."""
        return self._done.is_set()

    def set_callback(self, cb):
        """Set a callback to be invoked when this request is finished.

        If the request is already finished, then the callback is invoked immediately."""
        with self._cb_lock:
            # if already finished, run the callback now
            run_cb = self.done()
            if not run_cb:
                # otherwise, leave the callback for later
                self._callback = cb
        if run_cb:
            cb(self)

    def cancel(self):
        """Cancel the request if it is not already complete.

        Only supported for move requests.
        """
        if self.request != 'move':
            raise TypeError('Can only cancel move requests')
        return self.thread.request("cancel", move_req=self)

    def wait(self, timeout=5.0):
        """Wait for the request to complete, or for the timeout to elapse.

        If the request succeeds, then its result value is returned.
        If the timeout expires, then raise TimeoutError.
        If the request fails, then raise an exception with more information.
        """
        if not self._done.wait(timeout=timeout):
            raise TimeoutError(f'Timeout waiting for {self.label} to complete')
        elif self.exc_info is not None:
            raise self.FutureError(
                f"An error occurred during {self.label}"
            ) from self.exc_info[1]
        elif self.error is not None:
            raise self.FutureError(self.error)
        return self.result

    def set_result(self, result):
        self.result = result
        self._finish()

    def set_exc_info(self, exc):
        self.exc_info = exc
        self._finish()

    def fail(self, reason):
        self.error = reason
        self._finish()

    def _finish(self):
        with self._cb_lock:
            self._done.set()
            cb = self._callback
            self._callback = None
        if cb is not None:
            try:
                cb(self)
            except Exception:
                logger.exception(f"Error invoking callback for {self}")

    @property
    def target_pos(self):
        assert self.request == 'move'
        return self.kwds['pos']
