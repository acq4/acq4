from __future__ import annotations

import contextlib
import contextvars
import functools
import inspect
import logging
import sys
import threading
import time
import traceback
from typing import Any, Callable, Optional
from typing import Generic, TypeVar

from acq4.logging_config import get_logger
from acq4.util import Qt, ptime
from pyqtgraph import FeedbackButton

# ContextVar tracking the innermost running Future on the current thread.
_current_future_var: contextvars.ContextVar["Future | None"] = contextvars.ContextVar(
    "current_future", default=None
)


def current_future() -> "Future | None":
    """Return the Future currently executing on this thread, or None."""
    return _current_future_var.get()


class TaskStack:
    """Wraps a ContextVar[tuple[str, ...]] to track a chain of named task scopes."""

    def __init__(self):
        self._var: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
            "task_stack", default=()
        )

    @contextlib.contextmanager
    def push(self, name: str):
        """Context manager that appends *name* to the current chain and restores on exit."""
        token = self._var.set(self._var.get() + (name,))
        try:
            yield
        finally:
            self._var.reset(token)

    @contextlib.contextmanager
    def push_full(self, chain: tuple[str, ...]):
        """Context manager that replaces the entire stack with *chain* and restores on exit."""
        token = self._var.set(chain)
        try:
            yield
        finally:
            self._var.reset(token)

    def get(self) -> tuple[str, ...]:
        """Return the current task chain."""
        return self._var.get()

    def full_stack(self) -> str:
        """Return the current chain joined by ' > ', or '' if empty."""
        return " > ".join(self._var.get())


task_stack = TaskStack()

FUTURE_RETVAL_TYPE = TypeVar("FUTURE_RETVAL_TYPE")
WAITING_RETVAL_TYPE = TypeVar("WAITING_RETVAL_TYPE")


class Unset:
    pass


UNSET = Unset()  # unique sentinel value for "not set"


class FutureSignals(Qt.QObject):
    """Companion QObject that holds Qt signals for a Future.

    Created lazily the first time signals are accessed on a Future instance.
    """

    sigFinished = Qt.Signal(object)
    sigStateChanged = Qt.Signal(object, object)


