from __future__ import print_function
import numpy as np
from collections import OrderedDict
from ..Device import Device
from acq4.util import Qt
from ...Manager import getManager
from acq4.util.Mutex import Mutex
from acq4.pyqtgraph import ptime
from .devgui import PatchPipetteDeviceGui
from .testpulse import TestPulseThread
from .pressure import PressureControl
from .statemanager import PatchPipetteStateManager
from .autobias import AutoBiasHandler


class PatchPipette(Device):
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
    sigAutoBiasChanged = Qt.Signal(object, object, object)  # self, enabled, target
    sigMoveStarted = Qt.Signal(object)  # self
    sigMoveFinished = Qt.Signal(object, object)  # self, position
    sigTargetChanged = Qt.Signal(object, object)  # self, target

    # catch-all signal for event logging
    sigNewEvent = Qt.Signal(object, object)  # self, event

    # These attributes can be modified to customize state management, test pulse acquisition, and auto bias
    defaultStateManagerClass = PatchPipetteStateManager
    defaultTestPulseThreadClass = TestPulseThread
    defaultAutoBiasClass = AutoBiasHandler

    def __init__(self, deviceManager, config, name):
        pipName = config.pop('pipetteDevice', None)
        self.pipetteDevice = deviceManager.getDevice(pipName)
        clampName = config.pop('clampDevice', None)
        self.clampDevice = None if clampName is None else deviceManager.getDevice(clampName)

        Device.__init__(self, deviceManager, config, name)
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
            self.pressureDevice.sigPressureChanged.connect(self.pressureChanged)
        self.userPressure = False
        
        self._lastTestPulse = None
        self._initTestPulse(config.get('testPulse', {}))
        self._autoBiasHandler = None
        self._initAutoBias()

        self._initStateManager()

        self.pipetteDevice.sigCalibrationChanged.connect(self._pipetteCalibrationChanged)
        self.pipetteDevice.sigMoveStarted.connect(self._pipetteMoveStarted)
        self.pipetteDevice.sigMoveFinished.connect(self._pipetteMoveFinished)
        self.pipetteDevice.sigTargetChanged.connect(self._pipetteTargetChanged)

        deviceManager.declareInterface(name, ['patchpipette'], self)

        # restore last known state for this pipette
        lastState = self.readConfigFile('last_state')
        # restoring previous state is temporarily disabled -- this needs a lot more work to be safe.
        # self.setState(lastState.get('state', 'out'))
        # self.broken = lastState.get('broken', False)
        # self.calibrated = lastState.get('calibrated', False)
        # self.setActive(False)  # Always start pipettes disabled rather than restoring last state?
        # # self.setActive(lastState.get('active', False))

    def scopeDevice(self):
        return self.pipetteDevice.scopeDevice()

    def imagingDevice(self):
        return self.pipetteDevice.imagingDevice()

    def getPatchStatus(self):
        """Return a dict describing the status of the patched cell.

        Includes keys:
        * state ('bath', 'sealing', 'on-cell', 'whole-cell', etc..)
        * resting potential
        * resting current
        * input resistance
        * access resistance
        * capacitance
        * clamp mode ('IC' or 'VC')
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

    def pressureChanged(self, dev, source, pressure):
        self.sigPressureChanged.emit(self, source, pressure)
        self.emitNewEvent(OrderedDict([('event', 'pressureChanged'), ('source', source), ('pressure', pressure)]))

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
        """Attempt to set the state (out, bath, seal, whole cell, etc.) of this patch pipette.

        The actual resulting state is returned.
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
        self.emitNewEvent(OrderedDict([('event', 'state_changed'), ('state', state), ('old_state', oldState)]))

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
        self.emitNewEvent(OrderedDict([('event', 'pipette_calibrated')]))

    def _pipetteTransformChanged(self, pip, movedDevice):
        pos = pip.globalPosition()
        self.emitNewEvent(OrderedDict([('event', 'pipetteTransformChanged'), ('globalPosition', pos)]))

    def setActive(self, active):
        self.active = active
        self.sigActiveChanged.emit(self, active)
        self.emitNewEvent(OrderedDict([('event', 'active_changed'), ('active', active)]))

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
        event = OrderedDict([('event', 'test_pulse')])
        event.update(result.analysis())
        self.emitNewEvent(event)

    def _initTestPulse(self, params):
        self.resetTestPulseHistory()
        self._testPulseThread = self.defaultTestPulseThreadClass(self, params)
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
        self.emitNewEvent(OrderedDict([('event', 'testPulseEnabled'), ('enabled', self.testPulseEnabled)]))

    def lastTestPulse(self):
        return self._lastTestPulse

    def _initAutoBias(self):
        self._autoBiasHandler = self.defaultAutoBiasClass(self)

    def enableAutoBias(self, enable=True):
        self._autoBiasHandler.setParams(enabled=enable)
        self.sigAutoBiasChanged.emit(self, enable, self.autoBiasTarget())
        self.emitNewEvent(OrderedDict([('event', 'autoBiasEnabled'), ('enabled', enable), ('target', self.autoBiasTarget())]))

    def autoBiasEnabled(self):
        return self._autoBiasHandler.getParam('enabled')

    def setAutoBiasTarget(self, v):
        self._autoBiasHandler.setParams(targetPotential=v)
        self.sigAutoBiasChanged.emit(self, self.autoBiasEnabled(), v)
        self.emitNewEvent(OrderedDict([('event', 'autoBiasTargetChanged'), ('enabled', self.autoBiasEnabled()), ('target', v)]))

    def autoBiasTarget(self):
        return self._autoBiasHandler.getParam('targetPotential')

    def _initStateManager(self):
        # allow external modification of state manager class
        self._stateManager = self.defaultStateManagerClass(self)

    def stateManager(self):
        return self._stateManager

    def quit(self):
        self.enableTestPulse(False, block=True)
        self._stateManager.quit()

    def goHome(self, speed):
        self.setState('out')
        return self.pipetteDevice.goHome(speed)

    def _pipetteMoveStarted(self, pip):
        self.sigMoveStarted.emit(self)
        self.emitNewEvent(OrderedDict([
            ('event', 'move_start'),
        ]))

    def _pipetteMoveFinished(self, pip):
        pos = self.pipetteDevice.globalPosition()
        self.sigMoveFinished.emit(self, pos)
        self.emitNewEvent(OrderedDict([
            ('event', 'move_stop'), 
            ('position', [pos[0], pos[1], pos[2]]),
        ]))

    def _pipetteTargetChanged(self, pip, pos):
        self.sigTargetChanged.emit(self, pos)
        self.emitNewEvent(OrderedDict([
            ('event', 'target_changed'), 
            ('target_position', [pos[0], pos[1], pos[2]]),
        ]))

    def emitNewEvent(self, event):
        newEv = OrderedDict([
            ('device', self.name()),
            ('timestamp', ptime.time()),
        ])
        newEv.update(event)
        self.sigNewEvent.emit(self, newEv)
