from __future__ import print_function
import time, threading
import numpy as np
from ..Pipette import Pipette, PipetteDeviceGui
from acq4.util import Qt
from acq4.util.future import Future
from ...Manager import getManager
from acq4.util.Thread import Thread
from acq4.util.debug import printExc
from acq4.pyqtgraph import ptime, disconnect, metaarray


class PatchPipette(Pipette):
    """Represents a single patch pipette, manipulator, and headstage.

    This class extends from the Pipette device class to provide automation and visual feedback
    on the status of the patch:

        * Whether a cell is currently patched
        * Input resistance, access resistance, and holding levels

    This is also a good place to implement pressure control, autopatching, slow voltage clamp, etc.
    """
    sigStateChanged = Qt.Signal(object, object, object)  # self, newState, oldState
    sigActiveChanged = Qt.Signal(object, object)  # self, active
    sigTestPulseFinished = Qt.Signal(object, object)  # self, TestPulse
    sigTestPulseEnabled = Qt.Signal(object, object)  # self, enabled
    sigUserPressureEnabled = Qt.Signal(object, object)  # self, enabled

    # This attribute can be modified to insert a custom state manager. 
    defaultStateManagerClass = None

    def __init__(self, deviceManager, config, name):
        clampName = config.pop('clampDevice', None)
        self.clampDevice = None if clampName is None else deviceManager.getDevice(clampName)

        Pipette.__init__(self, deviceManager, config, name)
        self.state = "out"
        self.active = False
        self.broken = False
        self.calibrated = False

        self.pressureDevice = None
        if 'pressureDevice' in config:
            self.pressureDevice = PressureControl(config['pressureDevice'])
        self.userPressure = False
        
        self._lastTestPulse = None
        self._initTestPulse(config.get('testPulse', {}))
        self._initStateManager()

        self.sigCalibrationChanged.connect(self._pipetteCalibrationChanged)

        # restore last known state for this pipette
        lastState = self.readConfigFile('last_state')
        self.setState(lastState.get('state', 'out'))
        self.broken = lastState.get('broken', False)
        self.calibrated = lastState.get('calibrated', False)
        self.setActive(False)  # Always start pipettes disabled rather than restoring last state?
        # self.setActive(lastState.get('active', False))

    def getPatchStatus(self):
        """Return a dict describing the status of the patched cell.

        Includes keys:
        * state ('bath', 'sealing', 'on-cell', 'whole-cell', etc..)
        * resting potential
        * resting current
        * input resistance
        * access resistance
        * capacitance
        * clamp mode ('ic' or 'vc')
        * timestamp of last measurement

        """
        # maybe 'state' should be available via a different method?

    def getPressure(self):
        pass

    def setPressure(self, pressure):
        if self.pressureDevice is None:
            return
        self.pressureDevice.setPressure(pressure)        

    def setSelected(self):
        pass

    def approach(self):
        """Prepare pipette to enter tissue and patch a cell.

        - Move pipette to diagonal approach position
        - Auto-correct pipette offset
        - May increase pressure
        - Automatically hide tip/target markers when the tip is near the target
        """

    def seal(self):
        """Attempt to seal onto a cell.

        * switches to VC holding after passing 100 MOhm
        * increase suction if seal does not form
        """

    def setState(self, state):
        """out, bath, approach, seal, attached, breakin, wholecell
        """
        self._stateManager.requestStateChange(state)

    def _setState(self, state):
        """Called by state manager when state has changed.
        """
        oldState = self.state
        self.state = state
        self._writeStateFile()
        self.sigStateChanged.emit(self, state, oldState)

    def _writeStateFile(self):
        state = {
            'state': self.state,
            'active': self.active,
            'calibrated': self.calibrated,
            'broken': self.broken,
        }
        self.writeConfigFile(state, 'last_state')

    def getState(self):
        return self.state

    def breakIn(self):
        """Rupture the cell membrane using negative current pulses.

        * -2 psi for 3 sec or until rupture
        * -4, -6, -8 psi if needed
        * longer wait time if needed
        """

    def newPipette(self):
        """A new physical pipette has been attached; reset any per-pipette state.
        """
        self.broken = False
        self.calibrated = False
        # todo: set calibration to average 
        self.resetTestPulseHistory()

    def _pipetteCalibrationChanged(self):
        self.calibrated = True

    def setActive(self, active):
        self.active = active
        self.sigActiveChanged.emit(self, active)

    def autoPipetteOffset(self):
        clamp = self.clampDevice
        if clamp is not None:
            clamp.autoPipetteOffset()

    def cleanPipette(self):
        config = self.config.get('cleaning', {})
        return PatchPipetteCleanFuture(self, config)

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return PatchPipetteDeviceGui(self, win)

    def _testPulseFinished(self, dev, result):
        self._lastTestPulse = result
        if self._testPulseHistorySize >= self._testPulseHistory.shape[0]:
            newTPH = np.empty(self._testPulseHistory.shape[0]*2, dtype=self._testPulseHistory.dtype)
            newTPH[:self._testPulseHistory.shape[0]] = self._testPulseHistory
            self._testPulseHistory = newTPH
        analysis = result.analysis()
        self._testPulseHistory[self._testPulseHistorySize]['time'] = result.startTime()
        for k in analysis:
            self._testPulseHistory[self._testPulseHistorySize][k] = analysis[k]
        self._testPulseHistorySize += 1

        self.sigTestPulseFinished.emit(self, result)

    def _initTestPulse(self, params):
        self.resetTestPulseHistory()
        self._testPulseThread = TestPulseThread(self, params)
        self._testPulseThread.sigTestPulseFinished.connect(self._testPulseFinished)

    def testPulseHistory(self):
        return self._testPulseHistory[:self._testPulseHistorySize].copy()

    def resetTestPulseHistory(self):
        self._lastTestPulse = None
        self._testPulseHistory = np.empty(1000, dtype=[
            ('time', 'float'),
            ('baselinePotential', 'float'),
            ('baselineCurrent', 'float'),
            ('peakResistance', 'float'),
            ('steadyStateResistance', 'float'),
        ])
            
        self._testPulseHistorySize = 0

    def enableTestPulse(self, enable=True, block=False):
        if enable:
            self._testPulseThread.start()
        else:
            self._testPulseThread.stop(block=block)

    def testPulseEnabled(self):
        return self._testPulseThread.isRunning()

    def lastTestPulse(self):
        return self._lastTestPulse

    def _initStateManager(self):
        # allow external modification of state manager class
        cls = self.defaultStateManagerClass or PatchPipetteStateManager
        self._stateManager = cls(self)

    def quit(self):
        self.enableTestPulse(False, block=True)
        self._stateManager.quit()


