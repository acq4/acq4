from __future__ import print_function
import numpy as np
from ..Pipette import Pipette
from acq4.util import Qt
from ...Manager import getManager
from acq4.util.Mutex import Mutex
from acq4.pyqtgraph import ptime
from .devgui import PatchPipetteDeviceGui
from .testpulse import TestPulseThread
from .pressure import PressureControl
from .statemanager import PatchPipetteStateManager


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
    sigPressureChanged = Qt.Signal(object, object, object)  # self, source, pressure

    # This attribute can be modified to insert a custom state manager. 
    defaultStateManagerClass = None

    def __init__(self, deviceManager, config, name):
        clampName = config.pop('clampDevice', None)
        self.clampDevice = None if clampName is None else deviceManager.getDevice(clampName)

        Pipette.__init__(self, deviceManager, config, name)
        self._eventLog = []  # chronological record of events 
        self._eventLogLock = Mutex()
        
        # key measurements made during patch process
        self._patchRecord = {}
        self._patchRecordLock = Mutex()
        self.resetPatchRecord()

        # current state variables
        self.state = "out"
        self.active = False
        self.broken = False
        self.fouled = False
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
        # restoring previous state is temporarily disabled -- this needs a lot more work to be safe.
        # self.setState(lastState.get('state', 'out'))
        # self.broken = lastState.get('broken', False)
        # self.calibrated = lastState.get('calibrated', False)
        # self.setActive(False)  # Always start pipettes disabled rather than restoring last state?
        # # self.setActive(lastState.get('active', False))

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

    def updatePatchRecord(self, **kwds):
        with self._patchRecordLock:
            self._patchRecord.update(kwds)

    def resetPatchRecord(self):
        with self._patchRecordLock:
            self._patchRecord = {
                'initialResistance': None,
                'initialOffset': None,
                'fouledBeforeSeal': None,
                'resistanceBeforeSeal': None,
                'maxSealResistance': None,
                'resistanceAfterBlowout': None,
                'offsetBeforeSeal': None,
                'offsetAfterBlowout': None,
                'detectedCell': None,
                'attemptedSeal': False,
                'sealSuccessful': None,
                'attemptedBreakin': False,
                'breakinSuccessful': None,
                'initialBaselineCurrent': None,
                'initialBaselinePotential': None,
                'wholeCellBeginTime': None,
                'wholeCellEndTime': None,
            }

    def getPressure(self):
        pass

    def setPressure(self, pressure):
        """Set the pipette pressure (float; in Pa) or pressure source (str).

        If float, then the pressure regulator is set to the specified pressure in Pa and
        the source is set to 'regulator'. If str, then the source is set to the specified
        value and the regulator pressure is set to 0.
        """
        pdev = self.pressureDevice
        if pdev is None:
            return
        if isinstance(pressure, str):
            source = pressure
            pressure = 0
            pdev.setSource(source)
            pdev.setPressure(pressure)
        else:
            source = 'regulator'
            pdev.setPressure(pressure)
            pdev.setSource(source)

        self.sigPressureChanged.emit(self, source, pressure)

    def setSelected(self):
        pass

    def approach(self, initialMoveSpeed='fast'):
        """Prepare pipette to enter tissue and patch a cell.

        - Move pipette to diagonal approach position
        - Auto-correct pipette offset
        - May increase pressure
        - Automatically hide tip/target markers when the tip is near the target
        """
        return self._stateManager.startApproach(initialMoveSpeed)

    def seal(self):
        """Attempt to seal onto a cell.

        * switches to VC holding after passing 100 MOhm
        * increase suction if seal does not form
        """

    def setState(self, state):
        """out, bath, approach, seal, attached, breakin, wholecell
        """
        return self._stateManager.requestStateChange(state)

    def listStates(self):
        """Return a list of all known state names this pipette can be set to.
        """
        return self._stateManager.listStates()

    def _setState(self, state):
        """Called by state manager when state has changed.
        """
        oldState = self.state
        self.state = state
        self._writeStateFile()
        self.logEvent("stateChange", state=state)
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

    def logEvent(self, eventType, **kwds):
        with self._eventLogLock:
            print("%s %s %r" % (self.name(), eventType, kwds))
            self._eventLog.append((eventType, ptime.time(), kwds))

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
        self.fouled = False
        self.calibrated = False
        # todo: set calibration to average 
        self.newPatchAttempt()

    def newPatchAttempt(self):
        """Ready to begin a new patch attempt; reset TP history and patch record.
        """
        self.resetPatchRecord()
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
        return self._stateManager.cleanPipette()

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
        self._testPulseThread.started.connect(self.testPulseEnabledChanged)
        self._testPulseThread.finished.connect(self.testPulseEnabledChanged)

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

    def testPulseEnabledChanged(self):
        self.sigTestPulseEnabled.emit(self, self.testPulseEnabled)

    def lastTestPulse(self):
        return self._lastTestPulse

    def _initStateManager(self):
        # allow external modification of state manager class
        cls = self.defaultStateManagerClass or PatchPipetteStateManager
        self._stateManager = cls(self)

    def stateManager(self):
        return self._stateManager

    def quit(self):
        self.enableTestPulse(False, block=True)
        self._stateManager.quit()

    def goHome(self, speed):
        self.setState('out')
        return Pipette.goHome(self, speed)
