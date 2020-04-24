# -*- coding: utf-8 -*-
from __future__ import print_function
from .. import AnalysisModule
from acq4.Manager import getManager
from acq4.util import Qt

class PatchAnalysisModule(AnalysisModule):
    """
    Very minimal task analysis module used for measuring membrane and access 
    resistance from a DAQGeneric device  
    
    For simplicity, many parts of this analysis are hardcoded--pulse timings,
    amplitudes, device/channel names, etc. 
    """
    device = "VoltageClamp"
    channel = "CurrentOutput"
    
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.rmLabel = Qt.QLabel("Membrane Resistance:")
        self.raLabel = Qt.QLabel("Access Resistance:")
        self.layout.addWidget(self.rmLabel)
        self.layout.addWidget(self.raLabel)
        
        # Optional: this configures automatic save/restore of widget state
        self.postGuiInit()
        
    def newFrame(self, frame):
        # Grab the data for the correct device / channel
        data = frame['result'][self.device]['Channel': self.channel]
        
        # Baseline is hardcoded here as t=0 to 50ms
        baseline = data['Time': 0.0:0.01]
        
        # Rm test is hardcoded here as t=90 to 100ms
        rmtest = data['Time': 0.018:0.0195]
        steadyStateCurrent = rmtest.mean() - baseline.mean()
        
        # Ra test is hardcoded here as t=50 to 52ms
        ratest = data['Time': 0.01:0.012]
        peakCurrent = ratest.max() - baseline.mean()
        
        # Assume 10 mV test voltage pulse
        testVoltage = 10e-3
        
        Rm = testVoltage / steadyStateCurrent
        Ra = testVoltage / peakCurrent

        print(Rm, Ra, testVoltage, steadyStateCurrent, peakCurrent)
        
        self.rmLabel.setText(u"Membrane Resistance: %0.2f MΩ" % (Rm/1e6))
        self.raLabel.setText(u"Access Resistance: %0.2f MΩ" % (Ra/1e6))


        