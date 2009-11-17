# -*- coding: utf-8 -*-
from GraphicsView import *
from PlotItem import *

class PlotWidget(GraphicsView):
    """Widget implementing a graphicsView with a single PlotItem inside."""
    def __init__(self, parent=None):
        GraphicsView.__init__(self)
        self.enableMouse(False)
        self.plotItem = PlotItem()
        self.setCentralItem(self.plotItem)
        ## Wrap a few methods from plotItem
        for m in ['setXRange', 'setYRange', 'autoRange', 'getLabel', 'getScale', 'showLabel', 'showScale']:
            setattr(self, m, getattr(self.plotItem, m))
        
    def addItem(self, *args):
        self.plotItem.addItem(*args)
        
    def autoRange(self):
        self.plotItem.autoRange()        
