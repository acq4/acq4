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

## Hydrogen electron probability density
def psi(i, j, k, n=50):
    x = i-n/2.
    y = j-n/2.
    z = k-n/2.
    th = np.arctan2(z, (x**2+y**2)**0.5)
    phi = np.arctan2(y, x)
    r = (x**2 + y**2 + z **2)**0.5
    a0 = 2
    return ((1./81.) * (2./np.pi)**0.5 * (1./a0)**(3/2) * (6 - r/a0) * (r/a0) * np.exp(-r/(3*a0)) * np.cos(th))**2
    #return ((1./81.) * (1./np.pi)**0.5 * (1./a0)**(3/2) * (r/a0)**2 * (r/a0) * np.exp(-r/(3*a0)) * np.sin(th) * np.cos(th) * np.exp(2 * 1j * phi))**2 


data = np.fromfunction(psi, (50,50,50)); 


#data = np.fromfunction(lambda i,j,k: np.sin(0.2*((i-25)**2+(j-15)**2+k**2)**0.5), (50,50,50)); 
tr.translate(-25, -25, -25)
for i in np.linspace(data.min(), data.max(), 3)[1:-1]:
    faces = pg.isosurface(data, i)
    m = gl.GLMeshItem(faces)
    w.addItem(m)
    m.setTransform(tr)
    

#data = np.zeros((5,5,5))
#data[2,2,1:4] = 1
#data[2,1:4,2] = 1
#data[1:4,2,2] = 1
#tr.translate(-2.5, -2.5, 0)
#data = np.ones((2,2,2))
#data[0, 1, 0] = 0
#faces = pg.isosurface(data, 0.5)
#m = gl.GLMeshItem(faces)
#w.addItem(m)
#m.setTransform(tr)

## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
