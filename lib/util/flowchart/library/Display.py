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
        self.items = weakref.WeakKeyDictionary()
        
    def setPlot(self, plot):
        #print "======set plot"
        self.plot = plot
        
    def process(self, In, display=True):
        if display:
            self.plot.clear()
            for k, v in In.iteritems():
                if v is None:
                    continue
                if isinstance(v, QtGui.QGraphicsItem):
                    self.items[k] = v
                    self.plot.addItem(v)
                else:
                    self.items[k] = self.plot.plot(v)
            
    def setInput(self, **args):
        for k in args:
            self.plot.plot(args[k])
    

class EventListPlotter(Node):
    """Prepares an event list for display in a PlotWidget."""
    nodeName = 'EventListPlotter'
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={
            'events': {'io': 'in'}, 
            'plot': {'io': 'out'}
        })
        
    def process(self, events, display=True):
        conn = self['plot'].connections()
        if len(conn) == 0:
            return
        plot = conn.keys()[0].node().plot
        
        if len(events) > 200:
            events = events[:200]
        self.item = graphicsItems.VTickGroup(events, view=plot)
        self.item.setYRange([0.8, 1.0], relative=True)
        return {'plot': self.item}
        