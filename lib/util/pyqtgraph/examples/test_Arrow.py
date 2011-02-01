# -*- coding: utf-8 -*-
## Add path to library (just for examples; you do not need this)
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np
from PyQt4 import QtGui, QtCore
from pyqtgraph.PlotWidget import *
from pyqtgraph.graphicsItems import *


app = QtGui.QApplication([])
mw = QtGui.QMainWindow()

p = PlotWidget()
mw.setCentralWidget(p)
c = p.plot(x=np.sin(np.linspace(0, 2*np.pi, 100)), y=np.cos(np.linspace(0, 2*np.pi, 100)))
a = CurveArrow(c)
p.addItem(a)

mw.show()

anim = a.makeAnimation(loop=-1)
anim.start()
