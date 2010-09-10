# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore

class FlowchartGraphicsView(QtGui.QGraphicsView):
    def __init__(self, *args):
        QtGui.QGraphicsView.__init__(self, *args)
        self.setMouseTracking(True)
        self.lastPos = None
        self.setTransformationAnchor(self.AnchorUnderMouse)
        
    def mousePressEvent(self, ev):
        self.lastPos = ev.pos()
        return QtGui.QGraphicsView.mousePressEvent(self, ev)

    def mouseMoveEvent(self, ev):
        if ev.buttons() &  QtCore.Qt.RightButton:
            if self.lastPos is not None:
                dif = ev.pos() - self.lastPos
                self.scale(1.01**-dif.y(), 1.01**-dif.y())
        elif ev.buttons() & QtCore.Qt.MidButton:
            if self.lastPos is not None:
                dif = ev.pos() - self.lastPos
                self.translate(dif.x(), -dif.y())
        else:
            self.emit(QtCore.SIGNAL('hoverOver'), self.items(ev.pos()))
        self.lastPos = ev.pos()
        return QtGui.QGraphicsView.mouseMoveEvent(self, ev)
