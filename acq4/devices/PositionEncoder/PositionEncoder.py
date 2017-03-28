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
        driver: 'AxoPatch200'
        position : 'linear' # or 'rotational'
        PPU : 360 # pulses per unit : ppr - pulses per revolution ; or ppm - pulses per meter
        ChannelA: 
            device: 'DAQ'
            channel: '/Dev2/port0/line3'
            type: 'di'
        ChannelB:
            device: 'DAQ'
            channel: '/Dev2/port0/line4'
            type: 'di'
            
    """
    
    sigShowModeDialog = QtCore.Signal(object)
    sigHideModeDialog = QtCore.Signal()
    #sigHoldingChanged = QtCore.Signal(object)  ## provided by DAQGeneric
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
            self.unit = '°'

        self.config = config
        self.modeLock = Mutex(Mutex.Recursive)   ## protects self.mdCanceled
        self.devLock = Mutex(Mutex.Recursive)    ## protects self.holding, possibly self.config, ..others, perhaps?
        self.mdCanceled = False
        
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        self.edgeCounter = 0
        dm.declareInterface(name, ['encoder'], self)
    
    def calculateAngle(self,chanA,chanB):
        
        chanAB = chanA.astype(bool)
        chanBB = chanB.astype(bool)

        self.bitSequence = (chanAB ^ chanBB) | chanBB << 1
        self.delta = (self.bitSequence[1:] - self.bitSequence[:-1]) % 4
        self.delta = np.concatenate((np.array([0]),self.delta))
        self.delta[self.delta==3] = -1
        angle = np.cumsum(-self.delta)*360./(2.*4.*self.ppu)
        
        #time = np.linspace(0, float(numPts)/rate,numPts)
        #angleSparse = angle[diff!=0]
        #timeSparse  = time[diff!=0]
        #speed =  (angleSparse[1:]-angleSparse[:-1])/(timeSparse[1:]-timeSparse[:-1])
        return angle

    def createTask(self, cmd, parentTask):
        return PositionEncoderTask(self, cmd, parentTask)
        
    def taskInterface(self, taskRunner):
        return PositionEncoderTaskGui(self, taskRunner)
        
    def deviceInterface(self, win):
        return PositionEncoderDevGui(self)
    
    #def getMapping(self, chans=None, mode=None):
    #    return AP200DataMapping(self, self.ivModes, chans, mode )
        
        
class PositionEncoderTask(DAQGenericTask):
    def __init__(self, dev, cmd, parentTask):
        ## make a few changes for compatibility with multiclamp        
        if 'daqProtocol' not in cmd:
            cmd['daqProtocol'] = {}
        #if 'command' in cmd:
        #    if 'holding' in cmd:
        #        cmd['daqProtocol']['command'] = {'command': cmd['command'], 'holding': cmd['holding']}
        #    else:
        #        cmd['daqProtocol']['command'] = {'command': cmd['command']}
    
        ## Make sure we're recording from the correct secondary channel
        #if dev.hasSecondaryChannel:
        #    if 'mode' in cmd:
        #        mode = cmd['mode']
        #    else:
        #        mode = dev.getMode()
        #    dev.reconfigureSecondaryChannel(mode)
       
        cmd['daqProtocol']['ChannelA'] = {'record': True}
        cmd['daqProtocol']['ChannelB'] = {'record': True}
        #cmd['daqProtocol']['counterValue'] = {'record': True}
        #cmd['daqProtocol']['position'] = {'record': True}
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'], parentTask)
        self.cmd = cmd

    def configure(self):
        ## Record initial state or set initial value
        #if 'holding' in self.cmd:
        #    self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        #if 'mode' in self.cmd:
        #    self.dev.setMode(self.cmd['mode'])
        #self.ampState = {'mode': self.dev.getMode(), 'LPF': self.dev.getLPF(), 'gain': self.dev.getGain()}
        
        ## Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self)
        #self.mapping.setMode(self.ampState['mode']) 
        
    #def getChanScale(self, chan):
        #print "AxoPatch200Task.getChanScale called."
        #if chan == 'primary':
            #return self.ampState['gain']
        #elif chan == 'command':
            #return self.dev.getCmdGain(self.ampState['mode'])
        #elif chan == 'secondary':
            #return self.dev.getChanScale('secondary')
        #else:
            #raise Exception("No scale for channel %s" % chan)
   
    def stop(self,abort):
        pass
    
    def isDone(self):
        return True
    
    def storeResult(self, dirHandle):
        #DAQGenericTask.storeResult(self, dirHandle)
        #dirHandle.setInfo(self.ampState)
        result = self.getResult()
        #result._info[-1]['ClampState'] = self.ampState
        dirHandle.writeFile(result, self.dev.name())
        
    def getResult(self):
        ## getResult from DAQGeneric, then add in command waveform
        result = DAQGenericTask.getResult(self)

        chanA = result['Channel':'ChannelA'].asarray()
        chanB = result['Channel':'ChannelB'].asarray()
        
        angle = self.dev.calculateAngle(chanA,chanB)
        
        arr = result.view(np.ndarray)
        arr = np.append(arr, self.dev.bitSequence[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'bitSequence', 'units': None})
        
        arr = np.append(arr, self.dev.delta[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'delta', 'units': None})
        
        arr = np.append(arr, angle[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'angle', 'units': 'degrees'})

        #arr = np.append(arr, speed[np.newaxis, :], axis=0)
        #result._info[0]['cols'].append({'name': 'speed'})

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
        #self.modeCombo = QtGui.QComboBox()
        #self.splitter2.addWidget(self.modeCombo)
        #self.modeCombo.addItems(self.dev.listModes())
        
        self.splitter3 = QtGui.QSplitter()
        self.splitter3.setOrientation(QtCore.Qt.Vertical)
        
        p1 = self.createChannelWidget('Quadrature Output (TTL)')
        p2 = self.createChannelWidget('Angle (degrees)')
        #p3 = self.createChannelWidget('Speed')


        self.quadrWidget = p1
        self.angleWidget = p2
        #self.speedWidget = p3
        #self.chanBPlot = p2
        #self.chanAPlot = p1
        #self.ctrlWidget = QtGui.QWidget()
        #self.ctrl = Ui_protoCtrl()
        #self.ctrl.setupUi(self.ctrlWidget)
        #self.splitter2.addWidget(self.ctrlWidget)
        
        self.splitter1.addWidget(self.splitter2)
        #self.splitter1.addWidget(self.splitter3)
        self.splitter2.addWidget(p1)
        self.splitter2.addWidget(p2)
        #self.splitter2.addWidget(p3)
        self.splitter1.setSizes([100, 500])
        
        self.stateGroup = WidgetGroup([
            (self.splitter1, 'splitter1'),
            (self.splitter2, 'splitter2'),
            #(self.splitter3, 'splitter3'),
        ])
        
        #self.modeCombo.currentIndexChanged.connect(self.modeChanged)
        #self.modeChanged()
        
    def createChannelWidget(self,ch):
        daqName = None
        p = PlotWidget(self)
        #conf = self.dev._DGConfig[ch]
        #units = ''
        #if 'units' in conf:
        #    units = conf['units']
        #print 'units',units
        #print 'conf', conf
        p.setLabel('left', text=ch, units=None)
        self.plots[ch] = p

        p.registerPlot(self.dev.name() + '.' + ch)

        #if conf['type'] in ['ao', 'do']:
        #w = OutputChannelGui(self, ch, conf, p, self.dev, self.taskRunner, daqName)
        #w.sigSequenceChanged.connect(self.sequenceChanged)
        #elif conf['type'] in ['ai', 'di','ci']:
        #    w = InputChannelGui(self, ch, conf, p, self.dev, self.taskRunner, daqName)
        #else:
        #    raise Exception("Unrecognized device type '%s'" % conf['type'])
        #self.channels[ch] = w
        return  p    
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        state = self.currentState()
        state['devState'] = TaskGui.saveState(self)
        #state['mode'] = self.getMode()
        #state['holdingEnabled'] = self.ctrl.holdingCheck.isChecked()
        #state['holding'] = self.ctrl.holdingSpin.value()
        return state
        
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        #self.modeCombo.setCurrentIndex(self.modeCombo.findText(state['mode']))
        #self.ctrl.holdingCheck.setChecked(state['holdingEnabled'])
        #if state['holdingEnabled']:
        #    self.ctrl.holdingSpin.setValue(state['holding'])
        self.stateGroup.setState(state)
        if 'devState' in state:
            TaskGui.restoreState(self, state['devState'])
    
    def generateTask(self, params=None):
        #daqTask = DAQGenericTaskGui.generateTask(self, params)
        
        self.clearRawPlots()
        pTask = TaskGui.generateTask(self, params)
        task = {
            #'mode': self.getMode(),
            'posProtocol': pTask
        }
        return task

    def handleResult(self,results,params):
        color1 =QtGui.QColor(100, 100, 100)
        color2 =QtGui.QColor(0, 100, 100)
        #color3 =QtGui.QColor(100, 100, 0)

        # calculate angle and speed from quadrature sequence
        chanA = results['Channel':'ChannelA'].asarray()
        chanB = results['Channel':'ChannelB'].asarray()
        
        numPts = results._info[-1]['DAQ']['ChannelA']['numPts']
        rate   = results._info[-1]['DAQ']['ChannelA']['rate']
        angle = self.dev.calculateAngle(chanA,chanB)
        time = np.linspace(0, float(numPts)/rate, numPts)
        self.quadrWidget.plot(chanA, x=time, pen=QtGui.QPen(color1))
        self.quadrWidget.plot(chanB, x=time, pen=QtGui.QPen(color2))
        #self.angleWidget.plot(y=seq,x=time, pen=QtGui.QPen(color1))
        #self.speedWidget.plot(y=diff, x=time[1:], pen=QtGui.QPen(color1))
        self.angleWidget.plot(y=angle,x=time, pen=QtGui.QPen(color1))
        #self.speedWidget.plot(y=speed, x=timeSparse[1:], pen=QtGui.QPen(color1))

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
        
        #self.enconderType = config.get('PPU', None)
        #self.ppu = config.get('PPU', None)
        
        self.ui.TypeLabel.setText(self.dev.encoderType)
        self.ui.ResolutionLabel.setText(str(self.dev.ppu))
        self.ui.UnitLabel.setText(self.dev.unit)
        
        #self.ui.vcHoldingSpin.setOpts(step=1, minStep=1e-3, dec=True, suffix='V', siPrefix=True)
        #self.ui.icHoldingSpin.setOpts(step=1, minStep=1e-12, dec=True, suffix='A', siPrefix=True)
        #for name in dev.modeNames.values():
        #    self.ui.modeCombo.addItem(name)
        #self.updateStatus()
        
        #self.ui.modeCombo.currentIndexChanged.connect(self.modeComboChanged)
        #self.ui.vcHoldingSpin.valueChanged.connect(self.vcHoldingChanged)
        #self.ui.icHoldingSpin.valueChanged.connect(self.icHoldingChanged)
        #self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        #self.dev.sigModeChanged.connect(self.devModeChanged)
        
    #def updateStatus(self):
        ##global modeNames
        #mode = self.dev.getMode()
        #if mode is None:
            #return
        #vcHold = self.dev.getHolding('vc')
        #icHold = self.dev.getHolding('ic')
        
        #self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        #self.ui.vcHoldingSpin.setValue(vcHold)
        #self.ui.icHoldingSpin.setValue(icHold)

    #def devHoldingChanged(self, chan, hval):
        #if isinstance(hval, dict):
            #self.ui.vcHoldingSpin.blockSignals(True)
            #self.ui.icHoldingSpin.blockSignals(True)
            #self.ui.vcHoldingSpin.setValue(hval['vc'])
            #self.ui.icHoldingSpin.setValue(hval['ic'])
            #self.ui.vcHoldingSpin.blockSignals(False)
            #self.ui.icHoldingSpin.blockSignals(False)
            
    #def devModeChanged(self, mode):
        #self.ui.modeCombo.blockSignals(True)
        #self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        #self.ui.modeCombo.blockSignals(False)
        
    #def vcHoldingChanged(self):
        #self.dev.setHolding('vc', self.ui.vcHoldingSpin.value())
        
    #def icHoldingChanged(self):
        #self.dev.setHolding('ic', self.ui.icHoldingSpin.value())
        
    #def modeComboChanged(self, m):
        #try:
            #self.dev.setMode(str(self.ui.modeCombo.itemText(m)))
        #except CancelException:
            #self.updateStatus()
        
        
