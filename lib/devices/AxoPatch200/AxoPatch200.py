#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericProtoGui
from Mutex import Mutex, MutexLocker
#from lib.devices.Device import *
from PyQt4 import QtCore, QtGui
import time
import numpy as np
from WidgetGroup import *
from advancedTypes import OrderedDict
from debug import printExc
from devGuiTemplate import *

# telegraph voltage/output translation from the Axopatch 200 amplifier
mode_tel = np.array([6, 4, 3, 2, 1])
#mode_char = ['V', 'T', '0', 'I', 'F']
modeNames = OrderedDict([(0, 'V-Clamp'), (2, 'I=0'), (4, 'I-Clamp Fast'), (3, 'I-Clamp Normal'), (1, 'Track'), ])
ivModes = {'V-Clamp':'vc', 'Track':'vc', 'I=0':'ic', 'I-Clamp Fast':'ic', 'I-Clamp Normal':'ic', 'vc':'vc', 'ic':'ic'}
modeAliases = {'ic': 'I-Clamp Fast', 'i=0': 'I=0', 'vc': 'V-Clamp'}

# Axopatch gain telegraph
# telegraph should not read below 2 V in CC mode
gain_tel = np.array([0.5,  1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5])
gain_vm  = np.array([0.5,  0.5, 0.5, 0.5, 1,   2,   5,   10,  20,  50,  100, 200, 500]) * 1e9  ## values in mv/pA
gain_im  = np.array([0.05, 0.1, 0.2, 0.5, 1,   2,   5,   10,  20,  50,  100, 200, 500])        ## values in mV/mV

# Axopatch LPF telegraph
lpf_tel = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
lpf_freq = np.array([1.0, 2.0, 5.0, 10.0, 100.0])

        #GainChannel: 'DAQ', '/Dev1/ai14'
        #LPFchannel: 'DAQ', '/Dev1/ai15'
        #VCommand: 'DAQ', '/Dev1/ao0'
        #ScaledSignal: 'DAQ', '/Dev1/ai5'
        