class PatchPipetteStateManager(object):
    """Used to monitor the status of a patch pipette and automatically transition between states.

    State manager affects:
     - pipette state ('bath', 'seal', 'wholecell', etc.)
     - clamp mode
     - clamp holding value
     - pressure
     - test pulse
    """
    def __init__(self, dev):
        self.pressureStates = {
            'out': 'atmosphere',
            'bath': 0.5,
            'approach': 0.5,
            'seal': 'user',
        }
        self.clampStates = {   # mode, holding, TP
            'out': ('vc', 0, False),
            'bath': ('vc', 0, True),
            'approach': ('vc', 0, True),
            'seal': ('vc', 0, True),
            'attached': ('vc', -70e-3, True),
            'breakin': ('vc', -70e-3, True),
            'wholecell': ('vc', -70e-3, True),
        }

        self.dev = dev
        self.dev.sigTestPulseFinished.connect(self.testPulseFinished)
        self.dev.sigGlobalTransformChanged.connect(self.transformChanged)
        self.dev.sigStateChanged.connect(self.stateChanged)
        self.dev.sigActiveChanged.connect(self.activeChanged)

    def testPulseFinished(self, dev, result):
        """Called when a test pulse is finished
        """
        pass

    def transformChanged(self):
        """Called when pipette moves relative to global coordinate system
        """
        pass

    def stateChanged(self, oldState, newState):
        """Called when state has changed (possibly by user)
        """
        pass

    def requestStateChange(self, state):
        """Pipette has requested a state change; either accept and configure the new
        state or reject the new state.

        Return the name of the state that has been chosen.
        """
        self.configureState(state)
        return state

    def configureState(self, state):
        if state == 'out':
            # assume that pipette has been changed
            self.dev.newPipette()

        self.setupPressureForState(state)
        self.setupClampForState(state)
        self.dev._setState(state)

    def setupPressureForState(self, state):
        """Configure pressure for the requested state.
        """
        if not self.dev.active:
            return

        pdev = self.dev.pressureDevice
        if pdev is None:
            return
        pressure = self.pressureStates.get(state, None)
        if pressure is None:
            return
        
        if isinstance(pressure, str):
            pdev.setSource(pressure)
            pdev.setPressure(0)
        else:
            pdev.setPressure(pressure)
            pdev.setSource('regulator')

    def setupClampForState(self, state):
        if not self.dev.active:
            return

        cdev = self.dev.clampDevice
        mode, holding, tp = self.clampStates.get(state, (None, None, None))

        if mode is not None:
            cdev.setMode(mode)
            if holding is not None:
                cdev.setHolding(value=holding)

        if state == 'approach':
            cdev.autoPipetteOffset()
            self.dev.resetTestPulseHistory()
        
        if tp is not None:
            self.dev.enableTestPulse(tp)

    def activeChanged(self, pip, active):
        if active:
            self.configureState(self.dev.state)
        else:
            self.dev.enableTestPulse(False)
            self.dev.pressureDevice.setSource('atmosphere')

    def quit(self):
        disconnect(self.dev.sigTestPulseFinished, self.testPulseFinished)
        disconnect(self.dev.sigGlobalTransformChanged, self.transformChanged)
        disconnect(self.dev.sigStateChanged, self.stateChanged)



