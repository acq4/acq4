# -*- coding: utf-8 -*-

from ..Node import Node
import functions
from common import *
import pyqtgraph as pg

class Threshold(CtrlNode):
    """Absolute threshold detection filter. Returns indexes where data crosses threshold."""
    nodeName = 'ThresholdDetect'
    uiTemplate = [
        ('direction', 'combo', {'values': ['rising', 'falling'], 'index': 0}),
        ('threshold', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'dec': True, 'range': [None, None], 'siPrefix': True}),
    ]
    
    def __init__(self, name, **opts):
        CtrlNode.__init__(self, name, self.uiTemplate)
        
    def processData(self, data):
        s = self.stateGroup.state()
        if s['direction'] == 'rising':
            d = 1
        else:
            d = -1
        return functions.threshold(data, s['threshold'], d)

class StdevThreshold(CtrlNode):
    """Relative threshold event detection. Finds regions in data greater than threshold*stdev.
    Returns a record array with columns: index, length, sum, peak.
    This function is only useful for data with its baseline removed."""
    
    nodeName = 'StdevThreshold'
    uiTemplate = [
        ('threshold', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
    ]
    
    def __init__(self, name, **opts):
        CtrlNode.__init__(self, name, self.uiTemplate)
        
    def processData(self, data):
        s = self.stateGroup.state()
        return functions.stdevThresholdEvents(data, s['threshold'])


class ZeroCrossingEvents(CtrlNode):
    """Detects events in a waveform by splitting the data up into chunks separated by zero-crossings, 
    then keeping only the ones that meet certain criteria."""
    nodeName = 'ZeroCrossing'
    uiTemplate = [
        ('minLength', 'intSpin', {'value': 0, 'min': 0, 'max': 100000}),
        ('minSum', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
        ('minPeak', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
        ('eventLimit', 'intSpin', {'value': 400, 'min': 1, 'max': 1e9}),
    ]
    
    def __init__(self, name, **opts):
        CtrlNode.__init__(self, name, self.uiTemplate)
        
    def processData(self, data):
        s = self.stateGroup.state()
        events = functions.zeroCrossingEvents(data, minLength=s['minLength'], minPeak=s['minPeak'], minSum=s['minSum'])
        events = events[:s['eventLimit']]
        return events

class ThresholdEvents(CtrlNode):
    """Detects regions of a waveform that cross a threshold (positive or negative) and returns the time, length, sum, and peak of each event."""
    nodeName = 'ThresholdEvents'
    uiTemplate = [
        ('threshold', 'spin', {'value': 1e-12, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
        ('adjustTimes', 'check', {'value': True}),
        ('minLength', 'intSpin', {'value': 0, 'min': 0, 'max': 1e9}),
        ('minSum', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
        ('minPeak', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
        ('eventLimit', 'intSpin', {'value': 100, 'min': 1, 'max': 1e9}),
        ('deadTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [0,None], 'siPrefix': True, 'suffix': 's'}),
    ]

    def __init__(self, name, **opts):
        CtrlNode.__init__(self, name, self.uiTemplate)
        #self.addOutput('plot')
        #self.remotePlot = None
        
    #def connected(self, term, remote):
        #CtrlNode.connected(self, term, remote)
        #if term is not self.plot:
            #return
        #node = remote.node()
        #node.sigPlotChanged.connect(self.connectToPlot)
        #self.connectToPlot(node)

    #def connectToPlot(self, node):
        #if self.remotePlot is not None:
            #self.remotePlot = None
            
        #if node.plot is None:
            #return
        #plot = self.plot.
            
    #def disconnected(self, term, remote):
        #CtrlNode.disconnected(self, term, remote)
        #if term is not self.plot:
            #return
        #remote.node().sigPlotChanged.disconnect(self.connectToPlot)
        #self.disconnectFromPlot()

    #def disconnectFromPlot(self):
        #if self.remotePlot is None:
            #return
        #for l in self.lines:
            #l.scene().removeItem(l)
        #self.lines = []

    def processData(self, data):
        s = self.stateGroup.state()
        events = functions.thresholdEvents(data, s['threshold'], s['adjustTimes'])
        
        ## apply first round of filters
        mask = events['len'] >= s['minLength']
        mask *= abs(events['sum']) >= s['minSum']
        mask *= abs(events['peak']) >= s['minPeak']
        events = events[mask]
        
        ## apply deadtime filter
        mask = np.ones(len(events), dtype=bool)
        last = 0
        dt = s['deadTime']
        for i in xrange(1, len(events)):
            if events[i]['time'] - events[last]['time'] < dt:
                mask[i] = False
            else:
                last = i
        #mask[1:] *= (events[1:]['time']-events[:-1]['time']) >= s['deadTime']
        events = events[mask]
        
        ## limit number of events
        events = events[:s['eventLimit']]
        return events

        
class EventFilter(CtrlNode):
    """Selects events from a list based on various criteria"""
    nodeName = "EventFilter"
    uiTemplate = [
        #('minLength', 'intSpin', {'value': 0, 'min': 0, 'max': 1e9}),
        #('minSum', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
        #('minPeak', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'range': [None, None], 'siPrefix': True}),
        #('eventLimit', 'intSpin', {'value': 100, 'min': 1, 'max': 1e9}),
        #('deadTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [0,None], 'siPrefix': True, 'suffix': 's'}),
        ('fitAmplitude', 'check', {'value': False}),
        ('minFitAmp', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('maxFitAmp', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('fitDecayTau', 'check', {'value': False}),
        ('minFitDecayTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('maxFitDecayTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('fitRiseTau', 'check', {'value': False}),
        ('minFitRiseTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('maxFitRiseTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('fitError', 'check', {'value': False}),
        ('minFitError', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('maxFitError', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('fitTime', 'check', {'value': False}),
        ('minFitTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('maxFitTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('region', 'combo', {'values': ['all']}),
    ]
    
    ranges = [
        ('fitAmplitude', 'minFitAmp', 'maxFitAmp'),
        ('fitDecayTau', 'minFitDecayTau', 'maxFitDecayTau'),
        ('fitRiseTau', 'minFitRiseTau', 'maxFitRiseTau'),
        ('fitError', 'minFitError', 'maxFitError'),
        ('fitTime', 'minFitTime', 'maxFitTime'),
    ]

    def __init__(self, *args, **kargs):
        CtrlNode.__init__(self, *args, **kargs)
        
        for check, spin1, spin2 in self.ranges:
            self.ctrls[check].toggled.connect(self.checkToggled)

    def checkToggled(self):
        #s = self.stateGroup.state()
        for name, a, b in self.ranges:
            
            if self.ctrls[name].isChecked():
                self.showRow(a)
                self.showRow(b)
            else:
                self.hideRow(a)
                self.hideRow(b)
        

    def processData(self, data):
        s = self.stateGroup.state()
        mask = np.ones(len(data), dtype=bool)
            
        for b, mn, mx in self.ranges:
            if s[b]:
                mask *= data[b] < s[mx]
                mask *= data[b] > s[mn]
                
        region = s['region']
        if region != 'all':
            mask *= data['region'] == region
            
        return data[mask]
            
            

class SpikeDetector(CtrlNode):
    """Very simple spike detector. Returns the indexes of sharp spikes by comparing each sample to its neighbors."""
    nodeName = "SpikeDetect"
    uiTemplate = [
        ('radius', 'intSpin', {'value': 1, 'min': 1, 'max': 100000}),
        ('minDiff', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'dec': True, 'siPrefix': True}),
    ]

    def __init__(self, name, **opts):
        CtrlNode.__init__(self, name, self.uiTemplate)
        
    def processData(self, data):
        s = self.stateGroup.state()
        radius = s['radius']
        d1 = data.view(np.ndarray)
        d2 = data[radius:] - data[:-radius] #a derivative
        mask1 = d2 > s['minDiff']  #where derivative is large and positive
        mask2 = d2 < -s['minDiff'] #where derivative is large and negative
        maskpos = mask1[:-radius] * mask2[radius:] #both need to be true
        maskneg = mask1[radius:] * mask2[:-radius]
        mask = maskpos + maskneg  ## All regions that match criteria
        
        ## now reduce consecutive hits to a single hit.
        hits = (mask[1:] - mask[:-1]) > 0
        sHits = np.argwhere(hits)[:,0]+(radius+2)
        
        ## convert to record array with 'index' column
        ret = np.empty(len(sHits), dtype=[('index', int), ('time', float)])
        ret['index'] = sHits
        ret['time'] = data.xvals('Time')[sHits]
        return ret

    def processBypassed(self, args):
        return {'Out': np.empty(0, dtype=[('index', int), ('time', float)])}
    
    
    
    
    
    