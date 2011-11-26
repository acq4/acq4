from pyqtgraph.Qt import QtGui, QtCore
import weakref
from GraphicsObject import GraphicsObject

class UIGraphicsItem(GraphicsObject):
    """Base class for graphics items with boundaries relative to a GraphicsView or ViewBox.
    The purpose of this class is to allow the creation of GraphicsItems which live inside 
    a scalable view, but whose boundaries will always stay fixed relative to the view's boundaries.
    For example: GridItem, InfiniteLine
    
    The view can be specified on initialization or it can be automatically detected when the item is painted.
    """
    
    #sigViewChanged = QtCore.Signal(object)  ## emitted whenever the viewport coords have changed
    
    def __init__(self, bounds=None):
        """
        Initialization Arguments:
            #view: The view box whose bounds will be used as a reference vor this item's bounds
            bounds: QRectF with coordinates relative to view box. The default is QRectF(0,0,1,1),
                    which means the item will have the same bounds as the view.
        """
        GraphicsObject.__init__(self)
        #self.updateView()
        self._connectedView = None
            
        if bounds is None:
            self._bounds = QtCore.QRectF(0, 0, 1, 1)
        else:
            self._bounds = bounds
            
            
        self._boundingRect = None
        #self._viewTransform = self.viewTransform()
        #self.setNewBounds()
        #QtCore.QObject.connect(view, QtCore.SIGNAL('viewChanged'), self.viewChangedEvent)
        
    def paint(self, *args):
        ## check for a new view object every time we paint.
        self.updateView()
    
    def updateView(self):
        ## if we already have a proper bounding rect, return immediately
        if self._boundingRect is not None:
            return
        
        ## check for this item's current viewbox or view widget
        view = self.getViewBox()
        if view is None:
            return
            
        if view is self._connectedView:
            return
            
        ## disconnect from previous view
        if self._connectedView is not None:
            cv = self._connectedView()
            if cv is not None:
                cv.sigRangeChanged.disconnect(self.viewRangeChanged)
            
        ## connect to new view
        view.sigRangeChanged.connect(self.viewRangeChanged)
        self._connectedView = weakref.ref(view)
        self.setNewBounds()
        #self._viewRect = self._view().rect()
            
        #if view is None:
            #view = self.getView()
            #if view is None:  ## definitely no view available yet
                #self._view = None
                #return
            
        #if self._view is not None:
            #self._view.sigRangeChanged.disconnect(self.viewRangeChanged)
            
        #self._view = weakref.ref(view)
        #self._viewRect = self._view().rect()
        #view.sigRangeChanged.connect(self.viewRangeChanged)

        
    def boundingRect(self):
        self.updateView()
        if self._boundingRect is None:
            return QtCore.QRectF()
        return self._boundingRect
        #if self.view() is None:
            #self.bounds = self._bounds
        #else:
            #vr = self._view().rect()
            #tr = self.viewTransform()
            #if vr != self._viewRect or tr != self._viewTransform:
                ##self.viewChangedEvent(vr, self._viewRect)
                #self._viewRect = vr
                #self._viewTransform = tr
                #self.setNewBounds()
        ##print "viewRect", self._viewRect.x(), self._viewRect.y(), self._viewRect.width(), self._viewRect.height()
        ##print "bounds", self.bounds.x(), self.bounds.y(), self.bounds.width(), self.bounds.height()
        #return self.bounds

    def setNewBounds(self):
        #if self.view() is None:
            #self.bounds = QtCore.QRectF()
            #return
        #bounds = QtCore.QRectF(
            #QtCore.QPointF(self._bounds.left()*self._viewRect.width(), self._bounds.top()*self._viewRect.height()),
            #QtCore.QPointF(self._bounds.right()*self._viewRect.width(), self._bounds.bottom()*self._viewRect.height())
        #)
        #bounds.adjust(0.5, 0.5, 0.5, 0.5)
        #self.bounds = self.viewTransform().inverted()[0].mapRect(bounds)
        self._boundingRect = self.viewRect()
        self.prepareGeometryChange()
        self.viewChangedEvent()

    def viewRangeChanged(self):
        """Called when the view widget is resized"""
        self.setNewBounds()
        #self.boundingRect()
        self.update()

    def viewChangedEvent(self):
        """Called whenever the view coordinates have changed."""
        pass

    #def viewTransform(self):
        #"""Returns a matrix that maps viewport coordinates onto scene coordinates"""
        #if self.view() is None:
            #return QtGui.QTransform()
        #else:
            #return self.view().viewportTransform()
        
    #def unitRect(self):
        #return self.viewTransform().inverted()[0].mapRect(QtCore.QRectF(0, 0, 1, 1))

    ## handled by GraphicsObject
    #def view(self):
        #if self._viewWidget is None or self._viewWidget() is None:
            #return None
        #return self._view()
        
    #def viewRect(self):
        #"""Return the viewport widget rect"""
        #v = self.view()
        #if v is None:
            #return QtCore.QRectF()
        #return v.rect()
