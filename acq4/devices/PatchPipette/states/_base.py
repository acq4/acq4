from __future__ import annotations

import contextlib
import queue
import sys
import threading
from copy import deepcopy
from typing import Any, Optional, Iterable

import numpy as np

from acq4 import getManager
from acq4.util import Qt
from acq4.util.future import Future, future_wrap
from neuroanalysis.test_pulse import PatchClampTestPulse
from pyqtgraph import disconnect
from pyqtgraph.units import µm


class PatchPipetteState(Future):
    """Base class for implementing the details of a patch pipette state:

    - Set initial pressure, clamp parameters, position, etc when starting the state
    - Optionally run a background thread; usually this will monitor pipette resistance
      and affect the pipette pressure, holding value, or position.

    This class is the base for other state subclasses classes and just takes care of some boilerplate:
     - assembling config from defaults and init args
     - set initial device state
     - starting thread (if run() method is implemented)
     - handling various job failure / finish modes
     - communicating next state transition to the state manager

    Parameters
    ----------
    initialPressureSource : str
        Initial pressure source; one of 'atmosphere', 'regulator', or 'user' (default None)
    initialPressure : float
        Initial pressure (Pascals) (default None)
    initialClampMode : str
        Initial clamp mode; one of 'VC' or 'IC' (default None)
    initialICHolding : float
        Initial holding current (Amps) if initialClampMode is 'IC' (default None)
    initialVCHolding : float
        Initial holding voltage (Volts) if initialClampMode is 'VC' (default None)
    initialTestPulseEnable : bool
        If True, enable test pulse generation at the start of the state (default None)
    initialTestPulseParameters : dict
        Test pulse parameters to set at the start of the state (default None)
    initialAutoBiasEnable : bool
        If True, enable auto bias at the start of the state (default False)
    initialAutoBiasTarget : float
        Auto bias target (Volts) to set at the start of the state (default 0 V)
    fallbackState : str
        Name of state to transition to if this state fails (default None)
    finishPatchRecord : bool
        If True, finish the current patch record when entering this state (default False)
    newPipette : bool
        If True, start a new pipette when entering this state (default False)
    reserveDAQ : bool
        If True, reserve the DAQ during the entire state. This is used to ensure that the state
        has real time access to test pulses (for cell detection, obstacle detection, etc)
        (default False)
    DAQReservationTimeout : float
        Maximum time (s) to wait for DAQ reservation if reserveDAQ=True (defualt 30 s)
    aboveSurfacePressure : float
        Pressure (Pascals) to apply when the pipette is above the surface (default 1500 Pa)
    belowSurfacePressureMin : float
        Minimum pressure (Pascals) to apply when the pipette is below the surface (default 1500 Pa)
    belowSurfacePressureMax : float
        Maximum pressure (Pascals) to apply when the pipette is below the surface (default 5000 Pa)
    belowSurfacePressureChange : float
        Rate of pressure increase (Pascals/meter) as the pipette goes deeper below the surface
        (default 50 Pa/µm)
    """

    # state subclasses must set a string name
    stateName = None

    # State classes may implement a run() method to be called in a background thread and it should call
    # self.checkStop() frequently
    run = None

    _parameterTreeConfig = {
        'initialPressureSource': {'type': 'list', 'default': None, 'limits': ['atmosphere', 'regulator', 'user'],
                                  'optional': True},
        'initialPressure': {'type': 'float', 'default': None, 'optional': True, 'suffix': 'Pa'},
        'initialClampMode': {'type': 'list', 'default': None, 'limits': ['VC', 'IC'], 'optional': True},
        'initialICHolding': {'type': 'float', 'default': None, 'optional': True, 'suffix': 'A'},
        'initialVCHolding': {'type': 'float', 'default': None, 'optional': True, 'suffix': 'V'},
        'initialTestPulseEnable': {'type': 'bool', 'default': None, 'optional': True},
        'initialTestPulseParameters': {'type': 'group', 'children': []},  # TODO
        'initialAutoBiasEnable': {'type': 'bool', 'default': False, 'optional': True},
        'initialAutoBiasTarget': {'type': 'float', 'default': 0, 'optional': True, 'suffix': 'V'},
        'fallbackState': {'type': 'str', 'default': None, 'optional': True},
        'finishPatchRecord': {'type': 'bool', 'default': False},
        'newPipette': {'type': 'bool', 'default': False},
        'reserveDAQ': {'default': False, 'type': 'bool'},
        'DAQReservationTimeout': {'default': 30, 'type': 'float', 'suffix': 's'},
        'aboveSurfacePressure': {'default': 1500, 'type': 'float', 'suffix': 'Pa'},
        'belowSurfacePressureMin': {'default': 1500, 'type': 'float', 'suffix': 'Pa'},
        'belowSurfacePressureMax': {'default': 5000, 'type': 'float', 'suffix': 'Pa'},
        'belowSurfacePressureChange': {'default': 50 / µm, 'type': 'float', 'suffix': 'Pa/m'},
    }

    @classmethod
    def parameterTreeConfig(cls) -> list[dict]:
        # combine the superclass config with the state-specific config. state-specific config takes precedence.
        if not hasattr(cls, '_parameterTreeConfig'):
            cls._parameterTreeConfig = {}
        config = deepcopy(cls._parameterTreeConfig)
        for base in cls.__bases__:
            if hasattr(base, 'parameterTreeConfig'):
                for c in deepcopy(base.parameterTreeConfig()):
                    if c['name'] not in config:
                        config[c['name']] = c
        for name, c in config.items():
            c['name'] = name
        # subclasses can decide whether to override initial values
        overrides = cls.parameterDefaultOverrides()
        for name, val in overrides.items():
            config[name]['default'] = val

        return list(config.values())

    @classmethod
    def parameterDefaultOverrides(cls) -> dict[str, object]:
        if not hasattr(cls, '_parameterDefaultOverrides'):
            return {}
        return cls._parameterDefaultOverrides

    @classmethod
    def defaultConfig(cls) -> dict[str, Any]:
        return {c['name']: c.get('default', None) for c in cls.parameterTreeConfig()}

    def __init__(self, dev, config=None):
        self._targetHasChanged = False
        from acq4.devices.PatchPipette import PatchPipette

        Future.__init__(self, name=f"State {self.stateName} for {dev}")

        self.dev: PatchPipette = dev

        # generate full config by combining passed-in arguments with default config
        self.config = self.defaultConfig()
        if config is not None:
            self.config.update(config)
        self._cleanupMutex = threading.Lock()
        self._cleanupFuture = None
        self._pressureAdjustment = None
        self._cell = None
        self._visualTargetTrackingFuture = None
        self._pauseMovement = False
        # indicates state that should be transitioned to next, if any.
        # This is usually set by the return value of run(), and must be invoked by the state manager.
        self.nextState = self.config.get('fallbackState', None)
        self.dev.sigTargetChanged.connect(self._onTargetChanged)

    def initialize(self):
        """Initialize pressure, clamp, etc. and start background thread when entering this state.

        This method is called by the state manager.
        """
        try:
            if self.config.get('finishPatchRecord') is True:
                self.dev.finishPatchRecord()
            if self.config.get('newPipette') is True:
                self.dev.newPipette()

            self.initializePressure()
            self.initializeClamp()

            # set up test pulse monitoring
            self.testPulseResults = queue.Queue()

            if self.run is None:
                # no work; just mark the task complete
                self._taskDone(interrupted=False, error=None)
            elif self.dev.active:
                self._thread = threading.Thread(target=self._runJob, name=f'{self.dev.name()} {self.stateName} thread')
                self._thread.start()
            else:
                self._taskDone(interrupted=True, error=f"Not starting state thread; {self.dev.name()} is not active.")
        except Exception as e:
            self._taskDone(interrupted=True, excInfo=sys.exc_info())
            raise

    def initializePressure(self):
        """Set initial pressure based on the config keys 'initialPressureSource' and 'initialPressure'
        """
        if self.dev.pressureDevice is None:
            return
        pressure = self.config.get('initialPressure', None)
        source = self.config.get('initialPressureSource', None)
        self.dev.pressureDevice.setPressure(source=source, pressure=pressure)

    def initializeClamp(self):
        """Set initial clamp parameters based on the config keys
        'initialClampMode', 'initialClampHolding', and 'initialTestPulseEnable'.
        """
        cdev = self.dev.clampDevice
        if cdev is None:
            return
        mode = self.config.get('initialClampMode')
        ic_holding = self.config.get('initialICHolding')
        vc_holding = self.config.get('initialVCHolding')
        tp = self.config.get('initialTestPulseEnable')
        tpParams = self.config.get('initialTestPulseParameters')
        bias = self.config.get('initialAutoBiasEnable')
        biasTarget = self.config.get('initialAutoBiasTarget')

        if mode is not None:
            cdev.setMode(mode)
            if tpParams is None:
                tpParams = {}
        if ic_holding is not None:
            cdev.setHolding(mode="IC", value=ic_holding)
        if vc_holding is not None:
            cdev.setHolding(mode="VC", value=vc_holding)

        # enable test pulse if config requests it AND the device is "active"
        if tp is not None:
            self.dev.clampDevice.enableTestPulse(tp and self.dev.active)
        if tpParams is not None:
            self.dev.clampDevice.setTestPulseParameters(**tpParams)

        if bias is not None:
            self.dev.clampDevice.enableAutoBias(bias)
        if biasTarget is not None:
            self.dev.clampDevice.setAutoBiasTarget(biasTarget)

    def monitorTestPulse(self):
        """Begin acquiring test pulse data in self.testPulseResults
        """
        self.dev.clampDevice.sigTestPulseFinished.connect(self.testPulseFinished)

    def processAtLeastOneTestPulse(self) -> list[PatchClampTestPulse]:
        """Wait for at least one test pulse to be processed."""
        while not (tps := self.getTestPulses(timeout=0.2)):
            self.checkStop()
        return tps

    def testPulseFinished(self, clamp, result):
        self.testPulseResults.put(result)

    def getTestPulses(self, timeout):
        """Get all test pulses in the queue. If no test pulses are available, then
        wait *timeout* seconds for one to arrive.
        """
        tps = []
        with contextlib.suppress(queue.Empty):
            if timeout is not None:
                tps.append(self.testPulseResults.get(timeout=timeout))
            while not self.testPulseResults.empty():
                tps.append(self.testPulseResults.get())
        return tps

    def adjustPressureForDepth(self):
        """While not that slow, we still want to keep the innermost loop as fast as we can."""
        if self._pressureAdjustment is None:
            self._pressureAdjustment = self._adjustPressureForDepth()
            self._pressureAdjustment.onFinish(self._finishPressureAdjustment, inGui=True)

    @future_wrap(logLevel='debug')
    def _adjustPressureForDepth(self, _future):
        depth = self.depthBelowSurface()
        if depth < 0:  # above surface
            pressure = self.config["aboveSurfacePressure"]
        else:
            pressure = self.config["belowSurfacePressureMin"] + depth * self.config["belowSurfacePressureChange"]
            pressure = min(pressure, self.config["belowSurfacePressureMax"])
        self.dev.pressureDevice.setPressure("regulator", pressure)

    def _finishPressureAdjustment(self, future):
        self._pressureAdjustment = None

    def cleanup(self) -> Future:
        with self._cleanupMutex:
            if self._cleanupFuture is None:
                self._cleanupFuture = self._cleanup()
            return self._cleanupFuture

    def _cleanup(self) -> Future:
        """Called after job completes, whether it failed or succeeded. Ask `self.wasInterrupted()` to see if the
        state was stopped early. Return a Future that completes when cleanup is done.
        """
        try:
            if self._visualTargetTrackingFuture is not None:
                self._cell.enableTracking(False)
                self._visualTargetTrackingFuture.stop("State cleanup")
                self._visualTargetTrackingFuture = None
        except Exception:
            self.logger.exception("Error stopping visual target tracking")
        disconnect(self.dev.pipetteDevice.sigTargetChanged, self._onTargetChanged)
        return Future.immediate()

    def _runJob(self):
        """Function invoked in background thread.

        This calls the custom run() method for the state subclass and handles the possible
        error / exit / completion states.
        """
        excInfo = None
        interrupted = True
        try:
            with contextlib.ExitStack() as stack:
                if self.config["reserveDAQ"]:
                    daq_name = self.dev.clampDevice.getDAQName("primary")
                    self.setState(f"{self.stateName}: waiting for {daq_name} lock")
                    stack.enter_context(
                        getManager().reserveDevices([daq_name], timeout=self.config["DAQReservationTimeout"]))
                    self.setState(f"{self.stateName}: {daq_name} lock acquired")
                self.nextState = self.run()
            interrupted = self.wasInterrupted()
        except Exception as e:
            # state aborted due to an error
            excInfo = sys.exc_info()
        finally:
            if self.dev.clampDevice is not None:
                disconnect(self.dev.clampDevice.sigTestPulseFinished, self.testPulseFinished)
            if not self.isDone():
                self._taskDone(interrupted=interrupted, excInfo=excInfo)

    def checkStop(self):
        # extend checkStop to also see if the pipette was deactivated.
        if self.dev.active is False:
            raise self.StopRequested("Stop state because device is not 'active'")
        Future.checkStop(self)

    def __repr__(self):
        return f'<{type(self).__name__} "{self.stateName}">'

    def surfaceIntersectionPosition(self):
        """Return the intersection of the direction unit vector with the surface."""
        pip = self.dev.pipetteDevice
        surface = pip.scopeDevice().getSurfaceDepth()
        return pip.positionAtDepth(surface)

    def depthBelowSurface(self, pos=None):
        if pos is None:
            pos = self.dev.pipetteDevice.globalPosition()
        # print(f"measuring {pos[2]} relative to the surface")
        surface = self.dev.pipetteDevice.scopeDevice().getSurfaceDepth()
        return surface - pos[2]

    def aboveSurface(self, pos=None):
        return self.depthBelowSurface(pos) < 0

    def maybeVisuallyTrackTarget(self):
        if not self.config["visualTargetTracking"]:
            return
        if self.closeEnoughToTargetToDetectCell():
            if self._visualTargetTrackingFuture is not None:
                self._cell.enableTracking(False)
                self._visualTargetTrackingFuture = None
            return
        if self._visualTargetTrackingFuture is None:
            self._cell = self.dev.cell
            self._visualTargetTrackingFuture = self._visualTargetTracking()

    def _visualTargetTracking(self):
        cell = self._cell
        if cell is None:
            raise RuntimeError("Cannot visually track target; no cell is assigned to this pipette device.")
        if not cell.isInitialized:
            cell.initializeTracker(self.dev.pipetteDevice.imagingDevice()).wait()

        cell.enableTracking(True)
        cell.sigTrackingMultipleFramesStart.connect(self._pausePipetteForExtendedTracking)
        cell.sigPositionChanged.connect(self.dev.pipetteDevice.setTarget)
        cell._trackingFuture.sigFinished.connect(self._visualTargetTrackingFinished)
        return cell._trackingFuture

    def _visualTargetTrackingFinished(self, future):
        from acq4_automation.feature_tracking.visualization import LiveTrackerVisualizer

        if not hasattr(self.dev, '_trackingVisualizers'):
            self.dev._trackingVisualizers = []
        disconnect(self._cell.sigPositionChanged, self.dev.pipetteDevice.setTarget)
        if future.wasStopped():
            return
        visualizer = LiveTrackerVisualizer(self._cell._tracker)
        self.dev._trackingVisualizers.append(visualizer)
        # TODO clean these up eventually or we'll leak memory
        visualizer.show()

    def _pausePipetteForExtendedTracking(self, cell):
        self._pauseMovement = True
        cell.sigTrackingMultipleFramesFinish.connect(self._resumePipetteAfterExtendedTracking)
        cell.sigTrackingMultipleFramesStart.disconnect(self._pausePipetteForExtendedTracking)

    def _resumePipetteAfterExtendedTracking(self, cell):
        self._pauseMovement = False
        cell.sigTrackingMultipleFramesFinish.disconnect(self._resumePipetteAfterExtendedTracking)

    def _waitForMoveWhileTargetChanges(self, position_fn, speed, continuous, future, interval=None, step=None):
        move_fut = None
        try:
            while move_fut is None or not move_fut.isDone():
                if self._pauseMovement:
                    if move_fut is not None:
                        move_fut.stop("Paused", wait=True)
                        move_fut = None
                    future.sleep(0.1)
                    continue
                if move_fut is None:
                    pos = position_fn()
                    if continuous:
                        move_fut = self.dev.pipetteDevice._moveToGlobal(pos, speed=speed)
                    else:
                        move_fut = self.dev.pipetteDevice.stepwiseAdvance(
                            target=pos,
                            speed=speed,
                            interval=interval,
                            step=step,
                        )
                if self._targetHasChanged:
                    self._targetHasChanged = False
                    move_fut.stop("Target changed", wait=True)
                    move_fut = None
                future.sleep(0.1)
        except Exception:
            if move_fut is not None and not move_fut.isDone():
                move_fut.stop("Error while moving", wait=True)
            raise

    def _onTargetChanged(self, pos):
        self._targetHasChanged = True

    def _distanceToTarget(self):
        pip = self.dev.pipetteDevice
        target = np.array(pip.targetPosition())
        pos = np.array(pip.globalPosition())
        return np.linalg.norm(target - pos)

    def closeEnoughToTargetToDetectCell(self):
        return self._distanceToTarget() < self.config['minDetectionDistance']


class SteadyStateAnalysisBase(object):
    @classmethod
    def plot_items(cls, *args, **kwargs) -> dict[str, Iterable[Qt.QGraphicsItem]]:
        """Returns data-independent plot items grouped by plot units."""
        return {}

    @classmethod
    def plots_for_data(cls, data: Iterable[np.void], *args, **kwargs) -> dict[str, Iterable[dict[str, Any]]]:
        """Given a list of datasets and init args, return the plotting arguments grouped by plot units."""
        return {}

    def __init__(self, **kwds):
        self._last_measurement: Optional[np.void] = None

    def process_test_pulses(self, tps: list[PatchClampTestPulse]) -> np.ndarray:
        return self.process_measurements(
            np.array([(tp.recording.start_time, tp.analysis['steady_state_resistance']) for tp in tps]))

    def process_measurements(self, measurements: np.ndarray) -> np.ndarray:
        raise NotImplementedError()

    @staticmethod
    def exponential_decay_avg(dt, prev_avg, value, tau):
        """Compute exponential decay average and ratio of new to old average."""
        alpha = 1 - np.exp(-dt / tau)
        avg = prev_avg * (1 - alpha) + value * alpha
        ratio = avg / prev_avg
        return avg, ratio
