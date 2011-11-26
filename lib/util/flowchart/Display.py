# -*- coding: utf-8 -*-
from pyqtgraph.flowchart.Node import Node
import weakref
from pyqtgraph import graphicsItems
from PyQt4 import QtCore, QtGui
from pyqtgraph.flowchart.library.common import *
import numpy as np

class EventListPlotter(CtrlNode):
    """Prepares an event list for display in a PlotWidget."""
    nodeName = 'EventListPlotter'
    uiTemplate = [
        ('color', 'color'),
    ]
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'events': {'io': 'in'}, 
            'plot': {'io': 'out', 'multi': True}
        }, ui=self.uiTemplate)
        self.items = {}
        self.ctrls['color'].sigColorChanged.connect(self.colorChanged)
        
    def colorChanged(self):
        c = self.ctrls['color'].color()
        for i in self.items.itervalues():
            i.setPen(c)
        
    def process(self, events, display=True):
        if not display:
            return {'plot': None}
        conn = self['plot'].connections()
        if len(events) > 200:
            events = events[:200]
        color = self.ctrls['color'].color()
        
        ## don't keep items from last run; they may have been removed already.
        self.items = {}
        
        for c in conn:
            plot = c.node().getPlot()
            if plot is None:
                continue
            ## It's possible items were cleared out already; always rebuild.
            #if c in self.items:
                #item = self.items[c]
                #item.setXVals(events)  
            #else:
                #self.items[c] = graphicsItems.VTickGroup(events, view=plot, pen=color)
                #self.items[c].setYRange([0., 0.2], relative=True)
            self.items[c] = graphicsItems.VTickGroup(events, view=plot, pen=color)
            self.items[c].setYRange([0., 0.2], relative=True)
        return {'plot': self.items}


    