# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.pyqtgraph.flowchart.library.common import *
from acq4.pyqtgraph.graphicsItems.InfiniteLine import InfiniteLine
import numpy as np
import acq4.util.functions as functions
from six.moves import range

class Threshold(CtrlNode):
    """Absolute threshold detection filter. Returns indexes where data crosses threshold."""
    nodeName = 'ThresholdDetect'
    uiTemplate = [
        ('direction', 'combo', {'values': ['rising', 'falling'], 'index': 0}),
        ('threshold', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'dec': True, 'bounds': [None, None], 'siPrefix': True}),
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
        ('threshold', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'bounds': [None, None], 'siPrefix': True}),
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
        ('minSum', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'bounds': [None, None], 'siPrefix': True}),
        ('minPeak', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'bounds': [None, None], 'siPrefix': True}),
        ('eventLimit', 'intSpin', {'value': 400, 'min': 1, 'max': 1e9}),
    ]
    
    def __init__(self, name, **opts):
        CtrlNode.__init__(self, name, self.uiTemplate)
        
    def processData(self, data):
        s = self.stateGroup.state()
        events = functions.zeroCrossingEvents(data, minLength=s['minLength'], minPeak=s['minPeak'], minSum=s['minSum'])
        events = events[:s['eventLimit']]
        return events

