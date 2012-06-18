# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)

import numpy as np
import pyqtgraph.multiprocess as mp
from pyqtgraph.multiprocess.parallelizer import Parallelize, Parallelizer
import time

print "\n=================\nParallelize"
tasks = [1,2,4,8]
results = [None] * len(tasks)

start = time.time()
with Parallelize(enumerate(tasks), results=results, workers=1) as tasker:
    for i, x in tasker:
        results[i] = (np.random.normal(size=3000000) * x).std()
print results
print "serial:", time.time() - start

start = time.time()
with Parallelize(enumerate(tasks), results=results) as tasker:
    for i, x in tasker:
        results[i] = (np.random.normal(size=3000000) * x).std()
print results
print "parallel:", time.time() - start


start = time.time()
par = Parallelizer()
with par(1) as i:
    for i, x in enumerate(tasks):
        res = (np.random.normal(size=3000000) * x).std()
        par.finish((i, res))
print par.result()
print "serial:", time.time() - start

start = time.time()
par = Parallelizer()
with par(2) as i:
    for j, x in enumerate(tasks[i*2:(i+1)*2]):
        res = (np.random.normal(size=3000000) * x).std()
        par.finish((i, res))
print par.result()
print "parallel:", time.time() - start


import sys
sys.exit()


print "\n=================\nStart Process"
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



print "\n=================\nStart ForkedProcess"
proc = mp.ForkedProcess()
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

print "\n=================\nStart QtProcess"
proc = mp.QtProcess()
d1 = proc.transfer(np.random.normal(size=1000))
d2 = proc.transfer(np.random.normal(size=1000))
rpg = proc._import('pyqtgraph')
plt = rpg.plot(d1+d2)

## Start Qt event loop unless running in interactive mode or using pyside.
#import sys
#if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
    #QtGui.QApplication.instance().exec_()
