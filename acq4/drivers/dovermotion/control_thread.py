from __future__ import annotations

import logging
import queue
import sys
import threading

import numpy as np

from .motionsynergy_api import get_motionsynergyapi, initialize, check, MotionSynergyException

logger = logging.getLogger(__name__)


class SmartStageControlThread:
    """Monitor position, initiate and track move status

    This thread is used by the main SmartStage class; it has no user-facing API
    other than the SmartStageRequestFuture objects it returns.
    """

    def __init__(self, pos_callback, poll_interval, callback_threshold, move_complete_threshold):
        self.pos_callback = pos_callback
        self.poll_interval = poll_interval
        self.callback_threshold = callback_threshold
        self.move_complete_threshold = move_complete_threshold

        self.motionsynergy, self.instrument_settings = get_motionsynergyapi()
        initialize()
        self.product = self.motionsynergy.GetFirstProduct()
        self.productType = self.product.ProductType
        # for now, axes are all the axes available. Later we may want to split these up if there are multiple devices..
        self.axes = list(self.motionsynergy.AxisList)

        self.last_pos = None
        self.last_enabled_state = None
        self.enable_state_callbacks = []
        self.quit_request: SmartStageRequestFuture | None = None
        self.current_move: SmartStageRequestFuture | None = None
        self.request_queue = queue.Queue()

        self.thread = None
        self.start_thread()

    def set_callback(self, cb):
        self.pos_callback = cb

    def add_enabled_state_callback(self, cb):
        if cb not in self.enable_state_callbacks:
            self.enable_state_callbacks.append(cb)

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

    def _run(self):
        while self.quit_request is None:
            # check on position and move in progress
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
                req = self.request_queue.get(timeout=self.poll_interval)
            except queue.Empty:
                req = None

            if req is not None:
                try:
                    self._handle_request(req)
                except MotionSynergyException:
                    logger.exception(f"Error handling request {req.request}({req.kwds})")

        self.quit_request.set_result(None)

    def _check_position(self):
        """Check the current position and move status
        """
        pos = self._get_pos()

        # check position and invoke change callback 
        if self.pos_callback is not None:
            if self.last_pos is None:
                self.pos_callback(pos)
            else:
                diff = np.abs(pos - self.last_pos)
                if np.any(diff > self.callback_threshold):
                    try:
                        self.pos_callback(pos)
                    except Exception:
                        logger.exception("Error in position callback")
        self.last_pos = pos

    def _check_move_status(self):
        if self.current_move is None:
            return
        if all(task.IsCompleted for task in self.current_move.tasks):
            alerts = [
                f"{task.Result.Alert.UserDescription}; {task.Result.Alert.Description}"
                for task in self.current_move.tasks
                if not task.Result.Success
            ]

            if len(alerts) == 0:
                self.current_move.set_result(None)
            else:
                self.current_move.fail(f"Move failed: {', '.join(alerts)}")
            self.current_move = None

    def _check_enabled_state(self):
        enabled_state = self._get_enabled_state()
        if enabled_state == self.last_enabled_state:
            return
        self.last_enabled_state = enabled_state
        for cb in list(self.enable_state_callbacks):
            try:
                cb(enabled_state)
            except Exception:
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
            elif cmd == 'enabled_state':
                fut.set_result(self._get_enabled_state())
            else:
                raise ValueError(f'unrecognized request {cmd}')

        except Exception:
            fut.set_exc_info(sys.exc_info())

    def _handle_move(self, fut):
        if self.current_move is not None:
            self._stop(reason='Interrupted by another move request.')
        fut.tasks = self._move(
            pos=fut.kwds['pos'],
            speed=fut.kwds['speed'],
            acceleration=fut.kwds['acceleration'],
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
            self._stop(f"Request to {move_req.request} was cancelled")
        fut.set_result(None)

    def _handle_disable(self, fut):
        # TODO: cancel any current move
        self._stop(reason='Motors disabled by request.')
        for axis in self.axes:
            if axis.GetIsEnabled().Value is not False:
                check(axis.Disable(), error_msg="Error disabling axis: ")
        fut.set_result(None)

    def _handle_enable(self, fut):
        for axis in self.axes:
            if axis.GetIsEnabled().Value is not True:
                check(axis.Enable(), error_msg="Error enabling axis: ")
        fut.set_result(None)

    def _get_enabled_state(self):
        states = tuple(axis.GetIsEnabled().Value for axis in self.axes)
        return states

    def _get_pos(self):
        results = [check(axis.GetActualPosition(), error_msg="Error getting axis position: ") for axis in self.axes]
        return np.array([float(result.Value) for result in results])

    def _move(self, pos, speed, acceleration):
        """Directly request a move.
        
        To ensure a mostly linear travel, speed/acceleration are distributed to the axes based on the relative distance
        to the target.
        
        Returns a list of tasks that can be waited on.
        """
        assert len(pos) == len(self.axes), f"Expected {len(self.axes)} coordinates, got {len(pos)}"
        pos = list(pos)
        current_pos = self._get_pos()
        target_pos = np.array([current_pos[i] if x is None else x for i, x in enumerate(pos)])
        diff = target_pos - current_pos
        dist = np.linalg.norm(diff)
        scale_per_axis = np.abs(diff) / dist
        speed_per_axis = speed * scale_per_axis
        accel_per_axis = acceleration * scale_per_axis

        for i, axis in enumerate(self.axes):
            if np.abs(diff[i]) < self.move_complete_threshold:
                pos[i] = None
            if pos[i] is not None:
                check(axis.SetVelocity(speed_per_axis[i]), error_msg="Error setting axis speed: ")
                check(axis.SetAcceleration(accel_per_axis[i]), error_msg="Error setting axis acceleration: ")
        return [
            axis.MoveAbsolute(pos[i])
            for i, axis in enumerate(self.axes)
            if pos[i] is not None
        ]


class SmartStageRequestFuture:
    """Represents a future result to be generated following a request to the control thread.
    """

    class FutureError(Exception):
        pass

    def __init__(self, ctrl_thread, req, kwds):
        self.thread: SmartStageControlThread = ctrl_thread
        self.request = req
        self.kwds = kwds
        self._callback = None
        self._cb_lock = threading.Lock()
        self._done = threading.Event()
        self.result = None
        self.exc_info = None
        self.error = None
        self.tasks = []

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
            raise TimeoutError(f'Timeout waiting for {self.request} to complete')
        elif self.exc_info is not None:
            raise self.FutureError(
                f"An error occurred during the request to {self.request}"
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
            cb(self)

    @property
    def target_pos(self):
        assert self.request == 'move'
        return self.kwds['pos']
