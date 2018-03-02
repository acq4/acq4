#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericTaskGui, DataMapping
from acq4.util.Mutex import Mutex
#from acq4.devices.Device import *
from acq4.util import Qt
import time
import numpy as np
from acq4.pyqtgraph.WidgetGroup import WidgetGroup
from collections import OrderedDict
from acq4.util.debug import printExc
from .devGuiTemplate import *



        #GainChannel: 'DAQ', '/Dev1/ai14'
        #LPFchannel: 'DAQ', '/Dev1/ai15'
        #VCommand: 'DAQ', '/Dev1/ao0'
        #ScaledSignal: 'DAQ', '/Dev1/ai5'


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
        
    
    
    
    
class AxoPatch200(DAQGeneric):
    
    sigShowModeDialog = Qt.Signal(object)
    sigHideModeDialog = Qt.Signal()
    #sigHoldingChanged = Qt.Signal(object)  ## provided by DAQGeneric
    sigModeChanged = Qt.Signal(object)

    def __init__(self, dm, config, name):
        
        # Generate config to use for DAQ 
        daqConfig = {}
        
        for ch in ['GainChannel', 'LPFChannel', 'ModeChannel']:
            if ch not in config:
                continue
            daqConfig[ch]  = config[ch].copy()
        #if 'GainChannel' in config:
        #    daqConfig['gain'] = {'type': 'ai', 'channel': config['GainChannel']}
        #if 'LPFChannel' in config:
        #    daqConfig['LPF'] = {'type': 'ai', 'channel': config['LPFChannel'], 'units': 'Hz'}
        if 'ScaledSignal' in config:
            #daqConfig['primary'] = {'type': 'ai', 'channel': config['ScaledSignal']}
            daqConfig['primary'] = config['ScaledSignal']
            if config['ScaledSignal'].get('type', None) != 'ai':
                raise Exception("AxoPatch200: ScaledSignal configuration must have type:'ai'")
        if 'Command' in config:
            #daqConfig['command'] = {'type': 'ao', 'channel': config['Command']}
            daqConfig['command'] = config['Command']
            if config['Command'].get('type', None) != 'ao':
                raise Exception("AxoPatch200: ScaledSignal configuration must have type:'ao'")
            
        ## Note that both of these channels can be present, but we will only ever record from one at a time.
        ## Usually, we'll record from "I OUTPUT" in current clamp and "10 Vm OUTPUT" in voltage clamp.
        if 'SecondaryVCSignal' in config: 
            self.hasSecondaryChannel = True
            #daqConfig['secondary'] = {'type': 'ai', 'channel': config['SecondaryVCSignal']}
            daqConfig['secondary'] = config['SecondaryVCSignal']
            if config['SecondaryVCSignal'].get('type', None) != 'ai':
                raise Exception("AxoPatch200: SecondaryVCSignal configuration must have type:'ai'")
        elif 'SecondaryICSignal' in config:
            self.hasSecondaryChannel = True
            #daqConfig['secondary'] = {'type': 'ai', 'channel': config['SecondaryICSignal']}
            daqConfig['secondary'] = config['SecondaryICSignal']
            if config['SecondaryICSignal'].get('type', None) != 'ai':
                raise Exception("AxoPatch200: SecondaryICSignal configuration must have type:'ai'")
        else:
            self.hasSecondaryChannel = False
        
        self.version = config.get('version', '200B')

        # Axopatch gain telegraph
        # telegraph should not read below 2 V in CC mode
        self.gain_tel = np.array([0.5,  1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5])
        self.gain_vm  = np.array([0.5,  0.5, 0.5, 0.5, 1,   2,   5,   10,  20,  50,  100, 200, 500]) * 1e9  ## values in mv/pA
        self.gain_im  = np.array([0.05, 0.1, 0.2, 0.5, 1,   2,   5,   10,  20,  50,  100, 200, 500])        ## values in mV/mV

        # Axopatch Lowpass Bessel Filter
        self.lpf_tel = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
        self.lpf_freq = np.array([1.0, 2.0, 5.0, 10.0, 50.0])

        if self.version == '200':
            # telegraph voltage/output translation from the Axopatch 200 amplifier
            self.mode_tel = np.array([6, 4, 2])
            self.modeNames = OrderedDict([(0, 'V-Clamp'), (1, 'Track'), (2, 'I-Clamp')])
            self.ivModes = {'V-Clamp':'vc', 'Track':'ic', 'I-Clamp':'ic', 'vc':'vc', 'ic':'ic'}
            self.modeAliases = {'ic': 'I-Clamp', 'i=0': 'Track', 'vc': 'V-Clamp'}

        elif self.version == '200A':
            # telegraph voltage/output translation from the Axopatch 200 amplifier
            self.mode_tel = np.array([6, 4, 2, 1])
            self.modeNames = OrderedDict([(0, 'V-Clamp'), (1, 'Track'), (2, 'I-Clamp Normal'), (3, 'I-Clamp Fast'),  ])
            self.ivModes = {'V-Clamp':'vc', 'Track':'vc', 'I-Clamp Fast':'ic', 'I-Clamp Normal':'ic', 'vc':'vc', 'ic':'ic'}
            self.modeAliases = {'ic': 'I-Clamp Fast', 'i=0': 'Track', 'vc': 'V-Clamp'}

        elif self.version == '200B':
            # telegraph voltage/output translation from the Axopatch 200 amplifier
            self.mode_tel = np.array([6, 4, 3, 2, 1])
            self.modeNames = OrderedDict([(0, 'V-Clamp'), (2, 'I=0'), (4, 'I-Clamp Fast'), (3, 'I-Clamp Normal'), (1, 'Track'), ])
            self.ivModes = {'V-Clamp':'vc', 'Track':'vc', 'I=0':'ic', 'I-Clamp Fast':'ic', 'I-Clamp Normal':'ic', 'vc':'vc', 'ic':'ic'}
            self.modeAliases = {'ic': 'I-Clamp Fast', 'i=0': 'I=0', 'vc': 'V-Clamp'}
            self.lpf_freq[-1] = 100.0  # 200B's highest LPF value is 100kHz instead of 50.
        else:
            raise Exception("AxoPatch200: version must be '200', '200A' or '200B' (got %r)" % version)

        self.holding = {
            'vc': config.get('vcHolding', -0.05),
            'ic': config.get('icHolding', 0.0)
        }
        
        self.config = config
        self.modeLock = Mutex(Mutex.Recursive)   ## protects self.mdCanceled
        self.devLock = Mutex(Mutex.Recursive)    ## protects self.holding, possibly self.config, ..others, perhaps?
        self.mdCanceled = False
        
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        self.modeDialog = Qt.QMessageBox()
        self.modeDialog.hide()
        self.modeDialog.setModal(False)
        self.modeDialog.setWindowTitle("Mode Switch Request")
        self.modeDialog.addButton(self.modeDialog.Cancel)
        self.modeDialog.buttonClicked.connect(self.modeDialogClicked)
        
        self.sigShowModeDialog.connect(self.showModeDialog)
        self.sigHideModeDialog.connect(self.hideModeDialog)
        
        
        
        try:
            self.setHolding()
        except:
            printExc("Error while setting holding value:")
            
        dm.declareInterface(name, ['clamp'], self)

    def createTask(self, cmd, parentTask):
        return AxoPatch200Task(self, cmd, parentTask)
        
    def taskInterface(self, taskRunner):
        return AxoPatchTaskGui(self, taskRunner, self.ivModes)
        
    def deviceInterface(self, win):
        return AxoPatchDevGui(self)
    
    def getMapping(self, chans=None, mode=None):
        return AP200DataMapping(self, self.ivModes, chans, mode )
        
        
    def setHolding(self, mode=None, value=None, force=False):
        #print "setHolding", mode, value
        #global ivModes
        with self.devLock:
            currentMode = self.getMode()
            if mode is None:
                mode = currentMode
            ivMode = self.ivModes[mode]  ## determine vc/ic
                
            if value is None:
                value = self.holding[ivMode]
            else:
                self.holding[ivMode] = value
            
            if ivMode == self.ivModes[currentMode] or force:
                mapping = self.getMapping(mode=mode)
                ## override the scale since getChanScale won't necessarily give the correct value
                ## (we may be about to switch modes)
                DAQGeneric.setChanHolding(self, 'command', value, mapping=mapping)
           
            self.sigHoldingChanged.emit('primary', self.holding.copy())
            
    def setChanHolding(self, chan, value=None):
        if chan == 'command':
            self.setHolding(value=value)
        
    def getHolding(self, mode=None):
        #global ivModes
        with self.devLock:
            if mode is None:
                mode = self.getMode()
            ivMode = self.ivModes[mode]  ## determine vc/ic
            return self.holding[ivMode]
        
    def listModes(self):
        #global modeNames
        return list(self.modeNames.values())
        
    def setMode(self, mode):
        """Set the mode of the AxoPatch (by requesting user intervention). Takes care of switching holding levels in I=0 mode if needed."""
        #global modeAliases
        startMode = self.getMode()
        if mode in self.modeAliases:
            mode = self.modeAliases[mode]
        if startMode == mode:
            return
        
        startIvMode = self.ivModes[startMode]
        ivMode = self.ivModes[mode]
        if (startIvMode == 'vc' and ivMode == 'ic') or (startIvMode == 'ic' and ivMode == 'vc'):
            ## switch to I=0 first
            self.requestModeSwitch(self.modeAliases['i=0'])
            
        self.setHolding(ivMode, force=True)  ## we're in I=0 mode now, so it's ok to force the holding value.
        
        ## TODO:
        ## If mode switches back the wrong direction, we need to reset the holding value and cancel.
        self.requestModeSwitch(mode) 
        
    def requestModeSwitch(self, mode):
        """Pop up a dialog asking the user to switch the amplifier mode, wait for change. This function is thread-safe."""
        #global modeNames
        with self.modeLock:
            self.mdCanceled = False
        app = Qt.QApplication.instance()
        msg = 'Please set %s mode switch to %s' % (self.name(), mode)

        self.sigShowModeDialog.emit(msg)
        
        #print "Set mode:", mode
        ## Wait for the mode to change to the one we're waiting for, or for a cancel
        while True:
            if Qt.QThread.currentThread() == app.thread():
                app.processEvents()
            else:
                Qt.QThread.yieldCurrentThread()
            if self.modeDialogCanceled():
                #print "  Caught user cancel"
                raise CancelException('User canceled mode switch request')
            currentMode = self.getMode()
            if currentMode == mode:
                break
            if currentMode is None:
                #print "  Can't determine mode"
                raise Exception("Can not determine mode of AxoPatch!")
            time.sleep(0.01)
            time.sleep(0.2)
            #print "  ..current:", currentMode
            
        #print "  got mode"

        self.sigHideModeDialog.emit()
        self.sigModeChanged.emit(mode)
        
        
    def showModeDialog(self, msg):
        with self.modeLock:
            self.mdCanceled = False
        self.modeDialog.setText(msg)
        self.modeDialog.show()
        self.modeDialog.activateWindow()
        
    def hideModeDialog(self):
        self.modeDialog.hide()
        
    def modeDialogCanceled(self):
        with self.modeLock:
            return self.mdCanceled
        
    def modeDialogClicked(self):
        ## called when user clicks 'cancel' on the mode dialog
        self.mdCanceled = True
        self.modeDialog.hide()
        
    def getMode(self):
        #print "getMode"
        with self.devLock:
            #print "  got lock"
            #global mode_tel, modeNames
            m = self.readChannel('ModeChannel', raw=True)
            #print "  read value", m
            if m is None:
                return None
            mode = self.modeNames[np.argmin(np.abs(self.mode_tel-m))]
            return mode
    
    def getLPF(self):
        with self.devLock:
            #global lpf_tel, lpf_freq
            f = self.readChannel('LPFChannel')
            if f is None:
                return None
            return self.lpf_freq[np.argmin(np.abs(self.lpf_tel-f))]
        
    def getGain(self):
        with self.devLock:
            mode = self.getMode()
            if mode is None:
                return None
            g = self.getGainSwitchValue()
            return self.interpretGainSwitchValue(g, mode)
            
    def interpretGainSwitchValue(self, val, mode):
        ## convert a gain-switch-position integer (as returned from getGainSwitchValue)
        ## into an actual gain value
            #global gain_vm, gain_im, ivModes
            if val is None:
                return None
            if self.ivModes[mode] == 'vc':
                return self.gain_vm[val]
            else:
                return self.gain_im[val]
        
        
    def getGainSwitchValue(self):
        ## return the integer value corresponding to the current position of the output gain switch
        #global gain_tel
        g = self.readChannel('GainChannel', raw=True)
        if g is None:
            return None
        return np.argmin(np.abs(self.gain_tel-g))
    
    def getCmdGain(self, mode=None):
        with self.devLock:
            if mode is None:
                mode = self.getMode()
            #global ivModes
            ivMode = self.ivModes[mode]
            if ivMode == 'vc':
                return 50.0 # in VC mode, sensitivity is 20mV/V; scale is 1/20e-3 = 50
            else:
                return 5e8 # in IC mode, sensitivity is 2nA/V; scale is 1/2e-9 = 5e8
        
    #def getChanScale(self, chan):
        #if chan == 'command':
            #return self.getCmdGain()
        #elif chan == 'primary':
            #return self.getGain()
        #else:
            #return DAQGeneric.getChanScale(self, chan)
            #raise Exception("No scale for channel %s" % chan)
        
    def getChanUnits(self, chan):
        #global ivModes
        iv = self.ivModes[self.getMode()]
        if iv == 'vc':
            units = ['V', 'A']
        else:
            units = ['A', 'V']
            
        if chan == 'command':
            return units[0]
        elif chan == 'secondary':
            return units[0]
        elif chan == 'primary':
            return units[1]
        
    def readChannel(self, ch, **opts):
        ## this should go away.
        return self.getChannelValue(ch, **opts)
        #if ch in self.config:
            #chOpts = self.config[ch]
            #dev = self.dm.getDevice(chOpts['device'])
            #return dev.getChannelValue(chOpts['channel'], chOpts.get('mode', None))
        #else:
            #return None
        
    def reconfigureSecondaryChannel(self, mode):
        ## Secondary channel changes depending on which mode we're in.
        if self.ivModes[mode] == 'vc':
            if 'SecondaryVCSignal' in self.config:
                self.reconfigureChannel('secondary', self.config['SecondaryVCSignal'])
        else:
            if 'SecondaryICSignal' in self.config:
                self.reconfigureChannel('secondary', self.config['SecondaryICSignal'])
        
