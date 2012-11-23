# -*- coding: utf-8 -*-

##  This example uses the isosurface function to convert a scalar field
##  (a hydrogen orbital) into a mesh for 3D display.

## Add path to library (just for examples; you do not need this)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg
import pyqtgraph.opengl as gl

app = QtGui.QApplication([])
w = gl.GLViewWidget()
w.show()

w.setCameraPosition(distance=40)

g = gl.GLGridItem()
g.scale(2,2,1)
g.setDepthValue(10)  # draw grid after surface since it is translucent
w.addItem(g)

import numpy as np

cols = 100
rows = 100
x = np.linspace(-10, 10, cols+1).reshape(cols+1,1)
y = np.linspace(-10, 10, rows+1).reshape(1,rows+1)
d = (x**2 + y**2) * 0.1
d2 = d ** 0.5 + 0.1

verts = np.empty((cols+1, rows+1, 3))
verts[:,:,0] = x
verts[:,:,1] = y
verts[:,:,2] = 0

colors = np.zeros((cols+1, rows+1, 4))
colors[...,3] = 1.0

faces = np.empty((cols*rows*2, 3), dtype=np.uint)
rowtemplate1 = np.arange(cols).reshape(cols, 1) + np.array([[0, 1, cols+1]])
rowtemplate2 = np.arange(cols).reshape(cols, 1) + np.array([[cols+1, 1, cols+2]])
for row in range(rows):
    start = row * cols * 2 
    faces[start:start+cols] = rowtemplate1 + row * (cols+1)
    faces[start+cols:start+(cols*2)] = rowtemplate2 + row * (cols+1)

## Mesh item will automatically compute face normals.
md = gl.MeshData.MeshData(vertexes=verts.reshape((cols+1) * (rows+1), 3), faces=faces, vertexColors=colors.reshape((cols+1) * (rows+1), 4))
m1 = gl.GLMeshItem(meshdata=md, smooth=False, computeNormals=False)
w.addItem(m1)

phi = 0
def update():
    global verts, m1, md, d, d2, phi, colors
    phi -= 0.1
    verts[:,:,2] = np.sin(d + phi) / d2
    md.setVertexes()
    colors[...,0] = np.clip(verts[:,:,2]+0.5, 0, 1)
    colors[...,1] = np.clip(verts[:,:,2], 0, 1)
    colors[...,2] = np.clip(verts[:,:,2]-1, 0, 1)
    md.setVertexColors(colors.reshape(colors.shape[0]*colors.shape[1], 4))
    m1.vertexes = None
    m1.colors = None
    m1.update()
    
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(30)

## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
