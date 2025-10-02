import contextlib
import logging
import sys
import threading

from pyqtgraph import exceptionHandling

logger = logging.getLogger("acq4")


def installExceptionHandler():
    # install global exception handler for others to hook into.

    exceptionHandling.setTracebackClearing(True)
    exceptionHandling.register(exception_callback)


@contextlib.contextmanager
def except_and_print(exc_types, *a, **kw):
    try:
        yield
    except exc_types:
        logger.exception(*a, **kw)


thread_locals = threading.local()


def exception_callback(*args):
    # nothing fancy if an error occurs in this thread *while* trying to log another exception
    if getattr(thread_locals, 'block_logging', False):
        exceptionHandling.original_excepthook(*args)

    try:
        thread_locals.block_logging = True
        log_fn = logger.exception
        # can be overridden by raising HelpfulException(msgType='...')
        msg_type = getattr(args[1], 'kwargs', {}).get('msgType', '')
        if msg_type == 'status':
            log_fn = logger.info
        elif msg_type == 'warning':
            log_fn = logger.warning
        log_fn("Unexpected error", exc_info=args)
    except Exception:
        print("Error: Exception could not be logged.")
        exceptionHandling.original_excepthook(*sys.exc_info())
    finally:
        thread_locals.block_logging = False
