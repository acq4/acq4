from PyQt4 import QtCore, QtGui, QtOpenGL, QtSvg
from numpy import vstack
import time
from Point import *
#from vector import *

    
  

class GraphicsView(QtGui.QGraphicsView):
  def __init__(self, *args):
    QtGui.QGraphicsView.__init__(self, *args)
    palette = QtGui.QPalette()
    brush = QtGui.QBrush(QtGui.QColor(0,0,0))
    brush.setStyle(QtCore.Qt.SolidPattern)
    palette.setBrush(QtGui.QPalette.Active,QtGui.QPalette.Base,brush)
    brush = QtGui.QBrush(QtGui.QColor(0,0,0))
    brush.setStyle(QtCore.Qt.SolidPattern)
    palette.setBrush(QtGui.QPalette.Inactive,QtGui.QPalette.Base,brush)
    brush = QtGui.QBrush(QtGui.QColor(244,244,244))
    brush.setStyle(QtCore.Qt.SolidPattern)
    palette.setBrush(QtGui.QPalette.Disabled,QtGui.QPalette.Base,brush)
    self.setPalette(palette)
    self.setProperty("cursor",QtCore.QVariant(QtCore.Qt.ArrowCursor))
    self.setFocusPolicy(QtCore.Qt.StrongFocus)
    self.setFrameShape(QtGui.QFrame.NoFrame)
    self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    self.setTransformationAnchor(QtGui.QGraphicsView.NoAnchor)
    self.setResizeAnchor(QtGui.QGraphicsView.AnchorViewCenter)
    #self.setResizeAnchor(QtGui.QGraphicsView.NoAnchor)
    self.setViewportUpdateMode(QtGui.QGraphicsView.SmartViewportUpdate)
    self.setSceneRect(QtCore.QRectF(-1e100, -1e100, 1e100, 1e100))
    self.setInteractive(False)
    self.lockedViewports = []
    self.lastMousePos = None
    self.setMouseTracking(False)
    self.aspectLocked = False
    #self.scale = Point(1.0, -1.0)
    self.yInverted = False
    #self.translate = Point(0.0, 0.0)
    self.range = QtCore.QRectF(0, 0, 1, 1)
    self.currentItem = None
    self.clearMouse()
    self.updateMatrix()
    
    
  def clearMouse(self):
    self.mouseTrail = []
    self.lastButtonReleased = None
  
  def resizeEvent(self, ev):
    #if ev.oldSize().width() == -1 or ev.oldSize().height() == -1:
      #return
    #print "Resize:"
    #s = Point(float(self.size().width())/ev.oldSize().width(), float(self.size().height())/ev.oldSize().height())
    #print ev.oldSize()
    #print self.size()
    #print s
    #self.scale = self.scale * s
    self.setRange(self.range, padding=0)
    self.updateMatrix()
  
  def updateMatrix(self, propagate=True):
    #print "======"
    self.translate = Point(self.range.center())
    #self.scale = Point(self.range.width() / self.size().width(), self.range.height() / self.size().height())
    self.scale = Point(self.size().width()/self.range.width(), self.size().height()/self.range.height())
    if not self.yInverted:
      self.scale = self.scale * Point(1, -1)
    
    m = QtGui.QMatrix()
    
    ## First center the viewport at 0
    self.resetMatrix()
    center = self.viewportTransform().inverted()[0].map(Point(self.width()/2., self.height()/2.))
    #print center, self.yInverted
    if self.yInverted:
      m.translate(center.x(), center.y())
    else:
      m.translate(center.x(), -center.y())
      
    ## Now scale and translate properly
    #print self.scale
    if self.aspectLocked:
      self.scale = Point(self.scale.min())
    m.scale(self.scale[0], self.scale[1])
    #print self.translate
    st = self.translate
    m.translate(-st[0], -st[1])
    self.setMatrix(m)
    
    if propagate:
      #r = self.range()
      for v in self.lockedViewports:
        v.setXRange(self.range, padding=0)
    
  def visibleRange(self):
    r = QtCore.QRectF(self.rect())
    return self.viewportTransform().inverted()[0].mapRect(r)

  def setRange(self, newRect, padding=0.05, lockAspect=None, propagate=True):
    #print "-----------> setRange"
    #print "  requested range:", newRect
    #print "  current translate/scale:", self.translate, self.scale
    padding = Point(padding)
    
    #rect = QtCore.QRectF(self.rect())
    #newRect = QtCore.QRectF(newRect)
    #size = Point(rect.width(), rect.height())
    #newSize = Point(newRect.width(), newRect.height())
    #if newSize[0] == 0 or newSize[1] == 0:
      #return
    #self.scale = (1.0 / (1.0+padding)) * size / newSize
    #if lockAspect:
      #self.scale = Point(self.scale.min())
    #if not self.yInverted:
      #self.scale *= Point(1.0, -1.0)
    #self.translate = Point(-newRect.center().x(), newRect.center().y())
    
    newRect = QtCore.QRectF(newRect)
    pw = newRect.width() * padding[0]
    ph = newRect.height() * padding[1]
    self.range = newRect.adjusted(-pw, -ph, pw, ph)
    
    #if self.aspectLocked:
      #print 'correct aspect'
      #a1 = float(self.width()) / self.height()
      #a2 = float(self.range.width()) / self.range.height()
      #if a1 > a2:
        #print 'adjust w'
        #adj = 0.5 * (self.range.height()*a1 - self.range.width())
        #self.range.adjust(-adj, 0, adj, 0)
      #elif a2 > a1:
        #print 'adjust h'
        #adj = 0.5 * (self.range.width()/a1 - self.range.height())
        #self.range.adjust(0, -adj, 0, adj)
    
    self.updateMatrix(propagate)
    #print "  new range:", self.range()
    #print "  new translate/scale", self.translate, self.scale
    self.emit(QtCore.SIGNAL('viewChanged(QRectF)'), self.range)
    #print "<----------- setRange"
    
    
  def lockXRange(self, v1):
    if not v1 in self.lockedViewports:
      self.lockedViewports.append(v1)
    
  def setXRange(self, r, padding=0.05):
    #print "-----------> setXRange"
    r1 = QtCore.QRectF(self.range)
    r1.setLeft(r.left())
    r1.setRight(r.right())
    self.setRange(r1, padding=[padding, 0], propagate=False)
    #print "<---------- setYRange"
    
  def setYRange(self, r, padding=0.05):
    #print "----------> setYRange"
    r1 = QtCore.QRectF(self.range)
    r1.setTop(r.top())
    r1.setBottom(r.bottom())
    self.setRange(r1, padding=[0, padding], propagate=False)
    #print "<---------- setYRange"
    
  def invertY(self, invert=True):
    if self.yInverted != invert:
      self.scale[1] *= -1.
    self.yInverted = invert
    self.updateMatrix()
  
  
  def wheelEvent(self, ev):
    QtGui.QGraphicsView.wheelEvent(self, ev)
    sc = 1.001 ** ev.delta()
    self.scale *= sc
    self.updateMatrix()
    
    
  def setAspectLocked(self, s):
    self.aspectLocked = s
    
  #def mouseDoubleClickEvent(self, ev):
    #QtGui.QGraphicsView.mouseDoubleClickEvent(self, ev)
    #pass
    
  ## This function is here because interactive mode is disabled due to bugs.
  def graphicsSceneEvent(self, ev, pev=None, fev=None):
    ev1 = GraphicsSceneMouseEvent()
    ev1.setPos(QtCore.QPointF(ev.pos().x(), ev.pos().y()))
    ev1.setButtons(ev.buttons())
    ev1.setButton(ev.button())
    ev1.setModifiers(ev.modifiers())
    ev1.setScenePos(self.mapToScene(QtCore.QPoint(ev.pos())))
    if pev is not None:
      ev1.setLastPos(pev.pos())
      ev1.setLastScenePos(pev.scenePos())
      ev1.setLastScreenPos(pev.screenPos())
    if fev is not None:
      ev1.setButtonDownPos(fev.pos())
      ev1.setButtonDownScenePos(fev.scenePos())
      ev1.setButtonDownScreenPos(fev.screenPos())
    return ev1
    
  def mousePressEvent(self, ev):
    QtGui.QGraphicsView.mousePressEvent(self, ev)
    self.lastMousePos = Point(ev.pos())
    if ev.buttons() == QtCore.Qt.LeftButton:
      self.currentItem = None
      maxZ = None
      for i in self.items(ev.pos()):
        if maxZ is None or maxZ < i.zValue():
          self.currentItem = i
          maxZ = i.zValue()
      self.pev = self.graphicsSceneEvent(ev)
      self.fev = self.pev
      if self.currentItem is not None:
        self.currentItem.mousePressEvent(self.pev)
      self.clearMouse()
      self.mouseTrail.append(Point(self.mapToScene(ev.pos())))
      self.emit(QtCore.SIGNAL("mousePressed(PyQt_PyObject)"), self.mouseTrail)
        
  def mouseReleaseEvent(self, ev):
    QtGui.QGraphicsView.mouseReleaseEvent(self, ev)
    if ev.button() == QtCore.Qt.LeftButton:
      self.mouseTrail.append(Point(self.mapToScene(ev.pos())))
      self.emit(QtCore.SIGNAL("mouseReleased(PyQt_PyObject)"), self.mouseTrail)
      if self.currentItem is not None:
        pev = self.graphicsSceneEvent(ev, self.pev, self.fev)
        self.pev = pev
        self.currentItem.mouseReleaseEvent(pev)
    self.lastButtonReleased = ev.button()

  def mouseMoveEvent(self, ev):
    QtGui.QGraphicsView.mouseMoveEvent(self, ev)
    self.emit(QtCore.SIGNAL("sceneMouseMoved(PyQt_PyObject)"), self.mapToScene(ev.pos()))
    
    if ev.buttons() == QtCore.Qt.LeftButton:
      self.mouseTrail.append(Point(self.mapToScene(ev.pos())))
      if self.currentItem is not None:
        pev = self.graphicsSceneEvent(ev, self.pev, self.fev)
        self.pev = pev
        self.currentItem.mouseMoveEvent(pev)
    
    if self.lastMousePos is None:
      self.lastMousePos = Point(ev.pos())
    delta = Point(ev.pos()) - self.lastMousePos
    
    self.lastMousePos = Point(ev.pos())
    
    if ev.buttons() == QtCore.Qt.RightButton:
      delta = Point(clip(delta[0], -10, 10), clip(delta[1], -10, 10))
      scale = 1.01 ** delta
      if self.aspectLocked:
        scale[0] = scale[1]
        if self.yInverted:
          scale[0] = 1. / scale[0]
      adj = (self.range.width()*(scale[0]-1), self.range.height()*(scale[1]-1))
      
      #print delta, adj
      #print self.range
      self.range.adjust(adj[0], -adj[1], -adj[0], adj[1])
      #print self.range
      #self.scale *= scale
      self.updateMatrix()
      self.emit(QtCore.SIGNAL('regionChanged(QRectF)'), self.range)
    elif ev.buttons() == QtCore.Qt.MidButton:
      tr = -delta / self.scale
      self.range.adjust(tr[0], tr[1], tr[0], tr[1])
      self.updateMatrix()
      self.emit(QtCore.SIGNAL('regionChanged(QRectF)'), self.range)

    
  def writeSvg(self, fileName=None):
    if fileName is None:
      fileName = str(QtGui.QFileDialog.getSaveFileName())
    self.svg = QtSvg.QSvgGenerator()
    self.svg.setFileName(fileName)
    self.svg.setSize(self.size())
    self.svg.setResolution(600)
    painter = QtGui.QPainter(self.svg)
    self.render(painter)
    
  def writeImage(self, fileName=None):
    if fileName is None:
      fileName = str(QtGui.QFileDialog.getSaveFileName())
    self.png = QtGui.QImage(self.size(), QtGui.QImage.Format_ARGB32)
    painter = QtGui.QPainter(self.png)
    rh = self.renderHints()
    self.setRenderHints(QtGui.QPainter.Antialiasing)
    self.render(painter)
    self.setRenderHints(rh)
    self.png.save(fileName)
    
  def getFreehandLine(self):
    
    # Wait for click
    self.clearMouse()
    while self.lastButtonReleased != QtCore.Qt.LeftButton:
      QtGui.qApp.sendPostedEvents()
      QtGui.qApp.processEvents()
      time.sleep(0.01)
    fl = vstack(self.mouseTrail)
    return fl
  
  def getClick(self):
    fl = self.getFreehandLine()
    return fl[-1]
  

