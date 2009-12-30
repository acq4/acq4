# -*- coding: utf-8 -*-
"""
acq4-camera.py -  Camera-only ACQ4 invocation script
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This script shows an example alternate startup for ACQ4, using a different
configuration file and automatically loading the Camera and DataManager 
modules.
"""

print "Loading ACQ4..."

from lib.Manager import *
import os, sys
from numpy import *
from PyQt4 import QtGui, QtCore

## Initialize Qt
app = QtGui.QApplication(sys.argv)

## Configuration file to load
config = 'config/default.cfg'

## Create Manager. This configures devices and creates the main manager window.
m = Manager(config, sys.argv[1:])
m.loadNamedModule('Camera')
m.loadModule(module='DataManager', name='DM', config={})

## for debugging with pdb
#QtCore.pyqtRemoveInputHook()

## Start Qt event loop.
app.exec_()

print "Qt event loop exited."