class Future(Generic[FUTURE_RETVAL_TYPE]):
    """Used to track the progress of an asynchronous task.

    The simplest subclasses reimplement percentDone() and call _taskDone() when finished.
    """

    class StopRequested(Exception):
        """Raised by checkStop if stop() has been invoked."""

    class Stopped(Exception):
        """Raised by futures that were politely stopped."""

    class Timeout(TimeoutError):
        """Raised by wait() if the timeout period elapses."""

    @classmethod
    def immediate(cls, result=None, error=None, excInfo=None, stopped=False, name=None) -> Future:
        """Create a future that is already resolved with the optional result."""
        if name is None:
            name = cls.nameFromStack()
        fut = cls(name=name, logLevel=None)
        if stopped:
            fut.stop(reason=error)
        fut._taskDone(
            returnValue=result,
            error=error,
            interrupted=(error or excInfo) is not None,
            excInfo=excInfo,
        )
        return fut

    @staticmethod
    def nameFromStack(depth=1):
        """Generate a useful name for a Future based on the code line that created it"""
        frame = inspect.currentframe().f_back  # start in parent's frame
        for _ in range(depth):
            frame = frame.f_back  # walk up the stack
        return f"(unnamed from {frame.f_code.co_filename}:{frame.f_lineno})"

    def __init__(
        self,
        fn=None,
        args=(),
        kwargs=None,
        *,
        onError=None,
        name=None,
        logLevel='debug',
        detach=False,
        on_finish=None,
    ):
        self.startTime = ptime.time()
        self._name = self.nameFromStack() if name is None else name
        self.logger = get_logger(f"{__name__}.{self._name}")
        self.logLevel = logLevel
        self._isDone = False
        self._callbacks = []
        self._onError = onError
        self._completionLock = threading.RLock()
        self._wasInterrupted = False
        self._errorMessage = None
        self._excInfo = None
        self._stop_requested = threading.Event()
        self._signals: Optional["FutureSignals"] = None
        self._state = "starting"
        self._errorMonitorThread = None
        self._executingThread = None
        self._stopsToPropagate = []
        self._returnVal: "T | None" = None
        self.finishedEvent = threading.Event()

        # Capture creation stack for enhanced exception tracebacks
        self._creationStack = traceback.extract_stack()[:-1]  # Exclude current frame
        self._creationThread = threading.current_thread()

        self.log(f"Future [{self._name}] created")

        if fn is not None:
            if name is None:
                self._name = getattr(fn, '__qualname__', repr(fn))
            if on_finish is not None:
                self.add_finish_callback(on_finish)
            parent = current_future()
            if parent is not None and not detach:
                parent._stopsToPropagate.append(self)
            self._executeInThread(fn, tuple(args), dict(kwargs or {}))

    # -- Qt signal proxy -------------------------------------------------------

    @property
    def signals(self) -> "FutureSignals":
        """Lazily-created QObject companion providing sigFinished and sigStateChanged."""
        if self._signals is None:
            with self._completionLock:
                if self._signals is None:
                    self._signals = FutureSignals()
        return self._signals

    @property
    def sigFinished(self):
        return self.signals.sigFinished

    @property
    def sigStateChanged(self):
        return self.signals.sigStateChanged

    @property
    def _stopRequested(self) -> bool:
        return self._stop_requested.is_set()

    @_stopRequested.setter
    def _stopRequested(self, value: bool):
        if value:
            self._stop_requested.set()
        else:
            self._stop_requested.clear()

    @property
    def is_done(self) -> bool:
        return self._isDone

    @property
    def is_stopped(self) -> bool:
        return self._stopRequested

    @property
    def _done(self) -> threading.Event:
        """Alias for finishedEvent; set when the future finishes."""
        return self.finishedEvent

    def add_finish_callback(self, fn) -> None:
        """Call fn(result, exception) when done. Calls immediately if already done."""

        def _wrap(future):
            exc = future.exceptionRaised()
            result = future._returnVal
            fn(result, exc)

        self.onFinish(_wrap)

    def detach(self) -> None:
        """Detach from the parent future — parent stop will no longer cascade here."""
        parent = current_future()
        if parent is not None and self in parent._stopsToPropagate:
            parent._stopsToPropagate.remove(self)

    def _executeInThread(self, func, args, kwargs):
        """Start func in a background thread, propagating the current context."""
        ctx = contextvars.copy_context()
        self._executingThread = threading.Thread(
            target=ctx.run,
            args=(self._executeAndSetReturn, func, args, kwargs),
            daemon=True,
            name=f"execute thread for {repr(self)}",
        )
        self._executingThread.start()

    def _executeAndSetReturn(self, func, args, kwargs):
        cf_token = _current_future_var.set(self)
        with task_stack.push(self._name):
            try:
                self.setResult(rval=func(*args, **kwargs))
            except Stopped:
                self._stopRequested = True
                self.setResult(error="stopped", interrupted=True)
            except Exception:
                self.setResult(excInfo=sys.exc_info())
            finally:
                _current_future_var.reset(cf_token)
                self._do_task_completion_jobs()

    # -------------------------------------------------------------------------

    def log(self, message):
        if self.logLevel is not None:
            getattr(self.logger, self.logLevel, self.logger.debug)(message)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self.log(f"Future name changed from [{self._name}] to [{value}]")
        self._name = value

    def __repr__(self):
        return f"<{self.__class__.__name__} {self._name}>"

    def propagateStopsInto(self, future: Future):
        """Add a future to the list of futures that will be stopped if this future is stopped."""
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
        self.log(f"Future [{self._name}] state changed: {state}")
        self._state = state
        self.sigStateChanged.emit(self, state)

    def percentDone(self):
        """Return the percent of the task that has completed.

        Must be reimplemented in subclasses.
        """
        raise NotImplementedError("method must be reimplemented in subclass")

    def stop(self, reason: str | None = "task stop requested", wait=False):
        """Stop the task (nicely).

        Subclasses may extend this method and/or use checkStop to determine whether
        stop() has been called. Returns immediately unless *wait* is True, in which case
        this method will block until the task has stopped.
        """
        if self.isDone():
            return

        if reason is not None:
            self._errorMessage = reason
        self.log(f"Asking Future [{self._name}] to stop: {reason}")
        self._stopRequested = True
        for f in self._stopsToPropagate:
            f.stop(reason=reason)
        if wait:
            with contextlib.suppress(self.Stopped):
                self.wait()

    def _taskDone(self, interrupted=False, error=UNSET, excInfo=UNSET, returnValue=UNSET):
        """Called by subclasses when the task is done (regardless of the reason)"""
        self.setResult(rval=returnValue, error=error, excInfo=excInfo, interrupted=interrupted)
        self._do_task_completion_jobs()

    def setResult(
        self,
        rval: Any = UNSET,
        error: str | None | Unset = UNSET,
        excInfo: str | None | Unset = UNSET,
        interrupted: bool | None | Unset = UNSET,
    ):
        """Set result attributes on this future.
        This should only be called internally by the future or subclasses, or when the state of the future is handled externally.

        Parameters
        ----------
        rval : Any
            The return value of the future.
        error : str | None | Unset
            The error message if the future encountered an error.
        excInfo : str | None | Unset
            The exception information if the future encountered an error.
        interrupted : bool | None | Unset
            Indicates whether the future was interrupted.
            If unspecified, it will be set to True if there was an error or exception.
        """
        with self._completionLock:
            if self._isDone:
                raise ValueError("Cannot alter future after future is done.")

            if rval is not UNSET:
                self._returnVal = rval
            if error is not UNSET:
                self._errorMessage = error
            if excInfo is not UNSET:
                self._excInfo = excInfo

            if interrupted is not UNSET:
                self._wasInterrupted = interrupted
            elif error is not UNSET or excInfo is not UNSET:
                self._wasInterrupted = True

    def _do_task_completion_jobs(self):
        with self._completionLock:
            if self._isDone:
                raise ValueError("Cannot finish future again; already done.")
            self._isDone = True

        error = self._errorMessage
        excInfo = self._excInfo

        msg = f"Future [{self._name}] finished."
        if self._wasInterrupted:
            msg = msg + " [interrupted]"
        if error is not None:
            msg = msg + f" [{error}]"
        self.log(msg)

        if self._onError is not None and (error or excInfo):
            try:
                self._onError(self)
            except Exception as e:
                self.logger.exception(
                    f"{type(e).__name__}: {e} in Future.onError callback: {self._onError}"
                )
        self.finishedEvent.set()  # tell wait() that we're done
        self.sigFinished.emit(self)  # tell everyone else that we're done
        self._callCallbacks()

    def wasInterrupted(self):
        """Return True if the task was interrupted before completing (due to an error or a stop request)."""
        return self._wasInterrupted

    def wasStopped(self):
        """Return True if the task was stopped."""
        return self._stopRequested

    def logErrors(self, message=""):
        if self.wasInterrupted() and not self.wasStopped():
            try:
                self.wait()
            except Exception:
                self.logger.exception(message)

    def exceptionRaised(self):
        return self._excInfo[1] if self._excInfo is not None else None

    def isDone(self):
        """Return True if the task has completed successfully or was interrupted."""
        with self._completionLock:
            return self._isDone

    def onFinish(self, callback, *args, inGui: bool = False, **kwargs):
        """Make sure the callback is called when the future is finished, including if the future is already done."""
        from acq4.util.threadrun import runInGuiThread

        with self._completionLock:
            done = self._isDone
            if not done:
                self._callbacks.append((inGui, callback, args, kwargs))
        if done:
            if inGui:
                runInGuiThread(callback, self, *args, **kwargs)
            else:
                callback(self, *args, **kwargs)

    def _callCallbacks(self):
        """Call all callbacks registered with onFinish().

        This is called when the task is completed.
        """
        from acq4.util.threadrun import runInGuiThread

        for inGui, callback, args, kwargs in self._callbacks:
            try:
                if inGui:
                    runInGuiThread(callback, self, *args, **kwargs)
                else:
                    callback(self, *args, **kwargs)
            except Exception as e:
                self.logger.exception(f"{type(e).__name__}: {e} in Future callback: {callback}")

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
                raise self.Timeout(f"Timeout waiting for task {self} to complete.")

            if self.isDone():
                break

            if updates is True:
                Qt.QTest.qWait(min(1, int(pollInterval * 1000)))
            else:
                self._wait(pollInterval)

        if self.wasInterrupted():
            err = self.errorMessage()
            original_exc = self.exceptionRaised()

            if self._stopRequested:
                msg = f"Task {self} did not complete: {err}" if err else f"Task {self} stopped."
                raise self.Stopped(msg)
            elif original_exc is not None:
                if self._excInfo is not None:
                    raise original_exc.with_traceback(self._excInfo[2])
                raise original_exc
            msg = (
                f"Task {self} did not complete: {err}" if err else f"Task {self} did not complete."
            )
            raise RuntimeError(msg)

        return self._returnVal

    def enhanceException(self, exc):
        """Wrap an exception with Future creation stack and execution context in its str()."""
        creation_frames = "".join(traceback.format_list(self._creationStack))
        parts = [f"{type(exc).__name__}: {exc}"]
        parts.append(f"\n--- Future creation context ---\n{creation_frames}")

        if self._excInfo is not None and self._excInfo[2] is not None:
            exec_tb = "".join(traceback.format_tb(self._excInfo[2]))
            exec_thread = self._executingThread
            if exec_thread is not None and exec_thread != self._creationThread:
                thread_name = exec_thread.name
                parts.append(f"\n--- Thread boundary: {thread_name} ---\n{exec_tb}")
            else:
                parts.append(f"\n--- Execution context ---\n{exec_tb}")

        enhanced_msg = "".join(parts)
        try:
            enhanced = type(exc)(enhanced_msg)
        except Exception:
            enhanced = RuntimeError(enhanced_msg)
        enhanced.__cause__ = exc
        return enhanced

    def _wait(self, duration):
        """Default sleep implementation used by wait(); may be overridden to return early."""
        self.finishedEvent.wait(timeout=duration)

    def checkStop(self):
        """Raise self.StopRequested if self.stop() has been called.

        This may be used by subclasses to periodically check for stop requests.

        The optional *delay* argument causes this method to sleep while periodically
        checking for a stop request.
        """
        if self._stopRequested:
            raise self.StopRequested()

    def sleep(self, duration, interval=0.2):
        """Sleep for the specified duration (in seconds) while checking for stop requests."""
        stop = ptime.time() + duration
        self.checkStop()
        while True:
            now = ptime.time()
            if now > stop:
                return

            time.sleep(max(0.0, min(interval, stop - now)))
            self.checkStop()

    def waitFor(
        self, future: Future[WAITING_RETVAL_TYPE], timeout=20.0
    ) -> Future[WAITING_RETVAL_TYPE]:
        """Wait for another future to complete while also checking for stop requests on self."""
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
            except Future.Timeout as e:
                if future.wasInterrupted():  # a _real_ timeout, as opposed to our 0.1s loopbeat
                    future.wait()  # let it sing
                if timeout is not None and time.time() - start > timeout:
                    raise self.Timeout(f"Timed out waiting {timeout}s for {future!r}") from e
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
        monitorFn = functools.partial(
            self._monitorErrors,
            message=message,
            pollInterval=pollInterval,
            originalFrame=originalFrame,
        )
        self._errorMonitorThread = threading.Thread(
            target=monitorFn, daemon=True, name=f"error monitor for {self}"
        )
        self._errorMonitorThread.start()

    def _monitorErrors(self, message, pollInterval, originalFrame):
        try:
            self.wait(pollInterval=pollInterval)
        except Exception as exc:
            if "{stack}" in message:
                stack = "".join(traceback.format_stack(originalFrame))
            else:
                stack = None

            try:
                formattedMsg = message.format(
                    stack=stack, error=traceback.format_exception_only(type(exc), exc)
                )
            except Exception as exc2:
                formattedMsg = f"{message} [additional error formatting error message: {exc2}]"
            raise RuntimeError(formattedMsg) from exc


