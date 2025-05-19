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


def inGuiThread(func):
    def run_func_in_gui_thread(*args, **kwds):
        return runInGuiThread(func, *args, **kwds)
    return run_func_in_gui_thread


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
