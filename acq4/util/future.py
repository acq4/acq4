from __future__ import annotations

import functools
import sys
import threading
import time
import traceback
from typing import Callable, Generic, TypeVar, ParamSpec

from acq4.util import Qt, ptime
from pyqtgraph import FeedbackButton

FUTURE_RETVAL_TYPE = TypeVar('FUTURE_RETVAL_TYPE')
WAITING_RETVAL_TYPE = TypeVar('WAITING_RETVAL_TYPE')


class Future(Qt.QObject, Generic[FUTURE_RETVAL_TYPE]):
    """Used to track the progress of an asynchronous task.

    The simplest subclasses reimplement percentDone() and call _taskDone() when finished.
    """
    sigFinished = Qt.Signal(object)  # self
    sigStateChanged = Qt.Signal(object, object)  # self, state

    class StopRequested(Exception):
        """Raised by checkStop if stop() has been invoked.
        """

    class Timeout(Exception):
        """Raised by wait() if the timeout period elapses.
        """

    @classmethod
    def immediate(cls, result=None):
        """Create a future that is already resolved with the optional result."""
        fut = cls()
        fut._taskDone(returnValue=result)
        return fut

    def __init__(self):
        Qt.QObject.__init__(self)
        
        self.startTime = ptime.time()

        self._isDone = False
        self._wasInterrupted = False
        self._errorMessage = None
        self._excInfo = None
        self._stopRequested = False
        self._state = 'starting'
        self._errorMonitorThread = None
        self._executingThread = None
        self._stopsToPropagate = []
        self._returnVal: "T | None" = None
        self.finishedEvent = threading.Event()

    def executeInThread(self, func, args, kwds):
        """Execute the specified function in a separate thread.

        The function should call _taskDone() when finished (or raise an exception).
        """
        self._executingThread = threading.Thread(target=self.executeAndSetReturn, args=(func, args, kwds), daemon=True)
        self._executingThread.start()

    def executeAndSetReturn(self, func, args, kwds):
        try:
            kwds['_future'] = self
            self._taskDone(returnValue=func(*args, **kwds))
        except Exception as exc:
            self._taskDone(interrupted=True, error=str(exc), excInfo=sys.exc_info())

    def propagateStopsInto(self, future: Future):
        """Add a future to the list of futures that will be stopped if this future is stopped.
        """
        self._stopsToPropagate.append(future)

    def getResult(self, **kwds) -> FUTURE_RETVAL_TYPE:
        self.wait(**kwds)
        return self._returnVal

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

        Subclasses may extend this method and/or use checkStop to determine whether
        stop() has been called.
        """
        if self.isDone():
            return

        if reason is not None:
            self._errorMessage = reason
        self._stopRequested = True
        for f in self._stopsToPropagate:
            f.stop(reason=reason)

    def _taskDone(self, interrupted=False, error=None, state=None, excInfo=None, returnValue=None):
        """Called by subclasses when the task is done (regardless of the reason)
        """
        if self._isDone:
            raise ValueError("_taskDone has already been called.")
        self._isDone = True
        if error is not None:
            # error message may have been set earlier
            self._errorMessage = error
        self._excInfo = excInfo
        self._wasInterrupted = interrupted
        if interrupted:
            self.setState(state or f'interrupted: {error}')
        else:
            self.setState(state or 'complete')
        if returnValue is not None:
            self._returnVal = returnValue
        self.finishedEvent.set()
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
                msg = f"Task {self} did not complete (no error message)."
            else:
                msg = f"Task {self} did not complete: {err}"
            if self._excInfo is not None:
                raise RuntimeError(msg) from self._excInfo[1]
            else:
                raise RuntimeError(msg)

    def _wait(self, duration):
        """Default sleep implementation used by wait(); may be overridden to return early.
        """
        self.finishedEvent.wait(timeout=duration)

    def checkStop(self, delay=0):
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
            
            time.sleep(max(0.0, min(0.1, stop-now)))
            if self._stopRequested:
                raise self.StopRequested()

    def sleep(self, duration, interval=0.2):
        """Sleep for the specified duration (in seconds) while checking for stop requests.
        """
        start = time.time()
        while time.time() < start + duration:
            self.checkStop()
            time.sleep(interval)

    def waitFor(self, future: Future[WAITING_RETVAL_TYPE], timeout=20.0) -> Future[WAITING_RETVAL_TYPE]:
        """Wait for another future to complete while also checking for stop requests on self.
        """
        start = time.time()
        while True:
            try:
                self.checkStop()
            except self.StopRequested:
                future.stop(reason="parent task stop requested")
                raise
            try:
                future.wait(0.1)
                break
            except future.Timeout as e:
                if timeout is not None and time.time() - start > timeout:
                    raise future.Timeout(f"Timed out waiting for {future!r}") from e
        return future

    def raiseErrors(self, message, pollInterval=1.0):
        """Monitor this future for errors and raise if any occur.

        This allows the caller to discard a future, but still expect errors to be delivered to the user. Note
        that errors are raised from a background thread.

        Parameters
        ----------
        message : str
            Exception message to raise. May include "{stack}" to insert the stack trace of the caller, and "{error}"
            to insert the original formatted exception.
        pollInterval : float | None
            Interval in seconds to poll for errors. This is only used with Futures that require a poller;
            Futures that immediately report errors when they occur will not use a poller.
        """
        if self._errorMonitorThread is not None:
            return
        originalFrame = sys._getframe().f_back
        monitorFn = functools.partial(self._monitorErrors, message=message, pollInterval=pollInterval, originalFrame=originalFrame)
        self._errorMonitorThread = threading.Thread(target=monitorFn, daemon=True)
        self._errorMonitorThread.start()

    def _monitorErrors(self, message, pollInterval, originalFrame):
        try:
            self.wait(pollInterval=pollInterval)
        except Exception as exc:
            if '{stack}' in message:
                stack = ''.join(traceback.format_stack(originalFrame))
            else:
                stack = None

            try:
                formattedMsg = message.format(stack=stack, error=traceback.format_exception_only(type(exc), exc))
            except Exception as exc2:
                formattedMsg = f"{message} [additional error formatting error message: {exc2}]"
            raise RuntimeError(formattedMsg) from exc


WRAPPED_FN_PARAMS = ParamSpec('WRAPPED_FN_PARAMS')
WRAPPEND_FN_RETVAL_TYPE = TypeVar('WRAPPEND_FN_RETVAL_TYPE')


# MC this doesn't handle typing correctly as Future.wrap, but I don't know why...
def future_wrap(
        func: Callable[WRAPPED_FN_PARAMS, WRAPPEND_FN_RETVAL_TYPE]
) -> Callable[WRAPPED_FN_PARAMS, Future[WRAPPEND_FN_RETVAL_TYPE]]:
    """Decorator to execute a function in a Thread wrapped in a future. The function must take a Future
    named "_future" as a keyword argument. This Future can be variously used to checkStop() the
    function, wait for other futures, and will be returned by the decorated function call. The function
    can still be called with `block=True` to prevent threaded execution, if device locking is a concern.
    Usage:
        @future_wrap
        def myFunc(arg1, arg2, _future=None):
            ...
            _future.checkStop()
            _future.waitFor(someOtherFuture)
            ...
        result = myFunc(arg1, arg2).getResult()
        threadless_result = myFunc(arg1, arg2, block=True).getResult()
    """

    @functools.wraps(func)
    def wrapper(*args: WRAPPED_FN_PARAMS.args, **kwds: WRAPPED_FN_PARAMS.kwargs) -> Future[WRAPPEND_FN_RETVAL_TYPE]:
        future = Future()
        if kwds.pop('block', False):
            kwds['_future'] = future
            if parent := kwds.pop('checkStopThrough', None):
                parent.propagateStopsInto(future)
            future.executeAndSetReturn(func, args, kwds)
            future.wait()
        else:
            future.executeInThread(func, args, kwds)
        return future

    return wrapper


class MultiFuture(Future):
    """Future tracking progress of multiple sub-futures.
    """
    def __init__(self, futures):
        self.futures = futures
        Future.__init__(self)

    def stop(self, reason="task stop requested"):
        for f in self.futures:
            f.stop(reason=reason)
        return Future.stop(self, reason)

    def percentDone(self):
        return min(f.percentDone() for f in self.futures)

    def wasInterrupted(self):
        return any(f.wasInterrupted() for f in self.futures)

    def isDone(self):
        return all(f.isDone() for f in self.futures)

    def errorMessage(self):
        return "; ".join([f.errorMessage() or '' for f in self.futures])

    def currentState(self):
        return "; ".join([f.currentState() or '' for f in self.futures])


class FutureButton(FeedbackButton):
    """A button that starts a Future when clicked and displays feedback based on the Future's state."""
    sigFinished = Qt.Signal(object)  # future
    sigStateChanged = Qt.Signal(object, object)  # future, state

    def __init__(self, future_producer: Callable[[...], Future], *args, stoppable: bool = False, success=None, failure=None, processing=None):
        """Create a new FutureButton.

        Parameters
        ----------
        future_producer : Callable[[], Future]
            A function that takes no arguments and returns a Future instance.
        *args
            Arguments to pass to FeedbackButton.__init__.
        stoppable : bool
            If True, the Future can be stopped by clicking the button while it is in progress.
        success : str | None
            The message to display when the Future completes successfully. If None, the default message is "Success".
        failure : str | None
            The message to display when the Future fails. If None, the default message is the error message from the Future.
        processing : str | None
            The message to display while the Future is in progress. If None, the default message is "Processing...".
        """
        super().__init__(*args)
        self._future = None
        self._futureProducer = future_producer
        self._stoppable = stoppable
        self._userRequestedStop = False
        self._success = success
        self._failure = failure
        self._processing = processing
        self.clicked.connect(self._controlTheFuture)

    def processing(self, message="Processing..", tip="", processEvents=True):
        """Displays specified message on button to let user know the action is in progress. Threadsafe."""
        # This had to be reimplemented to allow stoppable buttons to remain enabled.
        isGuiThread = Qt.QtCore.QThread.currentThread() == Qt.QtCore.QCoreApplication.instance().thread()
        if isGuiThread:
            self.setEnabled(self._stoppable)
            self.setText(message, temporary=True)
            self.setToolTip(tip, temporary=True)
            if processEvents:
                Qt.QtWidgets.QApplication.processEvents()
        else:
            self.sigCallProcess.emit(message, tip, processEvents)

    def _controlTheFuture(self):
        if self._future is None:
            self.processing(self._processing or ("Cancel" if self._stoppable else "Processing..."))
            future = self._future = self._futureProducer()
            future.sigFinished.connect(self._futureFinished)
            if future.isDone():  # futures may immediately complete before we can connect to the signal
                self._futureFinished(future)
            future.sigStateChanged.connect(self._futureStateChanged)
        else:
            self._userRequestedStop = True
            self._future.stop(f"User clicked '{self.text()}' button")

    def _futureFinished(self, future):
        self._future = None
        self.sigFinished.emit(future)
        if not future.wasInterrupted():
            self.success(self._success or "Success")
        else:
            self.failure(self._failure or (future.errorMessage() or 'Failed!')[:40])
            if self._userRequestedStop:
                self._userRequestedStop = False
            else:
                future.wait()  # throw errors

    def _futureStateChanged(self, future, state):
        self.setText(state, temporary=True)
        self.sigStateChanged.emit(future, state)
