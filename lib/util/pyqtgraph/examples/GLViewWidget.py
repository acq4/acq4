# -*- coding: utf-8 -*-
## Add path to library (just for examples; you do not need this)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.opengl as gl

app = QtGui.QApplication([])
w = gl.GLViewWidget()
w.opts['distance'] = 100
w.show()


b = gl.GLBoxItem()
w.addItem(b)

import numpy as np
n = 32
data = np.random.randint(0, 255, size=4*n**3).astype(np.uint8).reshape((n,n,n,4))
data[...,3] *= 0.6
for i in range(n):
    data[i,:,:,0] = i*256./n
v = gl.GLVolumeItem(data,slices=32)
w.addItem(v)

