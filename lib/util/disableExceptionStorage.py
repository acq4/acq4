# -*- coding: utf-8 -*-
"""This module installs a wrapper around sys.excepthook which stops 
exceptions from causing long-term storage of local stack frames. This
has two major effects:
 - Unhandled exceptions will no longer cause memory leaks
 - Debuggers may have a hard time handling uncaught exceptions """

import sys

original_excepthook = sys.excepthook
def excepthook(*args):
    global original_excepthook
    ret = original_excepthook(*args)
    sys.last_traceback = None           ## the important bit

# sys.excepthook = excepthook
