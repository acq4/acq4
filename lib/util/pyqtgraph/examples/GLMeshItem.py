# -*- coding: utf-8 -*-
## Add path to library (just for examples; you do not need this)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg
import pyqtgraph.opengl as gl

app = QtGui.QApplication([])
w = gl.GLViewWidget()
w.show()


import numpy as np

tr = QtGui.QMatrix4x4()
#data = np.fromfunction(lambda i,j,k: np.sin(0.2*((i-25)**2+(j-15)**2+k**2)**0.5), (50,50,50)); 
#tr.translate(-25, -15, 0)
#faces = pg.isosurface(data, 0.0)
data = np.zeros((5,5,5))
data[2,2,1:4] = 1
data[2,1:4,2] = 1
data[1:4,2,2] = 1
tr.translate(-2.5, -2.5, 0)
faces = pg.isosurface(data, 0.5)

m = gl.GLMeshItem(faces)
w.addItem(m)
m.setTransform(tr)

## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
