# -*- coding: utf-8 -*-
from lib.Manager import *
import os, sys
from numpy import *
from PyQt4 import QtGui

## Make sure QApplication is created
app = QtGui.QApplication.instance()
if app is None:
    app = QtGui.QApplication(sys.argv)


config = 'config/mock.cfg'
if len(sys.argv) > 1:
    config = sys.argv[1]
config = os.path.abspath(config)

dm = Manager(config)
#dm.showDeviceRack()
dm.loadModule(module='DataManager', name='DM', config={})
#dm.setCurrentDir('junk')


win = QtGui.QMainWindow()
b = QtGui.QPushButton("Test")
win.setCentralWidget(b)
win.show()

def mkfiles():
    d = dm.getCurrentDir()
    d1 = d.mkdir("testDir", autoIncrement=True)
    a = MetaArray((2,2))
    d.writeFile(a, 'testFile', autoIncrement=True)
    d1.writeFile(a, 'testFile')

QtCore.QObject.connect(b, QtCore.SIGNAL('clicked()'), mkfiles)



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