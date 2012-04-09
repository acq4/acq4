

from GraphicsObject import *
import pyqtgraph.functions as fn
from pyqtgraph.Qt import QtGui, QtCore


class IsocurveItem(GraphicsObject):
    """
    Item displaying an isocurve of a 2D array.
    
    To align this item correctly with an ImageItem,
    call isocurve.setParentItem(image)
    """
    

    def __init__(self, data=None, level=0, pen='w'):
        GraphicsObject.__init__(self)

        self.level = level
        self.data = None
        self.path = None
        self.setPen(pen)
        self.setData(data, level)
        
        

        #if data is not None and level is not None:
            #self.updateLines(data, level)
            
    
    def setData(self, data, level=None):
        if level is None:
            level = self.level
        self.level = level
        self.data = data
        self.path = None
        self.prepareGeometryChange()
        self.update()
        

    def setLevel(self, level):
        self.level = level
        self.path = None
        self.update()
    

    def setPen(self, *args, **kwargs):
        self.pen = fn.mkPen(*args, **kwargs)
        self.update()

        
    def updateLines(self, data, level):
        ##print "data:", data
        ##print "level", level
        #lines = fn.isocurve(data, level)
        ##print len(lines)
        #self.path = QtGui.QPainterPath()
        #for line in lines:
            #self.path.moveTo(*line[0])
            #self.path.lineTo(*line[1])
        #self.update()
        self.setData(data, level)

    def boundingRect(self):
        if self.path is None:
            return QtCore.QRectF()
        return self.path.boundingRect()
    
    def generatePath(self):
        self.path = QtGui.QPainterPath()
        if self.data is None:
            return
        lines = fn.isocurve(self.data, self.level)
        for line in lines:
            self.path.moveTo(*line[0])
            self.path.lineTo(*line[1])
    
    def paint(self, p, *args):
        if self.path is None:
            self.generatePath()
        p.setPen(self.pen)
        p.drawPath(self.path)
        