#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import with_statement
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericTaskGui, DataMapping
from acq4.devices.DAQGeneric.DaqChannelGui import *
from acq4.devices.Device import TaskGui
from acq4.util.Mutex import Mutex
#from acq4.devices.Device import *
from PyQt4 import QtCore, QtGui
import time
import numpy as np
from acq4.pyqtgraph.WidgetGroup import WidgetGroup
from collections import OrderedDict
from acq4.util.debug import printExc
from devGuiTemplate import Ui_encoderDevGui
from acq4.pyqtgraph import PlotWidget
import acq4.util.metaarray as metaarray
import weakref

    
class PositionEncoder(DAQGeneric):
    """Device class for optical position encoders : linear or rotational.
      
    The configuration for these devices should look like (this is an example):
    
    RotaryEncoder:
        driver: 'PositionEncoder'
        encoderType : 'rotational' # 'linear' or 'rotational'
        PPU : 360 # pulses per unit : ppr - pulses per revolution ; or ppm - pulses per meter
        ChannelA:  # channel A creating square pulse wave
            device: 'DAQ'
            channel: '/Dev2/port0/line3'
            type: 'di'
        ChannelB: # channel B creating square pulse wave 
            device: 'DAQ'
            channel: '/Dev2/port0/line4'
            type: 'di'
        
            
    """
    
    sigShowModeDialog = QtCore.Signal(object)
    sigHideModeDialog = QtCore.Signal()
    sigModeChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):
        
        self.encoderName = name
        # Generate config to use for DAQ 
        daqConfig = {}
        
        for ch in ['ChannelA', 'ChannelB']:
            if ch not in config:
                raise Exception("PositionEncoder: configuration must have ChannelA and ChannelB information.")
            daqConfig[ch]  = config[ch].copy()
        
        
        self.encoderType = config.get('encoderType', None)
        self.ppu = config.get('PPU', None)
        
        if self.encoderType == 'linear' :
            self.unit = 'm'
        elif self.encoderType == 'rotational' :
            self.unit = 'degrees'
        else:
            raise Exception("PositionEncoder: encoderType must be either linear or rotational in the device configuration.")

        self.config = config
        self.modeLock = Mutex(Mutex.Recursive)   ## protects self.mdCanceled
        self.devLock = Mutex(Mutex.Recursive)    ## protects self.holding, possibly self.config, ..others, perhaps?
        self.mdCanceled = False
        
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        self.edgeCounter = 0
        dm.declareInterface(name, ['encoder'], self)
    
    def calculateProgress(self,chanA,chanB):
        
        chanAB = chanA.astype(bool)
        chanBB = chanB.astype(bool)

        self.bitSequence = (chanAB ^ chanBB) | chanBB << 1
        self.delta = (self.bitSequence[1:] - self.bitSequence[:-1]) % 4
        self.delta = np.concatenate((np.array([0]),self.delta))
        self.delta[self.delta==3] = -1
        if self.encoderType == 'rotational' :
            angle = np.cumsum(-self.delta)*360./(2.*4.*self.ppu)
            return angle
        elif self.encoderType == 'linear' :
            distance = np.cumsum(-self.delta)/(2.*4.*self.ppu)
            return distance
            
        
    def createTask(self, cmd, parentTask):
        return PositionEncoderTask(self, cmd, parentTask)
        
    def taskInterface(self, taskRunner):
        return PositionEncoderTaskGui(self, taskRunner)
        
    def deviceInterface(self, win):
        return PositionEncoderDevGui(self)
    
        
