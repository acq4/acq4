from PyQt4 import QtCore, QtGui, QtOpenGL, QtSvg
#from GraphicsView import qPtArr
from numpy import array, arccos, dot, pi, zeros, vstack, ubyte, fromfunction
from numpy.linalg import norm
import scipy.ndimage as ndimage
#from vector import *
from Point import *
from math import cos, sin

def rectStr(r):
    return "[%f, %f] + [%f, %f]" % (r.x(), r.y(), r.width(), r.height())

## Multiple inheritance not allowed in PyQt. Retarded workaround:
class QObjectWorkaround:
    def __init__(self):
        self._qObj_ = QtCore.QObject()
    def __getattr__(self, attr):
        if attr == '_qObj_':
            raise Exception("QObjectWorkaround not initialized!")
        return getattr(self._qObj_, attr)
    def connect(self, *args):
        return QtCore.QObject.connect(self._qObj_, *args)


class ROI(QtGui.QGraphicsItem, QObjectWorkaround):
    def __init__(self, pos, size=Point(1, 1), angle=0.0, invertible=False, maxBounds=None, snapSize=1.0, scaleSnap=False, translateSnap=False, rotateSnap=False):
        QObjectWorkaround.__init__(self)
        QtGui.QGraphicsItem.__init__(self)
        pos = Point(pos)
        size = Point(size)
        self.aspectLocked = False
        self.translatable = True
        
        self.pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        self.handlePen = QtGui.QPen(QtGui.QColor(150, 255, 255))
        self.handles = []
        self.state = {'pos': pos, 'size': size, 'angle': angle}
        self.lastState = None
        self.setPos(pos)
        self.rotate(-angle)
        self.setZValue(10)
        
        self.handleSize = 4
        self.invertible = invertible
        self.maxBounds = maxBounds
        
        self.snapSize = snapSize
        self.translateSnap = translateSnap
        self.rotateSnap = rotateSnap
        self.scaleSnap = scaleSnap
        
    def sceneBounds(self):
        return self.sceneTransform().mapRect(self.boundingRect())

    def setPen(self, pen):
        self.pen = pen
        self.update()
        
    def setPos(self, pos):
        pos = Point(pos)
        self.state['pos'] = pos
        QtGui.QGraphicsItem.setPos(self, pos)
        self.handleChange()
        
    def setSize(self, size):
        size = Point(size)
        self.prepareGeometryChange()
        self.state['size'] = size
        self.updateHandles()
        self.handleChange()
        
    def addTranslateHandle(self, pos, axes=None, item=None):
        pos = Point(pos)
        return self.addHandle({'type': 't', 'pos': pos, 'item': item})
    
    def addScaleHandle(self, pos, center, axes=None, item=None):
        pos = Point(pos)
        center = Point(center)
        info = {'type': 's', 'center': center, 'pos': pos, 'item': item}
        if pos.x() == center.x():
            info['xoff'] = True
        if pos.y() == center.y():
            info['yoff'] = True
        return self.addHandle(info)
    
    def addRotateHandle(self, pos, center, item=None):
        pos = Point(pos)
        center = Point(center)
        return self.addHandle({'type': 'r', 'center': center, 'pos': pos, 'item': item})
    
    def addScaleRotateHandle(self, pos, center, item=None):
        pos = Point(pos)
        center = Point(center)
        if pos[0] != center[0] and pos[1] != center[1]:
            raise Exception("Scale/rotate handles must have either the same x or y coordinate as their center point.")
        return self.addHandle({'type': 'sr', 'center': center, 'pos': pos, 'item': item})
    
    def addHandle(self, info):
        if not info.has_key('item') or info['item'] is None:
            h = Handle(self.handleSize, typ=info['type'], pen=self.handlePen, parent=self)
            h.setPos(info['pos'] * self.state['size'])
            info['item'] = h
        else:
            h = info['item']
        iid = len(self.handles)
        h.connectROI(self, iid)
        #h.mouseMoveEvent = lambda ev: self.pointMoveEvent(iid, ev)
        #h.mousePressEvent = lambda ev: self.pointPressEvent(iid, ev)
        #h.mouseReleaseEvent = lambda ev: self.pointReleaseEvent(iid, ev)
        self.handles.append(info)
        return h
        
    def mousePressEvent(self, ev):
        if self.translatable:
            self.cursorOffset = self.scenePos() - ev.scenePos()
            self.emit(QtCore.SIGNAL('regionChangeStarted'))
        
    def mouseMoveEvent(self, ev):
        if self.translatable:
            snap = None
            if self.translateSnap or (ev.modifiers & QtCore.Qt.ControlModifier):
                snap = Point(self.snapSize, self.snapSize)
            newPos = ev.scenePos() + self.cursorOffset
            self.translate(newPos - self.scenePos(), snap)
    
    def mouseReleaseEvent(self, ev):
        if self.translatable:
            self.emit(QtCore.SIGNAL('regionChangeFinished'))
    
    
    
    def pointPressEvent(self, pt, ev):
        self.emit(QtCore.SIGNAL('regionChangeStarted'))
        #self.pressPos = self.mapFromScene(ev.scenePos())
        #self.pressHandlePos = self.handles[pt]['item'].pos()
    
    def pointReleaseEvent(self, pt, ev):
        self.emit(QtCore.SIGNAL('regionChangeFinished'))
    
    def stateCopy(self):
        sc = {}
        sc['pos'] = Point(self.state['pos'])
        sc['size'] = Point(self.state['size'])
        sc['angle'] = self.state['angle']
        return sc
    
    def updateHandles(self):
        for h in self.handles:
            if h['item'] in self.children():
                p = h['pos']
                h['item'].setPos(h['pos'] * self.state['size'])
        
    
    def checkPointMove(self, pt, pos, modifiers):
        return True
    
    def pointMoveEvent(self, pt, ev):
        self.movePoint(pt, ev.scenePos(), ev.modifiers())
        
        
    def movePoint(self, pt, pos, modifiers=QtCore.Qt.KeyboardModifier()):
        newState = self.stateCopy()
        h = self.handles[pt]
        #p0 = self.mapToScene(h['item'].pos())
        p0 = self.mapToScene(h['pos'] * self.state['size'])
        p1 = Point(pos)
        if h.has_key('center'):
            c = h['center']
            cs = c * self.state['size']
            #lpOrig = h['pos'] - 
            lp0 = self.mapFromScene(p0) - cs
            lp1 = self.mapFromScene(p1) - cs
        
        if h['type'] == 't':
            #p0 = Point(self.mapToScene(h['item'].pos()))
            #p1 = Point(pos + self.mapToScene(self.pressHandlePos) - self.mapToScene(self.pressPos))
            
            snap = None
            if self.translateSnap or (modifiers & QtCore.Qt.ControlModifier):
                snap = Point(self.snapSize, self.snapSize)
            self.translate(p1-p0, snap)
        
        elif h['type'] == 's':
            #c = h['center']
            #cs = c * self.state['size']
            #p1 = (self.mapFromScene(ev.scenePos()) + self.pressHandlePos - self.pressPos) - cs
            
            if h['center'][0] == h['pos'][0]:
                lp1[0] = 0
            if h['center'][1] == h['pos'][1]:
                lp1[1] = 0
            
            if self.scaleSnap or (modifiers & QtCore.Qt.ControlModifier):
                lp1[0] = round(lp1[0] / self.snapSize) * self.snapSize
                lp1[1] = round(lp1[1] / self.snapSize) * self.snapSize
            
            hs = h['pos'] - c
            if hs[0] == 0:
                hs[0] = 1
            if hs[1] == 0:
                hs[1] = 1
            newSize = lp1 / hs
            
            if newSize[0] == 0:
                newSize[0] = newState['size'][0]
            if newSize[1] == 0:
                newSize[1] = newState['size'][1]
            if not self.invertible:
                if newSize[0] < 0:
                    newSize[0] = newState['size'][0]
                if newSize[1] < 0:
                    newSize[1] = newState['size'][1]
            if self.aspectLocked:
                newSize[0] = newSize[1]
            
            s0 = c * self.state['size']
            s1 = c * newSize
            cc = self.mapToScene(s0 - s1) - self.mapToScene(Point(0, 0))
            
            newState['size'] = newSize
            newState['pos'] = newState['pos'] + cc
            if self.maxBounds is not None:
                r = self.stateRect(newState)
                if not self.maxBounds.contains(r):
                    return
            
            self.setPos(newState['pos'])
            self.prepareGeometryChange()
            self.state = newState
            
            self.updateHandles()
        
        elif h['type'] == 'r':
            #newState = self.stateCopy()
            #c = h['center']
            #cs = c * self.state['size']
            #p0 = Point(h['item'].pos()) - cs
            #p1 = (self.mapFromScene(ev.scenePos()) + self.pressHandlePos - self.pressPos) - cs
            if lp1.length() == 0 or lp0.length() == 0:
                return
            
            ang = newState['angle'] + lp0.angle(lp1)
            if ang is None:
                return
            if self.rotateSnap or (modifiers & QtCore.Qt.ControlModifier):
                ang = round(ang / (pi/12.)) * (pi/12.)
            
            
            tr = QtGui.QTransform()
            tr.rotate(-ang * 180. / pi)
            
            cc = self.mapToScene(cs) - (tr.map(cs) + self.state['pos'])
            newState['angle'] = ang
            newState['pos'] = newState['pos'] + cc
            if self.maxBounds is not None:
                r = self.stateRect(newState)
                if not self.maxBounds.contains(r):
                    return
            self.setTransform(tr)
            self.setPos(newState['pos'])
            self.state = newState
        
        elif h['type'] == 'sr':
            #newState = self.stateCopy()
            if h['center'][0] == h['pos'][0]:
                scaleAxis = 1
            else:
                scaleAxis = 0
            
            #c = h['center']
            #cs = c * self.state['size']
            #p0 = Point(h['item'].pos()) - cs
            #p1 = (self.mapFromScene(ev.scenePos()) + self.pressHandlePos - self.pressPos) - cs
            if lp1.length() == 0 or lp0.length() == 0:
                return
            
            ang = newState['angle'] + lp0.angle(lp1)
            if ang is None:
                return
            if self.rotateSnap or (modifiers & QtCore.Qt.ControlModifier):
                ang = round(ang / (pi/12.)) * (pi/12.)
            
            hs = abs(h['pos'][scaleAxis] - c[scaleAxis])
            newState['size'][scaleAxis] = lp1.length() / hs
            if self.scaleSnap or (modifiers & QtCore.Qt.ControlModifier):
                newState['size'][scaleAxis] = round(newState['size'][scaleAxis] / self.snapSize) * self.snapSize
            if newState['size'][scaleAxis] == 0:
                newState['size'][scaleAxis] = 1
                
            c1 = c * newState['size']
            tr = QtGui.QTransform()
            tr.rotate(-ang * 180. / pi)
            
            cc = self.mapToScene(cs) - (tr.map(c1) + self.state['pos'])
            newState['angle'] = ang
            newState['pos'] = newState['pos'] + cc
            if self.maxBounds is not None:
                r = self.stateRect(newState)
                if not self.maxBounds.contains(r):
                    return
            self.setTransform(tr)
            self.setPos(newState['pos'])
            self.prepareGeometryChange()
            self.state = newState
        
            self.updateHandles()
        
        self.handleChange()
    
    def handleChange(self):
        changed = False
        if self.lastState is None:
            changed = True
        else:
            for k in self.state.keys():
                if self.state[k] != self.lastState[k]:
                    changed = True
        self.lastState = self.stateCopy()
        if changed:
            self.update()
            self.emit(QtCore.SIGNAL('regionChanged'), self)
            
    
    def scale(self, s, center=[0,0]):
        c = self.mapToScene(Point(center) * self.state['size'])
        self.prepareGeometryChange()
        self.state['size'] = self.state['size'] * s
        c1 = self.mapToScene(Point(center) * self.state['size'])
        self.state['pos'] = self.state['pos'] + c - c1
        self.setPos(self.state['pos'])
        self.updateHandles()
    
    def translate(self, pt, snap=None):
        newState = self.stateCopy()
        newState['pos'] = newState['pos'] + pt
        if snap != None:
            newState['pos'][0] = round(newState['pos'][0] / snap[0]) * snap[0]
            newState['pos'][1] = round(newState['pos'][1] / snap[1]) * snap[1]
            
        
        #d = ev.scenePos() - self.mapToScene(self.pressPos)
        if self.maxBounds is not None:
            r = self.stateRect(newState)
            #r0 = self.sceneTransform().mapRect(self.boundingRect())
            d = Point(0,0)
            if self.maxBounds.left() > r.left():
                d[0] = self.maxBounds.left() - r.left()
            elif self.maxBounds.right() < r.right():
                d[0] = self.maxBounds.right() - r.right()
            if self.maxBounds.top() > r.top():
                d[1] = self.maxBounds.top() - r.top()
            elif self.maxBounds.bottom() < r.bottom():
                d[1] = self.maxBounds.bottom() - r.bottom()
            newState['pos'] += d
        
        self.state['pos'] = newState['pos']
        self.setPos(self.state['pos'])
        self.handleChange()
    
    def stateRect(self, state):
        r = QtCore.QRectF(0, 0, state['size'][0], state['size'][1])
        tr = QtGui.QTransform()
        tr.rotate(-state['angle'] * 180 / pi)
        r = tr.mapRect(r)
        return r.adjusted(state['pos'][0], state['pos'][1], state['pos'][0], state['pos'][1])
    
    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.state['size'][0], self.state['size'][1])

    def paint(self, p, opt, widget):
        r = self.boundingRect()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(self.pen)
        p.drawRect(r)
        
    def getArrayRegion(self, data, img=None, axes=(0,1)):
        #print "----------------------"
        ## determine boundaries of image in scene coordinates
        ##   assumes image is not rotated!
        dShape = (data.shape[axes[0]], data.shape[axes[1]])
        if img is None:
            bounds = QtCore.QRectF(0, 0, dShape[0], dShape[1])
        else:
            imr = QtCore.QRect(0, 0, img.width(), img.height())
            bounds = img.sceneTransform().mapRect(imr)
            #print "imr, bounds", imr, bounds
        
        ## Determine shape of ROI in data coordinates
        scaleFactor = Point(dShape) / Point(bounds.width(), bounds.height())
        if abs(self.state['angle']) < 1e-5:
            paddedRgn = self.boundingRect()
        else:
            paddedRgn = self.boundingRect().adjusted(-scaleFactor[0], -scaleFactor[1], scaleFactor[0], scaleFactor[1])  ## pad by 1 pixel
        #print "paddedRgn", paddedRgn
            
        ## Determine region ROI covers in data
        ##   paddedRgn (ROI local coords) -> scene coords -> img local coords
        #rgn = self.sceneTransform().mapRect(paddedRgn).adjusted(-bounds.x(), -bounds.y(), -bounds.x(), -bounds.y())
        rgn = img.sceneTransform().inverted()[0].mapRect(self.sceneTransform().mapRect(paddedRgn))
        
        rgnPos = Point(rgn.x(), rgn.y())
        rgnSize = Point(rgn.width(), rgn.height())
        #print "rgn", rgn
        
        
        dataRect = QtCore.QRectF(0, 0, dShape[0], dShape[1])
        #print "dataRect", dataRect
        
        ## Find intersection between image and ROI
        readRgn = rgn.intersected(dataRect)
        #print "readRgn", readRgn
        
            
        ## convert readRegion to integer rect
        readRgni = QtCore.QRect(int(readRgn.x()), int(readRgn.y()), round(readRgn.width()), round(readRgn.height()))
        dpix = Point(readRgni.x() - readRgn.x(), readRgni.y() - readRgn.y())
        
        ## if there is no intersection, bail out
        if readRgni.width() == 0 or readRgn.height() == 0:
            #print "No intersection"
            return None
        
        
        ### From here on, we extract data from the source array
        ### and massage it into the return array
        
        writeRgn = readRgni.adjusted(int(-rgnPos[0]-dpix[0]), int(-rgnPos[1]-dpix[1]), round(-rgnPos[0]-dpix[0]), round(-rgnPos[1]-dpix[1]))
        
        ## transpose data so x and y are the first 2 axes
        trAx = range(0, data.ndim)
        trAx.remove(axes[0])
        trAx.remove(axes[1])
        tr1 = tuple(axes) + tuple(trAx)
        dataTr = data.transpose(tr1)
        #print "First transpose:", tr1, data.shape, dataTr.shape
        
        ## figure out the reverse transpose order
        tr2 = array(tr1)
        for i in range(0, len(tr2)):
            tr2[tr1[i]] = i
        tr2 = tuple(tr2)
        
        ## slice data out of transposed source array
        arr = dataTr[readRgni.x():readRgni.x()+readRgni.width(), readRgni.y():readRgni.y()+readRgni.height()]
        
        ## shift off partial pixels if needed
        if dpix[0] != 0 or dpix[1] != 0:
            sArr = ndimage.shift(arr, tuple(dpix) + (0,)*(arr.ndim-2), order=1)
        else:
            sArr = arr
        
        ## prepare write array and copy data
        arr1 = zeros((round(rgnSize[0]), round(rgnSize[1])) + dataTr.shape[2:], dtype=data.dtype)
        arr1[writeRgn.x():writeRgn.x()+arr.shape[0], writeRgn.y():writeRgn.y()+arr.shape[1]] = sArr
        
        
        ## rotate if needed
        #print self.state['angle']
        if abs(self.state['angle']) > 1e-5:
            arr2 = ndimage.rotate(arr1, self.state['angle'] * 180 / pi, order=1)
            
            ## crop down to original region
            rgn2 = QtCore.QRectF(0, 0, rgn.width(), rgn.height())
            tr = QtGui.QTransform()
            tr.rotate(self.state['angle'] * 180 / pi)
            tr2 = tr.inverted()[0]
            
            rgn3 = tr.mapRect(rgn2)
            p3 = Point(rgn3.x(), rgn3.y())
            p3r = tr2.map(p3) + Point(rgn.x(), rgn.y())
            
            p1r = self.state['pos'] - Point(bounds.x(), bounds.y()) - p3r
            p1 = Point(tr.map(p1r))
            p1 = Point(int(p1[0]), int(p1[1])) #- Point(1, 1)
            arr3 = arr2[p1[0]:p1[0]+round(self.state['size'][0]), p1[1]:p1[1]+round(self.state['size'][1])]
        else:
            arr3 = arr1
            
        ## Retranspose sliced data into original coordinates
        arr4 = arr3.transpose(tr2)
        #print "Reverse transpose:", tr2, arr3.shape, arr4.shape
        return arr4


        

