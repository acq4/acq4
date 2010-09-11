# -*- coding: utf-8 -*-
from Node import *
    
class PlotWidgetNode(Node):
    """Connection to PlotWidget. Will plot arrays, metaarrays, and display event lists."""
    nodeName = 'PlotWidget'
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={'In': {'io': 'in', 'multi': True}})
        self.plot = None
        
        
    def setPlot(self, plot):
        #print "======set plot"
        self.plot = plot
        
    def process(self, In, display=True):
        if display:
            self.plot.clear()
            for k, v in In.iteritems():
                if v is None:
                    continue
                self.plot.plot(v)
            
    def setInput(self, **args):
        for k in args:
            self.plot.plot(args[k])
    
