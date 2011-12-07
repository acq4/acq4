from pyqtgraph.Qt import QtGui, QtCore
from UIGraphicsItem import UIGraphicsItem
from InfiniteLine import InfiniteLine
import pyqtgraph.functions as fn


class LinearRegionItem(UIGraphicsItem):
    """
    Used for marking a horizontal or vertical region in plots.
    The region can be dragged and is bounded by lines which can be dragged individually.
    """
    
    sigRegionChangeFinished = QtCore.Signal(object)
    sigRegionChanged = QtCore.Signal(object)
    
    def __init__(self, vals=[0,1], orientation="vertical", brush=None, movable=True, bounds=None):
        UIGraphicsItem.__init__(self)
        self.orientation = orientation
        #if hasattr(self, "ItemHasNoContents"):  
            #self.setFlag(self.ItemHasNoContents)
        #self.rect = QtGui.QGraphicsRectItem(self)
        #self.rect.setParentItem(self)
        self.bounds = QtCore.QRectF()
        #self.view = weakref.ref(view)
        self.blockLineSignal = False
        
        if orientation[0] == 'h':
            self.lines = [
                InfiniteLine(QtCore.QPointF(0, vals[0]), 0, movable=movable, bounds=bounds), 
                InfiniteLine(QtCore.QPointF(0, vals[1]), 0, movable=movable, bounds=bounds)]
        else:
            self.lines = [
                InfiniteLine(QtCore.QPointF(vals[0], 0), 90, movable=movable, bounds=bounds), 
                InfiniteLine(QtCore.QPointF(vals[1], 0), 90, movable=movable, bounds=bounds)]
        
        for l in self.lines:
            l.setParentItem(self)
            #l.connect(l, QtCore.SIGNAL('positionChangeFinished'), self.lineMoveFinished)
            l.sigPositionChangeFinished.connect(self.lineMoveFinished)
            #l.connect(l, QtCore.SIGNAL('positionChanged'), self.lineMoved)
            l.sigPositionChanged.connect(self.lineMoved)
            
        if brush is None:
            brush = QtGui.QBrush(QtGui.QColor(0, 0, 255, 50))
        self.setBrush(brush)
        self.setMovable(movable)

    def getRegion(self):
        """Return the values at the edges of the region."""
        #if self.orientation[0] == 'h':
            #r = (self.bounds.top(), self.bounds.bottom())
        #else:
            #r = (self.bounds.left(), self.bounds.right())
        r = [self.lines[0].value(), self.lines[1].value()]
        return (min(r), max(r))

    def setRegion(self, rgn):
        if self.lines[0].value() == rgn[0] and self.lines[1].value() == rgn[1]:
            return
        self.blockLineSignal = True
        self.lines[0].setValue(rgn[0])
        self.blockLineSignal = False
        self.lines[1].setValue(rgn[1])
        #self.blockLineSignal = False
        self.lineMoved()
        self.lineMoveFinished()

    def setBrush(self, br):
        self.brush = fn.mkBrush(br)

    def setBounds(self, bounds):
        for l in self.lines:
            l.setBounds(bounds)
        
    def setMovable(self, m):
        for l in self.lines:
            l.setMovable(m)
        self.movable = m

    def boundingRect(self):
        br = UIGraphicsItem.boundingRect(self)
        rng = self.getRegion()
        if self.orientation == 'vertical':
           br.setLeft(rng[0])
           br.setRight(rng[1])
        else:
           br.setTop(rng[0])
           br.setBottom(rng[1])
        return br.normalized()
        
    def paint(self, p, *args):
        UIGraphicsItem.paint(self, p, *args)
        p.setBrush(self.brush)
        p.drawRect(self.boundingRect())
            
    def lineMoved(self):
        if self.blockLineSignal:
            return
        self.prepareGeometryChange()
        #self.emit(QtCore.SIGNAL('regionChanged'), self)
        self.sigRegionChanged.emit(self)
            
    def lineMoveFinished(self):
        #self.emit(QtCore.SIGNAL('regionChangeFinished'), self)
        self.sigRegionChangeFinished.emit(self)
        
            
    #def updateBounds(self):
        #vb = self.view().viewRect()
        #vals = [self.lines[0].value(), self.lines[1].value()]
        #if self.orientation[0] == 'h':
            #vb.setTop(min(vals))
            #vb.setBottom(max(vals))
        #else:
            #vb.setLeft(min(vals))
            #vb.setRight(max(vals))
        #if vb != self.bounds:
            #self.bounds = vb
            #self.rect.setRect(vb)
        
    #def mousePressEvent(self, ev):
        #if not self.movable:
            #ev.ignore()
            #return
        #for l in self.lines:
            #l.mousePressEvent(ev)  ## pass event to both lines so they move together
        ##if self.movable and ev.button() == QtCore.Qt.LeftButton:
            ##ev.accept()
            ##self.pressDelta = self.mapToParent(ev.pos()) - QtCore.QPointF(*self.p)
        ##else:
            ##ev.ignore()
            
    #def mouseReleaseEvent(self, ev):
        #for l in self.lines:
            #l.mouseReleaseEvent(ev)
            
    #def mouseMoveEvent(self, ev):
        ##print "move", ev.pos()
        #if not self.movable:
            #return
        #self.lines[0].blockSignals(True)  # only want to update once
        #for l in self.lines:
            #l.mouseMoveEvent(ev)
        #self.lines[0].blockSignals(False)
        ##self.setPos(self.mapToParent(ev.pos()) - self.pressDelta)
        ##self.emit(QtCore.SIGNAL('dragged'), self)

    def mouseDragEvent(self, ev):
        if not self.movable or int(ev.button() & QtCore.Qt.LeftButton) == 0:
            return
        ev.accept()
        
        delta = ev.pos() - ev.lastPos()
        self.lines[0].blockSignals(True)  # only want to update once
        for l in self.lines:
            l.setPos(l.pos()+delta)
            #l.mouseDragEvent(ev)
        self.lines[0].blockSignals(False)
        self.prepareGeometryChange()
        
        if ev.isFinish():
            self.sigRegionChangeFinished.emit(self)
        else:
            self.sigRegionChanged.emit(self)
            
        