# -*- coding: utf-8 -*-
from ..Node import Node
import weakref
from pyqtgraph import graphicsItems
from PyQt4 import QtCore, QtGui
from common import *

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
        if not display:
            return {'plot': None}
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
        

class ScatterPlot(CtrlNode):
    """Generates a scatter plot from a record array or nested dicts"""
    nodeName = 'ScatterPlot'
    uiTemplate = [
        ('x', 'combo', {'values': [], 'index': 0}),
        ('y', 'combo', {'values': [], 'index': 0})
    ]
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'input': {'io': 'in'},
            'plot': {'io': 'out'}
        })
        self.item = graphicsItems.ScatterPlotItem()
        self.keys = []
        
        #self.ui = QtGui.QWidget()
        #self.layout = QtGui.QGridLayout()
        #self.ui.setLayout(self.layout)
        
        #self.xCombo = QtGui.QComboBox()
        #self.yCombo = QtGui.QComboBox()
        
        
    
    def process(self, input, display=True):
        if not display:
            return {'plot': None}
            
        self.updateKeys(input[0])
        
        x = str(self.ctrls['x'].currentText())
        y = str(self.ctrls['y'].currentText())
        points = [{'pos': (i[x], i[y])} for i in input]
        self.item.setPoints(points)
        
        return {'plot': self.item}
        
        

    def updateKeys(self, data):
        self.ctrls['x'].blockSignals(True)
        self.ctrls['y'].blockSignals(True)
        for c in [self.ctrls['x'], self.ctrls['y']]:
            cur = str(c.currentText())
            c.clear()
            for k in data:
                c.addItem(k)
                if k == cur:
                    c.setCurrentIndex(c.count()-1)
        self.ctrls['x'].blockSignals(False)
        self.ctrls['y'].blockSignals(False)
                
        self.keys = [x for x in data]  ## data might be a list of strings or a dict
        

    def saveState(self):
        state = CtrlNode.saveState(self)
        return {'keys': self.keys, 'ctrls': state}
        
    def restoreState(self, state):
        self.updateKeys(state['keys'])
        CtrlNode.restoreState(state['ctrls'])
        
    