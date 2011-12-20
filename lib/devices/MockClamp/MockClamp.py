#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericProtoGui
from Mutex import Mutex, MutexLocker
#from lib.devices.Device import *
from PyQt4 import QtCore, QtGui
import time
import numpy as np
from pyqtgraph.WidgetGroup import WidgetGroup
from advancedTypes import OrderedDict
from debug import printExc
from devTemplate import *
import subprocess, pickle, os

ivModes = {'i=0':'ic', 'vc':'vc', 'ic':'ic'}
modeNames = ['vc', 'i=0', 'ic']
#modeAliases = {'ic': 'I-Clamp', 'i=0': 'I=0', 'vc': 'V-Clamp'}

import multiprocessing as m

class NeuronProc(m.Process):
    def __init__(self):
        self.pipe = m.Pipe()
        m.Process.__init__(self)
        self.daemon = True
        
    def send(self, data):
        self.pipe[0].send(data)
        
    def recv(self):
        return self.pipe[0].recv()
        
    def run(self):
        import neuronSim as nrn
        while True:
            cmd = self.pipe[1].recv()
            if cmd is None:
                break
            try:
                result = nrn.run(cmd)
                self.pipe[1].send(result)
            except:
                import sys
                ex = sys.exc_info()
                sys.excepthook(*ex)
                #self.pipe[1].send(ex)
                #print "sim: exception"
                self.pipe[1].send(None)