class PositionEncoderTask(DAQGenericTask):
    def __init__(self, dev, cmd, parentTask):
        self.dev = dev
        if 'daqProtocol' not in cmd:
            cmd['daqProtocol'] = {}
        
        cmd['daqProtocol']['ChannelA'] = {'record': True}
        cmd['daqProtocol']['ChannelB'] = {'record': True}
        
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'], parentTask)
        self.cmd = cmd

    def configure(self):
        DAQGenericTask.configure(self)
   
    def stop(self,abort):
        pass
    
    def isDone(self):
        return True
    
    def storeResult(self, dirHandle):
        result = self.getResult()
        dirHandle.writeFile(result, self.dev.name())
        
    def getResult(self):
        ## getResult from DAQGeneric, then add in calculated waveforms
        result = DAQGenericTask.getResult(self)

        chanA = result['Channel':'ChannelA'].asarray()
        chanB = result['Channel':'ChannelB'].asarray()
        
        progress = self.dev.calculateProgress(chanA,chanB)
        
        arr = result.view(np.ndarray)
        arr = np.append(arr, self.dev.bitSequence[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'bitSequence', 'units': None})
        
        arr = np.append(arr, self.dev.delta[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'delta', 'units': None})
        
        arr = np.append(arr, progress[np.newaxis, :], axis=0)
        
        if self.dev.encoderType == 'rotational' :
            result._info[0]['cols'].append({'name': 'angle', 'units': self.dev.unit})
        elif self.dev.encoderType == 'linear' :
            result._info[0]['cols'].append({'name': 'distance', 'units': self.dev.unit})
        


        info = {'PPU': self.dev.ppu,
                'encoderType': self.dev.encoderType,
                'encodingType': 'x4 encoding',
                }

        result._info[-1]['PositionEncoder'] = info

        result = metaarray.MetaArray(arr, info=result._info)

        return result

    
class PositionEncoderTaskGui(TaskGui):
    def __init__(self, dev, taskRunner):
        #DAQGenericTaskGui.__init__(self, dev, taskRunner, ownUi=False)
        TaskGui.__init__(self, dev, taskRunner)
        self.dev = dev

        self.plots = weakref.WeakValueDictionary()
        self.channels = {}
        #self.ivModes = ivModes
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
        
        p1 = self.createChannelWidget('Quadrature Output (TTL)')
        if self.dev.encoderType == 'rotational':
            p2 = self.createChannelWidget('Angle (degrees)')
        elif self.dev.encoderType == 'linear':
            p2 = self.createChannelWidget('Distance (m)')

        self.quadrWidget = p1
        self.angleWidget = p2
        
        self.splitter1.addWidget(self.splitter2)
        self.splitter2.addWidget(p1)
        self.splitter2.addWidget(p2)
        self.splitter1.setSizes([100, 500])
        
        self.stateGroup = WidgetGroup([
            (self.splitter1, 'splitter1'),
            (self.splitter2, 'splitter2'),
        ])
        
        
    def createChannelWidget(self,ch):
        daqName = None
        p = PlotWidget(self)
        p.setLabel('left', text=ch, units=None)
        self.plots[ch] = p

        p.registerPlot(self.dev.name() + '.' + ch)
        return  p    

    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        state = self.currentState()
        state['devState'] = TaskGui.saveState(self)
        return state
        
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        self.stateGroup.setState(state)
        if 'devState' in state:
            TaskGui.restoreState(self, state['devState'])
    
    def generateTask(self, params=None):
        self.clearRawPlots()
        pTask = TaskGui.generateTask(self, params)
        task = {
            'posProtocol': pTask
        }
        return task

    def handleResult(self,results,params):
        color1 =QtGui.QColor(100, 100, 100)
        color2 =QtGui.QColor(0, 100, 100)

        # calculate angle and speed from quadrature sequence
        chanA = results['Channel':'ChannelA'].asarray()
        chanB = results['Channel':'ChannelB'].asarray()
        
        numPts = results._info[-1]['DAQ']['ChannelA']['numPts']
        rate   = results._info[-1]['DAQ']['ChannelA']['rate']
        progress = self.dev.calculateProgress(chanA,chanB)
        time = np.linspace(0, float(numPts)/rate, numPts)
        self.quadrWidget.plot(chanA, x=time, pen=QtGui.QPen(color1))
        self.quadrWidget.plot(chanB, x=time, pen=QtGui.QPen(color2))
        self.angleWidget.plot(y=progress,x=time, pen=QtGui.QPen(color1))

    def clearRawPlots(self):
        for p in ['quadrWidget', 'angleWidget']:
            if hasattr(self, p):
                getattr(self, p).clear()
    
    def currentState(self):
        return self.stateGroup.state()

        
class PositionEncoderDevGui(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.ui = Ui_encoderDevGui()
        self.ui.setupUi(self)
        
        self.ui.TypeLabel.setText(self.dev.encoderType)
        self.ui.ResolutionLabel.setText(str(self.dev.ppu))
        self.ui.UnitLabel.setText(self.dev.unit)
    
        
        
