import inspect
import sys
import threading
from functools import wraps
from typing import TypeVar, ParamSpec, Callable, Any, cast

from . import Qt
from .future import Future


def runInThread(thread, func, *args, **kwds):
    """Run a function in another thread and return the result.

    The remote thread must be running a Qt event loop.
    """
    return ThreadCallFuture(thread, func, *args, **kwds)()


def runInGuiThread(func, *args, **kwds):
    """Run a function the main GUI thread and return the result."""
    gui_thread = Qt.QApplication.instance().thread()
    curr_thread = Qt.QtCore.QThread.currentThread()
    if gui_thread == curr_thread:
        return func(*args, **kwds)
    else:
        return ThreadCallFuture(gui_thread, func, *args, **kwds)()


def futureInGuiThread(func, *args, **kwds):
    """Run a function the main GUI thread and return a Future."""
    gui_thread = Qt.QApplication.instance().thread()
    curr_thread = Qt.QtCore.QThread.currentThread()
    if gui_thread == curr_thread:
        return Future.immediate(result=func(*args, **kwds))
    else:
        return ThreadCallFuture(gui_thread, func, *args, **kwds)


# Type variables for preserving function signature
T = TypeVar("T")
P = ParamSpec("P")


def inGuiThread(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to run a function or method in the GUI thread.

    Args:
        func: The function or method to decorate

    Additional params in decorated function:
        blocking: If True, waits for the function to complete. Default False.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        # Extract blocking parameter if present, default to False
        blocking = False
        if "blocking" in kwargs and kwargs["blocking"] is not None:
            blocking = kwargs.pop("blocking")

        if blocking:
            result = runInGuiThread(func, *args, **kwargs)
            return cast(T, result)
        else:
            Qt.QTimer.singleShot(0, lambda: func(*args, **kwargs))
            return cast(T, None)

    setattr(wrapper, "__annotations__", {**getattr(func, "__annotations__", {}), "blocking": "Optional[bool] = None"})
    return cast(Callable[P, T], wrapper)


class ThreadCallFuture(Future):
    sigRequestCall = Qt.Signal()

    def __init__(self, thread, func, *args, **kwds):
        Future.__init__(self, name="ThreadCallFuture")
        self.func = func
        self.args = args
        self.kwds = kwds
        self.exc = None

        if thread is None:
            thread = Qt.QApplication.instance().thread()
        self.moveToThread(thread)
        self.sigRequestCall.connect(self._callRequested)
        self.sigRequestCall.emit()

    def _callRequested(self):
        try:
            self.ret = self.func(*self.args, **self.kwds)
            self._taskDone()
        except Exception as exc:
            self.exc = exc
            self._taskDone(interrupted=True, excInfo=sys.exc_info())

    def __call__(self):
        self.wait()
        if self.exc is not None:
            raise self.exc
        else:
            return self.ret
