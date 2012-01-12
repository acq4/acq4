from pyqtgraph.Qt import QtGui, QtCore  
from pyqtgraph.GraphicsScene import GraphicsScene

__all__ = ['GraphicsWidget']
class GraphicsWidget(QtGui.QGraphicsWidget):
    def __init__(self, *args, **kargs):
        """
        Extends QGraphicsWidget with a workaround for a PyQt bug. 
        This class is otherwise identical to QGraphicsWidget.
        """
        QtGui.QGraphicsWidget.__init__(self, *args, **kargs)
        GraphicsScene.registerObject(self)  ## workaround for pyqt bug in graphicsscene.items()

    #def getMenu(self):
        #pass
        
    def setFixedHeight(self, h):
        self.setMaximumHeight(h)
        self.setMinimumHeight(h)

    def setFixedWidth(self, h):
        self.setMaximumWidth(h)
        self.setMinimumWidth(h)
        
    def height(self):
        return self.geometry().height()
    
    def width(self):
        return self.geometry().width()



