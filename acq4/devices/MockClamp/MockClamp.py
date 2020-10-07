#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, with_statement

import os

import pyqtgraph.multiprocess as mp
from acq4.devices.AxoPatch200 import CancelException
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericTaskGui
from acq4.devices.PatchClamp import PatchClamp
from pyqtgraph.WidgetGroup import WidgetGroup
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.debug import printExc

Ui_MockClampDevGui = Qt.importTemplate('.devTemplate')

ivModes = {'I=0': 'IC', 'VC': 'VC', 'IC': 'IC'}
modeNames = ['VC', 'I=0', 'IC']


class MockClamp(PatchClamp):

    def __init__(self, dm, config, name):

        PatchClamp.__init__(self, dm, config, name)

        # Generate config to use for DAQ 
        self.devLock = Mutex(Mutex.Recursive)

        daqConfig = {
            'command': config['Command'],
            'primary': config['ScaledSignal'],
        }

        self.holding = {
            'VC': config.get('vcHolding', -0.05),
            'IC': config.get('icHolding', 0.0)
        }

        self.mode = 'I=0'

        self.config = config

        # create a daq device under the hood
        self.daqDev = DAQGeneric(dm, daqConfig, '{}Daq'.format(name))

        try:
            self.setHolding()
        except:
            printExc("Error while setting holding value:")

        # Start a remote process to run the simulation.
        self.process = mp.Process()
        rsys = self.process._import('sys')
        rsys._setProxyOptions(returnType='proxy')  # need to access remote path by proxy, not by value
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
                # gain = self.getCmdGain(mode)
                ## override the scale since getChanScale won't necessarily give the correct value
                ## (we may be about to switch modes)
                # DAQGeneric.setChanHolding(self, 'command', value, scale=gain)
                pass
            self.sigHoldingChanged.emit('primary', self.holding.copy())

    def setChanHolding(self, chan, value=None):
        if chan == 'command':
            self.setHolding(value=value)
        else:
            self.daqDev.setChanHolding(self, chan, value)

    def getChanHolding(self, chan):
        if chan == 'command':
            return self.getHolding()
        else:
            return self.daqDev.getChanHolding(chan)

    def getHolding(self, mode=None):
        global ivModes
        with self.devLock:
            if mode is None:
                mode = self.getMode()
            ivMode = ivModes[mode]  ## determine vc/ic
            return self.holding[ivMode]

    def getState(self):
        return {
            'mode': self.getMode(),
        }

    def listModes(self):
        global modeNames
        return modeNames

    def setMode(self, mode):
        """Set the mode of the AxoPatch (by requesting user intervention). Takes care of switching holding levels in I=0 mode if needed."""
        mode = mode.upper()
        startMode = self.getMode()
        if startMode == mode:
            return

        startIvMode = ivModes[startMode]
        ivMode = ivModes[mode]
        if (startIvMode == 'VC' and ivMode == 'IC') or (startIvMode == 'IC' and ivMode == 'VC'):
            ## switch to I=0 first
            # self.requestModeSwitch('I=0')
            self.mode = 'I=0'

        self.setHolding(ivMode, force=True)  ## we're in I=0 mode now, so it's ok to force the holding value.

        ### TODO:
        ### If mode switches back the wrong direction, we need to reset the holding value and cancel.
        self.mode = ivMode
        self.sigStateChanged.emit(self.getState())

    def getMode(self):
        return self.mode

    def getChanUnits(self, chan):
        global ivModes
        iv = ivModes[self.getMode()]
        if iv == 'VC':
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
        # self.process.send(None)
        self.process.close()
        self.daqDev.quit()

    def getDAQName(self):
        """Return the DAQ name used by this device. (assumes there is only one DAQ for now)"""
        return self.config['Command']['device']

    def autoPipetteOffset(self):
        """Automatically set the pipette offset.
        """
        pass

    def autoBridgeBalance(self):
        """Automatically set the bridge balance.
        """
        pass

    def autoCapComp(self):
        """Automatically configure capacitance compensation.
        """
        pass


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
        DAQGenericTask.__init__(self, dev.daqDev, cmd['daqProtocol'], parentTask)

        self.cmd = cmd
        self.clampDev = dev

        modPath = os.path.abspath(os.path.split(__file__)[0])

    def configure(self):
        ### Record initial state or set initial value
        ##if 'holding' in self.cmd:
        ##    self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        if 'mode' in self.cmd:
            self.clampDev.setMode(self.cmd['mode'])
        mode = self.clampDev.getMode()
        self.ampState = {
            'mode': mode,
            'primaryUnits': 'A' if mode == 'VC' else 'V',
            # copying multiclamp format here, but should eventually pick something more universal 
            'ClampParams': ({
                                'BridgeBalResist': 0,
                                'BridgeBalEnable': True,
                            } if mode == 'IC' else {}),
        }

        ### Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self)

    def read(self):
        ## Called by DAQGeneric to simulate a read-from-DAQ
        res = self.job.result(timeout=30)._getValue()
        return res

    def write(self, data, dt):
        ## Called by DAQGeneric to simulate a write-to-DAQ
        self.job = self.clampDev.simulator.run({'data': data, 'dt': dt, 'mode': self.cmd['mode']}, _callSync='async')

    def isDone(self):
        ## check on neuron process
        # return self.process.poll() is not None
        return True

    def stop(self, abort=False):
        DAQGenericTask.stop(self, abort)

    def getResult(self):
        result = DAQGenericTask.getResult(self)
        result._info[-1]['startTime'] = next(iter(result._info[-1][self.clampDev.getDAQName()].values()))['startTime']
        result._info[-1]['ClampState'] = self.ampState
        return result


