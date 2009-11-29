# -*- coding: utf-8 -*-
from GraphicsView import *
from PlotItem import *
import exceptions
from lib.util.WidgetGroup import *

class PlotWidget(GraphicsView):
    """Widget implementing a graphicsView with a single PlotItem inside."""
    def __init__(self, parent=None):
        GraphicsView.__init__(self, parent)
        self.enableMouse(False)
        self.plotItem = PlotItem()
        self.setCentralItem(self.plotItem)
        ## Wrap methods from plotItem
        
    def __getattr__(self, attr):
        if hasattr(self.plotItem, attr):
            m = getattr(self.plotItem, attr)
            if hasattr(m, '__call__'):
                return m
        raise exceptions.NameError(attr)
            
            
        #for m in ['setXRange', 'setYRange', 'autoRange', 'getLabel', 'getScale', 'showLabel', 'setLabel', 'showScale', 'plot', 'addItem', 'autoRange', 'clear', 'registerPlot']:
            #setattr(self, m, getattr(self.plotItem, m))
        
    def widgetGroupInterface(self):
        return (None, PlotWidget.saveState, PlotWidget.restoreState)

    def saveState(self):
        return self.plotItem.saveState()
        
    def restoreState(self, state):
        return self.plotItem.restoreState(state)
        
