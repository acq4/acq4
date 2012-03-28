# -*- coding: utf-8 -*-
"""
acq4.py -  Main ACQ4 invocation script
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

print "Loading ACQ4..."

## rename any orphaned .pyc files -- these are probably leftover from 
## a module being moved and may interfere with expected operation.
import os, sys
from lib.util.pycRename import pycRename
modDir = os.path.abspath(os.path.split(__file__)[0])
pycRename(modDir)

import sip
sip.setapi('QString', 2)
sip.setapi('QVariant', 2)
    

## PyQt bug: make sure qt.conf was installed correctly
#pyDir = os.path.split(sys.executable)[0]
#qtConf = os.path.join(pyDir, 'qt.conf')
#if not os.path.exists(qtConf):
    #import shutil
    #pyqtConf = os.path.join(pyDir, 'Lib', 'site-packages', 'PyQt4', 'qt.conf')
    #if os.path.exists(pyqtConf):
        #print "PyQt fix: installing qt.conf where it should be.."
        #shutil.copy(pyqtConf, qtConf)

#import lib.util.PySideImporter  ## Use PySide instead of PyQt
from PyQt4 import QtGui, QtCore
#QtCore.QString = str
#def noop(x):
#    return x
#QtCore.QVariant = noop

## Needed to keep compatibility between pyside and pyqt
## (this can go away once the transition to PySide is complete)
if not hasattr(QtCore, 'Signal'):
    QtCore.Signal = QtCore.pyqtSignal
    QtCore.Slot = QtCore.pyqtSlot

    
from lib.Manager import *
from numpy import *


## Disable long-term storage of exception stack frames
## This fixes a potentially major memory leak, but
## may break some debuggers.
import disableExceptionStorage

## Initialize Qt
#QtGui.QApplication.setGraphicsSystem('raster')  ## needed for specific composition modes
app = QtGui.QApplication(sys.argv)

## Install a simple message handler for Qt errors:
def messageHandler(msgType, msg):
    import traceback
    print "Qt Error: (traceback follows)"
    print msg
    traceback.print_stack()
    try:
        logf = os.path.join(os.path.split(__file__)[0], "crash.log")
        fh = open(logf, 'a')
        fh.write(msg+'\n')
        fh.write('\n'.join(traceback.format_stack()))
        fh.close()
    except:
        print "Failed to write crash log:"
        traceback.print_exc()
        
    
    if msgType == QtCore.QtFatalMsg:
        try:
            print "Fatal error occurred; asking manager to quit."
            global man, app
            man.quit()
            app.processEvents()
        except:
            pass
    
QtCore.qInstallMsgHandler(messageHandler)

## For logging ALL python activity
#import pyconquer
#tr = pyconquer.Logger(fileregex="(Manager|DataManager|modules|devices|drivers)")
#tr.start()

## Configuration file to load
config = 'config/default.cfg'


## Create Manager. This configures devices and creates the main manager window.
man = Manager(config, sys.argv[1:])


## for debugging with pdb
#QtCore.pyqtRemoveInputHook()

## Start Qt event loop unless running in interactive mode.
interactive = (sys.flags.interactive == 1) and ('lib.util.PySideImporter' not in sys.modules)

## Run python code periodically to allow interactive debuggers to interrupt the qt event loop
timer = QtCore.QTimer()
def donothing(*args):
    x = 0
    for i in range(0, 100):
        x += i
timer.timeout.connect(donothing)
timer.start(1000)


if interactive:
    print "Interactive mode; not starting event loop."
    
    ## import some things useful on the command line
    from debug import *
    import pyqtgraph as pg
    import functions as fn
    import numpy as np

    ### Use CLI history and tab completion
    import atexit
    import os
    historyPath = os.path.expanduser("~/.pyhistory")
    try:
        import readline
    except ImportError:
        print "Module readline not available."
    else:
        import rlcompleter
        readline.parse_and_bind("tab: complete")
        if os.path.exists(historyPath):
            readline.read_history_file(historyPath)
    def save_history(historyPath=historyPath):
        try:
            import readline
        except ImportError:
            print "Module readline not available."
        else:
            readline.write_history_file(historyPath)
    atexit.register(save_history)
else:
    app.exec_()
    
    
    
    
    
#tr.stop()
