# -*- coding: utf-8 -*-
"""This module installs a wrapper around sys.excepthook which stops 
exceptions from causing long-term storage of local stack frames. This
has two major effects:
 - Unhandled exceptions will no longer cause memory leaks
 - Debuggers may have a hard time handling uncaught exceptions """

import sys
from lib.Manager import logMsg
import traceback
#from log import *

original_excepthook = sys.excepthook
logging = False
def excepthook(*args):
    global original_excepthook
    #print args
    ret = original_excepthook(*args)
    #getManager().logExc(*args)
    
    ## unhandled exceptions generate an error by default, but this
    ## can be overridden by raising HelpfulException(msgType='...')
    global logging
    if not logging:
        try:
            logging = True
            logMsg("Unexpected error: ", exception=args, msgType='error')
        except:
            print "Error: Exception could no be logged."
            original_excepthook(*sys.exc_info())
        finally:
            logging = False
    
    sys.last_traceback = None           ## the important bit

sys.excepthook = excepthook
