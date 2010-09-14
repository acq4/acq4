# -*- coding: utf-8 -*-
from ..Node import Node
import weakref
from pyqtgraph import graphicsItems
from PyQt4 import QtCore, QtGui

class PlotWidgetNode(Node):
    """Connection to PlotWidget. Will plot arrays, metaarrays, and display event lists."""
    nodeName = 'PlotWidget'
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={'In': {'io': 'in', 'multi': True}})
        self.plot = None
        self.items = {}
        
    def disconnected(self, localTerm, remoteTerm):
        if localTerm is self.In and remoteTerm in self.items:
            self.plot.removeItem(self.items[remoteTerm])
            del self.items[remoteTerm]
        
    def setPlot(self, plot):
        #print "======set plot"
        self.plot = plot
        
    def getPlot(self):
        return self.plot
        
    def process(self, In, display=True):
        if display:
            #self.plot.clearPlots()
            items = set()
            for name, vals in In.iteritems():
                if vals is None:
                    continue
                if type(vals) is not list:
                    vals = [vals]
                    
                for val in vals:
                    vid = id(val)
                    if vid in self.items:
                        items.add(vid)
                    else:
                        if isinstance(val, graphicsItems.PlotCurveItem):
                            self.plot.addCurve(val)
                            item = val
                        if isinstance(val, QtGui.QGraphicsItem):
                            self.plot.addItem(val)
                            item = val
                        else:
                            item = self.plot.plot(val)
                        self.items[vid] = item
                        items.add(vid)
            for vid in self.items.keys():
                if vid not in items:
                    self.plot.removeItem(self.items[vid])
                    del self.items[vid]
            
    #def setInput(self, **args):
        #for k in args:
            #self.plot.plot(args[k])
    

class EventListPlotter(Node):
    """Prepares an event list for display in a PlotWidget."""
    nodeName = 'EventListPlotter'
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={
            'events': {'io': 'in'}, 
            'plot': {'io': 'out', 'multi': True}
        })
        self.items = {}
        
    def process(self, events, display=True):
        conn = self['plot'].connections()
        if len(events) > 200:
            events = events[:200]
        for c in conn:
            plot = c.node().getPlot()
            if plot is None:
                continue
            if c in self.items:
                item = self.items[c]
                item.setXVals(events)
            else:
                self.items[c] = graphicsItems.VTickGroup(events, view=plot)
                self.items[c].setYRange([0., 0.2], relative=True)
        return {'plot': self.items}
        
