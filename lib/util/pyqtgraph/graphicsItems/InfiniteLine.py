from pyqtgraph.Qt import QtGui, QtCore
from GraphicsObject import GraphicsObject
import numpy as np
import weakref


class InfiniteLine(GraphicsObject):
    """
    Displays a line of infinite length.
    This line may be dragged to indicate a position in data coordinates.
    """
    
    sigDragged = QtCore.Signal(object)
    sigPositionChangeFinished = QtCore.Signal(object)
    sigPositionChanged = QtCore.Signal(object)
    
    def __init__(self, view, pos=0, angle=90, pen=None, movable=False, bounds=None):
        GraphicsObject.__init__(self)
        self.bounds = QtCore.QRectF()   ## graphicsitem boundary
        
        if bounds is None:              ## allowed value boundaries for orthogonal lines
            self.maxRange = [None, None]
        else:
            self.maxRange = bounds
        self.setMovable(movable)
        self.view = weakref.ref(view)
        self.p = [0, 0]
        self.setAngle(angle)
        self.setPos(pos)

        self.hasMoved = False

        if pen is None:
            pen = QtGui.QPen(QtGui.QColor(200, 200, 100))
        self.setPen(pen)
        self.currentPen = self.pen
        #self.setFlag(self.ItemSendsScenePositionChanges)
        #for p in self.getBoundingParents():
            #QtCore.QObject.connect(p, QtCore.SIGNAL('viewChanged'), self.updateLine)
        #QtCore.QObject.connect(self.view(), QtCore.SIGNAL('viewChanged'), self.updateLine)
        self.view().sigRangeChanged.connect(self.updateLine)
      
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
        
    def setAngle(self, angle):
        """Takes angle argument in degrees."""
        self.angle = ((angle+45) % 180) - 45   ##  -45 <= angle < 135
        self.updateLine()
        
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
            self.updateLine()
            #self.emit(QtCore.SIGNAL('positionChanged'), self)
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
                
    def updateLine(self):

        #unit = QtCore.QRect(0, 0, 10, 10)
        #if self.scene() is not None:
            #gv = self.scene().views()[0]
            #unit = gv.mapToScene(unit).boundingRect()
            ##print unit
            #unit = self.mapRectFromScene(unit)
            ##print unit
        
        vr = self.view().viewRect()
        #vr = self.viewBounds()
        if vr is None:
            return
        #print 'before', self.bounds
        
        if self.angle > 45:
            m = np.tan((90-self.angle) * np.pi / 180.)
            y2 = vr.bottom()
            y1 = vr.top()
            x1 = self.p[0] + (y1 - self.p[1]) * m
            x2 = self.p[0] + (y2 - self.p[1]) * m
        else:
            m = np.tan(self.angle * np.pi / 180.)
            x1 = vr.left()
            x2 = vr.right()
            y2 = self.p[1] + (x1 - self.p[0]) * m
            y1 = self.p[1] + (x2 - self.p[0]) * m
        #print vr, x1, y1, x2, y2
        self.prepareGeometryChange()
        self.line = (QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))
        self.bounds = QtCore.QRectF(self.line[0], self.line[1])
        ## Stupid bug causes lines to disappear:
        if self.angle % 180 == 90:
            px = self.pixelWidth()
            #self.bounds.setWidth(1e-9)
            self.bounds.setX(x1 + px*-5)
            self.bounds.setWidth(px*10)
        if self.angle % 180 == 0:
            px = self.pixelHeight()
            #self.bounds.setHeight(1e-9)
            self.bounds.setY(y1 + px*-5)
            self.bounds.setHeight(px*10)

        #QtGui.QGraphicsLineItem.setLine(self, x1, y1, x2, y2)
        #self.update()
        
    def boundingRect(self):
        #self.updateLine()
        #return QtGui.QGraphicsLineItem.boundingRect(self)
        #print "bounds", self.bounds
        return self.bounds
    
    def paint(self, p, *args):
        w,h  = self.pixelWidth()*5, self.pixelHeight()*5*1.1547
        #self.updateLine()
        l = self.line
        
        p.setPen(self.currentPen)
        #print "paint", self.line
        p.drawLine(l[0], l[1])
        
        p.setBrush(QtGui.QBrush(self.currentPen.color()))
        p.drawConvexPolygon(QtGui.QPolygonF([
            l[0] + QtCore.QPointF(-w, 0),
            l[0] + QtCore.QPointF(0, h),
            l[0] + QtCore.QPointF(w, 0),
        ]))
        
        #p.setPen(QtGui.QPen(QtGui.QColor(255,0,0)))
        #p.drawRect(self.boundingRect())
        
    def mousePressEvent(self, ev):
        if self.movable and ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            self.pressDelta = self.mapToParent(ev.pos()) - QtCore.QPointF(*self.p)
        else:
            ev.ignore()
            
    def mouseMoveEvent(self, ev):
        self.setPos(self.mapToParent(ev.pos()) - self.pressDelta)
        #self.emit(QtCore.SIGNAL('dragged'), self)
        self.sigDragged.emit(self)
        self.hasMoved = True

    def mouseReleaseEvent(self, ev):
        if self.hasMoved and ev.button() == QtCore.Qt.LeftButton:
            self.hasMoved = False
            #self.emit(QtCore.SIGNAL('positionChangeFinished'), self)
            self.sigPositionChangeFinished.emit(self)