class MockClampTaskGui(DAQGenericTaskGui):
    def __init__(self, dev, taskRunner):
        DAQGenericTaskGui.__init__(self, dev.daqDev, taskRunner, ownUi=False)
        self.clampDev = dev

        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.splitter1 = Qt.QSplitter()
        self.splitter1.setOrientation(Qt.Qt.Horizontal)
        self.layout.addWidget(self.splitter1)

        self.splitter2 = Qt.QSplitter()
        self.splitter2.setOrientation(Qt.Qt.Vertical)
        self.modeCombo = Qt.QComboBox()
        self.splitter2.addWidget(self.modeCombo)
        self.modeCombo.addItems(self.clampDev.listModes())

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
        # state['holdingEnabled'] = self.ctrl.holdingCheck.isChecked()
        # state['holding'] = self.ctrl.holdingSpin.value()
        return state

    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        # print 'state: ', state
        # print 'DaqGeneric : ', dir(DAQGenericTaskGui)
        if 'mode' in state:
            self.modeCombo.setCurrentIndex(self.modeCombo.findText(state['mode']))
        # self.ctrl.holdingCheck.setChecked(state['holdingEnabled'])
        # if state['holdingEnabled']:
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

        if ivm == 'VC':
            scale = 1e-3
            cmdUnits = 'V'
            inpUnits = 'A'
        else:
            scale = 1e-12
            cmdUnits = 'A'
            inpUnits = 'V'

        self.inputWidget.setUnits(inpUnits)
        self.cmdWidget.setUnits(cmdUnits)
        self.cmdWidget.setMeta('y', minStep=scale, step=scale * 10, value=0.)
        self.inputPlot.setLabel('left', units=inpUnits)
        self.cmdPlot.setLabel('left', units=cmdUnits)
        # w.setScale(scale)
        # for s in w.getSpins():
        # s.setOpts(minStep=scale)

        self.cmdWidget.updateHolding()

    def getMode(self):
        return str(self.modeCombo.currentText())

    def sequenceChanged(self):
        self.sigSequenceChanged.emit(self.clampDev.name())

    def getChanHolding(self, chan):
        if chan == 'command':
            return self.clampDev.getHolding(self.getMode())
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
        # self.ui.modeCombo.currentIndexChanged.connect(self.modeComboChanged)
        self.modeRadios = {
            'VC': self.ui.vcModeRadio,
            'IC': self.ui.icModeRadio,
            'I=0': self.ui.i0ModeRadio,
        }
        self.updateStatus()

        for v in self.modeRadios.values():
            v.toggled.connect(self.modeRadioChanged)
        self.ui.vcHoldingSpin.valueChanged.connect(self.vcHoldingChanged)
        self.ui.icHoldingSpin.valueChanged.connect(self.icHoldingChanged)
        self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        self.dev.sigStateChanged.connect(self.devStateChanged)

    def updateStatus(self):
        global modeNames
        mode = self.dev.getMode()
        if mode is None:
            return
        vcHold = self.dev.getHolding('VC')
        icHold = self.dev.getHolding('IC')
        self.modeRadios[mode].setChecked(True)
        # self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        self.ui.vcHoldingSpin.setValue(vcHold)
        self.ui.icHoldingSpin.setValue(icHold)

    def devHoldingChanged(self, chan, hval):
        if isinstance(hval, dict):
            self.ui.vcHoldingSpin.blockSignals(True)
            self.ui.icHoldingSpin.blockSignals(True)
            self.ui.vcHoldingSpin.setValue(hval['VC'])
            self.ui.icHoldingSpin.setValue(hval['IC'])
            self.ui.vcHoldingSpin.blockSignals(False)
            self.ui.icHoldingSpin.blockSignals(False)

    def devStateChanged(self):
        mode = self.dev.getMode()
        for r in self.modeRadios.values():
            r.blockSignals(True)
        # self.ui.modeCombo.blockSignals(True)
        # self.ui.modeCombo.setCurrentIndex(self.ui.modeCombo.findText(mode))
        self.modeRadios[mode].setChecked(True)
        # self.ui.modeCombo.blockSignals(False)
        for r in self.modeRadios.values():
            r.blockSignals(False)

    def vcHoldingChanged(self):
        self.dev.setHolding('VC', self.ui.vcHoldingSpin.value())

    def icHoldingChanged(self):
        self.dev.setHolding('IC', self.ui.icHoldingSpin.value())

    def modeRadioChanged(self, m):
        try:
            if not m:
                return
            for mode, r in self.modeRadios.items():
                if r.isChecked():
                    self.dev.setMode(mode)
        except CancelException:
            self.updateStatus()