class PatchPipetteCleanFuture(Future):
    """Tracks the progress of a patch pipette cleaning task.
    """
    def __init__(self, dev, config):
        Future.__init__(self)

        self.dev = dev

        self.config = {
            'cleanSequence': [(-5, 30.), (5, 45)],
            'rinseSequence': [(-5, 30.), (5, 45)],
            'approachHeight': 5e-3,
            'cleanPos': dev.loadPosition('clean'),
            'rinsePos': dev.loadPosition('rinse', None),
        }
        self.config.update(config)

        self._stopRequested = False
        self._thread = threading.Thread(target=self._clean)
        self._thread.start()

    def _clean(self):
        # Called in worker thread
        config = self.config.copy()
        dev = self.dev
        resetPos = None
        print(config)
        try:
            dev.retractFromSurface().wait()

            for stage in ('clean', 'rinse'):
                print(stage)
                self._checkStop()

                sequence = config[stage + 'Sequence']
                if len(sequence) == 0:
                    print("skip")
                    continue
                pos = config[stage + 'Pos']
                approachPos = [pos[0], pos[1], pos[2] + config['approachHeight']]

                dev._moveToGlobal(approachPos, 'fast').wait()
                self._checkStop()
                resetPos = approachPos
                dev._moveToGlobal(pos, 'fast').wait()
                self._checkStop()

                for pressure, delay in sequence:
                    dev.setPressure(pressure)
                    self._checkStop(delay)

        except self.StopRequested:
            self._taskDone(interrupted=True)
        except Exception as exc:
            printExc("Error during pipette cleaning:")
            self._taskDone(interrupted=True, error=str(exc))
        else:
            self._taskDone()
        finally:
            try:
                dev.setPressure(0)
            except Exception:
                printExc("Error resetting pressure after clean")
            
            if resetPos is not None:
                dev._moveToGlobal(resetPos, 'fast')