class Handle(QtGui.QGraphicsItem):
    def __init__(self, radius, typ=None, pen=QtGui.QPen(QtGui.QColor(200, 200, 220)), parent=None):
        QtGui.QGraphicsItem.__init__(self, parent)
        self.setZValue(11)
        self.roi = []
        self.radius = radius
        self.typ = typ
        self.bounds = QtCore.QRectF(-1e-10, -1e-10, 2e-10, 2e-10)
        self.pen = pen
        if typ == 't':
            self.sides = 4
            self.startAng = pi/4
        elif typ == 's':
            self.sides = 4
            self.startAng = 0
        elif typ == 'r':
            self.sides = 12
            self.startAng = 0
        elif typ == 'sr':
            self.sides = 12
            self.startAng = 0
        else:
            self.sides = 4
            self.startAng = pi/4
            
    def connectROI(self, roi, i):
        self.roi.append((roi, i))
    
    def boundingRect(self):
        return self.bounds
        
    def mousePressEvent(self, ev):
        self.cursorOffset = self.scenePos() - ev.scenePos()
        for r in self.roi:
            r[0].pointPressEvent(r[1], ev)
        
    def mouseReleaseEvent(self, ev):
        for r in self.roi:
            r[0].pointReleaseEvent(r[1], ev)
                
    def mouseMoveEvent(self, ev):
        pos = ev.scenePos() + self.cursorOffset
        self.movePoint(pos, ev.modifiers())
        
    def movePoint(self, pos, modifiers=QtCore.Qt.KeyboardModifier()):
        for r in self.roi:
            if not r[0].checkPointMove(r[1], pos, modifiers):
                return
        for r in self.roi:
            r[0].movePoint(r[1], pos, modifiers)
        
    def paint(self, p, opt, widget):
        m = p.transform()
        mi = m.inverted()[0]
        size = mi.map(Point(self.radius, self.radius)) - mi.map(Point(0, 0))
        size = (size.x()*size.x() + size.y() * size.y()) ** 0.5
        bounds = QtCore.QRectF(-size, -size, size*2, size*2)
        if bounds != self.bounds:
            self.bounds = bounds
            self.prepareGeometryChange()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(self.pen)
        ang = self.startAng
        dt = 2*pi / self.sides
        for i in range(0, self.sides):
            x1 = size * cos(ang)
            y1 = size * sin(ang)
            x2 = size * cos(ang+dt)
            y2 = size * sin(ang+dt)
            ang += dt
            p.drawLine(Point(x1, y1), Point(x2, y2))
        