class GraphicsSceneMouseEvent(QtGui.QGraphicsSceneMouseEvent):
  """Stand-in class for QGraphicsSceneMouseEvent"""
  def __init__(self):
    QtGui.QGraphicsSceneMouseEvent.__init__(self)
      
  def setPos(self, p):
    self.vpos = p
  def setButtons(self, p):
    self.vbuttons = p
  def setButton(self, p):
    self.vbutton = p
  def setModifiers(self, p):
    self.vmodifiers = p
  def setScenePos(self, p):
    self.vscenePos = p
  def setLastPos(self, p):
    self.vlastPos = p
  def setLastScenePos(self, p):
    self.vlastScenePos = p
  def setLastScreenPos(self, p):
    self.vlastScreenPos = p
  def setButtonDownPos(self, p):
    self.vbuttonDownPos = p
  def setButtonDownScenePos(self, p):
    self.vbuttonDownScenePos = p
  def setButtonDownScreenPos(self, p):
    self.vbuttonDownScreenPos = p
  
  def pos(self):
    return self.vpos
  def buttons(self):
    return self.vbuttons
  def button(self):
    return self.vbutton
  def modifiers(self):
    return self.vmodifiers
  def scenePos(self):
    return self.vscenePos
  def lastPos(self):
    return self.vlastPos
  def lastScenePos(self):
    return self.vlastScenePos
  def lastScreenPos(self):
    return self.vlastScreenPos
  def buttonDownPos(self):
    return self.vbuttonDownPos
  def buttonDownScenePos(self):
    return self.vbuttonDownScenePos
  def buttonDownScreenPos(self):
    return self.vbuttonDownScreenPos
  
  