# ---------------------------------------------------------------------------

# Module-level Stopped alias — matches Future.Stopped for catch-compatibility.
Stopped = Future.Stopped


def sleep(seconds: float, *, interval: float = 0.05) -> None:
    """Drop-in replacement for time.sleep. Raises Stopped if the current future is stopped.

    Safe to call outside any future — behaves like time.sleep.
    """
    fut = current_future()
    if fut is None:
        time.sleep(seconds)
        return
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        if fut._stop_requested.wait(timeout=min(interval, remaining)):
            raise Stopped()


def check_stop() -> None:
    """Raise Stopped if the current future has been stopped. Equivalent to sleep(0).

    Use in tight polling loops where a sleep would be inappropriate.
    """
    fut = current_future()
    if fut is not None and fut._stop_requested.is_set():
        raise Stopped()


import queue as _queue


class Queue:
    """Drop-in replacement for queue.Queue with stop-aware get().

    get() raises Stopped if the current future is stopped while waiting.
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._q = _queue.Queue(maxsize)

    def put(self, item, block=True, timeout=None):
        self._q.put(item, block=block, timeout=timeout)

    def put_nowait(self, item):
        self._q.put_nowait(item)

    def get(self, block=True, timeout=None):
        fut = current_future()
        if fut is None or not block:
            return self._q.get(block=block, timeout=timeout)
        deadline = None if timeout is None else time.monotonic() + timeout
        poll = 0.05
        while True:
            if fut._stopRequested:
                raise Stopped()
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if remaining == 0.0:
                raise _queue.Empty()
            wait_for = poll if remaining is None else min(poll, remaining)
            try:
                return self._q.get(timeout=wait_for)
            except _queue.Empty:
                if remaining is not None and time.monotonic() >= deadline:
                    raise

    def get_nowait(self):
        return self._q.get_nowait()

    def empty(self):
        return self._q.empty()

    def qsize(self):
        return self._q.qsize()

    def task_done(self):
        self._q.task_done()

    def join(self):
        self._q.join()


class Event:
    """Drop-in replacement for threading.Event with stop-aware wait().

    wait() raises Stopped if the current future is stopped while waiting.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self):
        self._event.set()

    def clear(self):
        self._event.clear()

    def is_set(self):
        return self._event.is_set()

    def wait(self, timeout=None):
        fut = current_future()
        if fut is None:
            return self._event.wait(timeout=timeout)
        deadline = None if timeout is None else time.monotonic() + timeout
        poll = 0.05
        while True:
            if fut._stopRequested:
                raise Stopped()
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if remaining == 0.0:
                return self._event.is_set()
            wait_for = poll if remaining is None else min(poll, remaining)
            if self._event.wait(wait_for):
                return True


