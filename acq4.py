# -*- coding: utf-8 -*-
"""
acq4.py -  Main ACQ4 invocation script
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

print "Loading ACQ4..."

## Path adjustments:
##   - make sure 'lib' path is available for module search
##   - add util to front of search path. This allows us to override some libs 
##     that may be installed globally with local versions.
import sys
import os.path as osp
path = osp.dirname(osp.abspath(__file__))
sys.path = [osp.join(path, 'lib', 'util'), osp.join(path, 'lib', 'util', 'pyqtgraph')] + sys.path + [path]


import sip
sip.setapi('QString', 2)
sip.setapi('QVariant', 2)
    
## rename any orphaned .pyc files -- these are probably leftover from 
## a module being moved and may interfere with expected operation.
import os, sys
from pyqtgraph import renamePyc
modDir = os.path.abspath(os.path.split(__file__)[0])
renamePyc(modDir)


#import lib.util.PySideImporter  ## Use PySide instead of PyQt
from PyQt4 import QtGui, QtCore

## Needed to keep compatibility between pyside and pyqt
## (this can go away once the transition to PySide is complete)
if not hasattr(QtCore, 'Signal'):
    QtCore.Signal = QtCore.pyqtSignal
    QtCore.Slot = QtCore.pyqtSlot

    
from lib.Manager import *
from numpy import *

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
        logf = "crash.log"
            
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

## Try a few default config file locations
configs = [
    osp.join(path, 'config', 'default.cfg'),
    osp.join(path, 'config', 'example', 'default.cfg'), # last, load the example config
    ]

for config in configs:
    if osp.isfile(config):
        break

## Create Manager. This configures devices and creates the main manager window.
man = Manager(config, sys.argv[1:])

# If example config was loaded, offer more help to the user.
message = "No configuration file found. ACQ4 is running from an example configuration file at %s. This configuration defines several simulated devices that allow you to test the capabilities of ACQ4. Would you like to load the tutorial now?" % config
if config == configs[-1]:
    mbox = QtGui.QMessageBox()
    mbox.setText(message)
    mbox.setStandardButtons(mbox.No | mbox.Yes)
    if mbox.exec_():
        man.showDocumentation('tutorial')
    

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
    pg.exit() ## force exit without garbage collection
    
    
    
    
#tr.stop()
