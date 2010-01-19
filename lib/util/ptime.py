# -*- coding: utf-8 -*-
"""
ptime.py -  Precision time function made os-independent (should have been taken care of by python)
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""


import sys
import time as systime
START_TIME = None
time = None

def winTime():
    """Return the current time in seconds with high precision (windows version, use Manager.time() to stay platform independent)."""
    #return systime.clock() + START_TIME    #### This is not required anymore?? If so, we can get rid of ptime altogether..
    return systime.time()

def unixTime():
    """Return the current time in seconds with high precision (unix version, use Manager.time() to stay platform independent)."""
    return systime.time()

if 'win' in sys.platform:
    systime.clock()  ### Required to start the clock in windows
    START_TIME = systime.time()
    time = winTime
else:
    time = unixTime