class TestROI(ROI):
    def __init__(self, pos, size, **args):
        #QtGui.QGraphicsRectItem.__init__(self, pos[0], pos[1], size[0], size[1])
        ROI.__init__(self, pos, size, **args)
        self.addTranslateHandle([0, 0])
        self.addTranslateHandle([0.5, 0.5])
        self.addScaleHandle([1, 1], [0, 0])
        self.addScaleRotateHandle([1, 0.5], [0.5, 0.5])
        self.addScaleHandle([0.5, 1], [0.5, 0.5])
        self.addRotateHandle([1, 0], [0, 0])
        self.addRotateHandle([0, 1], [1, 1])



class RectROI(ROI):
    def __init__(self, pos, size, centered=False, sideScalers=False, **args):
        #QtGui.QGraphicsRectItem.__init__(self, 0, 0, size[0], size[1])
        ROI.__init__(self, pos, size, **args)
        if centered:
            center = [0.5, 0.5]
        else:
            center = [0, 0]
            
        #self.addTranslateHandle(center)
        self.addScaleHandle([1, 1], center)
        if sideScalers:
            self.addScaleHandle([1, 0.5], [center[0], 0.5])
            self.addScaleHandle([0.5, 1], [0.5, center[1]])

class LineROI(ROI):
    def __init__(self, pos1, pos2, width, **args):
        pos1 = Point(pos1)
        pos2 = Point(pos2)
        d = pos2-pos1
        l = d.length()
        ang = Point(1, 0).angle(d)
        c = Point(-width/2. * sin(ang), -width/2. * cos(ang))
        pos1 = pos1 + c
        
        ROI.__init__(self, pos1, size=Point(l, width), angle=ang*180/pi, **args)
        self.addScaleRotateHandle([0, 0.5], [1, 0.5])
        self.addScaleRotateHandle([1, 0.5], [0, 0.5])
        self.addScaleHandle([0.5, 1], [0.5, 0.5])
        
        
