# -*- coding: utf-8 -*-
print "Loading ACQ4..."

from lib.Manager import *
import os, sys
from numpy import *
from PyQt4 import QtGui

## Make sure QApplication is created
app = QtGui.QApplication.instance()
if app is None:
    app = QtGui.QApplication(sys.argv)


config = 'config/default.cfg'
#if len(sys.argv) > 1:
    #config = sys.argv[1]
#config = os.path.abspath(config)

dm = Manager(config, sys.argv[1:])
#dm.showDeviceRack()

#dm.setCurrentDir('junk')

#print "Loading camera module.."
#qtcam = dm.loadModule(module='Camera', name='Camera', config={'camDev': 'Camera'})
#print "Loading dataManager module.."
#dm.loadModule(module='Manager', name='Manager', config={})

## Start Qt event loop.
app.exec_()
