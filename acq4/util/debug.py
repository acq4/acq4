import logging

from pyqtgraph.debug import *
from pyqtgraph.exceptionHandling import original_excepthook

logger = logging.getLogger("acq4")


def installExceptionHandler():
    # install global exception handler for others to hook into.
    import pyqtgraph.exceptionHandling as exceptionHandling

    exceptionHandling.setTracebackClearing(True)
    exceptionHandling.register(exceptionCallback)


blockLogging = False


def exceptionCallback(*args):
    # Called whenever there is an unhandled exception.

    # unhandled exceptions generate an error message by default, but this
    # can be overridden by raising HelpfulException(msgType='...')
    global blockLogging
    if not blockLogging:
        # if an error occurs *while* trying to log another exception, disable any further logging to prevent recursion.
        try:
            blockLogging = True
            kwargs = {'exception': args, 'msgType': "error"}
            # TODO is this needed still?
            # if args:  # and 'Timeout' in str(args[0]):
            #     kwargs['threads'] = {
            #         id: traceback.format_stack(frames)
            #         for id, frames in sys._current_frames().items()
            #         if id != threading.current_thread().ident
            #     }
            logger.exception("Unexpected error", exc_info=args)
        except:
            print("Error: Exception could not be logged.")
            original_excepthook(*sys.exc_info())
        finally:
            blockLogging = False