class MultiException(Exception):
    def __init__(self, message, exceptions=None):
        super().__init__(message)
        self._exceptions = exceptions or []

    def __str__(self):
        if not self._exceptions:
            return super().__str__()
        return (
            f"Oh no! A wild herd ({len(self._exceptions)}) of exceptions appeared!\n"
            + "\n".join(f"Exception #{i}: {e}" for i, e in enumerate(self._exceptions, 1))
        )


class MultiFuture(Future):
    """Future tracking progress of multiple sub-futures."""

    def __init__(self, futures, name=None):
        super().__init__(name=name)
        self.futures = futures
        for fut in futures:
            fut.onFinish(self._subFutureFinished)
            fut.sigStateChanged.connect(self._subFutureStateChanged)

    def _subFutureFinished(self, future):
        if self.isDone() and not self._isDone:
            self._taskDone()

    def _subFutureStateChanged(self, future, state):
        self.sigStateChanged.emit(future, state)  # TODO not self?

    def stop(self, reason="task stop requested", wait=False):
        for f in self.futures:
            f.stop(reason=reason, wait=wait)
        return super().stop(reason=reason, wait=wait)

    def percentDone(self):
        return min(f.percentDone() for f in self.futures)

    def wasInterrupted(self):
        return any(f.wasInterrupted() for f in self.futures)

    def exceptionRaised(self):
        exceptions = [f.exceptionRaised() for f in self.futures if f.exceptionRaised() is not None]
        if len(exceptions) == 1:
            return exceptions[0]
        elif exceptions:
            return MultiException("Multiple futures errored", exceptions)
        return None

    def isDone(self):
        return all(f.isDone() for f in self.futures)

    def errorMessage(self):
        error_messages = []
        for f in self.futures:
            # Try to get a meaningful error message from the future
            error_msg = f.errorMessage()
            if error_msg is None and f.wasInterrupted():
                # If no error message but future was interrupted, try to extract from exception
                exc = f.exceptionRaised()
                if exc is not None:
                    error_msg = str(exc)
            if error_msg:
                error_messages.append(str(error_msg))

        return "; ".join(error_messages) if error_messages else None

    def getResult(self):
        return [f.getResult() for f in self.futures]

    def currentState(self):
        return "; ".join([str(f.currentState()) or "" for f in self.futures])


