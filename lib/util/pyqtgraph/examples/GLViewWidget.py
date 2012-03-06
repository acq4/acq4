# -*- coding: utf-8 -*-
## Add path to library (just for examples; you do not need this)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.opengl as gl

app = QtGui.QApplication([])
w = gl.GLViewWidget()
w.opts['distance'] = 800
w.show()


b = gl.GLBoxItem()
w.addItem(b)

import numpy as np
n = 128
data = np.random.randint(0, 255, size=4*n**3).astype(np.uint8).reshape((n*2,n,n/2,4))
data[...,3] *=0.5
for i in range(data.shape[0]):
    data[i,:,:,0] *= float(i)/data.shape[0]
for i in range(data.shape[1]):
    data[:,i,:,1] *= float(i)/data.shape[1]
for i in range(data.shape[2]):
    data[:,:,i,2] *= float(i)/data.shape[1]
v = gl.GLVolumeItem(data)
w.addItem(v)


## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
