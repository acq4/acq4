# -*- coding: utf-8 -*-
"""
debug.py - Functions to aid in debugging 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

from acq4.pyqtgraph.debug import *
import acq4.pyqtgraph.debug as pgdebug


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
        
    
    
