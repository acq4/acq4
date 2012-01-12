# -*- coding: utf-8 -*-
## Add path to library (just for examples; you do not need this)                                                                           
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import scipy.ndimage as ndi
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg


app = QtGui.QApplication([])
win = QtGui.QMainWindow()
win.resize(800,600)
win.show()

cw = QtGui.QWidget()
win.setCentralWidget(cw)

l = QtGui.QGridLayout()
cw.setLayout(l)

v = pg.GraphicsView()
vb = pg.ViewBox()
v.setCentralItem(vb)
l.addWidget(v, 0, 0)

w = pg.HistogramLUTWidget()
l.addWidget(w, 0, 1)

data = ndi.gaussian_filter(np.random.normal(size=(256, 256)), (20, 20))
img = pg.ImageItem(data)
vb.addItem(img)
vb.autoRange()

w.setImageItem(img)


## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
