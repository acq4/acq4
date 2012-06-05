# -*- coding: utf-8 -*-
"""This module installs a wrapper around sys.excepthook which stops 
exceptions from causing long-term storage of local stack frames. This
has two major effects:
 - Unhandled exceptions will no longer cause memory leaks
 - Debuggers may have a hard time handling uncaught exceptions
 
The module also provides a callback mechanism allowing others to respond 
to exceptions.
"""

import sys, time
#from lib.Manager import logMsg
import traceback
#from log import *

original_excepthook = sys.excepthook
#logging = False

callbacks = []

def installCallback(fn):
    callbacks.append(fn)
    
def removeCallback(fn):
    callbacks.remove(fn)

def excepthook(*args):
    ## call original exception handler first (prints exception)
    global original_excepthook, callbacks
    print "=====", time.strftime("%Y.%m.%d %H:%m:%S", time.localtime(time.time())), "====="
    ret = original_excepthook(*args)
    
    for cb in callbacks:
        try:
            cb(*args)
        except:
            print "   --------------------------------------------------------------"
            print "      Error occurred during exception callback", cb
            print "   --------------------------------------------------------------"
            traceback.print_exception(*sys.exc_info())
        
    
    ## Clear long-term storage of last traceback to prevent memory-hogging.
    ## (If an exception occurs while a lot of data is present on the stack, 
    ## such as when loading large files, the data would ordinarily be kept
    ## until the next exception occurs. We would rather release this memory 
    ## as soon as possible.)
    sys.last_traceback = None           

sys.excepthook = excepthook



