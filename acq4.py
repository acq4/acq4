# -*- coding: utf-8 -*-
"""
acq4.py -  Main ACQ4 invocation script
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This script is about the simplest way to start up ACQ4. All it does is start the 
manager with a configuration file and let it go from there.
"""

print "Loading ACQ4..."
#import lib.util.PySideImporter  ## Use PySide instead of PyQt
from lib.Manager import *
import os, sys
from numpy import *
from PyQt4 import QtGui, QtCore


## Disable long-term storage of exception stack frames
## This fixes a potentially major memory leak, but
## may break some debuggers.
import disableExceptionStorage

## Needed to keep compatibility between pyside and pyqt
## (this can go away once the transition to PySide is complete)
QtCore.Signal = QtCore.pyqtSignal
QtCore.Slot = QtCore.pyqtSlot


## Initialize Qt
app = QtGui.QApplication(sys.argv)

## For logging ALL python activity
#import pyconquer
#tr = pyconquer.Logger(fileregex="(Manager|DataManager|modules|devices|drivers)")
#tr.start()

## Configuration file to load
config = 'config/default.cfg'


## Create Manager. This configures devices and creates the main manager window.
dm = Manager(config, sys.argv[1:])


## for debugging with pdb
#QtCore.pyqtRemoveInputHook()

## Start Qt event loop unless running in interactive mode.
try:
    assert sys.flags.interactive == 1
    print "Interactive mode; not starting event loop."
    
    ## import some things useful on the command line
    from debug import *
    from pyqtgraph.graphicsWindows import *
    from functions import *
    
except:
    ## Run python code periodically to allow interactive debuggers to interrupt the qt event loop
    timer = QtCore.QTimer()
    def donothing(*args):
        x = 0
        for i in range(0, 100):
            x += i
    timer.connect(timer, QtCore.SIGNAL("timeout()"), donothing)
    timer.start(200)
    
    print "Starting Qt event loop.."
    app.exec_()
    print "Qt event loop exited."
    
    
#tr.stop()