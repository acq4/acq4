# -*- coding: utf-8 -*-
from lib.Manager import *
import os, sys
from numpy import *
from PyQt4 import QtGui

## Make sure QApplication is created
app = QtGui.QApplication.instance()
if app is None:
    app = QtGui.QApplication(sys.argv)


config = 'config/default.cfg'
if len(sys.argv) > 1:
    config = sys.argv[1]
config = os.path.abspath(config)

dm = Manager(config)
#dm.showDeviceRack()

dm.setCurrentDir('junk')

print "Loading all modules.."
#p1 = dm.loadModule(module='Patch', name='Patch0', config={'clampDev': 'Clamp1'})
#p2 = dm.loadModule(module='Patch', name='Patch1', config={'clampDev': 'Clamp2'})
prm = dm.loadModule(module='ProtocolRunner', name='PR', config={'globalDir': os.path.abspath('config/protocols')})
qtcam = dm.loadModule(module='Camera', name='Camera', config={'camDev': 'Camera'})
dm.loadModule(module='DataManager', name='DM', config={})

## If running interactively, just return to the prompt and let python call the qt event loop for us.
## Otherwise, we need to run it ourselves:
print "Checking to see if we should start the Qt event loop"
if not sys.stdin.isatty():
    print "  .. starting the Qt event loop."
    app.exec_()
else:
    print "Exiting script, hopefully entering interactive mode.."

## isatty is broken for cygwin shell. This should not be needed for regular windows shell..
app.exec_()

#dm.quit()
