# -*- coding: utf-8 -*-
from lib.Manager import *
import os, sys
from numpy import *
from PyQt4 import QtGui

## Make sure QApplication is created
app = QtGui.QApplication.instance()
if app is None:
    app = QtGui.QApplication(sys.argv)

config = 'config/default_nodevs.cfg'

m = Manager(config)
m.loadModule(module='DataManager', name='DM', config={})

app.exec_()
