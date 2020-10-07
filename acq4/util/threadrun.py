import sys
import traceback

from . import Qt
from .future import Future


def runInThread(thread, func, *args, **kwds):
    """Run a function in another thread and return the result.

    The remote thread must be running a Qt event loop.
    """
    return ThreadCallFuture(thread, func, *args, **kwds)()


def runInGuiThread(func, *args, **kwds):
    """Run a function the main GUI thread and return the result.
    """
    return ThreadCallFuture(None, func, *args, **kwds)()


class ThreadCallFuture(Future):
    sigRequestCall = Qt.Signal()
    def __init__(self, thread, func, *args, **kwds):
        Future.__init__(self)
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
            err = ''.join(traceback.format_exception(*sys.exc_info()))
            self._taskDone(interrupted=True, error=err)

    def __call__(self):
        self.wait()
        if self.exc is not None:
            raise self.exc
        else:
            return self.ret


