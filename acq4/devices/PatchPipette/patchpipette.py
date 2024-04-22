from collections import OrderedDict

import numpy as np
from typing import Optional

from acq4.devices.PatchClamp.patchclamp import PatchClamp
from acq4.util import Qt
from acq4.util import ptime
from acq4.util.Mutex import Mutex
from .devgui import PatchPipetteDeviceGui
from .statemanager import PatchPipetteStateManager
from ..Camera import Camera
from ..Device import Device
from ..Pipette import Pipette
from ..PressureControl import PressureControl


class PatchPipette(Device):
    """Represents a single patch pipette, manipulator, and headstage.

    This class extends from the Pipette device class to provide automation and visual feedback
    on the status of the patch:

        * Whether a cell is currently patched
        * Input resistance, access resistance, and holding levels

    This is also a good place to implement pressure control, autopatching, slow voltage clamp, etc.

    If you intend this for use with the MultiPatch module, the device name in the configuration
    needs to end in a number.
    """
    sigStateChanged = Qt.Signal(object, object, object)  # self, newState, oldState
    sigActiveChanged = Qt.Signal(object, object)  # self, active
    sigPressureChanged = Qt.Signal(object, object, object)  # self, source, pressure
    sigMoveStarted = Qt.Signal(object)  # self
    sigMoveFinished = Qt.Signal(object, object)  # self, position
    sigTargetChanged = Qt.Signal(object, object)  # self, target
    sigNewPipetteRequested = Qt.Signal(object)  # self
    sigTipCleanChanged = Qt.Signal(object, object)  # self, clean
    sigTipBrokenChanged = Qt.Signal(object, object)  # self, broken

    # catch-all signal for event logging
    sigNewEvent = Qt.Signal(object, object)  # self, event

    # emitted every time we finish a patch attempt
    sigPatchAttemptFinished = Qt.Signal(object, object)  # self, patch record

    # These attributes can be modified to customize state management and test pulse acquisition
    defaultStateManagerClass = PatchPipetteStateManager

    def __init__(self, deviceManager, config, name):
        pipName = config.pop('pipetteDevice', None)
        self.pipetteDevice: Pipette = deviceManager.getDevice(pipName)

        clampName = config.pop('clampDevice', None)
        if clampName is None:
            self.clampDevice: Optional[PatchClamp] = None
        else:
            self.clampDevice: Optional[PatchClamp] = deviceManager.getDevice(clampName)
            self.clampDevice.sigStateChanged.connect(self.clampStateChanged)
            self.clampDevice.sigAutoBiasChanged.connect(self._autoBiasChanged)
            self.clampDevice.sigTestPulseFinished.connect(self._testPulseFinished)

        Device.__init__(self, deviceManager, config, name)
        self._eventLog = []  # chronological record of events 
        self._eventLogLock = Mutex()
        
        # current state variables
        self.active = False
        self.broken = False
        self.clean = False
        self.calibrated = False
        self.waitingForSwap = False
        self._lastPos = None

        # key measurements made during patch process and lifetime of pipette
        self._patchRecord = None
        self._pipetteRecord = None

        self.pressureDevice: Optional[PressureControl] = None
        if 'pressureDevice' in config:
            self.pressureDevice = deviceManager.getDevice(config['pressureDevice'])
            self.pressureDevice.sigPressureChanged.connect(self.pressureChanged)
        self.userPressure = False

        self._initStateManager()

        self.pipetteDevice.sigCalibrationChanged.connect(self._pipetteCalibrationChanged)
        self.pipetteDevice.sigMoveStarted.connect(self._pipetteMoveStarted)
        self.pipetteDevice.sigMoveFinished.connect(self._pipetteMoveFinished)
        self.pipetteDevice.sigMoveRequested.connect(self._pipetteMoveRequested)
        self.pipetteDevice.sigTargetChanged.connect(self._pipetteTargetChanged)
        self.pipetteDevice.parentDevice().sigPositionChanged.connect(self._manipulatorTransformChanged)
        self.pipetteDevice.parentDevice().sigOrientationChanged.connect(self._manipulatorTransformChanged)

        deviceManager.declareInterface(name, ['patchpipette'], self)

        # restore last known state for this pipette
        lastState = self.readConfigFile('last_state')
        # restoring previous state is temporarily disabled -- this needs a lot more work to be safe.
        # self.setState(lastState.get('state', 'out'))
        # self.broken = lastState.get('broken', False)
        # self.calibrated = lastState.get('calibrated', False)
        # self.setActive(False)  # Always start pipettes disabled rather than restoring last state?
        # # self.setActive(lastState.get('active', False))

    def isTipClean(self):
        return self.clean

    def setTipClean(self, clean):
        if clean == self.clean:
            return
        self.clean = clean
        self.sigTipCleanChanged.emit(self, clean)
        self.emitNewEvent('tip_clean_changed', {'clean': clean})

    def isTipBroken(self):
        return self.broken

    def setTipBroken(self, broken):
        if broken == self.broken:
            return
        self.broken = broken
        self.sigTipBrokenChanged.emit(self, broken)
        self.emitNewEvent('tip_broken_changed', {'broken': broken})
        # states should take care of this, but we want to make sure pressure stops quickly.
        if broken and self.pressureDevice is not None:
            self.pressureDevice.setPressure(pressure=0)

    def scopeDevice(self):
        return self.pipetteDevice.scopeDevice()

    def imagingDevice(self) -> Camera:
        return self.pipetteDevice.imagingDevice()

    def focusOnTip(self, speed, raiseErrors=False):
        imdev = self.imagingDevice()
        fut = imdev.moveCenterToGlobal(self.pipetteDevice.globalPosition(), speed=speed)
        if raiseErrors:
            fut.raiseErrors("Error while focusing on pipette tip: {error}")

    def focusOnTarget(self, speed, raiseErrors=False):
        imdev = self.imagingDevice()
        fut = imdev.moveCenterToGlobal(self.pipetteDevice.targetPosition(), speed=speed)
        if raiseErrors:
            fut.raiseErrors("Error while focusing on pipette target: {error}")

    def newPipette(self):
        """A new physical pipette has been attached; reset any per-pipette state.
        """
        self.setTipBroken(False)
        self.setTipClean(True)
        self.calibrated = False
        self.waitingForSwap = False
        self._pipetteRecord = None
        self.emitNewEvent('new_pipette', {})
        self.newPatchAttempt()
        self.setState('out')
        # todo: set calibration to average 

    def requestNewPipette(self):
        """Call to emit a signal requesting a new pipette.
        """
        self.waitingForSwap = True
        self.sigNewPipetteRequested.emit(self)

    def pipetteRecord(self):
        if self._pipetteRecord is None:
            self._pipetteRecord = {
                'originalResistance': None,
                'cleanCount': 0,
            }
        return self._pipetteRecord

    def newPatchAttempt(self):
        """Ready to begin a new patch attempt; reset TP history and patch record.
        """
        self.finishPatchRecord()
        if self.clampDevice:
            self.clampDevice.resetTestPulseHistory()
        self.emitNewEvent('new_patch_attempt', {})

    def _resetPatchRecord(self):
        self.finishPatchRecord()
        piprec = self.pipetteRecord()
        self._patchRecord = OrderedDict([
            ('patchPipette', self.name()),
            ('pipetteOriginalResistance', piprec['originalResistance']),
            ('pipetteCleanCount', piprec['cleanCount']),
            ('initialResistance', None),
            ('initialOffset', None),
            ('attemptedCellDetect', False),
            ('detectedCell', None),
            ('cellDetectInitialTarget', None),
            ('cellDetectFinalTarget', None),
            ('attemptedSeal', False),
            ('sealSuccessful', None),
            ('fouledBeforeSeal', None),
            ('resistanceBeforeSeal', None),
            ('resistanceBeforeBreakin', None),
            ('offsetBeforeSeal', None),
            ('attemptedBreakin', False),
            ('breakinSuccessful', None),
            ('spontaneousBreakin', None),
            ('initialBaselineCurrent', None),
            ('initialBaselinePotential', None),
            ('wholeCellStartTime', None),
            ('wholeCellStopTime', None),
            ('wholeCellPosition', None),
            ('resealResistance', None),
            ('resistanceAfterBlowout', None),
            ('offsetAfterBlowout', None),
            ('complete', False),
        ])

    def patchRecord(self):
        if self._patchRecord is None:
            self._resetPatchRecord()
        return self._patchRecord

    def finishPatchRecord(self):
        if self._patchRecord is None:
            return
        self._patchRecord['complete'] = True
        self.sigPatchAttemptFinished.emit(self, self._patchRecord)
        self._patchRecord = None

    def pressureChanged(self, dev, source, pressure):
        self.sigPressureChanged.emit(self, source, pressure)
        self.emitNewEvent('pressure_changed', OrderedDict([('source', source), ('pressure', pressure)]))

    def setSelected(self):
        pass

    def setState(self, state, setActive=True):
        """Attempt to set the state (out, bath, seal, whole cell, etc.) of this patch pipette.

        The actual resulting state is returned.
        """
        if setActive:
            self.setActive(True)
        return self._stateManager.requestStateChange(state)

    def listStates(self):
        """Return a list of all known state names this pipette can be set to.
        """
        return self._stateManager.listStates()

    def _setState(self, state, oldState):
        """Called by state manager when state has changed.
        """
        self._writeStateFile()
        self.emitNewEvent('state_change', OrderedDict([('state', state), ('old_state', oldState)]))
        self.sigStateChanged.emit(self, state, oldState)

    def _writeStateFile(self):
        state = {
            'state': self._stateManager.getState().stateName,
            'active': self.active,
            'calibrated': self.calibrated,
            'broken': self.broken,
        }
        self.writeConfigFile(state, 'last_state')

    def getState(self):
        return self._stateManager.getState()

    def breakIn(self):
        """Rupture the cell membrane using negative current pulses.

        * -2 psi for 3 sec or until rupture
        * -4, -6, -8 psi if needed
        * longer wait time if needed
        """

    def _pipetteCalibrationChanged(self):
        self.calibrated = True
        self.emitNewEvent('pipette_calibrated')

    def _manipulatorTransformChanged(self, dev, *args):
        pos = np.array(self.pipetteDevice.globalPosition())
        if self._lastPos is None or np.linalg.norm(pos - self._lastPos) > 1e-6:
            self._lastPos = pos
            self.emitNewEvent('pipette_transform_changed', {'globalPosition': tuple(pos)})

    def setActive(self, active):
        if self.active == active:
            return
        self.active = active
        self.sigActiveChanged.emit(self, active)
        self.emitNewEvent('active_changed', {'active': active})

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return PatchPipetteDeviceGui(self, win)

    def clampStateChanged(self, state):
        self.emitNewEvent('clamp_state_change', state)

    def _initStateManager(self):
        # allow external modification of state manager class
        self._stateManager = self.defaultStateManagerClass(self)
        self.setState('out')

    def stateManager(self):
        return self._stateManager

    def quit(self):
        if self.clampDevice:
            self.clampDevice.enableTestPulse(False, block=True)
        self._stateManager.quit()

    def goHome(self, speed, **kwds):
        self.setState('out')
        return self.pipetteDevice.goHome(speed, **kwds)

    def _pipetteMoveStarted(self, pip, pos):
        self.sigMoveStarted.emit(self)
        self.emitNewEvent('move_start', {'position': tuple(pos)})

    def _pipetteMoveRequested(self, pip, pos, speed, opts):
        self.emitNewEvent('move_requested', OrderedDict([
            ('position', tuple(pos)), 
            ('speed', speed), 
            ('opts', repr(opts)),
        ]))

    def _pipetteMoveFinished(self, pip, pos):
        self.sigMoveFinished.emit(self, pos)
        self.emitNewEvent('move_stop', {'position': [pos[0], pos[1], pos[2]]})

    def _pipetteTargetChanged(self, pip, pos):
        self.sigTargetChanged.emit(self, pos)
        self.emitNewEvent('target_changed', {'target_position': [pos[0], pos[1], pos[2]]})

    def _autoBiasChanged(self, clamp, enabled, target):
        self.emitNewEvent('auto_bias_change', {'enabled': enabled, 'target': target})

    def _testPulseFinished(self, clamp, result):
        self.emitNewEvent('test_pulse', result.analysis)

    def emitNewEvent(self, eventType, eventData=None):
        newEv = OrderedDict([
            ('device', self.name()),
            ('event_time', ptime.time()),
            ('event', eventType),
        ])
        if eventData is not None:
            newEv.update(eventData)
        self.sigNewEvent.emit(self, newEv)

        self._eventLog.append(newEv)

    def eventLog(self):
        return self._eventLog