class AxoPatch200Task(DAQGenericTask):
    def __init__(self, dev, cmd, parentTask):
        ## make a few changes for compatibility with multiclamp        
        if 'daqProtocol' not in cmd:
            cmd['daqProtocol'] = {}
        if 'command' in cmd:
            if 'holding' in cmd:
                cmd['daqProtocol']['command'] = {'command': cmd['command'], 'holding': cmd['holding']}
            else:
                cmd['daqProtocol']['command'] = {'command': cmd['command']}
    
        ## Make sure we're recording from the correct secondary channel
        if dev.hasSecondaryChannel:
            if 'mode' in cmd:
                mode = cmd['mode']
            else:
                mode = dev.getMode()
            dev.reconfigureSecondaryChannel(mode)
            cmd['daqProtocol']['secondary'] = {'record': True}
        
        
        cmd['daqProtocol']['primary'] = {'record': True}
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'], parentTask)
        self.cmd = cmd

    def configure(self):
        ## Record initial state or set initial value
        #if 'holding' in self.cmd:
        #    self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        if 'mode' in self.cmd:
            self.dev.setMode(self.cmd['mode'])
        self.ampState = {'mode': self.dev.getMode(), 'LPF': self.dev.getLPF(), 'gain': self.dev.getGain()}
        
        ## Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self)
        self.mapping.setMode(self.ampState['mode']) 
        
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
            
    def storeResult(self, dirHandle):
        #DAQGenericTask.storeResult(self, dirHandle)
        #dirHandle.setInfo(self.ampState)
        result = self.getResult()
        result._info[-1]['ClampState'] = self.ampState
        dirHandle.writeFile(result, self.dev.name())
        

    
