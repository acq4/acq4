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

class AP200DataMapping(DataMapping):
    def __init__(self, dev, ivModes, chans=None, mode=None):
        ## mode can be provided:
        ##   - during __init__
        ##   - explicitly when calling map functions
        ##   - implicitly when calling map functions (uses device's current mode)
        
        self.dev = dev
        self.mode = mode
        self.ivModes = ivModes
        self.gainSwitch = self.dev.getGainSwitchValue()
        
    def setMode(self, mode):
        self.mode = mode
            
    def getGain(self, chan, mode, switch=None):
        if switch == None:
            switch = self.gainSwitch
        if mode is None:
            if self.mode is None:
                mode = self.dev.getMode()
            else:
                mode = self.mode
        if chan != 'command':
            return self.dev.interpretGainSwitchValue(switch, mode)
        else:
            #global ivModes
            ivMode = self.ivModes[mode]
            if ivMode == 'vc':
                return 50.0 # in VC mode, sensitivity is 20mV/V; scale is 1/20e-3 = 50
            else:
                return 5e8 # in IC mode, sensitivity is 2nA/V; scale is 1/2e-9 = 5e8
        
    def mapToDaq(self, chan, data, mode=None):
        gain = self.getGain(chan, mode)
        return data * gain
        
        
    def mapFromDaq(self, chan, data, mode=None):
        gain = self.getGain(chan, mode)
        return data / gain
        
    
    
    
    
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
        
        ##    daqConfig['gain'] = {'type': 'ai', 'channel': config['GainChannel']}
        ##if 'LPFChannel' in config:
        ##    daqConfig['LPF'] = {'type': 'ai', 'channel': config['LPFChannel'], 'units': 'Hz'}
        #if 'ScaledSignal' in config:
            ##daqConfig['primary'] = {'type': 'ai', 'channel': config['ScaledSignal']}
            #daqConfig['primary'] = config['ScaledSignal']
            #if config['ScaledSignal'].get('type', None) != 'ai':
                #raise Exception("AxoPatch200: ScaledSignal configuration must have type:'ai'")
        #if 'Command' in config:
            ##daqConfig['command'] = {'type': 'ao', 'channel': config['Command']}
            #daqConfig['command'] = config['Command']
            #if config['Command'].get('type', None) != 'ao':
                #raise Exception("AxoPatch200: ScaledSignal configuration must have type:'ao'")
            
        ### Note that both of these channels can be present, but we will only ever record from one at a time.
        ### Usually, we'll record from "I OUTPUT" in current clamp and "10 Vm OUTPUT" in voltage clamp.
        #if 'SecondaryVCSignal' in config: 
            #self.hasSecondaryChannel = True
            ##daqConfig['secondary'] = {'type': 'ai', 'channel': config['SecondaryVCSignal']}
            #daqConfig['secondary'] = config['SecondaryVCSignal']
            #if config['SecondaryVCSignal'].get('type', None) != 'ai':
                #raise Exception("AxoPatch200: SecondaryVCSignal configuration must have type:'ai'")
        #elif 'SecondaryICSignal' in config:
            #self.hasSecondaryChannel = True
            ##daqConfig['secondary'] = {'type': 'ai', 'channel': config['SecondaryICSignal']}
            #daqConfig['secondary'] = config['SecondaryICSignal']
            #if config['SecondaryICSignal'].get('type', None) != 'ai':
                #raise Exception("AxoPatch200: SecondaryICSignal configuration must have type:'ai'")
        #else:
            #self.hasSecondaryChannel = False
        
        self.encoderType = config.get('encoderType', None)
        self.ppu = config.get('PPU', None)
        
        if self.encoderType == 'linear' :
            self.unit = 'm'
        elif self.encoderType == 'rotational' :
            self.unit = '°'

        #elif self.version == '200B':
            ## telegraph voltage/output translation from the Axopatch 200 amplifier
            #self.mode_tel = np.array([6, 4, 3, 2, 1])
            #self.modeNames = OrderedDict([(0, 'V-Clamp'), (2, 'I=0'), (4, 'I-Clamp Fast'), (3, 'I-Clamp Normal'), (1, 'Track'), ])
            #self.ivModes = {'V-Clamp':'vc', 'Track':'vc', 'I=0':'ic', 'I-Clamp Fast':'ic', 'I-Clamp Normal':'ic', 'vc':'vc', 'ic':'ic'}
            #self.modeAliases = {'ic': 'I-Clamp Fast', 'i=0': 'I=0', 'vc': 'V-Clamp'}
            #self.lpf_freq[-1] = 100.0  # 200B's highest LPF value is 100kHz instead of 50.
        #else:
            #raise Exception("AxoPatch200: version must be '200', '200A' or '200B' (got %r)" % version)

        #self.holding = {
            #'vc': config.get('vcHolding', -0.05),
            #'ic': config.get('icHolding', 0.0)
        #}
        
        self.config = config
        self.modeLock = Mutex(Mutex.Recursive)   ## protects self.mdCanceled
        self.devLock = Mutex(Mutex.Recursive)    ## protects self.holding, possibly self.config, ..others, perhaps?
        self.mdCanceled = False
        
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        #self.modeDialog = QtGui.QMessageBox()
        #self.modeDialog.hide()
        #self.modeDialog.setModal(False)
        #self.modeDialog.setWindowTitle("Mode Switch Request")
        #self.modeDialog.addButton(self.modeDialog.Cancel)
        #self.modeDialog.buttonClicked.connect(self.modeDialogClicked)
        
        #self.sigShowModeDialog.connect(self.showModeDialog)
        #self.sigHideModeDialog.connect(self.hideModeDialog)
        
        
        self.edgeCounter = 0
        
        #try:
        #    self.setHolding()
        #except:
        #    printExc("Error while setting holding value:")
        #    
        dm.declareInterface(name, ['encoder'], self)
    
    def calculateAngle(self,chanA,chanB):
        
        chanAB = chanA.astype(bool)
        chanBB = chanB.astype(bool)

        self.seq = (chanAB ^ chanBB) | chanBB << 1
        self.diff = (self.seq[1:] - self.seq[:-1]) % 4
        self.diff[self.diff==3] = -1
        angle = np.cumsum(-self.diff)*360./(2.*4.*self.ppu)
        
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
        #result = self.getResult()
        #stateB = np.array(result['Channel':'ChannelB']).astype(bool)
        #stateA = np.array(result['Channel':'ChannelA']).astype(bool)
        #print stateB
        #seq = (stateA ^ stateB) | stateB << 1
        #print seq
        #self.cmd['sequence'] = seq
        #, mean(result['Channel':'ChannelB'])
        #print self.getResult()
        #print self.cmd
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
        arr = np.append(arr, self.dev.seq[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'sequence'})
        
        arr = np.append(arr, self.dev.diff[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'difference'})
        
        arr = np.append(arr, angle[np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'angle', 'units': 'degrees'})

        #arr = np.append(arr, speed[np.newaxis, :], axis=0)
        #result._info[0]['cols'].append({'name': 'speed'})

        info = {'PPU': self.dev.ppu,
                'encoderType': self.dev.encoderType,
                'encodingType': 'x4 encoding',
                #'expectedPower': self.expectedPower,
                #'requestedWavelength':self.cmd.get('wavelength', None),
                #'shutterMode':self.cmd['shutterMode'],
                #'powerCheckRequested':self.cmd.get('checkPower', False),
                #'pulsesCmd': self.cmd.get('pulses', None)
                }


        result._info[-1]['PositionEncoder'] = info

        result = metaarray.MetaArray(arr, info=result._info)

        print 'in get result'
        return results

    
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
        
        p1 = self.createChannelWidget('Quadrature Output')
        p2 = self.createChannelWidget('Angle')
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
        self.quadrWidget.plot(chanA, pen=QtGui.QPen(color1))
        self.quadrWidget.plot(chanB, pen=QtGui.QPen(color2))
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

    #def modeChanged(self):
        ##global ivModes
        #ivm = self.ivModes[self.getMode()]
        #w = self.cmdWidget
        
        #if ivm == 'vc':
            #scale = 1e-3
            #cmdUnits = 'V'
            #inpUnits = 'A'
        #else:
            #scale = 1e-12
            #cmdUnits = 'A'
            #inpUnits = 'V'
            
        #self.inputWidget.setUnits(inpUnits)
        #self.cmdWidget.setUnits(cmdUnits)
        #self.cmdWidget.setMeta('y', minStep=scale, step=scale*10, value=0.)
        #self.inputPlot.setLabel('left', units=inpUnits)
        #self.cmdPlot.setLabel('left', units=cmdUnits)
        ##w.setScale(scale)
        #for s in w.getSpins():
            #s.setOpts(minStep=scale)
                
        #self.cmdWidget.updateHolding()
    
    #def getMode(self):
    #    return str(self.modeCombo.currentText())

    #def getChanHolding(self, chan):
    #    if chan == 'command':
    #        return self.dev.getHolding(self.getMode())
    #    else:
    #        raise Exception("Can't get holding value for channel %s" % chan)
            

        
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
        
        
