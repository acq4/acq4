# -*- coding: utf-8 -*-
## Add path to library (just for examples; you do not need this)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.opengl as gl

app = QtGui.QApplication([])
w = gl.GLViewWidget()
w.opts['distance'] = 20
w.show()

ax = gl.GLAxisItem()
ax.setSize(5,5,5)
w.addItem(ax)

pts = [{'pos': (0,0,0), 'size':10, 'color':(0.2, 0.2, 1.0, 1.0)}, {'pos': (1,0,0), 'size':20}, {'pos': (0,1,0)}, {'pos': (0,0,1)}]
sp = gl.GLScatterPlotItem(pts)
w.addItem(sp)

## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