class FutureButton(FeedbackButton):
    """A button that starts a Future when clicked and displays feedback based on the Future's state.

    Pass a zero-arg callable as the first argument. FutureButton wraps it in Future(fn) on click,
    so the callable runs in a background thread. The callable should do its work synchronously —
    use sleep() and check_stop() for cooperative cancellation.
    """

    sigFinished = Qt.Signal(object)  # future
    sigStateChanged = Qt.Signal(object, object)  # future, state

    def __init__(
        self,
        fn: Optional[Callable] = None,
        *args,
        stoppable: bool = False,
        success=None,
        failure=None,
        raiseOnError: bool = True,
        processing=None,
        showStatus: bool = True,
    ):
        """Create a new FutureButton.

        Parameters
        ----------
        fn : Callable[[], Any]
            Zero-arg callable that does the work. Runs in a background thread via Future(fn).
        *args
            Arguments to pass to FeedbackButton.__init__.
        stoppable : bool
            If True, clicking the button while work is in progress stops the Future.
        success : str | None
            Message shown on success. Defaults to "Success".
        failure : str | None
            Message shown on failure. Defaults to the Future's error message.
        raiseOnError : bool
            If True, re-raises any exception from the future. Default is True.
        processing : str | None
            Message shown while work is in progress. Defaults to "Processing...".
        """
        super().__init__(*args)
        self._future = None
        self._fn = fn
        self._stoppable = stoppable
        self._userRequestedStop = False
        self._success = success
        self._raiseOnError = raiseOnError
        self._failure = failure
        self._processing = processing
        self._showStatus = showStatus
        self.clicked.connect(self._controlTheFuture)

    def setOpts(self, **kwds):
        allowed_args = {
            "fn",
            "stoppable",
            "success",
            "failure",
            "processing",
            "showStatus",
            "raiseOnError",
        }
        for k, v in kwds.items():
            if k not in allowed_args:
                raise NameError(f"Unknown option {k}")
            setattr(self, f"_{k}", v)

    def processing(self, message="Processing..", tip="", processEvents=True):
        """Displays specified message on button to let user know the action is in progress. Threadsafe."""
        # This had to be reimplemented to allow stoppable buttons to remain enabled.
        isGuiThread = (
            Qt.QtCore.QThread.currentThread() == Qt.QtCore.QCoreApplication.instance().thread()
        )
        if isGuiThread:
            self.setEnabled(self._stoppable)
            self.setText(message, temporary=True)
            self.setChecked(True)
            self.setToolTip(tip, temporary=True)
            self.setStyleSheet("background-color: #AFA; color: #000;", temporary=True)
            if processEvents:
                Qt.QtWidgets.QApplication.processEvents()
        else:
            self.sigCallProcess.emit(message, tip, processEvents)

    def _controlTheFuture(self):
        if self._future is None:
            self.processing(
                self._processing
                or (f"Cancel {self.text()}" if self._stoppable else "Processing...")
            )
            try:
                future = self._future = Future(self._fn)
            except Exception:
                self.failure("Error!")
                raise
            future.onFinish(self._futureFinished)
            future.sigStateChanged.connect(self._futureStateChanged)
        else:
            self._userRequestedStop = True
            self._future.stop(f"User clicked '{self.text()}' button")

    def _futureFinished(self, future):
        if self._future is None:
            return
        self._future = None
        self.sigFinished.emit(future)
        if not future.wasInterrupted():
            self.success(self._success or "Success")
        elif self._userRequestedStop:
            self._userRequestedStop = False
            self.reset()
        elif future.is_stopped:
            self.reset()
        else:
            self.failure(self._failure or (future.errorMessage() or "Failed!")[:40])
            if self._raiseOnError:
                future.wait()

    def _futureStateChanged(self, future, state):
        if self._showStatus:
            self.setText(state, temporary=True)
        self.sigStateChanged.emit(future, state)


