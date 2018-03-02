#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericTaskGui
from acq4.util.Mutex import Mutex
#from acq4.devices.Device import *
from acq4.util import Qt
import time
import numpy as np
from acq4.pyqtgraph.WidgetGroup import WidgetGroup
from collections import OrderedDict
from acq4.util.debug import printExc
from .devTemplate import *
import subprocess, pickle, os
import acq4.pyqtgraph.multiprocess as mp

ivModes = {'i=0':'ic', 'vc':'vc', 'ic':'ic'}
modeNames = ['vc', 'i=0', 'ic']


class MockClamp(DAQGeneric):
    
    sigModeChanged = Qt.Signal(object)

    def __init__(self, dm, config, name):

        # Generate config to use for DAQ 
        self.devLock = Mutex(Mutex.Recursive)
        
        daqConfig = {
            'command': config['Command'],
            'primary': config['ScaledSignal'],
        }
            
        self.holding = {
            'vc': config.get('vcHolding', -0.05),
            'ic': config.get('icHolding', 0.0)
        }
        
        self.mode = 'i=0'
        
        self.config = config
        
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        try:
            self.setHolding()
        except:
            printExc("Error while setting holding value:")
            
        # Start a remote process to run the simulation.
        self.process = mp.Process()
        rsys = self.process._import('sys')
        rsys._setProxyOptions(returnType='proxy') # need to access remote path by proxy, not by value
        rsys.path.append(os.path.abspath(os.path.dirname(__file__)))
        if config['simulator'] == 'builtin':
            self.simulator = self.process._import('hhSim')
        elif config['simulator'] == 'neuron':
            self.simulator = self.process._import('neuronSim')
        
        dm.declareInterface(name, ['clamp'], self)

    def createTask(self, cmd, parentTask):
        return MockClampTask(self, cmd, parentTask)
        
    def taskInterface(self, taskRunner):
        return MockClampTaskGui(self, taskRunner)
        
    def deviceInterface(self, win):
        return MockClampDevGui(self)
        
        
    def setHolding(self, mode=None, value=None, force=False):
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
        startMode = self.getMode()
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
        self.mode = ivMode
        self.sigModeChanged.emit(self.mode)
        
    def getMode(self):
        return self.mode
        
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
        
    def quit(self):
        #self.process.send(None)
        self.process.close()
        DAQGeneric.quit(self)
        
class MockClampTask(DAQGenericTask):
    def __init__(self, dev, cmd, parentTask):
        ## make a few changes for compatibility with multiclamp        
        if 'daqProtocol' not in cmd:
            cmd['daqProtocol'] = {}
            
        daqP = cmd['daqProtocol']
            
        if 'command' in cmd:
            if 'holding' in cmd:
                daqP['command'] = {'command': cmd['command'], 'holding': cmd['holding']}
            else:
                daqP['command'] = {'command': cmd['command']}
        daqP['command']['lowLevelConf'] = {'mockFunc': self.write}
        
        
        cmd['daqProtocol']['primary'] = {'record': True, 'lowLevelConf': {'mockFunc': self.read}}
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'], parentTask)
        
        self.cmd = cmd

        modPath = os.path.abspath(os.path.split(__file__)[0])
        

    def configure(self):
        ### Record initial state or set initial value
        ##if 'holding' in self.cmd:
        ##    self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        if 'mode' in self.cmd:
            self.dev.setMode(self.cmd['mode'])
        self.ampState = {'mode': self.dev.getMode()}
        
        ### Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self)

    def read(self):
        ## Called by DAQGeneric to simulate a read-from-DAQ
        res = self.job.result(timeout=30)._getValue()
        return res

    def write(self, data, dt):
        ## Called by DAQGeneric to simulate a write-to-DAQ
        self.job = self.dev.simulator.run({'data': data, 'dt': dt, 'mode': self.cmd['mode']}, _callSync='async')

    def isDone(self):
        ## check on neuron process
        #return self.process.poll() is not None
        return True
        
    def stop(self, abort=False):
        DAQGenericTask.stop(self, abort)
        
        
        

    
class MockClampTaskGui(DAQGenericTaskGui):
    def __init__(self, dev, taskRunner):
        DAQGenericTaskGui.__init__(self, dev, taskRunner, ownUi=False)
        
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
        self.cmdWidget.setMeta('x', siPrefix=True, suffix='s', dec=True)
        self.cmdWidget.setMeta('y', siPrefix=True, dec=True)
        
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
        #print 'state: ', state
        #print 'DaqGeneric : ', dir(DAQGenericTaskGui)
        if 'mode' in state:
            self.modeCombo.setCurrentIndex(self.modeCombo.findText(state['mode']))
        #self.ctrl.holdingCheck.setChecked(state['holdingEnabled'])
        #if state['holdingEnabled']:
        #    self.ctrl.holdingSpin.setValue(state['holding'])
        if 'daqState' in state:
            return DAQGenericTaskGui.restoreState(self, state['daqState'])
        else:
            return None
            
    def generateTask(self, params=None):
        daqTask = DAQGenericTaskGui.generateTask(self, params)
        
        task = {
            'mode': self.getMode(),
            'daqProtocol': daqTask
        }
        
            
        return task
        
        
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
        self.cmdWidget.setMeta('y', minStep=scale, step=scale*10, value=0.)
        self.inputPlot.setLabel('left', units=inpUnits)
        self.cmdPlot.setLabel('left', units=cmdUnits)
        #w.setScale(scale)
        #for s in w.getSpins():
            #s.setOpts(minStep=scale)
                
        self.cmdWidget.updateHolding()
    
    def getMode(self):
        return str(self.modeCombo.currentText())

    def getChanHolding(self, chan):
        if chan == 'command':
            return self.dev.getHolding(self.getMode())
        else:
            raise Exception("Can't get holding value for channel %s" % chan)
            

        
class MockClampDevGui(Qt.QWidget):
    def __init__(self, dev):
        Qt.QWidget.__init__(self)
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
            
        for v in self.modeRadios.values():
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
        for r in self.modeRadios.values():
            r.blockSignals(True)
        #self.ui.modeCombo.blockSignals(True)
        #self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        self.modeRadios[mode].setChecked(True)
        #self.ui.modeCombo.blockSignals(False)
        for r in self.modeRadios.values():
            r.blockSignals(False)
        
    def vcHoldingChanged(self):
        self.dev.setHolding('vc', self.ui.vcHoldingSpin.value())
        
    def icHoldingChanged(self):
        self.dev.setHolding('ic', self.ui.icHoldingSpin.value())
        
    def modeRadioChanged(self, m):
        try:
            if not m:
                return
            for mode, r in self.modeRadios.items():
                if r.isChecked():
                    self.dev.setMode(mode)
        except CancelException:
            self.updateStatus()
        
        
