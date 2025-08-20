import logging

import pyqtgraph.debug as pgdebug
from pyqtgraph.debug import *
from pyqtgraph.exceptionHandling import original_excepthook


def installExceptionHandler():
    # install global exception handler for others to hook into.
    import pyqtgraph.exceptionHandling as exceptionHandling

    exceptionHandling.setTracebackClearing(True)
    exceptionHandling.register(exceptionCallback)


def printExc(msg="", indent=4, prefix="|", msgType="error"):
    """Alert the user to an exception that has occurred, but without letting that exception propagate further.
    (This function is intended to be called within except: blocks)"""
    pgdebug.printExc(msg, indent, prefix)
    # try:
    #     import acq4.Manager
    #
    #     if hasattr(acq4, "Manager"):
    #         acq4.Manager.logExc(msg=msg, msgType=msgType)
    # except Exception:
    #     pgdebug.printExc(f"[failed to log this error to manager] {msgType}: {msg}")


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
            if args:  # and 'Timeout' in str(args[0]):
                kwargs['threads'] = {
                    id: traceback.format_stack(frames)
                    for id, frames in sys._current_frames().items()
                    if id != threading.current_thread().ident
                }
            logging.exception(f"Unexpected error: {kwargs!r}", exc_info=args)
        except:
            print("Error: Exception could not be logged.")
            original_excepthook(*sys.exc_info())
        finally:
            blockLogging = False