class AxoPatchTaskGui(DAQGenericTaskGui):
    def __init__(self, dev, taskRunner, ivModes):
        DAQGenericTaskGui.__init__(self, dev, taskRunner, ownUi=False)
        
        self.ivModes = ivModes
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.splitter1 = Qt.QSplitter()
        self.splitter1.setOrientation(Qt.Qt.Horizontal)
        self.layout.addWidget(self.splitter1)
        
        self.splitter2 = Qt.QSplitter()
        self.splitter2.setOrientation(Qt.Qt.Vertical)
        self.modeCombo = Qt.QComboBox()
        self.splitter2.addWidget(self.modeCombo)
        self.modeCombo.addItems(self.dev.listModes())
        
        self.splitter3 = Qt.QSplitter()
        self.splitter3.setOrientation(Qt.Qt.Vertical)
        
        (w1, p1) = self.createChannelWidget('primary')
        (w2, p2) = self.createChannelWidget('command')
        
        self.cmdWidget = w2
        self.inputWidget = w1
        self.cmdPlot = p2
        self.inputPlot = p1
        
        #self.ctrlWidget = Qt.QWidget()
        #self.ctrl = Ui_protoCtrl()
        #self.ctrl.setupUi(self.ctrlWidget)
        #self.splitter2.addWidget(self.ctrlWidget)
        
        self.splitter1.addWidget(self.splitter2)
        self.splitter1.addWidget(self.splitter3)
        self.splitter2.addWidget(w1)
        self.splitter2.addWidget(w2)
        self.splitter3.addWidget(p1)
        self.splitter3.addWidget(p2)
        self.splitter1.setSizes([100, 500])
        
        self.stateGroup = WidgetGroup([
            (self.splitter1, 'splitter1'),
            (self.splitter2, 'splitter2'),
            (self.splitter3, 'splitter3'),
        ])
        
        self.modeCombo.currentIndexChanged.connect(self.modeChanged)
        self.modeChanged()
        
        
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        state = {}
        state['daqState'] = DAQGenericTaskGui.saveState(self)
        state['mode'] = self.getMode()
        #state['holdingEnabled'] = self.ctrl.holdingCheck.isChecked()
        #state['holding'] = self.ctrl.holdingSpin.value()
        return state
        
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        self.modeCombo.setCurrentIndex(self.modeCombo.findText(state['mode']))
        #self.ctrl.holdingCheck.setChecked(state['holdingEnabled'])
        #if state['holdingEnabled']:
        #    self.ctrl.holdingSpin.setValue(state['holding'])
        return DAQGenericTaskGui.restoreState(self, state['daqState'])
    
    def generateTask(self, params=None):
        daqTask = DAQGenericTaskGui.generateTask(self, params)
        
        task = {
            'mode': self.getMode(),
            'daqProtocol': daqTask
        }
        
            
        return task
        
    def modeChanged(self):
        #global ivModes
        ivm = self.ivModes[self.getMode()]
        w = self.cmdWidget
        
        if ivm == 'vc':
            scale = 1e-3
            cmdUnits = 'V'
            inpUnits = 'A'
        else:
            scale = 1e-12
            cmdUnits = 'A'
            inpUnits = 'V'
            
        self.inputWidget.setUnits(inpUnits)
        self.cmdWidget.setUnits(cmdUnits)
        self.cmdWidget.setMeta('y', minStep=scale, step=scale*10, value=0.)
        self.inputPlot.setLabel('left', units=inpUnits)
        self.cmdPlot.setLabel('left', units=cmdUnits)
        #w.setScale(scale)
        for s in w.getSpins():
            s.setOpts(minStep=scale)
                
        self.cmdWidget.updateHolding()
    
    def getMode(self):
        return str(self.modeCombo.currentText())

    def getChanHolding(self, chan):
        if chan == 'command':
            return self.dev.getHolding(self.getMode())
        else:
            raise Exception("Can't get holding value for channel %s" % chan)
            

        
