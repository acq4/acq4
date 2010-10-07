# -*- coding: utf-8 -*-

from ..Node import Node
import functions
from common import *

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
    ]
    
    def __init__(self, name, **opts):
        CtrlNode.__init__(self, name, self.uiTemplate)
        
    def processData(self, data):
        s = self.stateGroup.state()
        return functions.zeroCrossingEvents(data, minLength=s['minLength'], minPeak=s['minPeak'], minSum=s['minSum'])



