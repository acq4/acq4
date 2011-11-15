# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtGui, QtCore

class FlowchartGraphicsView(QtGui.QGraphicsView):
    
    sigHoverOver = QtCore.Signal(object)
    sigClicked = QtCore.Signal(object)
    
    def __init__(self, *args):
        QtGui.QGraphicsView.__init__(self, *args)
        self.setMouseTracking(True)
        self.lastPos = None
        self.setTransformationAnchor(self.AnchorViewCenter)
        self.setRenderHints(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtGui.QGraphicsView.RubberBandDrag)
        self.setRubberBandSelectionMode(QtCore.Qt.ContainsItemBoundingRect)
        
    def mousePressEvent(self, ev):
        self.moved = False
        self.lastPos = ev.pos()
        return QtGui.QGraphicsView.mousePressEvent(self, ev)

    def mouseMoveEvent(self, ev):
        self.moved = True
        callSuper = False
        if ev.buttons() &  QtCore.Qt.RightButton:
            if self.lastPos is not None:
                dif = ev.pos() - self.lastPos
                self.scale(1.01**-dif.y(), 1.01**-dif.y())
        elif ev.buttons() & QtCore.Qt.MidButton:
            if self.lastPos is not None:
                dif = ev.pos() - self.lastPos
                self.translate(dif.x(), -dif.y())
        else:
            #self.emit(QtCore.SIGNAL('hoverOver'), self.items(ev.pos()))
            self.sigHoverOver.emit(self.items(ev.pos()))
            callSuper = True
        self.lastPos = ev.pos()
        
        if callSuper:
            QtGui.QGraphicsView.mouseMoveEvent(self, ev)
            
    def mouseReleaseEvent(self, ev):
        if not self.moved:
            #self.emit(QtCore.SIGNAL('clicked'), ev)
            self.sigClicked.emit(ev)
        return QtGui.QGraphicsView.mouseReleaseEvent(self, ev)


class FlowchartGraphicsScene(QtGui.QGraphicsScene):
    
    sigContextMenuEvent = QtCore.Signal(object)
    
    def __init__(self, *args):
        QtGui.QGraphicsScene.__init__(self, *args)
        
    def contextMenuEvent(self, ev):
        QtGui.QGraphicsScene.contextMenuEvent(self, ev)
        if not ev.isAccepted():
            self.sigContextMenuEvent.emit(ev)