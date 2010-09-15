# -*- coding: utf-8 -*-

from common import *
import functions
import numpy as np
from pyqtgraph import graphicsItems
import metaarray
import CheckTable
from advancedTypes import OrderedDict

class EventFitter(CtrlNode):
    """Takes a waveform and event list as input, returns extra information about each event.
    Optionally performs an exponential reconvolution before measuring each event.
    Plots fits of reconstructed events if the plot output is connected."""
    nodeName = "EventFitter"
    uiTemplate = [
        ('plotFits', 'check', {'value': True}),
        ('plotEvents', 'check', {'value': True}),
    ]
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'waveform': {'io': 'in'},
            'events': {'io': 'in'},
            'output': {'io': 'out'},
            'plot':  {'io': 'out'}
        })
        self.plotItems = []
        
    def process(self, waveform, events, display=True):
        #self.events = []
        tau = waveform.infoCopy(-1).get('expDeconvolveTau', None)
        nFields = len(events.dtype.fields)
        
        dtype = [(n, events[n].dtype) for n in events.dtype.names]
        
        output = np.empty(len(events), dtype=dtype + [('fitAmplitude', float), ('fitXOffset', float), ('fitRiseTau', float), ('fitDecayTau', float), ('fitError', float)])
        #output[:][:nFields] = events
        
        #for item, plot in self.plotItems:
            #plot.removeItem(item)
        self.plotItems = []
        
        for i in range(len(events)):
            start = events[i]['time']
            sliceLen = 50e-3
            if i+1 < len(events):
                nextStart = events[i+1]['time']
                if nextStart-start < sliceLen:
                    sliceLen = nextStart-start
            
            eventData = waveform['Time':start:start+sliceLen]
            times = eventData.xvals(0)
            if tau is not None:
                eventData = functions.expReconvolve(eventData, tau=tau)

            ## fitting to exponential rise * decay
            ## parameters are [amplitude, x-offset, rise tau, fall tau]
            mx = eventData.max()
            mn = eventData.min()
            if mx > -mn:
                amp = mx
            else:
                amp = mn
            guess = [amp, times[0], 0.01, 0.01]
            fit, junk, comp, err = functions.fitPsp(times, eventData.view(np.ndarray), guess, measureError=True)
            #print fit
            #self.events.append(eventData)
            output[i] = tuple(events[i]) + tuple(fit) + (err,)
            
            if display and self.plot.isConnected():
                if self.ctrls['plotFits'].isChecked():
                    item = graphicsItems.PlotCurveItem(comp, times, pen=QtGui.QPen(QtGui.QColor(0, 0, 255)))
                    self.plotItems.append(item)
                if self.ctrls['plotEvents'].isChecked():
                    item2 = graphicsItems.PlotCurveItem(eventData, times, pen=QtGui.QPen(QtGui.QColor(0, 255, 0)))
                    self.plotItems.append(item2)
                #plot = self.plot.connections().keys()[0].node().getPlot()
                #plot.addItem(item)
            
        return {'output': output, 'plot': self.plotItems}
            
            
            
class Histogram(CtrlNode):
    """Converts a list of values into a histogram."""
    nodeName = 'Histogram'
    uiTemplate = [
        ('numBins', 'intSpin', {'value': 100, 'min': 3, 'max': 100000})
    ]
    
    def processData(self, In):
        data = In.view(np.ndarray)
        units = None
        if isinstance(In, metaarray.MetaArray):
            units = In.axisUnits(1)
        y,x = np.histogram(data, bins=self.ctrls['numBins'].value())
        x = (x[1:] + x[:-1]) * 0.5
        return metaarray.MetaArray(y, info=[{'name': 'bins', 'values': x, 'units': units}])
        
        
        
class StatsCalculator(Node):
    """Calculates avg, sum, median, min, max, and stdev from input."""
    nodeName = "StatsCalculator"
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={
            'data': {'io': 'in'},
            'regions': {'io': 'in', 'multi': True},
            'stats': {'io': 'out'}
        })
        self.funcs = OrderedDict([
            ('sum', np.sum),
            ('avg', np.mean),
            ('med', np.median),
            ('min', np.min),
            ('max', np.max),
            ('std', np.std)
        ])
        
        self.ui = CheckTable.CheckTable(self.funcs.keys())
        QtCore.QObject.connect(self.ui, QtCore.SIGNAL('stateChanged'), self.update)
        
    def ctrlWidget(self):
        return self.ui
        
    def process(self, data, regions=None, display=True):
        self.ui.updateRows(data.dtype.fields.keys())
        state = self.ui.saveState()
        stats = OrderedDict()
        cols = state['cols']
        for row in state['rows']:
            name = row[0]
            flags = row[1:]
            v = data[name]
            for i in range(len(flags)):
                if flags[i]:
                    fn = self.funcs[cols[i]]
                    if len(v) > 0:
                        result = fn(v)
                    else:
                        result = 0
                    stats[name+'.'+cols[i]] = result
        return {'stats': stats}
        
    def saveState(self):
        state = Node.saveState(self)
        state['ui'] = self.ui.saveState()
        return state
        
    def restoreState(self, state):
        Node.restoreState(self, state)
        self.ui.restoreState(state['ui'])