import inspect
import sys
import threading
import types
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


# Type variables for preserving function signature
T = TypeVar("T")
P = ParamSpec("P")


def inGuiThread(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to run a function or method in the GUI thread.

    Works with:
    - Instance methods in an acq4.util.Qt.QObject subclass (as signals/slots)
    - Non-QObject methods, static methods and pure functions

    Args:
        func: The function or method to decorate

    Additional params at runtime:
        blocking: If True, waits for the function to complete. Default False.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        # Extract blocking parameter if present, default to False
        blocking = False
        if "blocking" in kwargs and kwargs["blocking"] is not None:
            blocking = kwargs.pop("blocking")

        # Determine if this is a method call
        is_method = args and getattr(getattr(args[0].__class__, func.__name__, None), "_original_func", None) == func

        if is_method:
            # This is a method call with a self parameter
            self = args[0]
            method_args = args[1:]

            # Check if we're running in a decorated class
            signal_name = f"__{func.__name__}Event"
            if hasattr(self.__class__, signal_name):
                # Using signal-based approach with class decorator
                signal = getattr(self, signal_name)
                if blocking:
                    impl_name = f"_{func.__name__}"
                    if hasattr(self, impl_name):
                        result = runInGuiThread(getattr(self, impl_name), *method_args, **kwargs)
                        return cast(T, result)
                    else:
                        # Fallback to signal with a barrier
                        barrier = threading.Event()
                        result_container = [None]

                        def signal_handler(*sig_args: Any) -> None:
                            result_container[0] = func(self, *sig_args, **kwargs)
                            barrier.set()

                        signal.connect(signal_handler)
                        signal.emit(*method_args)
                        barrier.wait()
                        signal.disconnect(signal_handler)
                        return cast(T, result_container[0])
                else:
                    # Non-blocking signal emission
                    signal.emit(*method_args)
                    return cast(T, None)
            else:
                # No class decoration, use QTimer or runInGuiThread
                if blocking:
                    result = runInGuiThread(func, *args, **kwargs)
                    return cast(T, result)
                else:
                    Qt.QTimer.singleShot(0, lambda: func(self, *method_args, **kwargs))
                    return cast(T, None)
        else:
            # This is a pure function or static method
            if blocking:
                result = runInGuiThread(func, *args, **kwargs)
                return cast(T, result)
            else:
                Qt.QTimer.singleShot(0, lambda: func(*args, **kwargs))
                return cast(T, None)

    sig = inspect.signature(func)
    param_count = len([p for p in sig.parameters.values()
                       if p.name != 'self' and p.default is p.empty])
    wrapper._param_count = param_count
    setattr(wrapper, "__annotations__", {**getattr(func, "__annotations__", {}), "blocking": "Optional[bool] = None"})
    wrapper._original_func = func
    wrapper._run_in_gui_thread = True
    return cast(Callable[P, T], wrapper)


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
            self._taskDone(interrupted=True, excInfo=sys.exc_info())

    def __call__(self):
        self.wait()
        if self.exc is not None:
            raise self.exc
        else:
            return self.ret
