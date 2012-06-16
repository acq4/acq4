# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np
import pyqtgraph.multiprocess as mp

app = pg.QtGui.QApplication([])

print "Start process"
proc = mp.Process()
print "started"
rnp = proc._import('numpy')
arr = rnp.array([1,2,3,4])
print repr(arr)
print str(arr)
print repr(arr.mean(returnValue=True))
print repr(arr.mean(returnValue=False))
print repr(arr.mean(returnValue='auto'))
#proc.join()
#print "process finished"

#print "Start forked process"
#try:
    #proc = mp.ForkedProcess()
#except SystemExit:
    #print "forked process exit"
    #raise
#print "started"
#rnp = proc._import('numpy')
#arr = rnp.array([1,2,3,4])
#print repr(arr)
#print str(arr)
#print repr(arr.mean())
#proc.join()
#print "process finished"

#print "Start Qt Process"
#proc = mp.QtProcess()
#rpg = proc._import('pyqtgraph')
#rpg.plot([1,5,2,3,4,2])


## Start Qt event loop unless running in interactive mode or using pyside.
#import sys
#if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
    #QtGui.QApplication.instance().exec_()
