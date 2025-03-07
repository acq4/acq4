from __future__ import annotations

import queue
import sys
import threading
import numpy as np

from .motionsynergy_api import get_motionsynergyapi, initialize


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
        self.quit_request: SmartStageRequestFuture | None = None
        self.current_move: SmartStageRequestFuture | None = None
        self.request_queue = queue.Queue()

        self.thread = None
        self.start_thread()

    def start_thread(self):
        if self.thread is not None and self.thread.is_alive():
            raise RuntimeError('Thread is already running')
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def request(self, req, **kwds):
        fut = SmartStageRequestFuture(self, req, kwds)
        self.request_queue.put(fut)
        return fut

    def _run(self):
        while self.quit_request is None:
            # check on position and move in progress
            self._check_position()
            self._check_move_status()

            try:
                req = self.request_queue.get(timeout=self.poll_interval)
            except queue.Empty:
                req = None

            if req is not None:
                self._handle_request(req)

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
                    self.pos_callback(pos)
        self.last_pos = pos

    def _check_move_status(self):
        if self.current_move is None:
            return
        if all(task.IsCompleted for task in self.current_move.tasks if task is not None):
            alerts = []
            for ax,task in enumerate(self.current_move.tasks):
                if task is None:
                    continue
                result = task.Result
                if result.Success is False:
                    desc = result.Alert.UserDescription 
                    if desc == '':
                        desc = result.Alert.Description
                    alerts.append(desc)
                
            if len(alerts) == 0:
                self.current_move.set_result(None)
            else:
                self.current_move.fail(f"Move failed: {', '.join(alerts)}")
            self.current_move = None

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
        for axis in self.axes:
            axis.Stop()
        if self.current_move is not None:
            self.current_move.fail(reason)
            self.current_move = None

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
            axis.Disable()
        fut.set_result(None)

    def _handle_enable(self, fut):
        for axis in self.axes:
            axis.Enable()
        fut.set_result(None)

    def _get_pos(self):
        return np.array([float(axis.GetActualPosition().Value) for axis in self.axes])

    def _move(self, pos, speed, acceleration):
        """Directly request a move.
        
        To ensure a mostly linear travel, speed/acceleration are distributed to the axes based on the relative distance to the target.
        
        Returns a list of tasks that can be waited on.
        """
        assert len(pos) == len(self.axes), f"Expected {len(self.axes)} coordinates, got {len(pos)}"
        current_pos = self._get_pos()
        target_pos = np.array([current_pos[i] if x is None else x for i,x in enumerate(pos)])
        diff = target_pos - current_pos
        dist = np.linalg.norm(diff)
        scale_per_axis = np.abs(diff) / dist
        speed_per_axis = speed * scale_per_axis
        accel_per_axis = acceleration * scale_per_axis

        for i,axis in enumerate(self.axes):
            if np.abs(diff[i]) < self.move_complete_threshold:
                pos[i] = None
            if pos[i] is not None:
                axis.SetVelocity(speed_per_axis[i])
                axis.SetAcceleration(accel_per_axis[i])
        tasks = []
        for i,axis in enumerate(self.axes):
            if pos[i] is None:
                tasks.append(None)
            else:
                tasks.append(axis.MoveAbsolute(pos[i]))
        return tasks


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
        return self.thread.cancel_move(self)

    def wait(self, timeout=5.0):
        """Wait for the request to complete, or for the timeout to elapse.
        
        If the request succeeds, then its result value is returned.
        If the timeout expires, then raise TimeoutError.
        If the request fails, then raise an exception with more information.
        """
        if self._done.wait(timeout=timeout) is False:
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
