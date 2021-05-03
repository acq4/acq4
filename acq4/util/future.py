from __future__ import print_function, division

import time

from pyqtgraph import ptime

from acq4.util import Qt


class Future(Qt.QObject):
    """Used to track the progress of an asynchronous task.

    The simplest subclasses reimplement percentDone() and call _taskDone() when finished.
    """
    sigFinished = Qt.Signal(object)  # self
    sigStateChanged = Qt.Signal(object, object)  # self, state

    class StopRequested(Exception):
        """Raised by _checkStop if stop() has been invoked.
        """

    class Timeout(Exception):
        """Raised by wait() if the timeout period elapses.
        """

    def __init__(self):
        Qt.QObject.__init__(self)
        
        self.startTime = ptime.time()

        self._isDone = False
        self._wasInterrupted = False
        self._errorMessage = None
        self._excInfo = None
        self._stopRequested = False
        self._state = 'starting'

    def currentState(self):
        """Return the current state of this future.

        The state can be any string used to indicate the progress this future is making in its task.
        """
        return self._state

    def setState(self, state):
        """Set the current state of this future.

        The state can be any string used to indicate the progress this future is making in its task.
        """
        if state == self._state:
            return
        self._state = state
        self.sigStateChanged.emit(self, state)

    def percentDone(self):
        """Return the percent of the task that has completed.

        Must be reimplemented in subclasses.
        """
        raise NotImplementedError("method must be reimplmented in subclass")

    def stop(self, reason="task stop requested"):
        """Stop the task (nicely).

        This method may return another future if stopping the task is expected to
        take time.

        Subclasses may extend this method and/or use _checkStop to determine whether
        stop() has been called.
        """
        if self.isDone():
            return

        if reason is not None:
            self._errorMessage = reason
        self._stopRequested = True

    def _taskDone(self, interrupted=False, error=None, state=None, excInfo=None):
        """Called by subclasses when the task is done (regardless of the reason)
        """
        if self._isDone:
            raise Exception("_taskDone has already been called.")
        self._isDone = True
        if error is not None:
            # error message may have been set earlier
            self._errorMessage = error
        self._excInfo = excInfo
        self._wasInterrupted = interrupted
        if interrupted:
            self.setState(state or 'interrupted: %s' % error)
        else:
            self.setState(state or 'complete')
        self.sigFinished.emit(self)

    def wasInterrupted(self):
        """Return True if the task was interrupted before completing (due to an error or a stop request).
        """
        return self._wasInterrupted

    def isDone(self):
        """Return True if the task has completed successfully or was interrupted.
        """
        return self._isDone

    def errorMessage(self):
        """Return a string description of the reason for a task failure,
        or None if there was no failure (or if the reason is unknown).
        """
        return self._errorMessage
        
    def wait(self, timeout=None, updates=False, pollInterval=0.1):
        """Block until the task has completed, has been interrupted, or the
        specified timeout has elapsed.

        If *updates* is True, process Qt events while waiting.

        If a timeout is specified and the task takes too long, then raise Future.Timeout.
        If the task ends incomplete for another reason, then raise RuntimeError.
        """
        start = ptime.time()
        while True:
            if (timeout is not None) and (ptime.time() > start + timeout):
                raise self.Timeout("Timeout waiting for task to complete.")
                
            if self.isDone():
                break
            
            if updates is True:
                Qt.QTest.qWait(min(1, int(pollInterval * 1000)))
            else:
                self._wait(pollInterval)
        
        if self.wasInterrupted():
            err = self.errorMessage()
            if err is None:
                # This would be a fantastic place to "raise from self._excInfo[1]" once we move to py3
                raise RuntimeError("Task did not complete.")
            else:
                raise RuntimeError("Task did not complete: %s" % err)

    def _wait(self, duration):
        """Default sleep implementation used by wait(); may be overridden to return early.
        """
        time.sleep(duration)

    def _checkStop(self, delay=0):
        """Raise self.StopRequested if self.stop() has been called.

        This may be used by subclasses to periodically check for stop requests.

        The optional *delay* argument causes this method to sleep while periodically
        checking for a stop request.
        """
        if delay == 0 and self._stopRequested:
            raise self.StopRequested()

        stop = ptime.time() + delay
        while True:
            now = ptime.time()
            if now > stop:
                return
            
            time.sleep(max(0, min(0.1, stop-now)))
            if self._stopRequested:
                raise self.StopRequested()

    def sleep(self, duration, interval=0.2):
        """Sleep for the specified duration (in seconds) while checking for stop requests.
        """
        start = time.time()
        while time.time() < start + duration:
            self._checkStop()
            time.sleep(interval)

    def waitFor(self, futures, timeout=20.0):
        """Wait for multiple futures to complete while also checking for stop requests on self.
        """
        if not isinstance(futures, (list, tuple)):
            futures = [futures]
        if len(futures) == 0:
            return
        start = time.time()
        while True:
            self._checkStop()
            allDone = True
            for fut in futures[:]:
                try:
                    fut.wait(0.1)
                    futures.remove(fut)
                except fut.Timeout:
                    allDone = False
                    break
            if allDone:
                break
            if timeout is not None and time.time() - start > timeout:
                raise futures[0].Timeout("Timed out waiting for %r" % futures)


class MultiFuture(Future):
    """Future tracking progress of multiple sub-futures.
    """
    def __init__(self, futures):
        self.futures = futures

    def stop(self, reason="task stop requested"):
        for f in self.futures:
            f.stop(reason=reason)
        return Future.stop(self, reason)

    def percentDone(self):
        return min([f.percentDone() for f in self.futures])

    def wasInterrupted(self):
        return any([f.wasInterrupted() for f in self.futures])

    def isDone(self):
        return all([f.isDone() for f in self.futures])

    def errorMessage(self):
        return "; ".join([f.errorMessage() for f in self.futures])

    def currentState(self):
        return "; ".join([f.currentState() for f in self.futures])