class AxoPatch200(DAQGeneric):
    
    sigShowModeDialog = QtCore.Signal(object)
    sigHideModeDialog = QtCore.Signal()
    sigHoldingChanged = QtCore.Signal(object)
    sigModeChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):

        # Generate config to use for DAQ 
        daqConfig = {}
        
        ## Don't sctually need to inform the DAQ about these channels.
        #if 'GainChannel' in config:
        #    daqConfig['gain'] = {'type': 'ai', 'channel': config['GainChannel']}
        #if 'LPFChannel' in config:
        #    daqConfig['LPF'] = {'type': 'ai', 'channel': config['LPFChannel'], 'units': 'Hz'}
        if 'ScaledSignal' in config:
            daqConfig['primary'] = {'type': 'ai', 'channel': config['ScaledSignal']}
        if 'Command' in config:
            daqConfig['command'] = {'type': 'ao', 'channel': config['Command']}
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        self.holding = {
            'vc': config.get('vcHolding', -0.05),
            'ic': config.get('icHolding', 0.0)
        }
        
        self.config = config
        self.modeLock = Mutex(Mutex.Recursive)
        self.devLock = Mutex(Mutex.Recursive)
        self.mdCanceled = False
        
        self.modeDialog = QtGui.QMessageBox()
        self.modeDialog.hide()
        self.modeDialog.setModal(False)
        self.modeDialog.setWindowTitle("Mode Switch Request")
        self.modeDialog.addButton(self.modeDialog.Cancel)
        #QtCore.QObject.connect(self.modeDialog, QtCore.SIGNAL('buttonClicked(QAbstractButton*)'), self.modeDialogClicked)
        self.modeDialog.buttonClicked.connect(self.modeDialogClicked)
        
        #QtCore.QObject.connect(self, QtCore.SIGNAL('showModeDialog'), self.showModeDialog)
        #QtCore.QObject.connect(self, QtCore.SIGNAL('hideModeDialog'), self.hideModeDialog)
        self.sigShowModeDialog.connect(self.showModeDialog)
        self.sigHideModeDialog.connect(self.hideModeDialog)
        
        
        
        try:
            self.setHolding()
        except:
            printExc("Error while setting holding value:")

    def createTask(self, cmd):
        return AxoPatch200Task(self, cmd)
        
    def protocolInterface(self, prot):
        return AxoPatchProtoGui(self, prot)
        
    def deviceInterface(self, win):
        return AxoPatchDevGui(self)
        
        
    def setHolding(self, mode=None, value=None, force=False):
        #print "setHolding", mode, value
        global ivModes
        with self.devLock:
            currentMode = self.getMode()
            if mode is None:
                mode = currentMode
            ivMode = ivModes[mode]  ## determine vc/ic
                
            if value is None:
                value = self.holding[ivMode]
            else:
                self.holding[ivMode] = value
            
            if ivMode == ivModes[currentMode] or force:
                gain = self.getCmdGain(mode)
                ## override the scale since getChanScale won't necessarily give the correct value
                ## (we may be about to switch modes)
                DAQGeneric.setChanHolding(self, 'command', value, scale=gain)
            #self.emit(QtCore.SIGNAL('holdingChanged'), self.holding.copy())
            self.sigHoldingChanged.emit(self.holding.copy())
            
    def setChanHolding(self, chan, value=None):
        if chan == 'command':
            self.setHolding(value=value)
        
    def getHolding(self, mode=None):
        global ivModes
        with self.devLock:
            if mode is None:
                mode = self.getMode()
            ivMode = ivModes[mode]  ## determine vc/ic
            return self.holding[ivMode]
        
    def listModes(self):
        global modeNames
        return modeNames.values()
        
    def setMode(self, mode):
        """Set the mode of the AxoPatch (by requesting user intervention). Takes care of switching holding levels in I=0 mode if needed."""
        global modeAliases
        startMode = self.getMode()
        if mode in modeAliases:
            mode = modeAliases[mode]
        if startMode == mode:
            return
        
        startIvMode = ivModes[startMode]
        ivMode = ivModes[mode]
        if (startIvMode == 'vc' and ivMode == 'ic') or (startIvMode == 'ic' and ivMode == 'vc'):
            ## switch to I=0 first
            self.requestModeSwitch('I=0')
            
        self.setHolding(ivMode, force=True)  ## we're in I=0 mode now, so it's ok to force the holding value.
        
        ## TODO:
        ## If mode switches back the wrong direction, we need to reset the holding value and cancel.
        self.requestModeSwitch(mode) 
        
    def requestModeSwitch(self, mode):
        """Pop up a dialog asking the user to switch the amplifier mode, wait for change. This function is thread-safe."""
        global modeNames
        with self.modeLock:
            self.mdCanceled = False
        app = QtGui.QApplication.instance()
        msg = 'Please set AxoPatch mode switch to %s' % mode
        #self.emit(QtCore.SIGNAL('showModeDialog'), msg)
        self.sigShowModeDialog.emit(msg)
        
        #print "Set mode:", mode
        ## Wait for the mode to change to the one we're waiting for, or for a cancel
        while True:
            if QtCore.QThread.currentThread() == app.thread():
                app.processEvents()
            else:
                QtCore.QThread.yieldCurrentThread()
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
        #self.emit(QtCore.SIGNAL('hideModeDialog'))
        #self.emit(QtCore.SIGNAL('modeChanged'), mode)
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
            global mode_tel, modeNames
            m = self.readChannel('ModeChannel')
            #print "  read value"
            if m is None:
                return None
            mode = modeNames[np.argmin(np.abs(mode_tel-m))]
            return mode
    
    def getLPF(self):
        with self.devLock:
            global lpf_tel, lpf_freq
            f = self.readChannel('LPFChannel')
            if f is None:
                return None
            return lpf_freq[np.argmin(np.abs(lpf_tel-f))]
        
    def getGain(self):
        with self.devLock:
            global gain_tel, gain_vm, gain_im, ivModes
            mode = self.getMode()
            if mode is None:
                return None
            g = self.readChannel('GainChannel')
            if g is None:
                return None
            if ivModes[mode] == 'vc':
                return gain_vm[np.argmin(np.abs(gain_tel-g))]
            else:
                return gain_im[np.argmin(np.abs(gain_tel-g))]
        
    def getCmdGain(self, mode=None):
        with self.devLock:
            if mode is None:
                mode = self.getMode()
            ivMode = ivModes[mode]
            if ivMode == 'vc':
                return 50.0 # in VC mode, sensitivity is 20mV/V; scale is 1/20e-3 = 50
            else:
                return 5e8 # in IC mode, sensitivity is 2nA/V; scale is 1/2e-9 = 5e8
        
    def getChanScale(self, chan):
        if chan == 'command':
            return self.getCmdGain()
        elif chan == 'primary':
            return self.getGain()
        else:
            raise Exception("No scale for channel %s" % chan)
        
    def getChanUnits(self, chan):
        global ivModes
        iv = ivModes[self.getMode()]
        if iv == 'vc':
            units = ['V', 'A']
        else:
            units = ['A', 'V']
            
        if chan == 'command':
            return units[0]
        elif chan == 'primary':
            return units[1]
        
    def readChannel(self, ch):
        if ch in self.config:
            chOpts = self.config[ch]
            dev = chOpts[0]
            chan = chOpts[1]
            if len(chOpts) > 2:
                mode = chOpts[2]
            else:
                mode = None
            dev = self.dm.getDevice(dev)
            return dev.getChannelValue(chan, mode)
        else:
            return None
        
