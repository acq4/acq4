from pyqtgraph.Qt import QtGui, QtCore  
from pyqtgraph.GraphicsView import GraphicsScene

class GraphicsWidget(QtGui.QGraphicsWidget):
    def __init__(self, *args, **kargs):
        """
        Extends QGraphicsWidget with a workaround for a PyQt bug. 
        This class is otherwise identical to QGraphicsWidget.
        """
        QtGui.QGraphicsWidget.__init__(self, *args, **kargs)
        GraphicsScene.registerObject(self)  ## workaround for pyqt bug in graphicsscene.items()

    def getMenu(self):
        pass