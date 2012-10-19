from .GraphicsWidget import GraphicsWidget
from .LabelItem import LabelItem
from ..Qt import QtGui, QtCore
from .. import functions as fn

__all__ = ['LegendItem']

class LegendItem(GraphicsWidget):
    def __init__(self, size, offset):
        GraphicsWidget.__init__(self)
        self.setFlag(self.ItemIgnoresTransformations)
        self.layout = QtGui.QGraphicsGridLayout()
        self.setLayout(self.layout)
        self.items = []
        self.size = size
        self.offset = offset
        self.setGeometry(QtCore.QRectF(self.offset[0], self.offset[1], self.size[0], self.size[1]))
        
    def addItem(self, item, title):
        label = LabelItem(title)
        sample = ItemSample(item)
        row = len(self.items)
        self.items.append((sample, label))
        self.layout.addItem(sample, row, 0)
        self.layout.addItem(label, row, 1)
        
    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.size[0], self.size[1])
        
    def paint(self, p, *args):
        p.setPen(fn.mkPen(255,255,255,100))
        p.setBrush(fn.mkBrush(100,100,100,50))
        p.drawRect(self.boundingRect())
        
        
class ItemSample(GraphicsWidget):
    def __init__(self, item):
        GraphicsWidget.__init__(self)
        self.item = item
    
    def boundingRect(self):
        return QtCore.QRectF(0, 0, 20, 20)
        
    def paint(self, p, *args):
        p.setPen(fn.mkPen(self.item.opts['pen']))
        p.drawLine(2, 18, 18, 2)
        
        
        