class _TaskStackFilter(logging.Filter):
    """Injects the current task_stack as a string attribute on each log record."""

    def filter(self, record):
        record.task_stack = task_stack.full_stack()
        return True


def setup_teleprox_context_propagation():
    """Wire acq4's task_stack into teleprox RPC calls and log records.

    Registers a call-opts provider so every outgoing call_obj includes the
    current task_stack, and a call-context hook so every incoming call_obj
    restores task_stack for the duration of that call.  Also adds a log
    filter to the process-global LogSender (if one exists) so that log
    records forwarded to the main process carry the task_stack string.

    Safe to call multiple times; provider/hook registration is idempotent
    and the filter is only added once.
    """
    try:
        import teleprox.client as tc
        import teleprox.server as ts
    except ImportError:
        return

    def _provide_call_opts():
        stack = task_stack.get()
        return {'_acq4_task_stack': stack} if stack else None

    tc.set_call_opts_provider(_provide_call_opts)

    @contextlib.contextmanager
    def _call_context_hook(opts):
        stack = opts.get('_acq4_task_stack')
        if stack:
            with task_stack.push_full(tuple(stack)):
                yield
        else:
            yield

    ts.set_call_context_hook(_call_context_hook)

    _maybe_add_logsender_filter()


def _maybe_add_logsender_filter():
    """Add _TaskStackFilter to the process LogSender if present and not already added."""
    try:
        from teleprox.log.remote import sender
    except ImportError:
        return
    if sender is not None and not any(isinstance(f, _TaskStackFilter) for f in sender.filters):
        sender.addFilter(_TaskStackFilter())


# Auto-setup when this module is imported in any process that has teleprox.
# Remote processes call this path; the main process also calls setup_teleprox_context_propagation()
# explicitly from setup_logging() after the log file handler exists.
try:
    setup_teleprox_context_propagation()
except Exception:
    pass
