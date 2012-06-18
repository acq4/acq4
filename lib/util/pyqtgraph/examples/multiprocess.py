# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)

import numpy as np
import pyqtgraph.multiprocess as mp
from pyqtgraph.multiprocess.parallelizer import Parallelize #, Parallelizer
import time

print "\n=================\nParallelize"
tasks = [1,2,4,8]
results = [None] * len(tasks)
size = 2000000

start = time.time()
with Parallelize(enumerate(tasks), results=results, workers=1) as tasker:
    for i, x in tasker:
        print i, x
        tot = 0
        for j in xrange(size):
            tot += j * x
        results[i] = tot
print results
print "serial:", time.time() - start

start = time.time()
with Parallelize(enumerate(tasks), results=results) as tasker:
    for i, x in tasker:
        print i, x
        tot = 0
        for j in xrange(size):
            tot += j * x
        results[i] = tot
print results
print "parallel:", time.time() - start


#print "\n=================\nParallelize (old)"
#start = time.time()
#par = Parallelizer()
#with par(1) as i:
    #for i, x in enumerate(tasks):
        #print i, x
        #tot = 0
        #for j in xrange(size):
            #tot += j * x
        #par.finish((i, tot))
#print par.result()
#print "serial:", time.time() - start

#start = time.time()
#par = Parallelizer()
#with par(2) as i:
    #for i, x in enumerate(tasks):
        #print i, x
        #tot = 0
        #for j in xrange(size):
            #tot += j * x
        #par.finish((i, tot))
#print par.result()
#print "parallel:", time.time() - start


#import sys
#sys.exit()


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
