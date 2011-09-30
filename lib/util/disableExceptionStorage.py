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
def excepthook(*args):
    global original_excepthook
    #print args
    ret = original_excepthook(*args)
    #getManager().logExc(*args)
    logMsg("Unhandled exception: ", exception=args, msgType='error')
    sys.last_traceback = None           ## the important bit
    
    
sys.excepthook = excepthook
