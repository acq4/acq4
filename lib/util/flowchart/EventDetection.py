# -*- coding: utf-8 -*-

from pyqtgraph.flowchart.library.common import *
import numpy as np


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
        ('fitFractionalError', 'check', {'value': False}),
        ('minFitFractionalError', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('maxFitFractionalError', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('fitLengthOverDecay', 'check', {'value': False}),
        ('minFitLengthOverDecay', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('maxFitLengthOverDecay', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-12, 'range': [None,None], 'siPrefix': True, 'hidden': True}),
        ('fitTime', 'check', {'value': False}),
        ('minFitTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
        ('maxFitTime', 'spin', {'value': 0, 'step': 1, 'minStep': 1e-4, 'range': [None,None], 'siPrefix': True, 'suffix': 's', 'hidden': True}),
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
                except ValueError:  ## If the data doesn't kave this key, don't fret; just ignore it.
                    pass
        #print "  filter 1:", mask.sum()  
        region = s['region']
        if region != 'all':
            mask *= data['region'] == region
        #print "  filter 2:", mask.sum(), region
        #print "  filter 3:", len(data[mask])
        return {'output':data[mask]}