class ThresholdEvents(PlottingCtrlNode):
    """Detects regions of a waveform that cross a threshold (positive or negative) and returns the time, length, sum, and peak of each event."""
    nodeName = 'ThresholdEvents'
    uiTemplate = [
        ('baseline', 'spin', {'value':0, 'step':1, 'minStep': 0.1, 'dec': True, 'bounds': [None, None], 'siPrefix': True, 'tip': 'Blue line -- Set the baseline to measure the minPeak and threshold from'}),
        ('minPeak', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'bounds': [None, None], 'siPrefix': True, 'tip': 'Yellow line -- Events must reach this far from baseline to be detected.'}),
        ('threshold', 'spin', {'value': 1e-12, 'step': 1, 'minStep': 0.1, 'dec': True, 'bounds': [None, None], 'siPrefix': True, 'tip': 'Green line -- Events are detected only if they cross this threshold (distance from baseline).'}),
        ('display', 'check', {'value':True, 'tip':'If checked display dragable lines for baseline, minPeak and threshold'}),
        #('index', 'combo', {'values':['start','peak'], 'index':0}), 
        ('minLength', 'intSpin', {'value': 0, 'min': 0, 'max': 1e9, 'tip': 'Events must contain this many samples to be detected.'}),
        ('minSum', 'spin', {'value': 0, 'step': 1, 'minStep': 0.1, 'dec': True, 'bounds': [None, None], 'siPrefix': True}),
        ('eventLimit', 'intSpin', {'value': 100, 'min': 1, 'max': 1e9, 'tip': 'Limits the number of events that may be detected in a single trace. This prevents runaway processes due to over-sensitive detection criteria.'}),
        ('deadTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [0,None], 'siPrefix': True, 'suffix': 's', 'tip': 'Ignore events that occur too quickly following another event.'}),
        ('adjustTimes', 'check', {'value': True, 'tip': 'If False, then event times are reported where the trace crosses threshold. If True, the event time is adjusted to estimate when the trace would have crossed 0.'}),
        ('reverseTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [0,None], 'siPrefix': True, 'suffix': 's', 'tip': 'Ignore events that 1) have the opposite sign of the event immediately prior and 2) occur within the given time window after the prior event. This is useful for ignoring rebound signals.'}),
    ]

    def __init__(self, name, **opts):
        PlottingCtrlNode.__init__(self, name, self.uiTemplate)
        #self.plotTerminal = self.addOutput('plot', optional=True)
        self.baseLine = InfiniteLine(angle=0, movable=True, pen='b')
        self.minPeakLine = InfiniteLine(angle=0, movable=True, pen='y')
        self.thresholdLine = InfiniteLine(angle=0, movable=True, pen='g')
        self.lines = [self.baseLine, self.minPeakLine, self.thresholdLine]
        
        self.ctrls['display'].toggled.connect(self.displayToggled)
        self.ctrls['baseline'].sigValueChanged.connect(self.adjustBaseLine)
        self.ctrls['threshold'].sigValueChanged.connect(self.adjustThresholdLine)
        self.ctrls['minPeak'].sigValueChanged.connect(self.adjustPeakLine)
        for line in self.lines:
            line.sigPositionChangeFinished.connect(self.updateCtrlValues)
        #self.remotePlot = None
        
    def restoreState(self, state):
        CtrlNode.restoreState(self, state)
        for c in self.plotTerminal.connections():
            #print c
            p = c.node().getPlot()
            for l in self.lines:
                p.addItem(l)
        self.baseLine.setPos(self.ctrls['baseline'].value())
        self.minPeakLine.setPos(self.ctrls['minPeak'].value())
        self.thresholdLine.setPos(self.ctrls['threshold'].value())
        
    def displayToggled(self):
        b = self.ctrls['display'].isChecked()
        for item in self.lines:
            item.setVisible(b)
    
    def adjustBaseLine(self, sb):
        #print "vlaue:", value
        self.baseLine.setValue(sb.value())
        
    def adjustThresholdLine(self, sb):
        self.thresholdLine.setValue(sb.value()+self.baseLine.value())
        
    def adjustPeakLine(self, sb):
        self.minPeakLine.setValue(sb.value()+self.baseLine.value())
            
    def updateCtrlValues(self, line):
        self.ctrls['baseline'].setValue(self.baseLine.value())
        self.ctrls['minPeak'].setValue(self.minPeakLine.value()-self.baseLine.value())
        self.ctrls['threshold'].setValue(self.thresholdLine.value()-self.baseLine.value())
            
    #def connected(self, term, remote):
        #CtrlNode.connected(self, term, remote)
        #if term is not self.plot:
            #return
        #node = remote.node()
        #node.sigPlotChanged.connect(self.connectToPlot)
        #self.connectToPlot(node)

    def connectToPlot(self, node):
        #if self.remotePlot is not None:
        #    self.remotePlot = None
            
        if node.plot is None:
            return
        for l in self.lines:
            node.getPlot().addItem(l)
            
    #def disconnected(self, term, remote):
        #CtrlNode.disconnected(self, term, remote)
        #if term is not self.plot:
            #return
        #remote.node().sigPlotChanged.disconnect(self.connectToPlot)
        #self.disconnectFromPlot(remote.node().getPlot())

    def disconnectFromPlot(self, plot):
        #if self.remotePlot is None:
        #    return
        for l in self.lines:
            plot.removeItem(l)

    def processData(self, data):
        s = self.stateGroup.state()
        #print "==== Threshold Events ====="
        #print "   baseline:", s['baseline']
        events = functions.thresholdEvents(data, s['threshold'], s['adjustTimes'], baseline=s['baseline'])
        
        ## apply first round of filters
        mask = events['len'] >= s['minLength']
        mask *= abs(events['sum']) >= s['minSum']
        mask *= abs(events['peak']) >= abs(s['minPeak'])
        events = events[mask]
        
        ## apply deadtime filter
        mask = np.ones(len(events), dtype=bool)
        last = 0
        dt = s['deadTime']
        rt = s['reverseTime']
        for i in range(1, len(events)):
            tdiff = events[i]['time'] - events[last]['time']
            if tdiff < dt:  ## check dead time
                mask[i] = False
            elif tdiff < rt and (events[i]['peak'] * events[last]['peak'] < 0):  ## check reverse time
                mask[i] = False
            else:
                last = i
        #mask[1:] *= (events[1:]['time']-events[:-1]['time']) >= s['deadTime']
        events = events[mask]
        
        ## limit number of events
        events = events[:s['eventLimit']]
        return events

        
            
            

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
        d2 = d1[radius:] - d1[:-radius] #a derivative
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
        ('minFitAmp', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'bounds': [None,None], 'siPrefix': True, 'hidden': True}),
        ('maxFitAmp', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'bounds': [None,None], 'siPrefix': True, 'hidden': True}),
        ('fitDecayTau', 'check', {'value': False}),
        ('minFitDecayTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('maxFitDecayTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('fitRiseTau', 'check', {'value': False}),
        ('minFitRiseTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('maxFitRiseTau', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('fitFractionalError', 'check', {'value': False}),
        ('minFitFractionalError', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'bounds': [None,None], 'siPrefix': True, 'hidden': True}),
        ('maxFitFractionalError', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'bounds': [None,None], 'siPrefix': True, 'hidden': True}),
        ('fitLengthOverDecay', 'check', {'value': False}),
        ('minFitLengthOverDecay', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'bounds': [None,None], 'siPrefix': True, 'hidden': True}),
        ('maxFitLengthOverDecay', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'bounds': [None,None], 'siPrefix': True, 'hidden': True}),
        ('fitTime', 'check', {'value': False}),
        ('minFitTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('maxFitTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'bounds': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('region', 'combo', {'values': ['all']}),
    ]
    
    ranges = [
        ('fitAmplitude', 'minFitAmp', 'maxFitAmp'),
        ('fitDecayTau', 'minFitDecayTau', 'maxFitDecayTau'),
        ('fitRiseTau', 'minFitRiseTau', 'maxFitRiseTau'),
        ('fitFractionalError', 'minFitFractionalError', 'maxFitFractionalError'),
        ('fitLengthOverDecay', 'minFitLengthOverDecay', 'maxFitLengthOverDecay'),
        ('fitTime', 'minFitTime', 'maxFitTime'),
    ]

    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'events': {'io': 'in'},
            'regions': {'io': 'in'},
            'output': {'io': 'out', 'bypass': 'events'}})
        
        for check, spin1, spin2 in self.ranges:
            self.ctrls[check].toggled.connect(self.checkToggled)
        #self.updateRegions()
        
    def updateRegions(self, regions):
        regCombo = self.ctrls['region']
        
        ### first check length of comboLists and update if they do not match -- avoids index errors in check of individual items below
        if regCombo.count() != len(regions):
            regCombo.clear()
            regCombo.addItems(regions)
            return
        
        ### check individual items in the list
        test = []
        for i in range(regCombo.count()):
            test.append(regCombo.itemText(i) == regions[i])
        if False not in test:
            return
        else:  
            regCombo.clear()
            regCombo.addItems(regions)
            return
    
    def updateUi(self):
        pass
    
    

    def checkToggled(self):
        #s = self.stateGroup.state()
        for name, a, b in self.ranges:
            
            if self.ctrls[name].isChecked():
                self.showRow(a)
                self.showRow(b)
            else:
                self.hideRow(a)
                self.hideRow(b)
            

    def process(self, events, regions=None, display=True):
        s = self.stateGroup.state()
        data=events
        mask = np.ones(len(data), dtype=bool)

            
        if display:
            newReg = ['all']
            if regions is None:
                regions = {}
            for r in regions.keys():
                newReg.append(r.node().name())
            self.updateRegions(newReg)
            
            
        for b, mn, mx in self.ranges:
            if s[b]:
                try:
                    mask *= data[b] < s[mx]
                    mask *= data[b] > s[mn]
                except ValueError:  ## If the data doesn't have this key, don't fret; just ignore it.
                    pass
        #print "  filter 1:", mask.sum()  
        region = s['region']
        if region != 'all':
            mask *= data['region'] == region
        #print "  filter 2:", mask.sum(), region
        #print "  filter 3:", len(data[mask])
        return {'output':data[mask]}
