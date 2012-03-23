

from GraphicsObject import *
import pyqtgraph.functions as fn
from pyqtgraph.Qt import QtGui


class IsocurveItem(GraphicsObject):
    
    def __init__(self, data=None, level=None, pen='w', parent=None):
        GraphicsObject.__init__(self)
        
        
        self.path = QtGui.QPainterPath()
        self.setPen(pen)
        
        if data is not None and level is not None:
            self.updateLines(data, level)
            
        
            
    def setPen(self, *args, **kwargs):
        self.pen = fn.mkPen(*args, **kwargs)
        self.update()
        
    def updateLines(self, data, level):
        #print "data:", data
        #print "level", level
        lines = fn.isocurve(data, level)
        #print len(lines)
        self.path = QtGui.QPainterPath()
        for line in lines:
            self.path.moveTo(*line[0])
            self.path.lineTo(*line[1])
        self.update()
            

    def boundingRect(self):
        return self.path.boundingRect()
    
    def paint(self, p, *args):
        p.setPen(self.pen)
        p.drawPath(self.path)
        