class MockClamp(DAQGeneric):
    
    #sigShowModeDialog = QtCore.Signal(object)
    #sigHideModeDialog = QtCore.Signal()
    #sigHoldingChanged = QtCore.Signal(object)  ## provided by DAQGeneric
    sigModeChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):

        # Generate config to use for DAQ 
        daqConfig = {}
        self.devLock = Mutex(Mutex.Recursive)
        
        #if 'ScaledSignal' in config:
            #daqConfig['primary'] = {'type': 'ai', 'channel': config['ScaledSignal']}
        #if 'Command' in config:
            #daqConfig['command'] = {'type': 'ao', 'channel': config['Command']}
            
        
        daqConfig = {
            'command': config['Command'],
            'primary': config['ScaledSignal'],
        }
            
            
        ## Note that both of these channels can be present, but we will only ever record from one at a time.
        ## Usually, we'll record from "I OUTPUT" in current clamp and "10 Vm OUTPUT" in voltage clamp.
        #self.hasSecondaryChannel = True
        #if 'SecondaryVCSignal' in config: 
            #daqConfig['secondary'] = {'type': 'ai', 'channel': config['SecondaryVCSignal']}
        #elif 'SecondaryICSignal' in config:
            #daqConfig['secondary'] = {'type': 'ai', 'channel': config['SecondaryICSignal']}
        #else:
            #self.hasSecondaryChannel = False
            
        self.holding = {
            'vc': config.get('vcHolding', -0.05),
            'ic': config.get('icHolding', 0.0)
        }
        
        self.mode = 'i=0'
        
        self.config = config
        
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        #self.modeLock = Mutex(Mutex.Recursive)
        #self.mdCanceled = False
        
        #self.modeDialog = QtGui.QMessageBox()
        #self.modeDialog.hide()
        #self.modeDialog.setModal(False)
        #self.modeDialog.setWindowTitle("Mode Switch Request")
        #self.modeDialog.addButton(self.modeDialog.Cancel)
        ##QtCore.QObject.connect(self.modeDialog, QtCore.SIGNAL('buttonClicked(QAbstractButton*)'), self.modeDialogClicked)
        #self.modeDialog.buttonClicked.connect(self.modeDialogClicked)
        
        #QtCore.QObject.connect(self, QtCore.SIGNAL('showModeDialog'), self.showModeDialog)
        #QtCore.QObject.connect(self, QtCore.SIGNAL('hideModeDialog'), self.hideModeDialog)
        #self.sigShowModeDialog.connect(self.showModeDialog)
        #self.sigHideModeDialog.connect(self.hideModeDialog)
        
        
        
        try:
            self.setHolding()
        except:
            printExc("Error while setting holding value:")
            
        self.process = NeuronProc()
        self.process.start()
        
        #self.process = subprocess.Popen(
            #('python', os.path.join(modPath,'neuronSim.py')), 
            #bufsize=4096, 
            #stdin=subprocess.PIPE, 
            #stdout=subprocess.PIPE, 
            #stderr=subprocess.PIPE
        #) 
            

    def createTask(self, cmd):
        return MockClampTask(self, cmd)
        
    def protocolInterface(self, prot):
        return MockClampProtoGui(self, prot)
        
    def deviceInterface(self, win):
        return MockClampDevGui(self)
        
        
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
                #gain = self.getCmdGain(mode)
                ## override the scale since getChanScale won't necessarily give the correct value
                ## (we may be about to switch modes)
                #DAQGeneric.setChanHolding(self, 'command', value, scale=gain)
                pass
            #self.emit(QtCore.SIGNAL('holdingChanged'), self.holding.copy())
            self.sigHoldingChanged.emit('primary', self.holding.copy())
            
    def setChanHolding(self, chan, value=None):
        if chan == 'command':
            self.setHolding(value=value)
        else:
            DAQGeneric.setChanHolding(self, chan, value)

    def getChanHolding(self, chan):
        if chan == 'command':
            return self.getHolding()
        else:
            return DAQGeneric.getChanHolding(self, chan)
            
    def getHolding(self, mode=None):
        global ivModes
        with self.devLock:
            if mode is None:
                mode = self.getMode()
            ivMode = ivModes[mode]  ## determine vc/ic
            return self.holding[ivMode]
        
    def listModes(self):
        global modeNames
        return modeNames
        
    def setMode(self, mode):
        """Set the mode of the AxoPatch (by requesting user intervention). Takes care of switching holding levels in I=0 mode if needed."""
        #global modeAliases
        startMode = self.getMode()
        #if mode in modeAliases:
            #mode = modeAliases[mode]
        if startMode == mode:
            return
        
        startIvMode = ivModes[startMode]
        ivMode = ivModes[mode]
        if (startIvMode == 'vc' and ivMode == 'ic') or (startIvMode == 'ic' and ivMode == 'vc'):
            ## switch to I=0 first
            #self.requestModeSwitch('I=0')
            self.mode = 'i=0'
            
        self.setHolding(ivMode, force=True)  ## we're in I=0 mode now, so it's ok to force the holding value.
        
        ### TODO:
        ### If mode switches back the wrong direction, we need to reset the holding value and cancel.
        #self.requestModeSwitch(mode) 
        self.mode = ivMode
        self.sigModeChanged.emit(self.mode)
        
    def getMode(self):
        return self.mode
        ##print "getMode"
        #with self.devLock:
            ##print "  got lock"
            #global mode_tel, modeNames
            #m = self.readChannel('ModeChannel')
            ##print "  read value"
            #if m is None:
                #return None
            #mode = modeNames[np.argmin(np.abs(mode_tel-m))]
            #return mode
    
    #def getLPF(self):
        #with self.devLock:
            #global lpf_tel, lpf_freq
            #f = self.readChannel('LPFChannel')
            #if f is None:
                #return None
            #return lpf_freq[np.argmin(np.abs(lpf_tel-f))]
        
    #def getGain(self):
        #with self.devLock:
            #global gain_tel, gain_vm, gain_im, ivModes
            #mode = self.getMode()
            #if mode is None:
                #return None
            #g = self.readChannel('GainChannel')
            #if g is None:
                #return None
            #if ivModes[mode] == 'vc':
                #return gain_vm[np.argmin(np.abs(gain_tel-g))]
            #else:
                #return gain_im[np.argmin(np.abs(gain_tel-g))]
        
    #def getCmdGain(self, mode=None):
        #with self.devLock:
            #if mode is None:
                #mode = self.getMode()
            #ivMode = ivModes[mode]
            #if ivMode == 'vc':
                #return 50.0 # in VC mode, sensitivity is 20mV/V; scale is 1/20e-3 = 50
            #else:
                #return 5e8 # in IC mode, sensitivity is 2nA/V; scale is 1/2e-9 = 5e8
        
    #def getChanScale(self, chan):
        #if chan == 'command':
            #return self.getCmdGain()
        #elif chan == 'primary':
            #return self.getGain()
        #else:
            #return DAQGeneric.getChanScale(self, chan)
            ##raise Exception("No scale for channel %s" % chan)
        
    def getChanUnits(self, chan):
        global ivModes
        iv = ivModes[self.getMode()]
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
        
    def readChannel(self, ch):
        pass
        #if ch in self.config:
            #chOpts = self.config[ch]
            #dev = chOpts[0]
            #chan = chOpts[1]
            #if len(chOpts) > 2:
                #mode = chOpts[2]
            #else:
                #mode = None
            #dev = self.dm.getDevice(dev)
            #return dev.getChannelValue(chan, mode)
        #else:
            #return None
        
    #def reconfigureSecondaryChannel(self, mode):
        ### Secondary channel changes depending on which mode we're in.
        #if ivModes[mode] == 'vc':
            #if 'SecondaryVCSignal' in self.config:
                #self.reconfigureChannel('secondary', self.config['SecondaryVCSignal'])
        #else:
            #if 'SecondaryICSignal' in self.config:
                #self.reconfigureChannel('secondary', self.config['SecondaryICSignal'])
        
    def quit(self):
        self.process.send(None)
        DAQGeneric.quit(self)
        
