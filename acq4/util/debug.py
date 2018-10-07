# -*- coding: utf-8 -*-
from __future__ import print_function
"""
debug.py - Functions to aid in debugging 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

from acq4.pyqtgraph.debug import *
import acq4.pyqtgraph.debug as pgdebug


LOG_UI = None

def __reload__(old):
    # preserve old log window
    global LOG_UI
    LOG_UI = old['LOG']


def installExceptionHandler():
    ## install global exception handler for others to hook into.
    import acq4.pyqtgraph.exceptionHandling as exceptionHandling   
    exceptionHandling.setTracebackClearing(True)
    exceptionHandling.register(exceptionCallback)        
    

def createLogWindow(manager):
    from .LogWindow import LogWindow
    global LOG_UI
    assert LOG_UI is None
    LOG_UI = LogWindow(manager)
    return LOG_UI


def printExc(msg='', indent=4, prefix='|', msgType='error'):
    """Print an error message followed by an indented exception backtrace
    (This function is intended to be called within except: blocks)"""
    pgdebug.printExc(msg, indent, prefix)
    try:
        import acq4.Manager
        if hasattr(acq4, 'Manager'):
            acq4.Manager.logExc(msg=msg, msgType=msgType)
    except Exception:
        pgdebug.printExc("[failed to log this error to manager]")
        
    
def logMsg(msg, **kwargs):
    """msg: the text of the log message
       msgTypes: user, status, error, warning (status is default)
       importance: 0-9 (0 is low importance, 9 is high, 5 is default)
       other supported keywords:
          exception: a tuple (type, exception, traceback) as returned by sys.exc_info()
          docs: a list of strings where documentation related to the message can be found
          reasons: a list of reasons (as strings) for the message
          traceback: a list of formatted callstack/trackback objects (formatting a traceback/callstack returns a list of strings), usually looks like [['line 1', 'line 2', 'line3'], ['line1', 'line2']]
       Feel free to add your own keyword arguments. These will be saved in the log.txt file, but will not affect the content or way that messages are displayed.
        """
    global LOG_UI
    if LOG_UI is not None:
        try:
            LOG_UI.logMsg(msg, **kwargs)
        except:
            print("Error logging message:")
            print("    " + "\n    ".join(msg.split("\n")))
            print("    " + str(kwargs))
            sys.excepthook(*sys.exc_info())
    else:
        print("Can't log message; no log created yet.")
        #print args
        print(kwargs)
        
    
def logExc(msg, *args, **kwargs):
    """Calls logMsg, but adds in the current exception and callstack. Must be called within an except block, and should only be called if the exception is not re-raised. Unhandled exceptions, or exceptions that reach the top of the callstack are automatically logged, so logging an exception that will be re-raised can cause the exception to be logged twice. Takes the same arguments as logMsg."""
    global LOG_UI
    if LOG_UI is not None:
        try:
            LOG_UI.logExc(msg, *args, **kwargs)
        except:
            print("Error logging exception:")
            print("    " + "\n    ".join(msg.split("\n")))
            print("    " + str(kwargs))
            sys.excepthook(*sys.exc_info())
    else:
        print("Can't log error message; no log created yet.")
        print(args)
        print(kwargs)


blockLogging = False
def exceptionCallback(*args):
    ## Called whenever there is an unhandled exception.
    
    ## unhandled exceptions generate an error message by default, but this
    ## can be overridden by raising HelpfulException(msgType='...')
    global blockLogging
    if not blockLogging:  ## if an error occurs *while* trying to log another exception, disable any further logging to prevent recursion.
        try:
            blockLogging = True
            logMsg("Unexpected error: ", exception=args, msgType='error')
        except:
            print("Error: Exception could no be logged.")
            original_excepthook(*sys.exc_info())
        finally:
            blockLogging = False


