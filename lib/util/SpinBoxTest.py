# -*- coding: utf-8 -*-
from SpinBox import *
from PyQt4 import QtGui, QtCore
from SignalProxy import *


app = QtGui.QApplication([])
win = QtGui.QMainWindow()
g = QtGui.QVBoxLayout()
w = QtGui.QWidget()
w.setLayout(g)
s1 = SpinBox(win)
g.addWidget(s1)
s2 = QtGui.QSpinBox(win)
g.addWidget(s2)
win.setCentralWidget(w)
win.show()


def p(*args):
    print args
    
sp = proxyConnect(s1, QtCore.SIGNAL('valueChanged(int)'), p)