class MockClampTask(DAQGenericTask):
    def __init__(self, dev, cmd):
        ## make a few changes for compatibility with multiclamp        
        #print "task:"
        #print cmd
        if 'daqProtocol' not in cmd:
            cmd['daqProtocol'] = {}
            
        daqP = cmd['daqProtocol']
            
        if 'command' in cmd:
            if 'holding' in cmd:
                daqP['command'] = {'command': cmd['command'], 'holding': cmd['holding']}
            else:
                daqP['command'] = {'command': cmd['command']}
        #else:
            #daqP['command'] = {'command': None}
        daqP['command']['lowLevelConf'] = {'mockFunc': self.write}
        ### Make sure we're recording from the correct secondary channel
        #if dev.hasSecondaryChannel:
            #if 'mode' in cmd:
                #mode = cmd['mode']
            #else:
                #mode = dev.getMode()
            #dev.reconfigureSecondaryChannel(mode)
            #cmd['daqProtocol']['secondary'] = {'record': True}
        
        
        cmd['daqProtocol']['primary'] = {'record': True, 'lowLevelConf': {'mockFunc': self.read}}
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'])
        
        #print cmd
        
        self.cmd = cmd

        modPath = os.path.abspath(os.path.split(__file__)[0])
        

    def configure(self, tasks, startOrder):
        ### Record initial state or set initial value
        ##if 'holding' in self.cmd:
        ##    self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        if 'mode' in self.cmd:
            self.dev.setMode(self.cmd['mode'])
        self.ampState = {'mode': self.dev.getMode()}
        
        ### Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self, tasks, startOrder)

    def read(self):
        #print "read"
        #d = pickle.loads(self.process.stdout.read())
        #print "read done"
        #return d
        
        result = self.dev.process.recv()
        #if isinstance(result, Exception):
            #raise result
        #print result, isinstance(result, Exception), result.__class__.__bases__, result.__class__.__bases__[0].__bases__
        return result

    def write(self, data, dt):
        #print "write"
        self.dev.process.send({'data': data, 'dt': dt, 'mode': self.cmd['mode']})
        #self.process.stdin.write(data)
        #self.process.stdin.close()
        #print "write done"
        

    #def getChanScale(self, chan):
        #if chan == 'primary':
            #return self.ampState['gain']
        #elif chan == 'command':
            #return self.dev.getCmdGain(self.ampState['mode'])
        #elif chan == 'secondary':
            #return self.dev.getChanScale('secondary')
        #else:
            #raise Exception("No scale for channel %s" % chan)

    #def start(self):
        #data = pickle.dumps(self.daqTasks['command']['data'])
        #self.process.stdin.write(data)
        #self.process.stdin.close()
    
        
    def isDone(self):
        ## check on neuron process
        #return self.process.poll() is not None
        return True
        
    def stop(self, abort=False):
        #if not self.isDone():
            #if abort:
                #self.process.kill()
            #else:
                #self.process.wait()
        #self.getResult()
        DAQGenericTask.stop(self, abort)
        #self.process.wait()
        
        ## store result locally
        
    #def getChannelData(self, ch):
        #if ch == 'command':
            #return pickle.loads(self.process.stdout.read())

    #def storeResult(self, dirHandle):
        ##DAQGenericTask.storeResult(self, dirHandle)
        ##dirHandle.setInfo(self.ampState)
        #result = self.getResult()
        #result._info[-1]['ClampState'] = self.ampState
        #dirHandle.writeFile(result, self.dev.name)
        

    
class MockClampProtoGui(DAQGenericProtoGui):
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
        
            
        return proto
        
        
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
            

        
class MockClampDevGui(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.ui = Ui_MockClampDevGui()
        self.ui.setupUi(self)
        self.ui.vcHoldingSpin.setOpts(step=1, minStep=1e-3, dec=True, suffix='V', siPrefix=True)
        self.ui.icHoldingSpin.setOpts(step=1, minStep=1e-12, dec=True, suffix='A', siPrefix=True)
        #self.ui.modeCombo.currentIndexChanged.connect(self.modeComboChanged)
        self.modeRadios = {
            'vc': self.ui.vcModeRadio,
            'ic': self.ui.icModeRadio,
            'i=0': self.ui.i0ModeRadio,
        }
        self.updateStatus()
            
        for v in self.modeRadios.itervalues():
            v.toggled.connect(self.modeRadioChanged)
        self.ui.vcHoldingSpin.valueChanged.connect(self.vcHoldingChanged)
        self.ui.icHoldingSpin.valueChanged.connect(self.icHoldingChanged)
        self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        self.dev.sigModeChanged.connect(self.devModeChanged)
        
    def updateStatus(self):
        global modeNames
        mode = self.dev.getMode()
        if mode is None:
            return
        vcHold = self.dev.getHolding('vc')
        icHold = self.dev.getHolding('ic')
        self.modeRadios[mode].setChecked(True)
        #self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
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
        for r in self.modeRadios.itervalues():
            r.blockSignals(True)
        #self.ui.modeCombo.blockSignals(True)
        #self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        self.modeRadios[mode].setChecked(True)
        #self.ui.modeCombo.blockSignals(False)
        for r in self.modeRadios.itervalues():
            r.blockSignals(False)
        
    def vcHoldingChanged(self):
        self.dev.setHolding('vc', self.ui.vcHoldingSpin.value())
        
    def icHoldingChanged(self):
        self.dev.setHolding('ic', self.ui.icHoldingSpin.value())
        
    def modeRadioChanged(self, m):
        try:
            if not m:
                return
            for mode, r in self.modeRadios.iteritems():
                if r.isChecked():
                    self.dev.setMode(mode)
        except CancelException:
            self.updateStatus()
        
        
#class CancelException(Exception):
    #pass
