# -*- coding: utf-8 -*-
from lib.DeviceManager import *
import lib.DataManager as DataManager
import os, sys
from numpy import *
from PyQt4 import QtGui

config = 'config/default.cfg'
if len(sys.argv) > 1:
    config = sys.argv[1]
config = os.path.abspath(config)

dm = DeviceManager(config)
datam = DataManager.createDataHandler('junk/data')

qtcam = dm.loadModule(module='Camera', name='Camera', {'camDev': 'Camera'})

## If running interactively, just return to the prompt and let python call the qt event loop for us.
## Otherwise, we need to run it ourselves:
if not sys.stdin.isatty():
    app = QtGui.QApplication.instance()
    if app is None:
        app = QtGui.QApplication(sys.argv)
    app.exec_()
    