class MultiLineROI(QtGui.QGraphicsItemGroup, QObjectWorkaround):
    def __init__(self, points, width, **args):
        QObjectWorkaround.__init__(self)
        QtGui.QGraphicsItem.__init__(self)
        self.roiArgs = args
        if len(points) < 2:
            raise Exception("Must start with at least 2 points")
        self.lines = []
        self.lines.append(ROI([0, 0], [1, 5]))
        self.lines[-1].addScaleHandle([0.5, 1], [0.5, 0.5])
        h = self.lines[-1].addScaleRotateHandle([0, 0.5], [1, 0.5])
        h.movePoint(points[0])
        h.movePoint(points[0])
        for i in range(1, len(points)):
            h = self.lines[-1].addScaleRotateHandle([1, 0.5], [0, 0.5])
            if i < len(points)-1:
                self.lines.append(ROI([0, 0], [1, 5]))
                self.lines[-1].addScaleRotateHandle([0, 0.5], [1, 0.5], item=h)
            h.movePoint(points[i])
            h.movePoint(points[i])
            
        for l in self.lines:
            l.translatable = False
            self.addToGroup(l)
            l.connect(QtCore.SIGNAL('regionChanged'), self.roiChangedEvent)
            l.connect(QtCore.SIGNAL('regionChangeStarted'), self.roiChangeStartedEvent)
            l.connect(QtCore.SIGNAL('regionChangeFinished'), self.roiChangeFinishedEvent)
        
    def roiChangedEvent(self):
        w = self.lines[0].state['size'][1]
        for l in self.lines[1:]:
            w0 = l.state['size'][1]
            l.scale([1.0, w/w0], center=[0.5,0.5])
        self.emit(QtCore.SIGNAL('regionChanged'))
            
    def roiChangeStartedEvent(self):
        self.emit(QtCore.SIGNAL('regionChangeStarted'))
        
    def roiChangeFinishedEvent(self):
        self.emit(QtCore.SIGNAL('regionChangeFinished'))
        
            
    def getArrayRegion(self, arr, img=None):
        rgns = []
        for l in self.lines:
            rgn = l.getArrayRegion(arr, img)
            if rgn is None:
                return None
            rgns.append(rgn)
        return vstack(rgns)
        
        
