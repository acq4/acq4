# -*- coding: utf-8 -*-
"""
debug.py - Functions to aid in debugging 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

#import sys, traceback, time, gc, re, types, weakref, inspect, os, cProfile
#import acq4.util.ptime as ptime
#from numpy import ndarray
#from PyQt4 import QtCore, QtGui
from acq4.pyqtgraph.debug import *
import acq4.pyqtgraph.debug as pgdebug



def printExc(msg='', indent=4, prefix='|', msgType='error'):
    """Print an error message followed by an indented exception backtrace
    (This function is intended to be called within except: blocks)"""
    try:
        import acq4.Manager
        acq4.Manager.logExc(msg=msg, msgType=msgType)
    except ImportError:
        print "[import acq4 failed; not logging this error to manager]"
    pgdebug.printExc(msg, indent, prefix)
    
    
