# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtGui, QtCore
from pyqtgraph.GraphicsView import GraphicsView
from pyqtgraph.GraphicsScene import GraphicsScene
from pyqtgraph.graphicsItems.ViewBox import ViewBox

#class FlowchartGraphicsView(QtGui.QGraphicsView):
class FlowchartGraphicsView(GraphicsView):
    
    sigHoverOver = QtCore.Signal(object)
    sigClicked = QtCore.Signal(object)
    
    def __init__(self, widget, *args):
        #QtGui.QGraphicsView.__init__(self, *args)
        GraphicsView.__init__(self, *args, useOpenGL=False)
        #self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(255,255,255)))
        self._vb = FlowchartViewBox(widget, lockAspect=True, invertY=True)
        self.setCentralItem(self._vb)
        #self.scene().addItem(self.vb)
        #self.setMouseTracking(True)
        #self.lastPos = None
        #self.setTransformationAnchor(self.AnchorViewCenter)
        #self.setRenderHints(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        #self.setDragMode(QtGui.QGraphicsView.RubberBandDrag)
        #self.setRubberBandSelectionMode(QtCore.Qt.ContainsItemBoundingRect)
    
    def viewBox(self):
        return self._vb
    
    
    #def mousePressEvent(self, ev):
        #self.moved = False
        #self.lastPos = ev.pos()
        #return QtGui.QGraphicsView.mousePressEvent(self, ev)

    #def mouseMoveEvent(self, ev):
        #self.moved = True
        #callSuper = False
        #if ev.buttons() &  QtCore.Qt.RightButton:
            #if self.lastPos is not None:
                #dif = ev.pos() - self.lastPos
                #self.scale(1.01**-dif.y(), 1.01**-dif.y())
        #elif ev.buttons() & QtCore.Qt.MidButton:
            #if self.lastPos is not None:
                #dif = ev.pos() - self.lastPos
                #self.translate(dif.x(), -dif.y())
        #else:
            ##self.emit(QtCore.SIGNAL('hoverOver'), self.items(ev.pos()))
            #self.sigHoverOver.emit(self.items(ev.pos()))
            #callSuper = True
        #self.lastPos = ev.pos()
        
        #if callSuper:
            #QtGui.QGraphicsView.mouseMoveEvent(self, ev)
            
    #def mouseReleaseEvent(self, ev):
        #if not self.moved:
            ##self.emit(QtCore.SIGNAL('clicked'), ev)
            #self.sigClicked.emit(ev)
        #return QtGui.QGraphicsView.mouseReleaseEvent(self, ev)
        
class FlowchartViewBox(ViewBox):
    
    def __init__(self, widget, *args, **kwargs):
        ViewBox.__init__(self, *args, **kwargs)
        self.widget = widget
        self.menu = None
        self._subMenus = None ## need a place to store the menus otherwise they dissappear (even though they've been added to other menus) ((yes, it doesn't make sense))
        
    def getMenu(self):
        self.menu = QtGui.QMenu()
        #print "1a:", [str(a.text()) for a in self.menu.actions()]
        self._subMenus = self.getSubMenus()
        for menu in self._subMenus:
            self.menu.addMenu(menu)
            #print "1b:", [str(a.text()) for a in self.menu.actions()]
        #print "1c:", [str(a.text()) for a in self.menu.actions()]
        return self.menu
    
    def getSubMenus(self):
        menu1 = self.widget.buildMenu()
        menu1.setTitle("Add node")
        menu2 = ViewBox.getMenu(self)
        return [menu1, menu2]
    
    
        
        
        
        
        


##class FlowchartGraphicsScene(QtGui.QGraphicsScene):
#class FlowchartGraphicsScene(GraphicsScene):
    
    #sigContextMenuEvent = QtCore.Signal(object)
    
    #def __init__(self, *args):
        ##QtGui.QGraphicsScene.__init__(self, *args)
        #GraphicsScene.__init__(self, *args)
        
    #def mouseClickEvent(self, ev):
        ##QtGui.QGraphicsScene.contextMenuEvent(self, ev)
        #if not ev.button() in [QtCore.Qt.RightButton]:
            #self.sigContextMenuEvent.emit(ev)