# Helpers for running a function in a specific Qt thread and getting its result.
# Thin wrappers over the gentletask bridge in acq4.util.gentle.

from typing import TypeVar, ParamSpec

from . import Qt
from . import gentle


def runInThread(thread, func, *args, **kwds):
    """Run a function in another thread and return the result.

    The remote thread must be running a Qt event loop.
    """
    return gentle._GuiCall(thread, func, args, kwds).result()


def runInGuiThread(func, *args, **kwds):
    """Run a function in the main GUI thread and return the result."""
    return gentle.run_in_gui_thread(func, *args, **kwds)


def futureInGuiThread(func, *args, **kwds):
    """Run a function in the main GUI thread and return a task for its result."""
    return gentle.task_in_gui_thread(func, *args, **kwds)


# Type variables for preserving function signature
T = TypeVar("T")
P = ParamSpec("P")


def inGuiThread(func):
    def run_func_in_gui_thread(*args, **kwds):
        return runInGuiThread(func, *args, **kwds)
    return run_func_in_gui_thread