class AxoPatch200Task(DAQGenericTask):
    def __init__(self, dev, cmd):
        ## make a few changes for compatibility with multiclamp
        if 'daqProtocol' not in cmd:
            cmd['daqProtocol'] = {}
        if 'command' in cmd:
            if 'holding' in cmd:
                cmd['daqProtocol']['command'] = {'command': cmd['command'], 'holding': cmd['holding']}
            else:
                cmd['daqProtocol']['command'] = {'command': cmd['command']}
            
        cmd['daqProtocol']['primary'] = {'record': True}
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'])
        self.cmd = cmd

    def configure(self, tasks, startOrder):
        ## Record initial state or set initial value
        #if 'holding' in self.cmd:
        #    self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        if 'mode' in self.cmd:
            self.dev.setMode(self.cmd['mode'])
        self.ampState = {'mode': self.dev.getMode(), 'LPF': self.dev.getLPF(), 'gain': self.dev.getGain()}
        
        ## Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self, tasks, startOrder)
        
    def getChanScale(self, chan):
        if chan == 'primary':
            return self.ampState['gain']
        if chan == 'command':
            return self.dev.getCmdGain(self.ampState['mode'])
            
    def storeResult(self, dirHandle):
        DAQGenericTask.storeResult(self, dirHandle)
        dirHandle.setInfo(self.ampState)

    
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
        self.modeCombo = QtGui.QComboBox()
        self.splitter2.addWidget(self.modeCombo)
        self.modeCombo.addItems(self.dev.listModes())
        
        self.splitter3 = QtGui.QSplitter()
        self.splitter3.setOrientation(QtCore.Qt.Vertical)
        
        (w1, p1) = self.createChannelWidget('primary')
        (w2, p2) = self.createChannelWidget('command')
        
        self.cmdWidget = w2
        self.inputWidget = w1
        self.cmdPlot = p2
        self.inputPlot = p1
        
        #self.ctrlWidget = QtGui.QWidget()
        #self.ctrl = Ui_protoCtrl()
        #self.ctrl.setupUi(self.ctrlWidget)
        #self.splitter2.addWidget(self.ctrlWidget)
        
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
        
        #QtCore.QObject.connect(self.ctrl.holdingCheck, QtCore.SIGNAL('stateChanged(int)'), self.holdingCheckChanged)
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('holdingChanged'), self.holdingChanged)
        #QtCore.QObject.connect(self.modeCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.modeChanged)
        self.modeCombo.currentIndexChanged.connect(self.modeChanged)
        self.modeChanged()
        
        
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        state = {}
        state['daqState'] = DAQGenericProtoGui.saveState(self)
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
        return DAQGenericProtoGui.restoreState(self, state['daqState'])
    
    def generateProtocol(self, params=None):
        daqProto = DAQGenericProtoGui.generateProtocol(self, params)
        
        proto = {
            'mode': self.getMode(),
            'daqProtocol': daqProto
        }
        
        ## we want to handle holding values manually
        #if 'holding' in daqProto['Command']:
        #    proto['holding'] = daqProto['holding']
        #    del daqProto['holding']
        #if 'holding' in daqProto['Command']:
        #    proto['holding'] = daqProto['holding']
        #    del daqProto['holding']
        
        #if self.ctrl.holdingCheck.isChecked():
        #    proto['holding'] = self.ctrl.holdingSpin.value()
            
        return proto
        
    #def holdingCheckChanged(self, v):
    #    self.ctrl.holdingSpin.setEnabled(self.ctrl.holdingCheck.isChecked())
    #    self.holdingChanged()
            
    #def holdingChanged(self, *args):
    #    
    #    if not self.ctrl.holdingCheck.isChecked():
    #        hv = self.dev.getHolding(self.getMode())
    #        self.ctrl.holdingSpin.setValue(hv)
        
    def modeChanged(self):
        global ivModes
        ivm = ivModes[self.getMode()]
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
        self.inputPlot.setLabel('left', units=inpUnits)
        self.cmdPlot.setLabel('left', units=cmdUnits)
        w.setScale(scale)
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
            

        
class AxoPatchDevGui(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.ui = Ui_devGui()
        self.ui.setupUi(self)
        self.ui.vcHoldingSpin.setOpts(step=1, minStep=1e-3, dec=True, suffix='V', siPrefix=True)
        self.ui.icHoldingSpin.setOpts(step=1, minStep=1e-12, dec=True, suffix='A', siPrefix=True)
        self.updateStatus()
        #QtCore.QObject.connect(self.ui.modeCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.modeComboChanged)
        self.ui.modeCombo.currentIndexChanged.connect(self.modeComboChanged)
        #QtCore.QObject.connect(self.ui.vcHoldingSpin, QtCore.SIGNAL('valueChanged(double)'), self.vcHoldingChanged)
        self.ui.vcHoldingSpin.valueChanged.connect(self.vcHoldingChanged)
        #QtCore.QObject.connect(self.ui.icHoldingSpin, QtCore.SIGNAL('valueChanged(double)'), self.icHoldingChanged)
        self.ui.icHoldingSpin.valueChanged.connect(self.icHoldingChanged)
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('holdingChanged'), self.devHoldingChanged)
        self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('modeChanged'), self.devModeChanged)
        self.dev.sigModeChanged.connect(self.devModeChanged)
        
    def updateStatus(self):
        global modeNames
        mode = self.dev.getMode()
        if mode is None:
            return
        vcHold = self.dev.getHolding('vc')
        icHold = self.dev.getHolding('ic')
        self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        self.ui.vcHoldingSpin.setValue(vcHold)
        self.ui.icHoldingSpin.setValue(icHold)

    def devHoldingChanged(self, *args):
        if len(args) > 0 and isinstance(args[0], dict):
            self.ui.vcHoldingSpin.blockSignals(True)
            self.ui.icHoldingSpin.blockSignals(True)
            self.ui.vcHoldingSpin.setValue(args[0]['vc'])
            self.ui.icHoldingSpin.setValue(args[0]['ic'])
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