class TestPulseThread(Thread):

    sigTestPulseFinished = Qt.Signal(object, object)  # device, result

    class StopRequested(Exception):
        pass

    def __init__(self, dev, params):
        Thread.__init__(self, name="TestPulseThread(%s)"%dev.name())
        self.dev = dev
        self._stop = False
        self.params = {
            'clampMode': None,
            'interval': None,
            'sampleRate': 500000,
            'downsample': 20,
            'vcPreDuration': 5e-3,
            'vcPulseDuration': 10e-3,
            'vcPostDuration': 5e-3,
            'vcHolding': None,
            'vcAmplitude': -10e-3,
            'icPreDuration': 10e-3,
            'icPulseDuration': 50e-3,
            'icPostDuration': 30e-3,
            'icHolding': None,
            'icAmplitude': -10e-12,
            'average': 4,
            '_index': 0,
        }
        self._lastTask = None

        self._clampDev = self.dev.clampDevice
        self._daqName = list(self._clampDev.listChannels().values())[0]['device']  ## Just guess the DAQ by checking one of the clamp's channels
        self._clampName = self._clampDev.name()
        self._manager = getManager()

        self.setParameters(**params)

    def setParameters(self, **kwds):
        newParams = self.params.copy()
        for k,v in kwds.items():
            if k not in self.params:
                raise KeyError("Unknown parameter %s" % k)
            newParams[k] = v
        newParams['_index'] += 1
        self.params = newParams

    def start(self):
        self._stop = False
        Thread.start(self)

    def stop(self, block=False):
        self._stop = True
        if block:
            if not self.wait(10000):
                raise RuntimeError("Timed out waiting for test pulse thread exit.")
                
    def run(self):
        while True:
            try:
                self._checkStop()
                start = ptime.time()
                self.runOnce(_checkStop=True)

                interval = self.params['interval']
                if interval is None:
                    # start again immediately
                    continue
                
                # otherwise, wait until interval is over
                while True:
                    nextRun = start + self.params['interval']
                    now = ptime.time()
                    if now >= nextRun:
                        break
                    time.sleep(min(0.03, nextRun-now))
                    self._checkStop()
            except self.StopRequested:
                break
            except Exception:
                printExc("Error in test pulse thread:")
                time.sleep(2.0)

    def runOnce(self, _checkStop=False):
        currentMode = self._clampDev.getMode()
        params = self.params
        runMode = currentMode if params['clampMode'] is None else params['clampMode']
        if runMode == 'I=0':
            runMode = 'IC'

        # Can't reuse tasks yet; remove this when we can.
        self._lastTask = None

        if self._lastTask is None or self._lastTask._paramIndex != params['_index'] or self._lastTask._clampMode != runMode:
            taskParams = params.copy()

            # select parameters to use based on clamp mode
            for k in params:
                # rename like icPulseDuration => pulseDuration
                if k[:2] == runMode.lower():
                    taskParams[k[2].lower() + k[3:]] = taskParams[k]
                # remove all ic__ and vc__ params
                if k[:2] in ('ic', 'vc'):
                    taskParams.pop(k)
                taskParams['clampMode'] = runMode

            task = self.createTask(taskParams)
            task._paramIndex = params['_index']
            task._clampMode = runMode
            self._lastTask = task
        else:
            task = self._lastTask
        
        task.execute()

        while not task.isDone():
            if _checkStop:
                self._checkStop()
            time.sleep(0.01)

        result = task.getResult()
        tp = TestPulse(self._clampDev, taskParams, result)
        tp.analysis()
        self.sigTestPulseFinished.emit(self.dev, tp)
        
        return params, result

    def createTask(self, params):
        duration = params['preDuration'] + params['pulseDuration'] + params['postDuration']
        numPts = int(float(duration * params['sampleRate']) * params['downsample']) // params['downsample']
        params['numPts'] = numPts  # send this back for analysis
        mode = params['clampMode']

        cmdData = np.empty(numPts * params['average'])
        holding = params['holding'] or self._clampDev.getHolding(mode)
        cmdData[:] = holding

        for i in range(params['average']):
            start = (numPts * i) + int(params['preDuration'] * params['sampleRate'])
            stop = start + int(params['pulseDuration'] * params['sampleRate'])
            cmdData[start:stop] += params['amplitude']
        
        cmd = {
            'protocol': {'duration': duration * params['average']},
            self._daqName: {'rate': params['sampleRate'], 'numPts': numPts * params['average'], 'downsample': params['downsample']},
            self._clampName: {
                'mode': mode,
                'command': cmdData,
                'recordState': ['BridgeBalResist', 'BridgeBalEnable'],
            }
        }
        if params['holding'] is not None:
            cmd[self._clampName]['holding'] = params['holding']

        return self._manager.createTask(cmd)

    def _checkStop(self):
        if self._stop:
            raise self.StopRequested()


