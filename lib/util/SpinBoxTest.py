# -*- coding: utf-8 -*-
from SpinBox import *
from PyQt4 import QtGui, QtCore
from SignalProxy import *


app = QtGui.QApplication([])
win = QtGui.QMainWindow()
g = QtGui.QFormLayout()
w = QtGui.QWidget()
w.setLayout(g)
win.setCentralWidget(w)
s1 = SpinBox(value=5, step=0.1, bounds=[-1.5, None], suffix='units')
t1 = QtGui.QLineEdit()
g.addRow(s1, t1)
s2 = SpinBox(dec=True, step=0.1, minStep=1e-6, suffix='A', siPrefix=True)
t2 = QtGui.QLineEdit()
g.addRow(s2, t2)
s3 = SpinBox(dec=True, step=0.1, minStep=1e-6, bounds=[0, 10])
t3 = QtGui.QLineEdit()
g.addRow(s3, t3)
s4 = SpinBox(value=-10, log=True, step=0.1, minStep=0.1, bounds=[-100, 0], siPrefix=True)
t4 = QtGui.QLineEdit()
g.addRow(s4, t4)





win.show()


sp = proxyConnect(s1, QtCore.SIGNAL('valueChanged(double)'), lambda v: t1.setText(str(v)))
sp2 = proxyConnect(s3, QtCore.SIGNAL('valueChanged(double)'), lambda v: t3.setText(str(v)))
QtCore.QObject.connect(s2, QtCore.SIGNAL('valueChanged(double)'), lambda v: t2.setText(str(v)))
QtCore.QObject.connect(s4, QtCore.SIGNAL('valueChanged(double)'), lambda v: t4.setText(str(v)))