class AxoPatchDevGui(Qt.QWidget):
    def __init__(self, dev):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.ui = Ui_devGui()
        self.ui.setupUi(self)
        self.ui.vcHoldingSpin.setOpts(step=1, minStep=1e-3, dec=True, suffix='V', siPrefix=True)
        self.ui.icHoldingSpin.setOpts(step=1, minStep=1e-12, dec=True, suffix='A', siPrefix=True)
        for name in dev.modeNames.values():
            self.ui.modeCombo.addItem(name)
        self.updateStatus()
        
        self.ui.modeCombo.currentIndexChanged.connect(self.modeComboChanged)
        self.ui.vcHoldingSpin.valueChanged.connect(self.vcHoldingChanged)
        self.ui.icHoldingSpin.valueChanged.connect(self.icHoldingChanged)
        self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        self.dev.sigModeChanged.connect(self.devModeChanged)
        
    def updateStatus(self):
        #global modeNames
        mode = self.dev.getMode()
        if mode is None:
            return
        vcHold = self.dev.getHolding('vc')
        icHold = self.dev.getHolding('ic')
        
        self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        self.ui.vcHoldingSpin.setValue(vcHold)
        self.ui.icHoldingSpin.setValue(icHold)

    def devHoldingChanged(self, chan, hval):
        if isinstance(hval, dict):
            self.ui.vcHoldingSpin.blockSignals(True)
            self.ui.icHoldingSpin.blockSignals(True)
            self.ui.vcHoldingSpin.setValue(hval['vc'])
            self.ui.icHoldingSpin.setValue(hval['ic'])
            self.ui.vcHoldingSpin.blockSignals(False)
            self.ui.icHoldingSpin.blockSignals(False)
            
    def devModeChanged(self, mode):
        self.ui.modeCombo.blockSignals(True)
        self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        self.ui.modeCombo.blockSignals(False)
        
    def vcHoldingChanged(self):
        self.dev.setHolding('vc', self.ui.vcHoldingSpin.value())
        
    def icHoldingChanged(self):
        self.dev.setHolding('ic', self.ui.icHoldingSpin.value())
        
    def modeComboChanged(self, m):
        try:
            self.dev.setMode(str(self.ui.modeCombo.itemText(m)))
        except CancelException:
            self.updateStatus()
        
        
class CancelException(Exception):
    pass
