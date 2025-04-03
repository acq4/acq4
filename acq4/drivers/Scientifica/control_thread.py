from __future__ import annotations

import queue
import sys
import threading
import time

import numpy as np

from acq4.util.debug import printExc


class ScientificaControlThread:
    """Monitor position, initiate and track move status

    This thread is used by the main Scientifica class; it has no user-facing API
    other than the ScientificaRequestFuture objects it returns.
    """

    def __init__(self, dev):
        self.dev: 'Scientifica' = dev
        self.pos_callback = None
        self.obj_callback = None
        self.default_speed = dev.getSpeed()
        self.poll_interval = 0.05
        self.move_complete_threshold = 0.5  # distance in µm from target that is considered complete

        self.last_pos = None
        self.last_obj = None
        self.quit_request: ScientificaRequestFuture | None = None
        self.current_move: ScientificaRequestFuture | None = None
        self.request_queue = queue.Queue()

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def set_pos_callback(self, func):
        """Set a callback to be invoked when the position changes.
        """
        self.pos_callback = func

    def set_obj_callback(self, func):
        """Set a callback to be invoked when the objective changes (MOC devices).
        """
        self.obj_callback = func

    def set_default_speed(self, speed):
        """Set the default speed

        The device is set to this speed immediately after each move request
        (because we temporarily change the speed for the move).
        """
        self.default_speed = speed

    def stop(self):
        """Stop the device immediately"""
        return self._request('stop')

    def move(self, pos, speed, attempts_allowed=3):
        """Move the device to *pos* (in µm) with *speed* (in µm/s)"""
        return self._request('move', pos=pos, speed=speed, attempts_allowed=attempts_allowed)

    def quit(self):
        """Quit the control thread"""
        return self._request('quit')

    def cancel_move(self, req):
        """Cancel a previously requested move
        
        This is the same as calling req.cancel()"""
        return self._request('cancel', move_req=req)

    def run(self):
        while self.quit_request is None:
            # check on position and move in progress
            self.check_position()
            if self.obj_callback is not None:
                self.check_objective()

            try:
                req = self.request_queue.get(timeout=self.poll_interval)
            except queue.Empty:
                req = None

            if req is not None:
                self._handle_request(req)

        self.quit_request.set_result(None)

    def _request(self, req, **kwds):
        fut = ScientificaRequestFuture(self, req, kwds)
        self.request_queue.put(fut)
        return fut

    def _handle_request(self, fut: ScientificaRequestFuture):
        cmd = fut.request
        try:
            if cmd == 'stop':
                self._handle_stop()
                fut.set_result(None)
            elif cmd == 'move':
                self._handle_move(fut)
            elif cmd == 'quit':
                self.quit_request = fut
            elif cmd == 'cancel':
                self._handle_cancel(fut)
            else:
                raise ValueError(f'unrecognized request {cmd}')

        except Exception:
            fut.set_exc_info(sys.exc_info())

    def _handle_move(self, fut):
        if self.current_move is not None and fut is not self.current_move:
            # don't think this is needed
            # self.dev.serial.send('STOP')
            self.check_position()
            if self.current_move is not None:
                self.current_move.fail('Interrupted by another move request.')
            self.current_move = None
        self.current_move = fut
        self.send_move_command()

    def _handle_stop(self):
        self.dev.serial.send('STOP')
        if self.current_move is not None:
            while True:
                self.check_position(miss_reason='Stopped by request.')
                if self.dev.isMoving():
                    time.sleep(0.1)
                else:
                    break
            self.current_move = None

    def _handle_cancel(self, fut):
        move_req = fut.kwds['move_req']
        if not move_req.done():
            if move_req is self.current_move:
                self.dev.serial.send('STOP')
                self.current_move = None
            move_req.fail(f"Request to {move_req.request} was cancelled")
        fut.set_result(None)

    def send_move_command(self):
        fut = self.current_move
        speed = fut.kwds['speed']
        pos = fut.kwds['pos']
        with self.dev.serial.lock:
            for i in range(3):
                try:
                    # need to send 3 commands uninterrupted in sequence
                    if speed is not None:
                        self.dev.setSpeed(speed)
                    ticks = [x * self.dev.ticksPerMicron for x in pos]
                    self.dev.serial.send(b'ABS %d %d %d' % tuple(ticks))
                    if speed is not None:
                        self.dev.setSpeed(self.default_speed)
                except (TimeoutError, RuntimeError):
                    if i >= 2:
                        raise
                    # ignore and retry
                    self.dev.serial.flush()
                break

    def check_position(self, miss_reason=None, recheck=True):
        """Check the current position and move status, and update the current move if necessary.

        Parameters
        ----------
        miss_reason : str | None
            If the current move is not complete, then this is the reason why, and the move will be failed without retry.
        recheck : bool
            If True, then check the position again after a short delay to ensure that the device has stopped moving.
        """
        # check position and invoke change callback 
        try:
            pos = self.dev.getPos()
        except Exception:
            self.dev.serial.flush()
            printExc("Ignored error while getting position from Scientifica device:")
            return

        if self.pos_callback is not None and pos != self.last_pos:
            self.pos_callback(pos)
        self.last_pos = pos

        if self.current_move is None:
            return

        if self.dev.isMoving():
            return  # still moving, check again later

        # stopped; one way or another, the current move is done with this attempt
        fut = self.current_move
        dif = np.linalg.norm(np.array(pos) - np.array(fut.target_pos))

        # if we reached the target, then the move is a success.
        if dif < self.move_complete_threshold:
            self.current_move = None
            fut.set_result(None)
            return
        elif recheck:
            # Sometimes devices report they are finished moving before they have
            # completely stopped. Wait a moment, then check again to be sure.
            time.sleep(0.1)
            return self.check_position(miss_reason, recheck=False)

        # If we missed the target and we aren't allowed to check the position again, then
        # re-attempt the move if possible
        if fut.can_retry:
            fut.n_attempts += 1
            self.send_move_command()
            return

        # Otherwise, the move request fails
        self.current_move = None
        if miss_reason is not None:
            fut.fail(miss_reason)
        else:
            fut.fail(
                f"Stopped moving before reaching target (target={fut.target_pos} actual={pos} dist={dif:1f}µm)"
            )

    def check_objective(self):
        try:
            obj = self.dev.getObjective()
        except Exception:
            self.dev.serial.flush()
            printExc("Ignored error while getting objective from Scientifica device:")
            return

        if self.obj_callback is not None and obj != self.last_obj:
            self.obj_callback(obj)
        self.last_obj = obj


class ScientificaRequestFuture:
    """Represents a future result to be generated following a request to the control thread.
    """

    class FutureError(Exception):
        pass

    def __init__(self, ctrl_thread, req, kwds):
        self.thread: ScientificaControlThread = ctrl_thread
        self.request = req
        self.kwds = kwds
        self._callback = None
        self._cb_lock = threading.Lock()
        self._done = threading.Event()
        self.result = None
        self.exc_info = None
        self.error = None
        self.n_attempts = 0

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

    @property
    def can_retry(self):
        return self.kwds.get('attempts_allowed', 0) > self.n_attempts and not self.done()

    def cancel(self):
        """Cancel the request if it is not already complete.
        
        Only supported for move requests.
        """
        if self.request != 'move':
            raise TypeError('Can only cancel move requests')
        self.kwds['attempts_allowed'] = 0
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
