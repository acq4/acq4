from pyqtgraph.Qt import QtGui, QtCore
import weakref
from GraphicsObject import GraphicsObject

class UIGraphicsItem(GraphicsObject):
    """Base class for graphics items with boundaries relative to a GraphicsView or ViewBox.
    The purpose of this class is to allow the creation of GraphicsItems which live inside 
    a scalable view, but whose boundaries will always stay fixed relative to the view's boundaries.
    For example: GridItem, InfiniteLine
    
    The view can be specified on initialization or it can be automatically detected when the item is painted.
    
    NOTE: Only the item's boundingRect is affected; the item is not transformed in any way. Use viewRangeChanged
    to respond to changes in the view.
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
        self._connectedView = None
            
        if bounds is None:
            self._bounds = QtCore.QRectF(0, 0, 1, 1)
        else:
            self._bounds = bounds
            
        self._boundingRect = None
        
    def paint(self, *args):
        ## check for a new view object every time we paint.
        self.updateView()
    
    def updateView(self):
        ## called to see whether this item has a new view to connect to
        
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
        
    def boundingRect(self):
        self.updateView()
        if self._boundingRect is None:
            return QtCore.QRectF()
        return QtCore.QRectF(self._boundingRect)

    def setNewBounds(self):
        """Update the item's bounding rect to match the viewport"""
        self._boundingRect = self.viewRect()
        #print "\nnew bounds:", self, self._boundingRect
        self.prepareGeometryChange()
        self.viewChangedEvent()

    def viewRangeChanged(self):
        """Called when the view widget/viewbox is resized/rescaled"""
        self.setNewBounds()
        self.update()
        

    def viewChangedEvent(self):
        """Called whenever the view coordinates have changed."""
        pass


    def setPos(self, *args):
        GraphicsObject.setPos(self, *args)
        self.setNewBounds()