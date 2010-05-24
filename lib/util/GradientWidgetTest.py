# -*- coding: utf-8 -*-

from GradientWidget import *
from PyQt4 import QtGui

app = QtGui.QApplication([])
w = QtGui.QMainWindow()
w.show()
cw = GradientWidget()
w.setCentralWidget(cw)
