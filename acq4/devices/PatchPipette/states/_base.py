from __future__ import annotations

import contextlib
import numpy as np
import queue
import sys
import threading
from copy import deepcopy
from typing import Any, Optional

from acq4.util import Qt
from acq4.util.debug import printExc
from acq4.util.future import Future
from neuroanalysis.test_pulse import PatchClampTestPulse
from pyqtgraph import disconnect


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
    """

    # state subclasses must set a string name
    stateName = None

    # State classes may implement a run() method to be called in a background thread
    run = None

    _parameterTreeConfig = {
        'initialPressureSource': {'type': 'list', 'default': None, 'limits': ['atmosphere', 'regulator', 'user'],
                                  'optional': True},
        'initialPressure': {'type': 'float', 'default': None, 'optional': True, 'suffix': 'Pa'},
        'initialClampMode': {'type': 'list', 'default': None, 'limits': ['VC', 'IC'], 'optional': True},
        'initialICHolding': {'type': 'float', 'default': None, 'optional': True},
        'initialVCHolding': {'type': 'float', 'default': None, 'optional': True},
        'initialTestPulseEnable': {'type': 'bool', 'default': None, 'optional': True},
        'initialTestPulseParameters': {'type': 'group', 'children': []},  # TODO
        'initialAutoBiasEnable': {'type': 'bool', 'default': False, 'optional': True},
        'initialAutoBiasTarget': {'type': 'float', 'default': 0, 'optional': True, 'suffix': 'V'},
        'fallbackState': {'type': 'str', 'default': None, 'optional': True},
        'finishPatchRecord': {'type': 'bool', 'default': False},
        'newPipette': {'type': 'bool', 'default': False},
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
        from acq4.devices.PatchPipette import PatchPipette

        Future.__init__(self)

        self.dev: PatchPipette = dev
        self._moveFuture = None

        # generate full config by combining passed-in arguments with default config
        self.config = self.defaultConfig()
        if config is not None:
            self.config.update(config)

        # indicates state that should be transitioned to next, if any.
        # This is usually set by the return value of run(), and must be invoked by the state manager.
        self.nextState = self.config.get('fallbackState', None)

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
                self._thread = threading.Thread(target=self._runJob)
                self._thread.start()
            else:
                self._taskDone(interrupted=True, error=f"Not starting state thread; {self.dev.name()} is not active.")
        except Exception as exc:
            self._taskDone(interrupted=True, error=str(exc))
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
        if ic_holding is not None:
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

    def cleanup(self):
        """Called after job completes, whether it failed or succeeded.
        """
        pass

    def _runJob(self):
        """Function invoked in background thread.

        This calls the custom run() method for the state subclass and handles the possible
        error / exit / completion states.
        """
        error = None
        excInfo = None
        interrupted = False
        try:
            # run must be reimplemented in subclass and call self.checkStop() frequently
            self.nextState = self.run()
            interrupted = self.wasInterrupted()
        except self.StopRequested as exc:
            error = str(exc)
            # state was stopped early by calling stop()
            interrupted = True
        except Exception as exc:
            # state aborted due to an error
            interrupted = True
            printExc(f"Error in {self.dev.name()} state {self.stateName}")
            error = str(exc)
            excInfo = sys.exc_info()
        finally:
            disconnect(self.dev.clampDevice.sigTestPulseFinished, self.testPulseFinished)
            if not self.isDone():
                self._taskDone(interrupted=interrupted, error=error, excInfo=excInfo)

    def checkStop(self, delay=0):
        # extend checkStop to also see if the pipette was deactivated.
        if self.dev.active is False:
            raise self.StopRequested("Stop state because device is not 'active'")
        Future.checkStop(self, delay)

    def __repr__(self):
        return f'<{type(self).__name__} "{self.stateName}">'

    def surfaceIntersectionPosition(self, direction):
        """Return the intersection of the direction unit vector with the surface."""
        pip = self.dev.pipetteDevice
        pos = np.array(pip.globalPosition())
        surface = pip.scopeDevice().getSurfaceDepth()
        return pos - direction * (surface - pos[2])


class SteadyStateAnalysisBase(object):
    @classmethod
    def plot_items(cls, *args, **kwargs) -> dict[str, iter[Qt.QGraphicsItem]]:
        """Returns data-independent plot items grouped by plot units."""
        return {}

    @classmethod
    def plots_for_data(cls, data: iter[np.void], *args, **kwargs) -> dict[str, iter[dict[str, Any]]]:
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
        alpha = 1 - np.exp(-dt / tau)
        avg = prev_avg * (1 - alpha) + value * alpha
        ratio = np.log10(avg / prev_avg)
        return avg, ratio


