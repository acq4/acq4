#!/usr/bin/python
# -*- coding: utf-8 -*-

from scipy import random
from PyQt4 import QtGui, QtCore
from PlotWidget import *
from graphicsItems import *


app = QtGui.QApplication([])
mw = QtGui.QMainWindow()
pw = PlotWidget()
mw.setCentralWidget(pw)

p1 = PlotCurveItem()
pw.addItem(p1)
rect = QtGui.QGraphicsRectItem(QtCore.QRectF(0, 0, 1, 1))
rect.setPen(QtGui.QPen(QtGui.QColor(100, 200, 100)))
pw.addItem(rect)

pen = QtGui.QPen(QtGui.QBrush(QtGui.QColor(255, 255, 255, 10)), 5)
pen.setCosmetic(True)
#pen.setJoinStyle(QtCore.Qt.MiterJoin)
p1.setShadowPen(pen)
p1.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 50)))

mw.show()


def rand(n):
    data = random.random(n)
    data[int(n*0.1):int(n*0.13)] += .5
    data[int(n*0.18)] += 2
    data[int(n*0.1):int(n*0.13)] *= 5
    data[int(n*0.18)] *= 20
    return data, arange(n, n+len(data)) / float(n)
    

def updateData():
    yd, xd = rand(10000)
    p1.updateData(yd, x=xd)

yd, xd = rand(10000)
updateData()
pw.autoRange()

t = QtCore.QTimer()
QtCore.QObject.connect(t, QtCore.SIGNAL('timeout()'), updateData)
#t.start(50)

