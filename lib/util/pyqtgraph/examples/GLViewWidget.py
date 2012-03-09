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

ax = gl.GLAxisItem()
ax.setSize(5,5,5)
w.addItem(ax)

b = gl.GLBoxItem()
w.addItem(b)

ax2 = gl.GLAxisItem()
ax2.setParentItem(b)

## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
