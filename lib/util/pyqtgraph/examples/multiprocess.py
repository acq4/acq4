# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)

import numpy as np
import pyqtgraph.multiprocess as mp


print "Start process"
proc = mp.Process()
print "started"
rnp = proc._import('numpy')
arr = rnp.array([1,2,3,4])
print repr(arr)
print str(arr)
print repr(arr.mean(_returnValue=True))
print repr(arr.mean(_returnValue=False))
print repr(arr.mean(_returnValue='auto'))
proc.join()
print "process finished"

print "Start forked process"
try:
    proc = mp.ForkedProcess()
except SystemExit:
    print "forked process exit"
    raise
print "started"
rnp = proc._import('numpy')
arr = rnp.array([1,2,3,4])
print repr(arr)
print str(arr)
print repr(arr.mean())
proc.join()
print "process finished"

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
app = pg.QtGui.QApplication([])

print "Start Qt Process"
proc = mp.QtProcess()
d1 = proc.transfer(np.random.normal(size=1000))
d2 = proc.transfer(np.random.normal(size=1000))
rpg = proc._import('pyqtgraph')
plt = rpg.plot(d1+d2)

## Start Qt event loop unless running in interactive mode or using pyside.
#import sys
#if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
    #QtGui.QApplication.instance().exec_()
