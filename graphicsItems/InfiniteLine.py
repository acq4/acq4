from ..Qt import QtGui, QtCore
from ..Point import Point
from .GraphicsObject import GraphicsObject
from .. import functions as fn
import numpy as np
import weakref


__all__ = ['InfiniteLine']
class InfiniteLine(GraphicsObject):
    """
    **Bases:** :class:`GraphicsObject <pyqtgraph.GraphicsObject>`
    
    Displays a line of infinite length.
    This line may be dragged to indicate a position in data coordinates.
    
    =============================== ===================================================
    **Signals:**
    sigDragged(self)
    sigPositionChangeFinished(self)
    sigPositionChanged(self)
    =============================== ===================================================
    """
    
    sigDragged = QtCore.Signal(object)
    sigPositionChangeFinished = QtCore.Signal(object)
    sigPositionChanged = QtCore.Signal(object)
    
    def __init__(self, pos=None, angle=90, pen=None, movable=False, bounds=None, 
                 hoverPen=None, span=(0, 1), markers=None):
        """
        =============== ==================================================================
        **Arguments:**
        pos             Position of the line. This can be a QPointF or a single value for
                        vertical/horizontal lines.
        angle           Angle of line in degrees. 0 is horizontal, 90 is vertical.
        pen             Pen to use when drawing line. Can be any arguments that are valid
                        for :func:`mkPen <pyqtgraph.mkPen>`. Default pen is transparent
                        yellow.
        hoverPen        Pen to use when the mouse cursor hovers over the line. 
                        Only used when movable=True.
        movable         If True, the line can be dragged to a new position by the user.
        bounds          Optional [min, max] bounding values. Bounds are only valid if the
                        line is vertical or horizontal.
        span            Optional tuple (min, max) giving the range over the view to draw
                        the line. For example, with a vertical line, use span=(0.5, 1)
                        to draw only on the top half of the view.
        markers         List of (marker, position, size) tuples, one per marker to display
                        on the line. See the addMarker method.
        =============== ==================================================================
        """
        
        GraphicsObject.__init__(self)
        
        if bounds is None:              ## allowed value boundaries for orthogonal lines
            self.maxRange = [None, None]
        else:
            self.maxRange = bounds
        self.moving = False
        self.setMovable(movable)
        self.mouseHovering = False
        self.p = [0, 0]
        self.setAngle(angle)
        if pos is None:
            pos = Point(0,0)
        self.setPos(pos)

        if pen is None:
            pen = (200, 200, 100)
        
        self.setPen(pen)
        
        if hoverPen is None:
            hoverPen = QtGui.QPen(self.pen)
            hoverPen.setWidth(self.pen.width() * 3)
        self.setHoverPen(hoverPen)
        
        self.span = span
        self.currentPen = self.pen
        self.markers = []
        self._maxMarkerSize = 0
        if markers is not None:
            for m in markers:
                self.addMarker(*m)
                
        # Cache variables for managing bounds
        self._endPoints = [0, 1] # 
        self._bounds = None
        self._lastViewSize = None
        
    def setMovable(self, m):
        """Set whether the line is movable by the user."""
        self.movable = m
        self.setAcceptHoverEvents(m)
      
    def setBounds(self, bounds):
        """Set the (minimum, maximum) allowable values when dragging."""
        self.maxRange = bounds
        self.setValue(self.value())
        
    def bounds(self):
        """Return the (minimum, maximum) values allowed when dragging.
        """
        return self.maxRange[:]
        
    def setPen(self, *args, **kwargs):
        """Set the pen for drawing the line. Allowable arguments are any that are valid 
        for :func:`mkPen <pyqtgraph.mkPen>`."""
        self.pen = fn.mkPen(*args, **kwargs)
        if not self.mouseHovering:
            self.currentPen = self.pen
            self.update()
        
    def setHoverPen(self, *args, **kwargs):
        """Set the pen for drawing the line while the mouse hovers over it. 
        Allowable arguments are any that are valid 
        for :func:`mkPen <pyqtgraph.mkPen>`.
        
        If the line is not movable, then hovering is also disabled.
        
        Added in version 0.9.9."""
        # If user did not supply a width, then copy it from pen
        widthSpecified = (len(args) == 1 and isinstance(args[0], QtGui.QPen) or
                          (isinstance(args[0], dict) and 'width' in args[0]) or
                          'width' in kwargs)
        self.hoverPen = fn.mkPen(*args, **kwargs)
        if not widthSpecified:
            self.hoverPen.setWidth(self.pen.width())
            
        if self.mouseHovering:
            self.currentPen = self.hoverPen
            self.update()
        
    def addMarker(self, marker, position=0.5, size=10.0):
        """Add a marker to be displayed on the line. 
        
        ============= =========================================================
        **Arguments**
        marker        String indicating the style of marker to add:
                      '<|', '|>', '>|', '|<', '<|>', '>|<', '^', 'v', 'o'
        position      Position (0.0-1.0) along the visible extent of the line
                      to place the marker. Default is 0.5.
        size          Size of the marker in pixels. Default is 10.0.
        ============= =========================================================
        """
        path = QtGui.QPainterPath()
        if marker == 'o': 
            path.addEllipse(QtCore.QRectF(-0.5, -0.5, 1, 1))
        if '<|' in marker:
            p = QtGui.QPolygonF([Point(0.5, 0), Point(0, -0.5), Point(-0.5, 0)])
            path.addPolygon(p)
            path.closeSubpath()
        if '|>' in marker:
            p = QtGui.QPolygonF([Point(0.5, 0), Point(0, 0.5), Point(-0.5, 0)])
            path.addPolygon(p)
            path.closeSubpath()
        if '>|' in marker:
            p = QtGui.QPolygonF([Point(0.5, -0.5), Point(0, 0), Point(-0.5, -0.5)])
            path.addPolygon(p)
            path.closeSubpath()
        if '|<' in marker:
            p = QtGui.QPolygonF([Point(0.5, 0.5), Point(0, 0), Point(-0.5, 0.5)])
            path.addPolygon(p)
            path.closeSubpath()
        if '^' in marker:
            p = QtGui.QPolygonF([Point(0, -0.5), Point(0.5, 0), Point(0, 0.5)])
            path.addPolygon(p)
            path.closeSubpath()
        if 'v' in marker:
            p = QtGui.QPolygonF([Point(0, -0.5), Point(-0.5, 0), Point(0, 0.5)])
            path.addPolygon(p)
            path.closeSubpath()
        
        self.markers.append((path, position, size))
        self._maxMarkerSize = max([m[2] / 2. for m in self.markers])
        self.update()

    def clearMarkers(self):
        """ Remove all markers from this line.
        """
        self.markers = []
        self._maxMarkerSize = 0
        self.update()
        
    def setAngle(self, angle):
        """
        Takes angle argument in degrees.
        0 is horizontal; 90 is vertical.
        
        Note that the use of value() and setValue() changes if the line is 
        not vertical or horizontal.
        """
        self.angle = angle #((angle+45) % 180) - 45   ##  -45 <= angle < 135
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
            GraphicsObject.setPos(self, Point(self.p))
            self.update()
            self.sigPositionChanged.emit(self)

    def getXPos(self):
        return self.p[0]
        
    def getYPos(self):
        return self.p[1]
        
    def getPos(self):
        return self.p

    def value(self):
        """Return the value of the line. Will be a single number for horizontal and 
        vertical lines, and a list of [x,y] values for diagonal lines."""
        if self.angle%180 == 0:
            return self.getYPos()
        elif self.angle%180 == 90:
            return self.getXPos()
        else:
            return self.getPos()
                
    def setValue(self, v):
        """Set the position of the line. If line is horizontal or vertical, v can be 
        a single value. Otherwise, a 2D coordinate must be specified (list, tuple and 
        QPointF are all acceptable)."""
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
    
    def setSpan(self, mn, mx):
        if self.span != (mn, mx):
            self.span = (mn, mx)
            self.update()
                
    def boundingRect(self):
        #br = UIGraphicsItem.boundingRect(self)
        vr = self.viewRect()  # bounds of containing ViewBox mapped to local coords.
        
        ## add a 4-pixel radius around the line for mouse interaction.
        
        px = self.pixelLength(direction=Point(1,0), ortho=True)  ## get pixel length orthogonal to the line
        if px is None:
            px = 0
        pw = max(self.pen.width() / 2, self.hoverPen.width() / 2)
        w = max(4, self._maxMarkerSize + pw) + 1
        w = w * px
        br = QtCore.QRectF(vr)
        br.setBottom(-w)
        br.setTop(w)

        length = br.width()
        left = br.left() + length * self.span[0]
        right = br.left() + length * self.span[1]
        br.setLeft(left - w)
        br.setRight(right + w)
        br = br.normalized()
        
        vs = self.getViewBox().size()
        
        if self._bounds != br or self._lastViewSize != vs:
            self._bounds = br
            self._lastViewSize = vs
            self.prepareGeometryChange()
        
        self._endPoints = (left, right)
        self._lastViewRect = vr
        
        return self._bounds

    def paint(self, p, *args):
        p.setRenderHint(p.Antialiasing)
        
        left, right = self._endPoints
        pen = self.currentPen
        pen.setJoinStyle(QtCore.Qt.MiterJoin)
        p.setPen(pen)
        p.drawLine(Point(left, 0), Point(right, 0))
        
        
        if len(self.markers) == 0:
            return
        
        # paint markers in native coordinate system
        tr = p.transform()
        p.resetTransform()
        
        start = tr.map(Point(left, 0))
        end = tr.map(Point(right, 0))
        up = tr.map(Point(left, 1))
        dif = end - start
        length = Point(dif).length()
        angle = np.arctan2(dif.y(), dif.x()) * 180 / np.pi
        
        p.translate(start)
        p.rotate(angle)
        
        up = up - start
        det = up.x() * dif.y() - dif.x() * up.y()
        p.scale(1, 1 if det > 0 else -1)
        
        p.setBrush(fn.mkBrush(self.currentPen.color()))
        #p.setPen(fn.mkPen(None))
        tr = p.transform()
        for path, pos, size in self.markers:
            p.setTransform(tr)
            x = length * pos
            p.translate(x, 0)
            p.scale(size, size)
            p.drawPath(path)
        
    def dataBounds(self, axis, frac=1.0, orthoRange=None):
        if axis == 0:
            return None   ## x axis should never be auto-scaled
        else:
            return (0,0)

    def mouseDragEvent(self, ev):
        if self.movable and ev.button() == QtCore.Qt.LeftButton:
            if ev.isStart():
                self.moving = True
                self.cursorOffset = self.pos() - self.mapToParent(ev.buttonDownPos())
                self.startPosition = self.pos()
            ev.accept()
            
            if not self.moving:
                return
                
            self.setPos(self.cursorOffset + self.mapToParent(ev.pos()))
            self.sigDragged.emit(self)
            if ev.isFinish():
                self.moving = False
                self.sigPositionChangeFinished.emit(self)
            
    def mouseClickEvent(self, ev):
        if self.moving and ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.setPos(self.startPosition)
            self.moving = False
            self.sigDragged.emit(self)
            self.sigPositionChangeFinished.emit(self)

    def hoverEvent(self, ev):
        if (not ev.isExit()) and self.movable and ev.acceptDrags(QtCore.Qt.LeftButton):
            self.setMouseHover(True)
        else:
            self.setMouseHover(False)

    def setMouseHover(self, hover):
        ## Inform the item that the mouse is (not) hovering over it
        if self.mouseHovering == hover:
            return
        self.mouseHovering = hover
        if hover:
            self.currentPen = self.hoverPen
        else:
            self.currentPen = self.pen
        self.update()
