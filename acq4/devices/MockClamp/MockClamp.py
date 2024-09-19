import os
import teleprox
from typing import Literal
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericTaskGui
from acq4.devices.PatchClamp import PatchClamp
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.debug import printExc
from pyqtgraph.WidgetGroup import WidgetGroup

ivModes = {'I=0': 'IC', 'VC': 'VC', 'IC': 'IC'}
modeNames = ['VC', 'I=0', 'IC']


class MockClamp(PatchClamp):
    """
    MockClamp is a class that simulates a patch clamp amplifier.


    Configuration examples::

        # Simuator imported from neuroanalysis
        simulator: 'neuroanalysis'

        # simulator using neuron with cell model downloaded from AllenSDK
        simulator: 'neuron'
        condaEnv: 'allensdk'
        modelId: 491623973  # mouse L5 pvalb perisomatic

    """
    def __init__(self, dm, config, name):
        self.daqConfig = {
            'command': config['Command'],
            'primary': config['ScaledSignal'],
        }

        PatchClamp.__init__(self, dm, config, name)

        # Generate config to use for DAQ 
        self.devLock = Mutex(Mutex.Recursive)

        self.holding = {
            'VC': config.get('vcHolding', -0.05),
            'IC': config.get('icHolding', 0.0)
        }

        self.mode: Literal['VC', 'IC', 'I=0'] = 'I=0'

        self.config = config

        # create a daq device under the hood
        self.daqDev = DAQGeneric(dm, self.daqConfig, f'{name}Daq')

        try:
            self.setHolding()
        except Exception:
            printExc("Error while setting holding value:")

        # Start a remote process to run the simulation.
        self.process = teleprox.ProcessSpawner(conda_env=config.get('condaEnv', None))
        rsys = self.process.client._import('sys')
        rsys.path.append(os.path.abspath(os.path.dirname(__file__)))
        if config['simulator'] == 'builtin':
            self.simulator = self.process.client._import('hhSim')
        elif config['simulator'] == 'neuron':
            self.simulator = self.process.client._import('neuronSim')
            if 'modelId' in config:
                self.simulator.load_allen(config['modelId'])
            else:
                self.simulator.load_default()
        elif config['simulator'] == 'neuroanalysis':
            self.simulator = self.process.client._import('neuroanalysisSim')

        dm.declareInterface(name, ['clamp'], self)

    def createTask(self, cmd, parentTask):
        return MockClampTask(self, cmd, parentTask)

    def taskInterface(self, taskRunner):
        return MockClampTaskGui(self, taskRunner)

    def setHolding(self, mode=None, value=None, force=False):
        global ivModes
        with self.devLock:
            currentMode = self.getMode()
            if mode is None:
                mode = currentMode
            mode = mode.upper()
            ivMode = ivModes[mode]  ## determine vc/ic

            if value is not None:
                self.holding[ivMode] = value

            # if ivMode == ivModes[currentMode] or force:
                # gain = self.getCmdGain(mode)
                ## override the scale since getChanScale won't necessarily give the correct value
                ## (we may be about to switch modes)
                # DAQGeneric.setChanHolding(self, 'command', value, scale=gain)
                # pass
            self.sigHoldingChanged.emit(ivMode, value)
            self.sigStateChanged.emit(self.getState())

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

    def getHolding(self, mode: str = None):
        global ivModes
        with self.devLock:
            if mode is None:
                mode = self.getMode()
            mode = mode.upper()
            if mode == 'I=0':
                return 0.0
            ivMode = ivModes[mode]  # determine vc/ic
            return self.holding[ivMode]

    def getState(self):
        mode = self.getMode()
        return {
            'mode': mode,
            'holding': self.getHolding(mode)
        }

    def getParam(self, name):
        return {'HoldingEnable': True}.get(name)

    def getLastState(self, mode=None):
        mode = mode or self.getMode()
        return {'mode': mode, 'holding': self.getHolding(mode)}

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
            # switch to I=0 first. TODO why?
            self.mode = 'I=0'

        self.setHolding(ivMode)

        ### TODO:
        ### If mode switches back the wrong direction, we need to reset the holding value and cancel.
        self.mode = mode
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

        if chan in ['command', 'secondary']:
            return units[0]
        elif chan == 'primary':
            return units[1]

    def readChannel(self, ch):
        pass

    def quit(self):
        # self.process.send(None)
        self.process.stop()
        self.daqDev.quit()

    def getDAQName(self, channel):
        """Return the DAQ name used by this device. (assumes there is only one DAQ for now)"""
        return self.daqConfig[channel]['device']

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
                daqP['command'] = {'command': cmd['command'], 'holding': dev.getHolding(cmd['mode'])}
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
            'ClampParams': ({} if mode == 'VC' else {
                                'BridgeBalResist': 0,
                                'BridgeBalEnable': True,
                            }),
        }

        ### Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self)

    def read(self):
        ## Called by DAQGeneric to simulate a read-from-DAQ
        return self.job.result(timeout=30)

    def write(self, data, dt):
        ## Called by DAQGeneric to simulate a write-to-DAQ
        self.job = self.clampDev.simulator.run({
            'data': data, 
            'dt': dt, 
            'mode': self.cmd['mode'],
            'vcHolding': self.clampDev.getHolding('VC'),
            'icHolding': self.clampDev.getHolding('IC'),
        }, _sync='async')

    def isDone(self):
        ## check on neuron process
        # return self.process.poll() is not None
        return True

    def stop(self, abort=False):
        DAQGenericTask.stop(self, abort)

    def getResult(self):
        result = DAQGenericTask.getResult(self)
        result._info[-1]['startTime'] = next(iter(result._info[-1][self.clampDev.getDAQName("primary")].values()))['startTime']
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
        return {
            'daqState': DAQGenericTaskGui.saveState(self),
            'mode': self.getMode(),
            # 'holdingEnabled': self.ctrl.holdingCheck.isChecked(),
            # 'holding': self.ctrl.holdingSpin.value(),
        }

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
        return {'mode': self.getMode(), 'daqProtocol': daqTask}

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
            raise ValueError(f"Can't get holding value for channel {chan}")
