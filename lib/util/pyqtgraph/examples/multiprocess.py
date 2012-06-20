# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)
import numpy as np
import pyqtgraph.multiprocess as mp
import pyqtgraph as pg
import time

print "\n=================\nParallelize"

## Do a simple task: 
##   for x in range(N):
##      sum([x*i for i in range(M)])
##
## We'll do this three times
##   - once without Parallelize
##   - once with Parallelize, but forced to use a single worker
##   - once with Parallelize automatically determining how many workers to use
##

tasks = range(10)
results = [None] * len(tasks)
results2 = results[:]
results3 = results[:]
size = 2000000

pg.mkQApp()

### Purely serial processing
start = time.time()
with pg.ProgressDialog('processing serially..', maximum=len(tasks)) as dlg:
    for i, x in enumerate(tasks):
        tot = 0
        for j in xrange(size):
            tot += j * x
        results[i] = tot
        dlg += 1
        if dlg.wasCanceled():
            raise Exception('processing canceled')
print "Serial time: %0.2f" % (time.time() - start)

### Use parallelize, but force a single worker
### (this simulates the behavior seen on windows, which lacks os.fork)
start = time.time()
with mp.Parallelize(enumerate(tasks), results=results2, workers=1, progressDialog='processing serially (using Parallelizer)..') as tasker:
    for i, x in tasker:
        tot = 0
        for j in xrange(size):
            tot += j * x
        tasker.results[i] = tot
print "\nParallel time, 1 worker: %0.2f" % (time.time() - start)
print "Results match serial:   ", results2 == results

### Use parallelize with multiple workers
start = time.time()
with mp.Parallelize(enumerate(tasks), results=results3, progressDialog='processing in parallel..') as tasker:
    for i, x in tasker:
        tot = 0
        for j in xrange(size):
            tot += j * x
        tasker.results[i] = tot
print "\nParallel time, %d workers: %0.2f" % (mp.Parallelize.suggestedWorkerCount(), time.time() - start)
print "Results match serial:      ", results3 == results




print "\n=================\nStart Process"
proc = mp.Process()
import os
print "parent:", os.getpid(), "child:", proc.proc.pid
print "started"
rnp = proc._import('numpy')
arr = rnp.array([1,2,3,4])
print repr(arr)
print str(arr)
print "return value:", repr(arr.mean(_returnType='value'))
print "return proxy:", repr(arr.mean(_returnType='proxy'))
print "return auto: ", repr(arr.mean(_returnType='auto'))
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
