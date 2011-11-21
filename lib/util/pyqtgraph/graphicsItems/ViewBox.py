from pyqtgraph.Qt import QtGui, QtCore
import numpy as np
from pyqtgraph.Point import Point
import pyqtgraph.functions as fn
from ItemGroup import ItemGroup

class ViewBox(QtGui.QGraphicsWidget):
    """
    Box that allows internal scaling/panning of children by mouse drag. 
    Not really compatible with GraphicsView having the same functionality.
    """
    
    sigYRangeChanged = QtCore.Signal(object, object)
    sigXRangeChanged = QtCore.Signal(object, object)
    sigRangeChangedManually = QtCore.Signal(object)
    sigRangeChanged = QtCore.Signal(object, object)
    
    def __init__(self, parent=None, border=None, lockAspect=False, enableMouse=True, invertY=False):
        QtGui.QGraphicsWidget.__init__(self, parent)
        #self.gView = view
        #self.showGrid = showGrid
        ## separating targetRange and viewRange allows the view to be resized
        ## while keeping all previously viewed contents visible
        self.targetRange = [[0,1], [0,1]]   ## child coord. range visible [[xmin, xmax], [ymin, ymax]]
        self.viewRange = [[0,1], [0,1]]     ## actual range viewed
        
        self.wheelScaleFactor = -1.0 / 8.0
        self.aspectLocked = False
        self.setFlag(self.ItemClipsChildrenToShape)
        self.setFlag(self.ItemIsFocusable, True)  ## so we can receive key presses
        #self.setFlag(QtGui.QGraphicsItem.ItemClipsToShape)
        #self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        
        #self.childGroup = QtGui.QGraphicsItemGroup(self)
        self.childGroup = ItemGroup(self)
        self.currentScale = Point(1, 1)
        self.useLeftButtonPan = True # normally use left button to pan
        # this also enables capture of keyPressEvents.
        
        ## Make scale box that is shown when dragging on the view
        self.rbScaleBox = QtGui.QGraphicsRectItem(0, 0, 1, 1)
        self.rbScaleBox.setPen(fn.mkPen((255,0,0), width=1))
        self.rbScaleBox.setBrush(fn.mkBrush(255,255,0,100))
        self.addItem(self.rbScaleBox)
        self.rbScaleBox.hide()
        
        self.axHistory = [] # maintain a history of zoom locations
        self.axHistoryPointer = -1 # pointer into the history. Allows forward/backward movement, not just "undo"
        
        self.yInverted = invertY
        self.setZValue(-100)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding))
        
        self.border = border
        
        self.mouseEnabled = [enableMouse, enableMouse]
        self.setAspectLocked(lockAspect)

    def keyPressEvent(self, ev):
        """
        This routine should capture key presses in the current view box.
        Key presses are used only when self.useLeftButtonPan is false
        The following events are implemented:
        ctrl-A : zooms out to the default "full" view of the plot
        ctrl-+ : moves forward in the zooming stack (if it exists)
        ctrl-- : moves backward in the zooming stack (if it exists)
         
        """
        #print ev.key()
        #print 'I intercepted a key press, but did not accept it'
        
        ## not implemented yet ?
        #self.keypress.sigkeyPressEvent.emit()
        
        ev.accept()
        if ev.text() == '-':
            self.scaleHistory(-1)
        elif ev.text() in ['+', '=']:
            self.scaleHistory(1)
        elif ev.key() == QtCore.Qt.Key_Backspace:
            self.scaleHistory(len(self.axHistory))
        else:
            ev.ignore()

    def scaleHistory(self, d):
        ptr = max(0, min(len(self.axHistory)-1, self.axHistoryPointer+d))
        if ptr != self.axHistoryPointer:
            self.axHistoryPointer = ptr
            self.showAxRect(self.axHistory[ptr])

    def setLeftButtonAction(self, mode='Rect'):
        if mode.lower() == 'rect':
            self.useLeftButtonPan = False
        elif mode.lower() == 'pan':
            self.useleftButtonPan = True
        else:
            raise Exception('graphicsItems:ViewBox:setLeftButtonAction: unknown mode = %s' % mode)
            
    def innerSceneItem(self):
        return self.childGroup
    
    def setMouseEnabled(self, x, y):
        self.mouseEnabled = [x, y]
    
    def addItem(self, item):
        if item.zValue() < self.zValue():
            item.setZValue(self.zValue()+1)
        item.setParentItem(self.childGroup)
        #print "addItem:", item, item.boundingRect()
        
    def removeItem(self, item):
        self.scene().removeItem(item)
        
    def resizeEvent(self, ev):
        #self.setRange(self.range, padding=0)
        self.updateMatrix()
        

    def viewRect(self):
        """Return a QRectF bounding the region visible within the ViewBox"""
        try:
            vr0 = self.viewRange[0]
            vr1 = self.viewRange[1]
            return QtCore.QRectF(vr0[0], vr1[0], vr0[1]-vr0[0], vr1[1] - vr1[0])
        except:
            print "make qrectf failed:", self.viewRange
            raise
    
    #def viewportTransform(self):
        ##return self.itemTransform(self.childGroup)[0]
        #return self.childGroup.itemTransform(self)[0]
    
    def targetRect(self):  
        """Return the region which has been requested to be visible. 
        (this is not necessarily the same as the region that is *actually* visible)"""
        try:
            tr0 = self.targetRange[0]
            tr1 = self.targetRange[1]
            return QtCore.QRectF(tr0[0], tr1[0], tr0[1]-tr0[0], tr1[1] - tr1[0])
        except:
            print "make qrectf failed:", self.targetRange
            raise
    
    def invertY(self, b=True):
        self.yInverted = b
        self.updateMatrix()
        
    def setAspectLocked(self, lock=True, ratio=1):
        """If the aspect ratio is locked, view scaling is always forced to be isotropic.
        By default, the ratio is set to 1; x and y both have the same scaling.
        This ratio can be overridden (width/height), or use None to lock in the current ratio.
        """
        if not lock:
            self.aspectLocked = False
        else:
            vr = self.viewRect()
            currentRatio = vr.width() / vr.height()
            if ratio is None:
                ratio = currentRatio
            self.aspectLocked = ratio
            if ratio != currentRatio:  ## If this would change the current range, do that now
                #self.setRange(0, self.viewRange[0][0], self.viewRange[0][1])
                self.updateMatrix()
        
    def childTransform(self):
        m = self.childGroup.transform()
        m1 = QtGui.QTransform()
        m1.translate(self.childGroup.pos().x(), self.childGroup.pos().y())
        return m*m1

    def viewScale(self):
        vr = self.viewRect()
        #print "viewScale:", self.range
        xd = vr.width()
        yd = vr.height()
        if xd == 0 or yd == 0:
            print "Warning: 0 range in view:", xd, yd
            return np.array([1,1])
        
        #cs = self.canvas().size()
        cs = self.boundingRect()
        scale = np.array([cs.width() / xd, cs.height() / yd])
        #print "view scale:", scale
        return scale

    def scaleBy(self, s, center=None):
        """Scale by s around given center point (or center of view)"""
        #print "scaleBy", s, center
        #if self.aspectLocked:
            #s[0] = s[1]
        scale = Point(s)
        if self.aspectLocked is not False:
            scale[0] = self.aspectLocked * scale[1]

        #xr, yr = self.range
        vr = self.viewRect()
        if center is None:
            center = Point(vr.center())
            #xc = (xr[1] + xr[0]) * 0.5
            #yc = (yr[1] + yr[0]) * 0.5
        else:
            center = Point(center)
            #(xc, yc) = center
        
        #x1 = xc + (xr[0]-xc) * s[0]
        #x2 = xc + (xr[1]-xc) * s[0]
        #y1 = yc + (yr[0]-yc) * s[1]
        #y2 = yc + (yr[1]-yc) * s[1]
        tl = center + (vr.topLeft()-center) * scale
        br = center + (vr.bottomRight()-center) * scale
       
        #print xr, xc, s, (xr[0]-xc) * s[0], (xr[1]-xc) * s[0]
        #print [[x1, x2], [y1, y2]]
        
        #if not self.aspectLocked:
            #self.setXRange(x1, x2, update=False, padding=0)
        #self.setYRange(y1, y2, padding=0)
        #print self.range
        
        self.setRange(QtCore.QRectF(tl, br), padding=0)
        
    def translateBy(self, t, viewCoords=False):
        t = t.astype(np.float)
        #print "translate:", t, self.viewScale()
        if viewCoords:  ## scale from pixels
            t /= self.viewScale()
        #xr, yr = self.range
        
        vr = self.viewRect()
        #print xr, yr, t
        #self.setXRange(xr[0] + t[0], xr[1] + t[0], update=False, padding=0)
        #self.setYRange(yr[0] + t[1], yr[1] + t[1], padding=0)
        self.setRange(vr.translated(Point(t)), padding=0)
        
    def wheelEvent(self, ev, axis=None):
        mask = np.array(self.mouseEnabled, dtype=np.float)
        if axis is not None and axis >= 0 and axis < len(mask):
            mv = mask[axis]
            mask[:] = 0
            mask[axis] = mv
        s = ((mask * 0.02) + 1) ** (ev.delta() * self.wheelScaleFactor) # actual scaling factor
        # scale 'around' mouse cursor position
        center = Point(self.childGroup.transform().inverted()[0].map(ev.pos()))
        self.scaleBy(s, center)
        #self.emit(QtCore.SIGNAL('rangeChangedManually'), self.mouseEnabled)
        self.sigRangeChangedManually.emit(self.mouseEnabled)
        ev.accept()

    def mouseMoveEvent(self, ev):
        QtGui.QGraphicsWidget.mouseMoveEvent(self, ev)
        pos = np.array([ev.pos().x(), ev.pos().y()])
        dif = pos - self.mousePos
        dif *= -1
        self.mousePos = pos
        


        ## Ignore axes if mouse is disabled
        mask = np.array(self.mouseEnabled, dtype=np.float)

        ## Scale or translate based on mouse button
        if ev.buttons() & (QtCore.Qt.LeftButton | QtCore.Qt.MidButton):
            if self.useLeftButtonPan == False:
                ## update scale box
                self.updateScaleBox()
                #ax = self.mouseRect()
                #self.rbScaleBox.setRect(ax)
                #self.sigRangeChangedManually.emit(self.mouseEnabled)
                ## don't emit until scale has changed
                ev.accept()
            else:
                if not self.yInverted:
                    mask *= np.array([1, -1])
                tr = dif*mask
                self.translateBy(tr, viewCoords=True)
                #self.emit(QtCore.SIGNAL('rangeChangedManually'), self.mouseEnabled)
                self.sigRangeChangedManually.emit(self.mouseEnabled)
                ev.accept()
        elif ev.buttons() & QtCore.Qt.RightButton:
            if self.aspectLocked is not False:
                mask[0] = 0
            dif = ev.screenPos() - ev.lastScreenPos()
            dif = np.array([dif.x(), dif.y()])
            dif[0] *= -1
            s = ((mask * 0.02) + 1) ** dif
            #print mask, dif, s
            center = Point(self.childGroup.transform().inverted()[0].map(ev.buttonDownPos(QtCore.Qt.RightButton)))
            self.scaleBy(s, center)
            #self.emit(QtCore.SIGNAL('rangeChangedManually'), self.mouseEnabled)
            self.sigRangeChangedManually.emit(self.mouseEnabled)
            ev.accept()
        else:
            ev.ignore()

    def mousePressEvent(self, ev):
        QtGui.QGraphicsWidget.mousePressEvent(self, ev)
        #if self.rbScaleBox is not None:
            #self.removeItem(self.rbScaleBox)
            #del self.rbScaleBox
            #self.rbScaleBox = None
            
        self.mousePos = np.array([ev.pos().x(), ev.pos().y()])
        self.pressPos = self.mousePos.copy()
        
        # check modifiers first:
        #mmods = ev.modifiers()
        #if mmods == QtCore.Qt.ControlModifier:
            #ax = self.axHistory(self.axHistoryPointer)
            #self.showAxRect(ax)
            ##print 'Previous'
        #elif mmods == QtCore.Qt.MetaModifier:
            #if self.axHistoryPointer+1 < len(self.axHistory):
                #self.axHistoryPointer += 1
                #self.showAxRect(self.AxHistory(self.axHistoryPointer+1))
            ##print 'Next'
        #elif mmods == QtCore.Qt.ShiftModifier:
            #self.axHistoryPointer = None
            #self.axHistory = []
            ##print 'cleared'
        #elif mmods == QtCore.Qt.AltModifier:

            
        ev.accept()

    def mouseReleaseEvent(self, ev):
        QtGui.QGraphicsWidget.mouseReleaseEvent(self, ev)
        pos = np.array([ev.pos().x(), ev.pos().y()])
        #if sum(abs(self.pressPos - pos)) < 3:  ## Detect click
            #if ev.button() == QtCore.Qt.RightButton:
                #self.ctrlMenu.popup(self.mapToGlobal(ev.pos()))
        self.mousePos = pos
        if ev.button() & (QtCore.Qt.LeftButton | QtCore.Qt.MidButton) and self.useLeftButtonPan == False:
            #if self.rbScaleBox is not None:
                #self.removeItem(self.rbScaleBox)
                ##del self.rbScaleBox # remove the rectangle
                #self.rbScaleBox = None
            #ax = self.mouseRect()
            
            ## Get rectangle from drag
            if self.rbScaleBox.isVisible():
                self.rbScaleBox.hide()
                ax = QtCore.QRectF(Point(self.pressPos), Point(self.mousePos))
                ax = self.childGroup.mapRectFromParent(ax)
                self.showAxRect(ax)
                ev.accept()
                self.axHistoryPointer += 1
                self.axHistory = self.axHistory[:self.axHistoryPointer] + [ax]

    def updateScaleBox(self):
        r = QtCore.QRectF(Point(self.pressPos), Point(self.mousePos))
        r = self.childGroup.mapRectFromParent(r)
        self.rbScaleBox.setPos(r.topLeft())
        self.rbScaleBox.resetTransform()
        self.rbScaleBox.scale(r.width(), r.height())
        self.rbScaleBox.show()

    def showAxRect(self, ax):
        self.setRange(ax.normalized()) # be sure w, h are correct coordinates
        self.sigRangeChangedManually.emit(self.mouseEnabled)

    #def mouseRect(self):
        #vs = self.viewScale()
        #vr = self.viewRange
        ## Convert positions from screen (view) pixel coordinates to axis coordinates 
        #ax = QtCore.QRectF(self.pressPos[0]/vs[0]+vr[0][0], -(self.pressPos[1]/vs[1]-vr[1][1]),
            #(self.mousePos[0]-self.pressPos[0])/vs[0], -(self.mousePos[1]-self.pressPos[1])/vs[1])
        #return(ax)

    def setRange(self, ax, minimum=None, maximum=None, padding=0.02, update=True):
        """
        Set the visible range of the ViewBox.
        Can be called with a QRectF:
            setRange(QRectF(x, y, w, h))
        Or with axis, min, max:
            setRange(0, xMin, xMax)
            setRange(1, yMin, yMax)
        """
        if isinstance(ax, QtCore.QRectF):
            changes = {0: [ax.left(), ax.right()], 1: [ax.top(), ax.bottom()]}
            #if self.aspectLocked is not False:
                #sbr = self.boundingRect()
                #if sbr.width() == 0 or (ax.height()/ax.width()) > (sbr.height()/sbr.width()):
                    #chax = 0
                #else:
                    #chax = 1

        elif ax in [1,0]:
            changes = {ax: [minimum,maximum]}
            #if self.aspectLocked is not False:
                #ax2 = 1 - ax
                #ratio = self.aspectLocked
                #r2 = self.range[ax2]
                #d = ratio * (max-min) * 0.5
                #c = (self.range[ax2][1] + self.range[ax2][0]) * 0.5
                #changes[ax2] = [c-d, c+d]
 
        else:
            print ax
            raise Exception("argument 'ax' must be 0, 1, or QRectF.")
        
        changed = [False, False]
        for ax, range in changes.iteritems():
            mn = min(range)
            mx = max(range)
            if mn == mx:   ## If we requested 0 range, try to preserve previous scale. Otherwise just pick an arbitrary scale.
                dy = self.viewRange[ax][1] - self.viewRange[ax][0]
                if dy == 0:
                    dy = 1
                mn -= dy*0.5
                mx += dy*0.5
                padding = 0.0
            if any(np.isnan([mn, mx])) or any(np.isinf([mn, mx])):
                raise Exception("Not setting range [%s, %s]" % (str(mn), str(mx)))
                
            p = (mx-mn) * padding
            mn -= p
            mx += p
            
            if self.targetRange[ax] != [mn, mx]:
                self.targetRange[ax] = [mn, mx]
                changed[ax] = True
            
        if update:
            self.updateMatrix(changed)

            
    def setYRange(self, min, max, update=True, padding=0.02):
        self.setRange(1, min, max, update=update, padding=padding)
        
    def setXRange(self, min, max, update=True, padding=0.02):
        self.setRange(0, min, max, update=update, padding=padding)

    def autoRange(self, padding=0.02):
        br = self.childGroup.childrenBoundingRect()
        self.setRange(br, padding=padding)

    def updateMatrix(self, changed=None):
        if changed is None:
            changed = [False, False]
        #print "udpateMatrix:"
        #print "  range:", self.range
        tr = self.targetRect()
        bounds = self.boundingRect()
        
        ## set viewRect, given targetRect and possibly aspect ratio constraint
        if self.aspectLocked is False or bounds.height() == 0:
            self.viewRange = [self.targetRange[0][:], self.targetRange[1][:]]
        else:
            viewRatio = bounds.width() / bounds.height()
            targetRatio = self.aspectLocked * tr.width() / tr.height()
            if targetRatio > viewRatio:  
                ## target is wider than view
                dy = 0.5 * (tr.width() / (self.aspectLocked * viewRatio) - tr.height())
                if dy != 0:
                    changed[1] = True
                self.viewRange = [self.targetRange[0][:], [self.targetRange[1][0] - dy, self.targetRange[1][1] + dy]]
            else:
                dx = 0.5 * (tr.height() * viewRatio * self.aspectLocked - tr.width())
                if dx != 0:
                    changed[0] = True
                self.viewRange = [[self.targetRange[0][0] - dx, self.targetRange[0][1] + dx], self.targetRange[1][:]]
        
        vr = self.viewRect()
        translate = Point(vr.center())
        #print "  bounds:", bounds
        if vr.height() == 0 or vr.width() == 0:
            return
        scale = Point(bounds.width()/vr.width(), bounds.height()/vr.height())
        m = QtGui.QTransform()
        
        ## First center the viewport at 0
        self.childGroup.resetTransform()
        center = self.transform().inverted()[0].map(bounds.center())
        #print "  transform to center:", center
        #if self.yInverted:
            #m.translate(center.x(), -center.y())
            #print "  inverted; translate", center.x(), center.y()
        #else:
        m.translate(center.x(), center.y())
            #print "  not inverted; translate", center.x(), -center.y()
            
        ## Now scale and translate properly
        if not self.yInverted:
            scale = scale * Point(1, -1)
        m.scale(scale[0], scale[1])
        st = translate
        m.translate(-st[0], -st[1])
        self.childGroup.setTransform(m)
        self.currentScale = scale
        
        if changed[0]:
            self.sigXRangeChanged.emit(self, tuple(self.viewRange[0]))
        if changed[1]:
            self.sigYRangeChanged.emit(self, tuple(self.viewRange[1]))
        if any(changed):
            self.sigRangeChanged.emit(self, self.viewRange)

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.size().width(), self.size().height())
        
    def paint(self, p, opt, widget):
        if self.border is not None:
            bounds = self.boundingRect()
            p.setPen(self.border)
            #p.fillRect(bounds, QtGui.QColor(0, 0, 0))
            p.drawRect(bounds)