class TestPulse(object):
    """Represents a single test pulse run, used to analyze and extract features.
    """
    def __init__(self, dev, taskParams, result):
        self.dev = dev
        self.devName = dev.name()
        self.taskParams = taskParams
        self.result = result
        self._analysis = None
        self._average = None

    @property
    def data(self):
        if self._average is None:
            params = self.taskParams
            result = self.result[self.devName]
            if params['average'] == 1:
                self._average = result
            else:
                numPts = params['numPts'] // params['downsample']
                pri = result['Channel': 'primary']
                avg = np.zeros(numPts)
                for i in range(params['average']):
                    avg += pri[i*numPts:(i+1)*numPts]
                avg /= params['average']
                self._average = result['Time':0:numPts].copy()
                self._average['Channel': 'primary']._data[:] = avg

        return self._average

    def startTime(self):
        return self.result[self.devName]._info[-1]['startTime']

    def analysis(self):
        if self._analysis is not None:
            return self._analysis
        analysis = {}
        params = self.taskParams
        pri = self.data['Channel': 'primary']

        base = pri['Time': 0:params['preDuration']]
        peak = pri['Time': params['preDuration']:params['preDuration']+2e-3]
        steady  = pri['Time': params['preDuration']:params['preDuration']+params['pulseDuration']-2e-3]
        peakValue = peak.max()
        steadyValue = np.median(steady)
        baseValue = np.median(base)

        if params['clampMode'] == 'VC':
            analysis['baselinePotential'] = params['holding'] or 0
            analysis['baselineCurrent'] = baseValue
            analysis['peakResistance'] = params['amplitude'] / (peakValue - baseValue)
            analysis['steadyStateResistance'] = params['amplitude'] / (steadyValue - baseValue)

        else:
            bridge = self.data._info[-1]['ClampState']['ClampParams']['BridgeBalResist']
            bridgeOn = self.data._info[-1]['ClampState']['ClampParams']['BridgeBalEnable']
            if not bridgeOn:
                bridge = 0.0
            analysis['baselineCurrent'] = params['holding'] or 0
            analysis['baselinePotential'] = baseValue
            analysis['peakResistance'] = bridge + (peakValue - baseValue) / params['amplitude']
            analysis['steadyStateResistance'] = bridge + (steadyValue - baseValue) / params['amplitude']

        analysis['peakResistance'] = np.clip(analysis['peakResistance'], 0, 20e9)
        analysis['steadyStateResistance'] = np.clip(analysis['steadyStateResistance'], 0, 20e9)

        self._analysis = analysis


class PressureControl(Qt.QObject):
    def __init__(self, deviceName):
        Qt.QObject.__init__(self)
        man = getManager()
        self.device = man.getDevice(deviceName)

    def setPressure(self, p):
        """Set the regulated output pressure to the pipette.

        Note: this does _not_ change the configuration of any values.
        """
        self.device.setChanHolding('pressure_out', p)

    def setSource(self, mode):
        """Configure valves for the specified pressure source: "atmosphere", "user", or "regulator"
        """
        if mode == 'atmosphere':
            self.device.setChanHolding('user_valve', 0)
            self.device.setChanHolding('regulator_valve', 0)
        elif mode == 'user':
            self.device.setChanHolding('user_valve', 1)
            self.device.setChanHolding('regulator_valve', 0)
        elif mode == 'regulator':
            self.device.setChanHolding('regulator_valve', 1)
        else:
            raise ValueError("Unknown pressure source %r" % mode)


class PatchPipetteDeviceGui(PipetteDeviceGui):
    def __init__(self, dev, win):
        self.cleanFuture = None

        PipetteDeviceGui.__init__(self, dev, win)

        self.cleanBtn = Qt.QPushButton('Clean Pipette')
        self.setCleanBtn = Qt.QPushButton('Set Clean Pos')
        self.setRinseBtn = Qt.QPushButton('Set Rinse Pos')
        self.cleanBtnLayout = Qt.QHBoxLayout()
        self.cleanBtnLayout.addWidget(self.cleanBtn)
        self.cleanBtn.setCheckable(True)
        self.cleanBtnLayout.addWidget(self.setCleanBtn)
        self.cleanBtnLayout.addWidget(self.setRinseBtn)
        row = self.layout.rowCount()
        self.layout.addLayout(self.cleanBtnLayout, row, 0)

        self.cleanBtn.clicked.connect(self.cleanClicked)
        self.setCleanBtn.clicked.connect(self.setCleanClicked)
        self.setRinseBtn.clicked.connect(self.setRinseClicked)

    def cleanClicked(self):
        if self.cleanBtn.isChecked():
            self.cleanBtn.setText("Cleaning..")
            self.cleanFuture = self.dev.cleanPipette()
            self.cleanFuture.sigFinished.connect(self.cleaningFinished)
        else:
            if self.cleanFuture is not None and not self.cleanFuture.isDone():
                self.cleanFuture.stop()
            self.cleanBtn.setText("Clean Pipette")

    def cleaningFinished(self):
        self.cleanBtn.setText("Clean Pipette")
        self.cleanBtn.setChecked(False)

    def setCleanClicked(self):
        self.dev.savePosition('clean')

    def setRinseClicked(self):
        self.dev.savePosition('rinse')
