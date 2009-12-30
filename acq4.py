# -*- coding: utf-8 -*-
"""
acq4.py -  Main ACQ4 invocation script
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This script is about the simplest way to start up ACQ4. All it does is start the 
manager with a configuration file and let it go from there.
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
dm = Manager(config, sys.argv[1:])

## for debugging with pdb
#QtCore.pyqtRemoveInputHook()

## Start Qt event loop.
## Optionally, one could comment out this line and run python interactively 
## to have direct access to the program internals.
app.exec_()

print "Qt event loop exited."