class EllipseROI(ROI):
    def __init__(self, pos, size, **args):
        #QtGui.QGraphicsRectItem.__init__(self, 0, 0, size[0], size[1])
        ROI.__init__(self, pos, size, **args)
        self.addRotateHandle([1.0, 0.5], [0.5, 0.5])
        self.addScaleHandle([0.5*2.**-0.5 + 0.5, 0.5*2.**-0.5 + 0.5], [0.5, 0.5])
            
    def paint(self, p, opt, widget):
        r = self.boundingRect()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(self.pen)
        p.drawEllipse(r)
        
    def getArrayRegion(self, arr, img=None):
        arr = ROI.getArrayRegion(self, arr, img)
        if arr is None or arr.shape[0] == 0 or arr.shape[1] == 0:
            return None
        w = arr.shape[0]
        h = arr.shape[1]
        ## generate an ellipsoidal mask
        mask = fromfunction(lambda x,y: (((x+0.5)/(w/2.)-1)**2+ ((y+0.5)/(h/2.)-1)**2)**0.5 < 1, (w, h))
    
        return arr * mask
        
class CircleROI(EllipseROI):
    def __init__(self, pos, size, **args):
        ROI.__init__(self, pos, size, **args)
        self.aspectLocked = True
        #self.addTranslateHandle([0.5, 0.5])
        self.addScaleHandle([0.5*2.**-0.5 + 0.5, 0.5*2.**-0.5 + 0.5], [0.5, 0.5])
        
