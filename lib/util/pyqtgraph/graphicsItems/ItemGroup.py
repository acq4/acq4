from pyqtgraph.Qt import QtGui, QtCore

__all__ = ['ItemGroup']
class ItemGroup(QtGui.QGraphicsItem):
    """
    Replacement for QGraphicsItemGroup
    """
    ## Should probably just use QGraphicsGroupItem and instruct it to pass events on to children..
    
    def __init__(self, *args):
        QtGui.QGraphicsItem.__init__(self, *args)
        if hasattr(self, "ItemHasNoContents"):
            self.setFlag(self.ItemHasNoContents)
    
    def boundingRect(self):
        return QtCore.QRectF()
        
    def paint(self, *args):
        pass
    
    def addItem(self, item):
        item.setParentItem(self)

