# -*- coding: utf-8 -*-
from GraphicsView import *
from MultiPlotItem import *
import exceptions

class MultiPlotWidget(GraphicsView):
    """Widget implementing a graphicsView with a single PlotItem inside."""
    def __init__(self, parent=None):
        GraphicsView.__init__(self, parent)
        self.enableMouse(False)
        self.mPlotItem = MultiPlotItem()
        self.setCentralItem(self.mPlotItem)
        ## Explicitly wrap methods from mPlotItem
        #for m in ['setData']:
            #setattr(self, m, getattr(self.mPlotItem, m))
                
    def __getattr__(self, attr):  ## implicitly wrap methods from plotItem
        if hasattr(self.mPlotItem, attr):
            m = getattr(self.mPlotItem, attr)
            if hasattr(m, '__call__'):
                return m
        raise exceptions.NameError(attr)

    def widgetGroupInterface(self):
        return (None, MultiPlotWidget.saveState, MultiPlotWidget.restoreState)

    def saveState(self):
        return {}
        #return self.plotItem.saveState()
        
    def restoreState(self, state):
        pass
        #return self.plotItem.restoreState(state)
