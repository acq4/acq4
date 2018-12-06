from __future__ import print_function
import time, threading
import numpy as np
from ..Pipette import Pipette, PipetteDeviceGui
from acq4.util import Qt
from acq4.util.future import Future
from ...Manager import getManager
from acq4.util.Thread import Thread
from acq4.util.debug import printExc
from acq4.pyqtgraph import ptime


class PatchPipette(Pipette):
    """Represents a single patch pipette, manipulator, and headstage.

    This class extends from the Pipette device class to provide automation and visual feedback
    on the status of the patch:

        * Whether a cell is currently patched
        * Input resistance, access resistance, and holding levels

    This is also a good place to implement pressure control, autopatching, slow voltage clamp, etc.
    """
    sigStateChanged = Qt.Signal(object)

    def __init__(self, deviceManager, config, name):
        self.pressures = {
            'out': 'atmosphere',
            'bath': 0.5,
            'approach': 0.5,
            'seal': 'user',
        }

        self._clampName = config.pop('clampDevice', None)
        self._clampDevice = None

        Pipette.__init__(self, deviceManager, config, name)
        self.state = "out"
        self.active = False

        self.pressureDevice = None
        if 'pressureDevice' in config:
            self.pressureDevice = PressureControl(config['pressureDevice'])

        self._initTestPulse(config.get('testPulse', {}))

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
        if self.pressureDevice is not None and state in self.pressures:
            p = self.pressures[state]
            if isinstance(p, str):
                self.pressureDevice.setSource(p)
                self.pressureDevice.setPressure(0)
            else:
                self.pressureDevice.setPressure(p)
                self.pressureDevice.setSource('regulator')

        self.state = state
        self.sigStateChanged.emit(self)

    def getState(self):
        return self.state

    def breakIn(self):
        """Rupture the cell membrane using negative current pulses.

        * -2 psi for 3 sec or until rupture
        * -4, -6, -8 psi if needed
        * longer wait time if needed
        """

    def setActive(self, active):
        self.active = active

    def clampDevice(self):
        if self._clampDevice is None:
            if self._clampName is None:
                return None
            self._clampDevice = getManager().getDevice(self._clampName)
        return self._clampDevice

    def autoPipetteOffset(self):
        clamp = self.clampDevice()
        if clamp is not None:
            clamp.autoPipetteOffset()

    def cleanPipette(self):
        config = self.config.get('cleaning', {})
        return PatchPipetteCleanFuture(self, config)

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return PatchPipetteDeviceGui(self, win)

    def _testPulseFinished(self, dev, params, result):
        self._lastTestPulse = (params, result)

    def _initTestPulse(self, params):
        self._testPulseThread = TestPulseThread(self, params)
        self._testPulseThread.sigTestPulseFinished.connect(self._testPulseFinished)

    def startTestPulse(self):
        self._testPulseThread.start()

    def stopTestPulse(self):
        self._testPulseThread.stop()


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

    sigTestPulseFinished = Qt.Signal(object, object, object)  # device, params, result

    class StopRequested(Exception):
        pass

    def __init__(self, dev, params):
        Thread.__init__(self)
        self.dev = dev
        self._stop = False
        self.params = {
            'clampMode': None,
            'interval': None,
            'sampleRate': 100000,
            'downsample': 4,
            'vcPreDuration': 10e-3,
            'vcPulseDuration': 10e-3,
            'vcPostDuration': 10e-3,
            'vcHolding': None,
            'vcAmplitude': -10e-3,
            'icPreDuration': 10e-3,
            'icPulseDuration': 30e-3,
            'icPostDuration': 10e-3,
            'icHolding': None,
            'icAmplitude': -10e-12,
            '_index': 0,
        }
        self._lastTask = None

        self._clampDev = self.dev.clampDevice()
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

    def stop(self):
        self._stop = True

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
        self._clampDev.reserve()
        try:
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
            self.sigTestPulseFinished.emit(self.dev, taskParams, result)
        finally:
            self._clampDev.release()
        
        return params, result

    def createTask(self, params):
        duration = params['preDuration'] + params['pulseDuration'] + params['postDuration']
        numPts = int(float(duration * params['sampleRate']))
        mode = params['clampMode']

        cmdData = np.empty(numPts)
        holding = params['holding'] or self._clampDev.getHolding(mode)
        cmdData[:] = holding

        start = int(params['preDuration'] * params['sampleRate'])
        stop = start + int(params['pulseDuration'] * params['sampleRate'])
        cmdData[start:stop] += params['amplitude']
        
        cmd = {
            'protocol': {'duration': duration},
            self._daqName: {'rate': params['sampleRate'], 'numPts': numPts, 'downsample': params['downsample']},
            self._clampName: {
                'mode': mode,
                'command': cmdData,
            }
        }
        if params['holding'] is not None:
            cmd[self._clampName]['holding'] = params['holding']

        return self._manager.createTask(cmd)

    def _checkStop(self):
        if self._stop:
            raise self.StopRequested()


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
