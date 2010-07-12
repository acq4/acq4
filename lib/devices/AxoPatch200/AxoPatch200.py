#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericProtoGui
from lib.util.Mutex import Mutex, MutexLocker
#from lib.devices.Device import *
from PyQt4 import QtCore, QtGui
import time
import numpy as np
from WidgetGroup import *

# telegraph voltage/output translation from the Axopatch 200 amplifier
mode_tel = np.array([6, 4, 3, 2, 1])
mode_char = ['V', 'T', '0', 'I', 'F']

# Axopatch gain telegraph
# telegraph should not read below 2 V in CC mode
gain_tel = np.array([0.5,  1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5])
gain_vm  = np.array([0.5,  0.5, 0.5, 0.5, 1,   2,   5,   10,  20,  50,  100, 200, 500]) * 1e9
gain_im  = np.array([0.05, 0.1, 0.2, 0.5, 1,   2,   5,   10,  20,  50,  100, 200, 500]) * 1e3

# Axopatch LPF telegraph
lpf_tel = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
lpf_freq = np.array([1.0, 2.0, 5.0, 10.0, 100.0])

        #GainChannel: 'DAQ', '/Dev1/ai14'
        #LPFchannel: 'DAQ', '/Dev1/ai15'
        #VCommand: 'DAQ', '/Dev1/ao0'
        #ScaledSignal: 'DAQ', '/Dev1/ai5'
        
class AxoPatch200(DAQGeneric):

    def __init__(self, dm, config, name):

        # Generate config to use for DAQ 
        daqConfig = {}
        if 'GainChannel' in config:
            daqConfig['gain'] = {'type': 'ai', 'channel': config['GainChannel']}
        if 'LPFChannel' in config:
            daqConfig['LPF'] = {'type': 'ai', 'channel': config['LPFChannel'], 'units': 'Hz'}
        if 'ScaledSignal' in config:
            daqConfig['scaledsignal'] = {'type': 'ai', 'channel': config['ScaledSignal'], 'units': 'A'}
        if 'VCommand' in config:
            daqConfig['vcommand'] = {'type': 'ao', 'channel': config['VCommand'], 'units': 'V'}
        DAQGeneric.__init__(self, dm, daqConfig, name)

    def createTask(self, cmd):
        return AxoPatch200Task(self, cmd)
        
    def protocolInterface(self, prot):
        return AxoPatchProtoGui(self, prot)
    
        
class AxoPatch200Task(DAQGenericTask):
    
    def __init__(self, dev, cmd):
        cmd['gain'] = {'record': False, 'recordInit': True}
        cmd['LPF'] = {'record': False, 'recordInit': True}
        cmd['scaledsignal'] = {'record': True}
        DAQGenericTask.__init__(self, dev, cmd)

    def configure(self, tasks, startOrder):
        ## Record initial state or set initial value
        DAQGenericTask.configure(self, tasks, startOrder)
        lpfv = self.initialState['LPF']
        ilpf = np.argmin(np.abs(lpf_tel-lpfv))
        self.initialState['LPF'] = lpf_freq[ilpf]
        
        gv = self.initialState['gain']
        igain = np.argmin(np.abs(gain_tel-gv))
        self.initialState['gain'] = gain_vm[igain]
        
        
    def getChanScale(self, chan):
        with MutexLocker(self.dev.lock): # may not be necessary in some contexts... just being cautious.
            ## Scale defaults to 1.0
            ## - can be overridden in configuration
            ## - can be overridden again in command
            if chan == 'scaledsignal':
                return self.initialState['gain']
            if chan == 'vcommand':
                return 50.0 # mV/V
                
            #scale = 1.0
            #if 'scale' in self.dev.config[chan]:
            #    scale = self.dev.config[chan]['scale']
            #if 'scale' in self.cmd[chan]:
            #    scale = self.cmd[chan]['scale']
            #return scale
            
            
class AxoPatchProtoGui(DAQGenericProtoGui):
    def __init__(self, dev, prot):
        DAQGenericProtoGui.__init__(self, dev, prot, ownUi=False)
        
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.splitter1 = QtGui.QSplitter()
        self.splitter1.setOrientation(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.splitter1)
        
        self.splitter2 = QtGui.QSplitter()
        self.splitter2.setOrientation(QtCore.Qt.Vertical)
        
        self.splitter3 = QtGui.QSplitter()
        self.splitter3.setOrientation(QtCore.Qt.Vertical)
        
        (w1, p1) = self.createChannelWidget('scaledsignal')
        (w2, p2) = self.createChannelWidget('vcommand')
        
        self.splitter1.addWidget(self.splitter2)
        self.splitter1.addWidget(self.splitter3)
        self.splitter2.addWidget(w1)
        self.splitter2.addWidget(w2)
        self.splitter3.addWidget(p1)
        self.splitter3.addWidget(p2)
        
        self.stateGroup = WidgetGroup([
            (self.splitter1, 'splitter1'),
            (self.splitter2, 'splitter2'),
            (self.splitter3, 'splitter3'),
        ])
        
        w2.setScale(0.001)
        w2.setUnits('V')
        for s in w2.getSpins():
            s.setOpts(minStep=1e-3)
        
        