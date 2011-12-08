from pyqtgraph.Qt import QtGui, QtCore
from pyqtgraph.Point import Point
from UIGraphicsItem import UIGraphicsItem
import numpy as np
import weakref


class InfiniteLine(UIGraphicsItem):
    """
    Displays a line of infinite length.
    This line may be dragged to indicate a position in data coordinates.
    """
    
    sigDragged = QtCore.Signal(object)
    sigPositionChangeFinished = QtCore.Signal(object)
    sigPositionChanged = QtCore.Signal(object)
    
    def __init__(self, pos=None, angle=90, pen=None, movable=False, bounds=None):
        """
        Initialization options:
            pos      - Position of the line. This can be a QPointF or a single value for vertical/horizontal lines.
            angle    - Angle of line in degrees. 0 is horizontal, 90 is vertical.
            pen      - Pen to use when drawing line
            movable  - If True, the line can be dragged to a new position by the user
            bounds   - Optional [min, max] bounding values. Bounds are only valid if the line is vertical or horizontal.
        """
        
        UIGraphicsItem.__init__(self)
        
        if bounds is None:              ## allowed value boundaries for orthogonal lines
            self.maxRange = [None, None]
        else:
            self.maxRange = bounds
        self.setMovable(movable)
        self.p = [0, 0]
        self.setAngle(angle)
        if pos is None:
            pos = Point(0,0)
        self.setPos(pos)

        if pen is None:
            pen = QtGui.QPen(QtGui.QColor(200, 200, 100))
        self.setPen(pen)
        self.currentPen = self.pen
        #self.setFlag(self.ItemSendsScenePositionChanges)
      
    def setMovable(self, m):
        self.movable = m
        self.setAcceptHoverEvents(m)
      
    def setBounds(self, bounds):
        self.maxRange = bounds
        self.setValue(self.value())
        
    def hoverEnterEvent(self, ev):
        self.currentPen = QtGui.QPen(QtGui.QColor(255, 0,0))
        self.update()
        ev.ignore()

    def hoverLeaveEvent(self, ev):
        self.currentPen = self.pen
        self.update()
        ev.ignore()
        
    def setPen(self, pen):
        self.pen = pen
        self.currentPen = self.pen
        self.update()
        
    def setAngle(self, angle):
        """Takes angle argument in degrees."""
        self.angle = ((angle+45) % 180) - 45   ##  -45 <= angle < 135
        self.resetTransform()
        self.rotate(self.angle)
        self.update()
        
    def setPos(self, pos):
        if type(pos) in [list, tuple]:
            newPos = pos
        elif isinstance(pos, QtCore.QPointF):
            newPos = [pos.x(), pos.y()]
        else:
            if self.angle == 90:
                newPos = [pos, 0]
            elif self.angle == 0:
                newPos = [0, pos]
            else:
                raise Exception("Must specify 2D coordinate for non-orthogonal lines.")
            
        ## check bounds (only works for orthogonal lines)
        if self.angle == 90:
            if self.maxRange[0] is not None:    
                newPos[0] = max(newPos[0], self.maxRange[0])
            if self.maxRange[1] is not None:
                newPos[0] = min(newPos[0], self.maxRange[1])
        elif self.angle == 0:
            if self.maxRange[0] is not None:
                newPos[1] = max(newPos[1], self.maxRange[0])
            if self.maxRange[1] is not None:
                newPos[1] = min(newPos[1], self.maxRange[1])
            
        if self.p != newPos:
            self.p = newPos
            UIGraphicsItem.setPos(self, Point(self.p))
            self.update()
            self.sigPositionChanged.emit(self)

    def getXPos(self):
        return self.p[0]
        
    def getYPos(self):
        return self.p[1]
        
    def getPos(self):
        return self.p

    def value(self):
        if self.angle%180 == 0:
            return self.getYPos()
        elif self.angle%180 == 90:
            return self.getXPos()
        else:
            return self.getPos()
                
    def setValue(self, v):
        self.setPos(v)

    ## broken in 4.7
    #def itemChange(self, change, val):
        #if change in [self.ItemScenePositionHasChanged, self.ItemSceneHasChanged]:
            #self.updateLine()
            #print "update", change
            #print self.getBoundingParents()
        #else:
            #print "ignore", change
        #return GraphicsObject.itemChange(self, change, val)
                
    def boundingRect(self):
        br = UIGraphicsItem.boundingRect(self)
        #print "line bounds:", self, br
        dt = self.deviceTransform()
        if dt is None:
            return QtCore.QRectF()
        lineDir = Point(dt.map(Point(1, 0)) - dt.map(Point(0,0)))  ## direction of line in pixel-space
        orthoDir = Point(lineDir[1], -lineDir[0])  ## orthogonal to line in pixel-space
        norm = orthoDir.norm()  ## direction of one pixel orthogonal to line
        
        dti = dt.inverted()[0]
        px = Point(dti.map(norm)-dti.map(Point(0,0)))  ## orthogonal pixel mapped back to item coords
        px = px[1]  ## project to y-direction
        
        br.setBottom(-px*2)
        br.setTop(px*2)
        return br.normalized()
    
    def paint(self, p, *args):
        UIGraphicsItem.paint(self, p, *args)
        br = self.boundingRect()
        p.setPen(self.currentPen)
        p.drawLine(Point(br.right(), 0), Point(br.left(), 0))
        #p.drawRect(self.boundingRect())
        
        
    #def mousePressEvent(self, ev):
        #if self.movable and ev.button() == QtCore.Qt.LeftButton:
            #ev.accept()
            #self.pressDelta = self.mapToParent(ev.pos()) - QtCore.QPointF(*self.p)
        #else:
            #ev.ignore()
            
    #def mouseMoveEvent(self, ev):
        #self.setPos(self.mapToParent(ev.pos()) - self.pressDelta)
        ##self.emit(QtCore.SIGNAL('dragged'), self)
        #self.sigDragged.emit(self)
        #self.hasMoved = True

    #def mouseReleaseEvent(self, ev):
        #if self.hasMoved and ev.button() == QtCore.Qt.LeftButton:
            #self.hasMoved = False
            ##self.emit(QtCore.SIGNAL('positionChangeFinished'), self)
            #self.sigPositionChangeFinished.emit(self)

    def mouseDragEvent(self, ev):
        if self.movable and ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            delta = self.mapToParent(ev.pos()) - self.mapToParent(ev.lastPos())
            #pressDelta = self.mapToParent(ev.buttonDownPos()) - Point(self.p)
            self.setPos(self.pos() + delta)
            self.sigDragged.emit(self)
            if ev.isFinish():
                self.sigPositionChangeFinished.emit(self)
        else:
            print ev
