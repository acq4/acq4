from collections import deque
from typing import Any, Optional

import contextlib
import numpy as np
import queue
import scipy.stats
import sys
import threading
import time
import warnings
from copy import deepcopy

from acq4 import getManager
from acq4.devices.PatchPipette.testpulse import TestPulse
from acq4.util import ptime
from acq4.util.debug import printExc
from acq4.util.future import Future
from pyqtgraph import disconnect, units


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
        'initialPressureSource': {'type': 'list', 'default': None, 'values': ['atmosphere', 'regulator', 'user'], 'optional': True},
        'initialPressure': {'type': 'float', 'default': None, 'optional': True, 'suffix': 'Pa'},
        'initialClampMode': {'type': 'list', 'default': None, 'values': ['VC', 'IC'], 'optional': True},
        'initialClampHolding': {'type': 'float', 'default': None, 'optional': True},
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
        holding = self.config.get('initialClampHolding')
        tp = self.config.get('initialTestPulseEnable')
        tpParams = self.config.get('initialTestPulseParameters')
        bias = self.config.get('initialAutoBiasEnable')
        biasTarget = self.config.get('initialAutoBiasTarget')

        if mode is not None:
            cdev.setMode(mode)
            if holding is not None:
                cdev.setHolding(mode=mode, value=holding)
            if tpParams is None:
                tpParams = {}

        # enable test pulse if config requests it AND the device is "active"
        if tp is not None:
            self.dev.enableTestPulse(tp and self.dev.active)
        if tpParams is not None:
            self.dev.setTestPulseParameters(**tpParams)

        if bias is not None:
            self.dev.enableAutoBias(bias)
        if biasTarget is not None:
            self.dev.setAutoBiasTarget(biasTarget)

    def monitorTestPulse(self):
        """Begin acquiring test pulse data in self.testPulseResults
        """
        self.dev.sigTestPulseFinished.connect(self.testPulseFinished)

    def testPulseFinished(self, pip, result):
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
            disconnect(self.dev.sigTestPulseFinished, self.testPulseFinished)
            if not self.isDone():
                self._taskDone(interrupted=interrupted, error=error, excInfo=excInfo)

    def checkStop(self, delay=0):
        # extend checkStop to also see if the pipette was deactivated.
        if self.dev.active is False:
            raise self.StopRequested("Stop state because device is not 'active'")
        Future.checkStop(self, delay)

    def __repr__(self):
        return f'<{type(self).__name__} "{self.stateName}">'


class OutState(PatchPipetteState):
    stateName = 'out'

    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': False,
        'finishPatchRecord': True,
    }


class ApproachState(PatchPipetteState):
    stateName = 'approach'

    _parameterDefaultOverrides = {
        'fallbackState': 'bath',
    }
    _parameterTreeConfig = {
        'nextState': {'type': 'str', 'default': 'cell detect'},
    }

    def run(self):
        # move to approach position + auto pipette offset
        fut = self.dev.pipetteDevice.goApproach('fast')
        self.dev.clampDevice.autoPipetteOffset()
        self.dev.resetTestPulseHistory()
        self.waitFor(fut, timeout=None)
        return self.config['nextState']


class WholeCellState(PatchPipetteState):
    stateName = 'whole cell'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': -70e-3,
        'initialTestPulseEnable': True,
        'initialAutoBiasEnable': True,
        'initialAutoBiasTarget': -70e-3,
    }

    def run(self):
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStartTime'] = ptime.time()
        patchrec['wholeCellPosition'] = tuple(self.dev.pipetteDevice.globalPosition())

        # TODO: Option to switch to I=0 for a few seconds to get initial RMP decay

        while True:
            # TODO: monitor for cell loss
            self.sleep(0.1)

    def cleanup(self):
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStopTime'] = ptime.time()
        PatchPipetteState.cleanup(self)


class BrokenState(PatchPipetteState):
    stateName = 'broken'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'finishPatchRecord': True,
    }

    def initialize(self):
        self.dev.setTipBroken(True)
        PatchPipetteState.initialize(self)


class FouledState(PatchPipetteState):
    stateName = 'fouled'
    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
    }

    def initialize(self):
        self.dev.setTipClean(False)
        PatchPipetteState.initialize(self)


class BathState(PatchPipetteState):
    """Handles detection of changes while in recording chamber

    - monitor resistance to detect entry into bath
    - auto pipette offset and record initial resistance
    - monitor resistance for pipette break / clog

    Parameters
    ----------
    bathThreshold : float
        Resistance (Ohms) below which the tip is considered to be immersed in the bath.
    breakThreshold : float
        Threshold for change in resistance (Ohms) for detecting a broken pipette.
    clogThreshold : float
        Threshold for change in resistance (Ohms) for detecting a clogged pipette.
    """
    stateName = 'bath'
    def __init__(self, *args, **kwds):
        PatchPipetteState.__init__(self, *args, **kwds)

    _parameterDefaultOverrides = {
        'initialPressure': 3500.,  # 0.5 PSI
        'initialPressureSource': 'regulator',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
    }
    _parameterTreeConfig = {
        'bathThreshold': {'type': 'float', 'default': 50e6, 'suffix': 'Ω'},
        'breakThreshold': {'type': 'float', 'default': -1e6, 'suffix': 'Ω'},
        'clogThreshold': {'type': 'float', 'default': 1e6, 'suffix': 'Ω'},
    }
    
    def run(self):
        self.monitorTestPulse()
        config = self.config
        dev = self.dev
        initialResistance = None
        bathResistances = []

        while True:
            self.checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue
            
            tp = tps[-1]  # if we're falling behind, just skip the extra test pulses

            ssr = tp.analysis()['steadyStateResistance']
            if ssr > config['bathThreshold']:
                # not in bath yet
                bathResistances = []
                continue

            bathResistances.append(ssr)

            if initialResistance is None:
                if len(bathResistances) > 8:
                    initialResistance = np.median(bathResistances)
                    self.setState('initial resistance measured: %0.2f MOhm' % (initialResistance * 1e-6))

                    # record initial resistance
                    patchrec = dev.patchRecord()
                    patchrec['initialBathResistance'] = initialResistance
                    piprec = dev.pipetteRecord()
                    if piprec['originalResistance'] is None:
                        piprec['originalResistance'] = initialResistance
                        patchrec['originalPipetteResistance'] = initialResistance

                else:
                    continue

            # check for pipette break
            if config['breakThreshold'] is not None and (ssr < initialResistance + config['breakThreshold']):
                self.setState('broken pipette detected')
                self._taskDone(interrupted=True, error="Pipette broken")
                return 'broken'

            # if close to target, switch to cell detect
            # pos = dev.globalPosition()
            # target = dev.
            if config['clogThreshold'] is not None and (ssr > initialResistance + config['clogThreshold']):
                self.setState('clogged pipette detected')
                self._taskDone(interrupted=True, error="Pipette clogged")
                return 'fouled'


class CellDetectState(PatchPipetteState):
    """Handles cell detection:

    - monitor resistance for cell proximity and switch to seal mode
    - monitor resistance for pipette break

    TODO:
    - Obstacle avoidance
    - Cell tracking

    Parameters
    ----------
    initialClampMode : str
        Clamp mode to set when beginning this state--
        'VC' or 'IC' (default 'VC')
    initialClampHolding : float
        Initial holding value to use when beginning this state (default 0)
    autoAdvance : bool
        If True, automatically advance the pipette while monitoring for cells (default True)
    advanceMode : str
        How to advance the pipette (default 'target'). Options are:
        **target** : advance the pipette tip toward its target
        **axial** : advance pipette along its axis
        **vertical** : advance pipette straight downward in Z
    advanceContinuous : bool
        Whether to advance the pipette with continuous motion or in small steps (default True)
    advanceStepInterval : float
        Time duration (seconds) to wait between steps when advanceContinuous=False(default 0.1)
    advanceStepDistance : float
        Distance (m) per step when advanceContinuous=False (default 1 um)
    maxAdvanceDistance : float | None
        Maximum distance (m) to advance past starting point (default None)
    maxAdvanceDistancePastTarget : float | None
        Maximum distance (m) to advance past target (default 10 um)
    maxAdvanceDepthBelowSurface : float | None
        Maximum depth (m) to advance below the sample surface (default None)
    advanceSpeed : float
        Speed (m/s) to advance the pipette when advanceContinuous=True (default 2 um/s)
    fastDetectionThreshold : float
        Threshold for fast change in pipette resistance (Ohm) to trigger cell detection (default 1 MOhm)
    slowDetectionThreshold : float
        Threshold for slow change in pipette resistance (Ohm) to trigger cell detection (default 200 kOhm)
    slowDetectionSteps : int
        Number of test pulses to integrate for slow change detection (default 3)
    breakThreshold : float
        Threshold for change in resistance (Ohm) to detect broken pipette (default -1 MOhm),
    reserveDAQ : bool
        If True, reserve the DAQ during the entire cell detection state. This is used in case multiple
        channels are present an cannot be accessed simultaneously to ensure that cell detection is not interrupted.
        (default False)
    cellDetectTimeout : float
        Maximum time (s) to wait for cell detection before switching to fallback state (default 30 s)
    DAQReservationTimeout : float
        Maximum time (s) to wait for DAQ reservation if reserveDAQ=True (defualt 30 s)

    """
    stateName = 'cell detect'
    def __init__(self, *args, **kwds):
        self.contAdvanceFuture = None
        self.lastMove = 0.0
        self.stepCount = 0
        self.advanceSteps = None
        PatchPipetteState.__init__(self, *args, **kwds)

    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'bath',
    }
    _parameterTreeConfig = {
        'autoAdvance': {'default': True, 'type': 'bool'},
        'advanceMode': {'default': 'target', 'type': 'str', 'values': ['target', 'axial', 'vertical']},
        'advanceContinuous': {'default': True, 'type': 'bool'},
        'advanceStepInterval': {'default': 0.1, 'type': 'float', 'suffix': 's'},
        'advanceStepDistance': {'default': 1e-6, 'type': 'float', 'suffix': 'm'},
        'maxAdvanceDistance': {'default': None, 'type': 'float', 'optional': True, 'suffix': 'm'},
        'maxAdvanceDistancePastTarget': {'default': 10e-6, 'type': 'float', 'suffix': 'm'},
        'maxAdvanceDepthBelowSurface': {'default': None, 'type': 'float', 'optional': True, 'suffix': 'm'},
        'advanceSpeed': {'default': 2e-6, 'type': 'float', 'suffix': 'm/s'},
        'fastDetectionThreshold': {'default': 1e6, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionThreshold': {'default': 0.2e6, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionSteps': {'default': 3, 'type': 'int'},
        'breakThreshold': {'default': -1e6, 'type': 'float', 'suffix': 'Ω'},
        'reserveDAQ': {'default': False, 'type': 'bool'},
        'cellDetectTimeout': {'default': 30, 'type': 'float', 'suffix': 's'},
        'DAQReservationTimeout': {'default': 30, 'type': 'float', 'suffix': 's'},
    }

    def run(self):
        if not self.config["reserveDAQ"]:
            return self._do_cell_detect()
        daq_name = self.dev.clampDevice.getDAQName("primary")
        self.setState(f"cell detect: waiting for {daq_name} lock")
        with getManager().reserveDevices([daq_name], timeout=self.config["DAQReservationTimeout"]):
            self.setState(f"cell detect: {daq_name} lock acquired")
            return self._do_cell_detect()

    def _do_cell_detect(self):
        startTime = ptime.time()
        config = self.config
        dev = self.dev
        self.monitorTestPulse()

        dev.clampDevice.autoPipetteOffset()

        patchrec = dev.patchRecord()
        patchrec['attemptedCellDetect'] = True
        initialResistance = None
        recentTestPulses = deque(maxlen=config['slowDetectionSteps'] + 1)
        patchrec['cellDetectInitialTarget'] = tuple(dev.pipetteDevice.targetPosition())

        while True:
            if config['cellDetectTimeout'] is not None and ptime.time() - startTime > config['cellDetectTimeout']:
                self._taskDone(interrupted=True, error="Timed out waiting for cell detect.")
                return config['fallbackState']

            self.checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue
            recentTestPulses.extend(tps)

            tp = tps[-1]
            ssr = tp.analysis()['steadyStateResistance']
            if initialResistance is None:
                # take note of initial resistance
                initialResistance = ssr
                self.setState(f"cell detection: got initial resistance {ssr}")

            # check for pipette break
            self.setState("cell detection: check for pipette break")
            if ssr < initialResistance + config['breakThreshold']:
                self._taskDone(interrupted=True, error="Pipette broken")
                patchrec['detectedCell'] = False
                return 'broken'

            # fast cell detection
            self.setState("cell detection: check for cell proximity")
            if ssr > initialResistance + config['fastDetectionThreshold']:
                return self._transition_to_seal("cell detected (fast criteria)", patchrec)
            # slow cell detection
            if len(recentTestPulses) > config['slowDetectionSteps']:
                res = np.array([tp.analysis()['steadyStateResistance'] for tp in recentTestPulses])
                if np.all(np.diff(res) > 0) and ssr - initialResistance > config['slowDetectionThreshold']:
                    return self._transition_to_seal("cell detected (slow criteria)", patchrec)
            self.checkStop()

            if config['autoAdvance']:
                if config['advanceContinuous']:
                    # Start continuous move if needed
                    if self.contAdvanceFuture is None:
                        self.setState("cell detection: continuous pipette advance")
                        self.startContinuousMove()
                    if self.contAdvanceFuture.isDone():
                        self.contAdvanceFuture.wait()  # check for move errors
                        return self._transition_to_fallback(patchrec)
                else:
                    # advance to next position if stepping
                    if self.advanceSteps is None:
                        self.setState("cell detection: stepping pipette")
                        self.advanceSteps = self.getAdvanceSteps()
                        print(len(self.advanceSteps))
                        print(self.advanceSteps)
                    if self.stepCount >= len(self.advanceSteps):
                        return self._transition_to_fallback(patchrec)
                    # make sure we obey advanceStepInterval
                    now = ptime.time()
                    if now - self.lastMove < config['advanceStepInterval']:
                        continue
                    self.lastMove = now

                    self.singleStep()

    def _transition_to_fallback(self, patchrec):
        self._taskDone(interrupted=True, error="No cell found before end of search path")
        patchrec['detectedCell'] = False
        return self.config['fallbackState']

    def _transition_to_seal(self, reason, patchrec):
        self.setState(reason)
        self._taskDone()
        patchrec['detectedCell'] = True
        return "seal"

    def getSearchEndpoint(self):
        """Return the final position along the pipette search path, taking into account 
        maxAdvanceDistance, maxAdvanceDepthBelowSurface, and maxAdvanceDistancePastTarget.
        """
        config = self.config
        dev = self.dev
        pip = dev.pipetteDevice
        pos = np.array(pip.globalPosition())
        surface = pip.scopeDevice().getSurfaceDepth()
        target = np.array(pip.targetPosition())

        # what direction are we moving?
        if config['advanceMode'] == 'vertical':
            direction = np.array([0.0, 0.0, -1.0])
        elif config['advanceMode'] == 'axial':
            direction = pip.globalDirection()
        elif config['advanceMode'] == 'target':
            direction = target - pos
        else:
            raise ValueError("advanceMode must be 'vertical', 'axial', or 'target'  (got %r)" % config['advanceMode'])
        direction = direction / np.linalg.norm(direction)

        endpoint = None

        # max search distance
        if config['maxAdvanceDistance'] is not None:
            endpoint = pos + direction * config['maxAdvanceDistance']            

        # max surface depth 
        if config['maxAdvanceDepthBelowSurface'] is not None and direction[2] < 0:
            endDepth = surface - config['maxAdvanceDepthBelowSurface']
            dz = endDepth - pos[2]
            depthEndpt = pos + direction * (dz / direction[2])
            # is the surface depth endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint-pos) > np.linalg.norm(depthEndpt-pos):
                endpoint = depthEndpt

        # max distance past target
        if config['advanceMode'] == 'target' and config['maxAdvanceDistancePastTarget'] is not None:
            targetEndpt = target + direction * config['maxAdvanceDistancePastTarget']
            # is the target endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint-pos) > np.linalg.norm(targetEndpt-pos):
                endpoint = targetEndpt

        if endpoint is None:
            raise Exception("Cell detect state requires one of maxAdvanceDistance, maxAdvanceDepthBelowSurface, or maxAdvanceDistancePastTarget.")

        return endpoint

    def startContinuousMove(self):
        """Begin moving pipette continuously along search path.
        """
        endpoint = self.getSearchEndpoint()
        self.contAdvanceFuture = self.dev.pipetteDevice._moveToGlobal(endpoint, speed=self.config['advanceSpeed'])

    def getAdvanceSteps(self):
        """Return the list of step positions to take along the search path.
        """
        config = self.config
        endpoint = self.getSearchEndpoint()
        pos = np.array(self.dev.pipetteDevice.globalPosition())
        diff = endpoint - pos
        dist = np.linalg.norm(diff)
        nSteps = int(dist / config['advanceStepDistance'])
        step = diff * config['advanceStepDistance'] / dist
        return pos[np.newaxis, :] + step[np.newaxis, :] * np.arange(nSteps)[:, np.newaxis]

    def singleStep(self):
        """Advance a single step in the search path and block until the move has finished.
        """
        config = self.config
        dev = self.dev

        stepPos = self.advanceSteps[self.stepCount]
        self.stepCount += 1
        fut = dev.pipetteDevice._moveToGlobal(stepPos, speed=config['advanceSpeed'])
        self.waitFor(fut)

    def cleanup(self):
        if self.contAdvanceFuture is not None:
            self.contAdvanceFuture.stop()
        patchrec = self.dev.patchRecord()
        patchrec['cellDetectFinalTarget'] = tuple(self.dev.pipetteDevice.targetPosition())
        PatchPipetteState.cleanup(self)


class SealState(PatchPipetteState):
    """Handles sealing onto cell

    State name: "seal"

    - monitor resistance to detect loose seal and GOhm seal
    - set holding potential after loose seal
    - modulate pressure to improve likelihood of forming seal
    - cut pressure after GOhm and transition to cell attached

    Parameters
    ----------
    pressureMode : str
        'auto' enables automatic pressure control during sealing; 
        'user' simply switches to user control for sealing.
    startingPressure : float
        Initial pressure (Pascals) to apply when beginning sealing in 'auto' mode.
    holdingThreshold : float
        Seal resistance (ohms) above which the holding potential will switch 
        from its initial value to the value specified in the *holdingPotential*
        parameter.
    holdingPotential : float
        Holding potential (volts) to apply to the pipette after the seal resistance
        becomes greater than *holdingThreshold*.
    sealThreshold : float
        Seal resistance (ohms) above which the pipette is considered sealed and
        transitions to the 'cell attached' state.  Default 1e9
    breakInThreshold : float
        Capacitance (Farads) above which the pipette is considered to be whole-cell and 
        transitions to the 'break in' state (in case of partial break-in, we don't want to transition
        directly to 'whole cell' state).
    nSlopeSamples : int
        Number of consecutive test pulse measurements over which the rate of change
        in seal resistance is measured (for automatic pressure control).
    autoSealTimeout : float
        Maximum timeout (seconds) before the seal attempt is aborted, 
        transitioning to *fallbackState*.
    pressureLimit : float
        The largest vacuum pressure (pascals, expected negative value) to apply during sealing.
        When this pressure is reached, the pressure is reset to 0 and the ramp starts over after a delay.
    pressureChangeRates : list
        A list of (seal_resistance_threshold, pressure_change) tuples that determine how much to
        change the current seal pressure based on the rate of change in seal resistance.
        For each iteration, select the first tuple in the list where the current rate of
        change in seal resistance is _less_ than the threshold specified in the tuple.
    delayBeforePressure : float
        Wait time (seconds) at beginning of seal state before applying negative pressure.
    delayAfterSeal : float
        Wait time (seconds) after GOhm seal is acquired, before transitioning to next state.
    afterSealPressure : float
        Pressure (Pascals) to apply during *delayAfterSeal* interval. This can help to stabilize the seal after initial formamtion.
    resetDelay : float
        Wait time (seconds) after pressureLimit is reached, before restarting pressure ramp.

    """
    stateName = 'seal'

    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'fouled',
    }
    _parameterTreeConfig = {
        'pressureMode': {'type': 'str', 'default': 'user', 'values': ['auto', 'user']},
        'startingPressure': {'type': 'float', 'default': -1000},
        'holdingThreshold': {'type': 'float', 'default': 100e6},
        'holdingPotential': {'type': 'float', 'default': -70e-3},
        'sealThreshold': {'type': 'float', 'default': 1e9},
        'breakInThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'nSlopeSamples': {'type': 'int', 'default': 5},
        'autoSealTimeout': {'type': 'float', 'default': 30.0, 'suffix': 's'},
        'pressureLimit': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},
        'maxVacuum': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},  # TODO Deprecated. Remove after 2024-10-01
        'pressureChangeRates': {'type': 'str', 'default': "[(0.5e6, -100), (100e6, 0), (-1e6, 200)]"},  # TODO
        'delayBeforePressure': {'type': 'float', 'default': 0.0, 'suffix': 's'},
        'delayAfterSeal': {'type': 'float', 'default': 5.0, 'suffix': 's'},
        'afterSealPressure': {'type': 'float', 'default': -1000, 'suffix': 'Pa'},
        'resetDelay': {'type': 'float', 'default': 5.0, 'suffix': 's'},
    }

    def initialize(self):
        if self.config['maxVacuum'] != self.defaultConfig()['maxVacuum']:
            warnings.warn("maxVacuum parameter is deprecated; use pressureLimit instead", DeprecationWarning)
            if self.config['pressureLimit'] != self.defaultConfig()['pressureLimit']:
                self.config['pressureLimit'] = self.config['maxVacuum']
        self.dev.clean = False
        PatchPipetteState.initialize(self)

    def run(self):
        self.monitorTestPulse()
        config = self.config
        dev: "PatchPipette" = self.dev

        recentTestPulses = deque(maxlen=config['nSlopeSamples'])
        while True:
            initialTP = dev.lastTestPulse()
            if initialTP is not None:
                break
            self.checkStop()
            time.sleep(0.05)
        
        initialResistance = initialTP.analysis()['steadyStateResistance']
        patchrec = dev.patchRecord()
        patchrec['resistanceBeforeSeal'] = initialResistance
        patchrec['capacitanceBeforeSeal'] = initialTP.analysis()['capacitance']
        startTime = ptime.time()
        pressure = config['startingPressure']
        if isinstance(config['pressureChangeRates'], str):
            config['pressureChangeRates'] = eval(config['pressureChangeRates'], units.__dict__)

        mode = config['pressureMode']
        self.setState(f'beginning seal (mode: {mode!r})')
        if mode == 'user':
            dev.pressureDevice.setPressure(source='user', pressure=0)
        elif mode == 'auto':
            dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
        else:
            raise ValueError(f"pressureMode must be 'auto' or 'user' (got '{mode}')")

        dev.setTipClean(False)

        patchrec['attemptedSeal'] = True
        holdingSet = False

        while True:
            self.checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            tps = self.getTestPulses(timeout=0.2)            
            recentTestPulses.extend(tps)
            if len(tps) == 0:
                continue
            tp = tps[-1]

            ssr = tp.analysis()['steadyStateResistance']
            cap = tp.analysis()['capacitance']

            patchrec['resistanceBeforeBreakin'] = ssr
            patchrec['capacitanceBeforeBreakin'] = cap

            if ssr > config['holdingThreshold'] and not holdingSet:
                self.setState(f'enable holding potential {config["holdingPotential"] * 1000:0.1f} mV')
                dev.clampDevice.setHolding(mode="VC", value=config['holdingPotential'])
                holdingSet = True

            # seal detected? 
            if ssr > config['sealThreshold']:
                # delay for a short period, possibly applying pressure to allow seal to stabilize
                if config['delayAfterSeal'] > 0:
                    if config['afterSealPressure'] == 0:
                        dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
                    else:
                        dev.pressureDevice.setPressure(source='regulator', pressure=config['afterSealPressure'])
                    self.sleep(config['delayAfterSeal'])

                dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
                self.setState('gigaohm seal detected')

                dev.clampDevice.autoCapComp()

                self._taskDone()
                patchrec['sealSuccessful'] = True
                return 'cell attached'
            
            if mode == 'auto':
                dt = ptime.time() - startTime
                if dt < config['delayBeforePressure']:
                    # delay at atmospheric pressure before starting suction
                    continue

                if dt > config['autoSealTimeout']:
                    patchrec['sealSuccessful'] = False
                    self._taskDone(interrupted=True, error=f"Seal failed after {dt:f} seconds")
                    return config['fallbackState']

                # update pressure
                res = np.array([tp.analysis()['steadyStateResistance'] for tp in recentTestPulses])
                times = np.array([tp.startTime() for tp in recentTestPulses])
                slope = scipy.stats.linregress(times, res).slope
                pressure = np.clip(pressure, config['pressureLimit'], 0)
                
                # decide how much to adjust pressure based on rate of change in seal resistance
                for max_slope, change in config['pressureChangeRates']:
                    if max_slope is None or slope < max_slope:
                        pressure += change
                        break
                
                # here, if the pressureLimit has been achieved and we are still sealing, cycle back to starting
                # pressure and redo the pressure change
                if pressure <= config['pressureLimit']:
                    dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
                    self.sleep(config['resetDelay'])
                    pressure = config['startingPressure']
                    dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
                    continue

                self.setState(f'Rpip slope: {slope / 1e6:g} MOhm/sec   Pressure: {pressure:g} Pa')
                dev.pressureDevice.setPressure(source='regulator', pressure=pressure)

    def cleanup(self):
        self.dev.pressureDevice.setPressure(source='atmosphere')
        PatchPipetteState.cleanup(self)


class CellAttachedState(PatchPipetteState):
    """Pipette in cell-attached configuration

    State name: "cell attached"

    - automatically transition to 'break in' after a delay
    - monitor for spontaneous break-in or loss of attached cell

    Parameters
    ----------
    autoBreakInDelay : float
        Delay time (seconds) before transitioning to 'break in' state. If None, then never automatically
        transition to break-in.
    breakInThreshold : float
        Capacitance (Farads) above which the pipette is considered to be whole-cell and immediately
        transitions to the 'break in' state (in case of partial break-in, we don't want to transition
        directly to 'whole cell' state).
    holdingCurrentThreshold : float
        Holding current (Amps) below which the cell is considered to be lost and the state fails.
    spontaneousBreakInState:
        Name of state to transition to when the membrane breaks in spontaneously. Default
        is 'break in' so that partial break-ins will be completed. To disable, set to 'whole cell'.
    """
    stateName = 'cell attached'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': -70e-3,
        'initialTestPulseEnable': True,
    }
    _parameterTreeConfig = {
        'autoBreakInDelay': {'type': 'float', 'default': None, 'optional': True, 'suffix': 's'},
        'breakInThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'holdingCurrentThreshold': {'type': 'float', 'default': -1e-9, 'suffix': 'A'},
        'spontaneousBreakInState': {'type': 'str', 'default': 'break in'},
    }

    def run(self):
        self.monitorTestPulse()
        patchrec = self.dev.patchRecord()
        config = self.config
        startTime = ptime.time()
        delay = config['autoBreakInDelay']
        while True:
            if delay is not None and ptime.time() - startTime > delay:
                return 'break in'

            self.checkStop()

            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue

            tp = tps[-1]
            holding = tp.analysis()['baselineCurrent']
            if holding < self.config['holdingCurrentThreshold']:
                self._taskDone(interrupted=True, error='Holding current exceeded threshold.')
                return
            
            cap = tp.analysis()['capacitance']
            if cap > config['breakInThreshold']:
                patchrec['spontaneousBreakin'] = True
                return config['spontaneousBreakInState']

            patchrec['resistanceBeforeBreakin'] = tp.analysis()['steadyStateResistance']
            patchrec['capacitanceBeforeBreakin'] = cap


class BreakInState(PatchPipetteState):
    """State using pressure pulses to rupture membrane for whole cell recording.

    State name: "break in"

    - applies a sequence of pressure pulses of increasing strength
    - monitors for break-in

    Parameters
    ----------
    nPulses : list of int
        Number of pressure pulses to apply on each break-in attempt
    pulseDurations : list of float
        Duration (seconds) of pulses to apply on each break in attempt
    pulsePressures : list of float
        Pressure (Pascals) of pulses to apply on each break in attempt
    pulseInterval : float
        Delay (seconds) between break in attempts
    capacitanceThreshold : float
        Capacitance (Farads) above which to transition to the 'whole cell' state
        (note that resistance threshold must also be met)
    resistanceThreshold : float
        Resistance (Ohms) below which to transition to the 'whole cell' state if 
        capacitance threshold is met, or fail otherwise.
    holdingCurrentThreshold : float
        Holding current (Amps) below which the cell is considered to be lost and the state fails.
    """
    stateName = 'break in'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': -70e-3,
        'initialTestPulseEnable': True,
        'fallbackState': 'fouled',
    }
    _parameterTreeConfig = {
        # idea!
        # 'pulses', 'type': 'table', 'columns': [
        #     'nPulses', 'type': 'int'},
        #     'duration', 'type': 'float', 'suffix': 's'},
        #     'pressure', 'type': 'float', 'suffix': 'Pa'},
        # ]},
        'nPulses': {'type': 'str', 'default': "[1, 1, 1, 1, 1, 2, 2, 3, 3, 5]"},
        'pulseDurations': {'type': 'str', 'default': "[0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.7, 1.5]"},
        'pulsePressures': {'type': 'str', 'default': "[-30e3, -35e3, -40e3, -50e3, -60e3, -60e3, -60e3, -60e3, -60e3, -60e3]"},
        'pulseInterval': {'type': 'float', 'default': 2},
        'resistanceThreshold': {'type': 'float', 'default': 650e6, 'suffix': 'Ω'},
        'capacitanceThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'holdingCurrentThreshold': {'type': 'float', 'default': -1e-9, 'suffix': 'A'},
    }

    def run(self):
        patchrec = self.dev.patchRecord()
        self.monitorTestPulse()
        config = self.config
        if isinstance(config['nPulses'], str):
            config['nPulses'] = eval(config['nPulses'], units.__dict__)
        if isinstance(config['pulseDurations'], str):
            config['pulseDurations'] = eval(config['pulseDurations'], units.__dict__)
        if isinstance(config['pulsePressures'], str):
            config['pulsePressures'] = eval(config['pulsePressures'], units.__dict__)
        lastPulse = ptime.time()
        attempt = 0

        while True:
            status = self.checkBreakIn()
            if status is True:
                patchrec['spontaneousBreakin'] = True
                patchrec['breakinSuccessful'] = True
                return 'whole cell'
            elif status is False:
                return

            if ptime.time() - lastPulse > config['pulseInterval']:
                nPulses = config['nPulses'][attempt]
                pdur = config['pulseDurations'][attempt]
                press = config['pulsePressures'][attempt]
                self.setState('Break in attempt %d' % attempt)
                status = self.attemptBreakIn(nPulses, pdur, press)
                patchrec['attemptedBreakin'] = True
                if status is True:
                    patchrec['breakinSuccessful'] = True
                    patchrec['spontaneousBreakin'] = False
                    return 'whole cell'
                elif status is False:
                    patchrec['breakinSuccessful'] = False
                    return config['fallbackState']
                lastPulse = ptime.time()
                attempt += 1
        
            if attempt >= len(config['nPulses']):
                self._taskDone(interrupted=True, error='Breakin failed after %d attempts' % attempt)
                patchrec['breakinSuccessful'] = False
                return config['fallbackState']

    def attemptBreakIn(self, nPulses, duration, pressure):
        for _ in range(nPulses):
            # get the next test pulse
            status = self.checkBreakIn()
            if status is not None:
                return status
            self.dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            time.sleep(duration)
            self.dev.pressureDevice.setPressure(source='atmosphere')
                
    def checkBreakIn(self):
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
        tp = tps[-1]

        analysis = tp.analysis()
        holding = analysis['baselineCurrent']
        if holding < self.config['holdingCurrentThreshold']:
            self._taskDone(interrupted=True, error='Holding current exceeded threshold.')
            return False

        # If ssr and cap cross threshold => successful break in
        # If only ssr crosses threshold => lost cell
        # If only cap crosses threshold => partial break in, keep trying
        ssr = analysis['steadyStateResistance']
        cap = analysis['capacitance']
        if self.config['resistanceThreshold'] is not None and ssr < self.config['resistanceThreshold']:
            return True
            # if cap > self.config['capacitanceThreshold']:
            #     return True
            # else:
            #     self._taskDone(interrupted=True, error="Resistance dropped below threshold but no cell detected.")
            #     return False

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after clean")
        PatchPipetteState.cleanup(self)


class ResealAnalysis(object):
    """Class to analyze test pulses and determine reseal behavior."""
    def __init__(self, stretch_threshold: float, tear_threshold: float, detection_tau: float, repair_tau: float):
        self._stretch_threshold = stretch_threshold
        self._tear_threshold = tear_threshold
        self._detection_tau = detection_tau
        self._repair_tau = repair_tau
        self._last_measurement: Optional[np.void] = None

    def is_stretching(self) -> bool:
        """Return True if the resistance is increasing too quickly."""
        return self._last_measurement and self._last_measurement['stretching']

    def is_tearing(self) -> bool:
        """Return True if the resistance is decreasing."""
        return self._last_measurement and self._last_measurement['tearing']

    def process_test_pulses(self, tps: list[TestPulse]) -> np.ndarray:
        return self.process_measurements(
            np.array([(tp.startTime(), tp.analysis()['steadyStateResistance']) for tp in tps]))

    def process_measurements(self, measurements: np.ndarray) -> np.ndarray:
        ret_array = np.zeros(
            len(measurements),
            dtype=[
                ('time', float),
                ('resistance', float),
                ('detect_avg', float),
                ('repair_avg', float),
                ('detect_ratio', float),
                ('repair_ratio', float),
                ('stretching', bool),
                ('tearing', bool),
            ])
        for i, measurement in enumerate(measurements):
            start_time, resistance = measurement
            if i == 0:
                if self._last_measurement is None:
                    ret_array[i] = (start_time, resistance, 1, 1, 0, 0, False, False)
                    self._last_measurement = ret_array[i]
                    continue
                else:
                    last_measurement = self._last_measurement
            else:
                last_measurement = ret_array[i - 1]

            dt = start_time - last_measurement['time']

            detection_alpha = 1 - np.exp(-dt / self._detection_tau)
            detection_avg = (
                    last_measurement['detect_avg'] * (1 - detection_alpha)
                    + resistance * detection_alpha
            )
            detection_ratio = np.log10(detection_avg / last_measurement['detect_avg'])
            repair_alpha = 1 - np.exp(-dt / self._repair_tau)
            repair_avg = (
                    last_measurement['repair_avg'] * (1 - repair_alpha)
                    + resistance * repair_alpha
            )
            repair_ratio = np.log10(repair_avg / last_measurement['repair_avg'])

            is_stretching = detection_ratio > self._stretch_threshold or repair_ratio > self._stretch_threshold
            is_tearing = detection_ratio < self._tear_threshold or repair_ratio < self._tear_threshold
            ret_array[i] = (
                start_time,
                resistance,
                detection_avg,
                repair_avg,
                detection_ratio,
                repair_ratio,
                is_stretching,
                is_tearing,
            )
            self._last_measurement = ret_array[i]
        return ret_array


class ResealState(PatchPipetteState):
    """State that retracts pipette slowly to attempt to reseal the cell.

    Negative pressure may optionally be applied to attempt nucleus extraction

    State name: "reseal"

    Parameters
    ----------
    extractNucleus : bool
        Whether to attempt nucleus extraction during reseal (default True)
    nuzzlePressureLimit : float
        Largest vacuum pressure (pascals, expected negative) to apply during nuzzling (default is -4 kPa)
    nuzzleDuration : float
        Duration (seconds) to spend nuzzling (default is 15s)
    nuzzleInitialPressure : float
        Initial pressure (Pa) to apply during nuzzling (default is 0 Pa)
    nuzzleLateralWiggleRadius : float
        Radius of lateral wiggle during nuzzling (default is 5 µm)
    nuzzleRepetitions : int
        Number of times to repeat the nuzzling sequence (default is 2)
    nuzzleSpeed : float
        Speed to move pipette during nuzzling (default is 5 µm / s)
    initialPressure : float
        Initial pressure (Pa) to apply after nucleus nuzzling, before retraction (default is -0.5 kPa)
    retractionPressure : float
        Pressure (Pa) to apply during retraction (default is -4 kPa)
    pressureChangeRate : float
        Rate at which pressure should change from initial/nuzzleLimit to retraction (default is 0.5 kPa / min)
    retractionSpeed : float
        Speed in m/s to move pipette during retraction (default is 0.3 um / s)
    resealTimeout : float
        Seconds before reseal attempt exits, not including grabbing the nucleus and baseline measurements (default is
        10 min)
    detectionTau : float
        Seconds of resistence measurements to average when detecting tears and stretches (default 1s)
    repairTau : float
        Seconds of resistence measurements to average when determining when a tear or stretch has been corrected
        (default 10s)
    fallbackState : str
        State to transition to if reseal fails (default is 'whole cell')
    stretchDetectionThreshold : float
        Maximum access resistance ratio before the membrane is considered to be stretching (default is 1.05)
    tearDetectionThreshold : float
        Minimum access resistance ratio before the membrane is considered to be tearing (default is 1)
    retractionSuccessDistance : float
        Distance (meters) to retract before checking for successful reseal (default is 200 µm)
    resealSuccessResistance : float
        Resistance (Ohms) above which the reseal is considered successful (default is 1e9)
    resealSuccessDuration : float
        Duration (seconds) to wait after successful reseal before transitioning to the slurp (default is 5s)
    slurpPressure : float
        Pressure (Pa) to apply when trying to get the nucleus into the pipette (default is -10 kPa)
    slurpRetractionSpeed : float
        Speed in m/s to move pipette during nucleus slurping (default is 10 µm / s)
    slurpDuration : float
        Duration (seconds) to apply suction when trying to get the nucleus into the pipette (default is 10s)
    slurpHeight : float
        Height (meters) above the surface to conduct nucleus slurping and visual check (default is 50 µm)
    """

    stateName = 'reseal'

    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialClampHolding': -70e-3,
        'initialTestPulseEnable': True,
        'initialPressure': -0.5e3,
        'initialPressureSource': 'regulator',
    }
    _parameterTreeConfig = {
        'extractNucleus': {'type': 'bool', 'default': True},
        'fallbackState': {'type': 'str', 'default': 'whole cell'},
        'nuzzleDuration': {'type': 'float', 'default': 15, 'suffix': 's'},
        'nuzzleInitialPressure': {'type': 'float', 'default': 0, 'suffix': 'Pa'},
        'nuzzleLateralWiggleRadius': {'type': 'float', 'default': 5e-6, 'suffix': 'm'},
        'nuzzlePressureLimit': {'type': 'float', 'default': -1e3, 'suffix': 'Pa'},
        'nuzzleRepetitions': {'type': 'int', 'default': 2},
        'nuzzleSpeed': {'type': 'float', 'default': 5e-6, 'suffix': 'm/s'},
        'pressureChangeRate': {'type': 'float', 'default': 0.5e3 / 60, 'suffix': 'Pa/s'},
        'resealTimeout': {'type': 'float', 'default': 10 * 60, 'suffix': 's'},
        'retractionPressure': {'type': 'float', 'default': -4e3, 'suffix': 'Pa'},
        'retractionSpeed': {'type': 'float', 'default': 0.3e-6, 'suffix': 'm/s'},
        'retractionSuccessDistance': {'type': 'float', 'default': 200e-6, 'suffix': 'm'},
        'resealSuccessResistance': {'type': 'float', 'default': 1e9, 'suffix': 'Ω'},
        'resealSuccessDuration': {'type': 'float', 'default': 5, 'suffix': 's'},
        'detectionTau': {'type': 'float', 'default': 1, 'suffix': 's'},
        'repairTau': {'type': 'float', 'default': 10, 'suffix': 's'},
        'stretchDetectionThreshold': {'type': 'float', 'default': 0.005},
        'tearDetectionThreshold': {'type': 'float', 'default': -0.00128},
        'slurpPressure': {'type': 'float', 'default': -10e3, 'suffix': 'Pa'},
        'slurpRetractionSpeed': {'type': 'float', 'default': 10e-6, 'suffix': 'm/s'},
        'slurpDuration': {'type': 'float', 'default': 10, 'suffix': 's'},
        'slurpHeight': {'type': 'float', 'default': 50e-6, 'suffix': 'm'},
    }

    def __init__(self, *args, **kwds):
        PatchPipetteState.__init__(self, *args, **kwds)
        self._moveFuture = None
        self._pressureFuture = None
        self._lastResistance = None
        self._firstSuccessTime = None
        self._startPosition = np.array(self.dev.pipetteDevice.globalPosition())
        self._analysis = ResealAnalysis(
            stretch_threshold=self.config['stretchDetectionThreshold'],
            tear_threshold=self.config['tearDetectionThreshold'],
            detection_tau=self.config['detectionTau'],
            repair_tau=self.config['repairTau'],
        )

    def nuzzle(self):
        """Wiggle the pipette around inside the cell to clear space for a nucleus to be extracted."""
        self.setState("nuzzling")
        pos = np.array(self.dev.pipetteDevice.globalPosition())
        # TODO move back a little?
        pipette_direction = self.dev.pipetteDevice.globalDirection()

        def random_wiggle_direction():
            """pick a random point on a circle perpendicular to the pipette axis"""
            while np.linalg.norm(vec := np.cross(pipette_direction, np.random.uniform(-1, 1, size=3))) == 0:
                pass  # prevent division by zero
            return self.config['nuzzleLateralWiggleRadius'] * vec / np.linalg.norm(vec)

        prev_dir = random_wiggle_direction()
        for _ in range(self.config['nuzzleRepetitions']):
            self.dev.pressureDevice.setPressure(source='regulator', pressure=self.config['nuzzleInitialPressure'])
            self._pressureFuture = self.dev.pressureDevice.rampPressure(
                target=self.config['nuzzlePressureLimit'], duration=self.config['nuzzleDuration'])
            start = ptime.time()
            while ptime.time() - start < self.config['nuzzleDuration']:
                while np.dot(direction := random_wiggle_direction(), prev_dir) > 0:
                    pass  # ensure different direction from previous
                self._moveFuture = self.dev.pipetteDevice._moveToGlobal(pos=pos + direction, speed=self.config['nuzzleSpeed'])
                prev_dir = direction
                self.waitFor(self._moveFuture)
            self._moveFuture = self.dev.pipetteDevice._moveToGlobal(pos=pos, speed=self.config['nuzzleSpeed'])
            self.waitFor(self._moveFuture)
            self.waitFor(self._pressureFuture)

    @Future.wrap
    def startRollingResistanceThresholds(self, _future: Future):
        """Start a rolling average of the resistance to detect stretching and tearing. Load the first 20s of data."""
        self.monitorTestPulse()
        start = ptime.time()
        while ptime.time() - start < self.config['repairTau']:
            _future.checkStop()
            self.processAtLeastOneTestPulse()

    def isStretching(self) -> bool:
        """Return True if the resistance is increasing too quickly."""
        return self._analysis.is_stretching()

    def isTearing(self) -> bool:
        """Return True if the resistance is decreasing."""
        return self._analysis.is_tearing()

    def isRetractionSuccessful(self):
        if self.retractionDistance() > self.config['retractionSuccessDistance'] or (
                self._lastResistance is not None and self._lastResistance > self.config['resealSuccessResistance']
        ):
            if self._firstSuccessTime is None:
                self._firstSuccessTime = ptime.time()
            elif ptime.time() - self._firstSuccessTime > self.config['resealSuccessDuration']:
                return True
        else:
            self._firstSuccessTime = None
        return False

    def processAtLeastOneTestPulse(self):
        """Wait for at least one test pulse to be processed."""
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
            self.sleep(0.2)
        self._lastResistance = self._analysis.process_test_pulses(tps)['resistance'][-1]

    def run(self):
        config = self.config
        dev = self.dev
        baseline_future = self.startRollingResistanceThresholds()
        if config['extractNucleus'] is True:
            self.nuzzle()
        dev.pressureDevice.setPressure(config['initialPressureSource'], config['initialPressure'])
        self.checkStop()
        self.setState("measuring baseline resistance")
        self.waitFor(baseline_future, timeout=self.config['repairTau'])
        self._pressureFuture = dev.pressureDevice.rampPressure(
            target=config['retractionPressure'], rate=config['pressureChangeRate'])

        start_time = ptime.time()  # getting the nucleus and baseline measurements doesn't count
        recovery_future = None
        retraction_future = None
        while not self.isRetractionSuccessful():
            if config['resealTimeout'] is not None and ptime.time() - start_time > config['resealTimeout']:
                self._taskDone(interrupted=True, error="Timed out attempting to reseal.")
                return config['fallbackState']

            self.processAtLeastOneTestPulse()

            if self.isStretching():
                if retraction_future and not retraction_future.isDone():
                    self.setState("handling stretch")
                    retraction_future.stop()
            elif self.isTearing():
                if retraction_future and not retraction_future.isDone():
                    self.setState("handling tear")
                    retraction_future.stop()
                    self._moveFuture = recovery_future = self.dev.pipetteDevice._moveToGlobal(
                        pos=self._startPosition, speed=self.config['retractionSpeed'])
            elif retraction_future is None or retraction_future.wasInterrupted():
                if recovery_future is not None and not recovery_future.isDone():
                    recovery_future.stop()
                self.setState("retracting")
                self._moveFuture = retraction_future = dev.pipetteDevice.retractFromSurface(
                    speed=config['retractionSpeed'])

            self.sleep(0.2)

        self.setState("slurping in nucleus")
        self.cleanup()
        dev.pressureDevice.setPressure(source='regulator', pressure=config['slurpPressure'])
        self._moveFuture = dev.pipetteDevice.goAboveTarget(config['slurpRetractionSpeed'])
        self.sleep(config['slurpDuration'])
        self.waitFor(self._moveFuture, timeout=90)
        dev.pipetteDevice.focusTip()
        dev.pressureDevice.setPressure(source='regulator', pressure=config['initialPressure'])
        self.sleep(np.inf)

    def retractionDistance(self):
        return np.linalg.norm(np.array(self.dev.pipetteDevice.globalPosition()) - self._startPosition)

    def cleanup(self):
        if self._moveFuture is not None:
            self._moveFuture.stop()
        if self._pressureFuture is not None:
            self._pressureFuture.stop()


class MoveNucleusToHomeState(PatchPipetteState):
    """State that moves the pipette to its home position while applying negative pressure.

    State name: home with nucleus

    Parameters
    ----------
    pressureLimit : float
        The smallest vacuum pressure (pascals, expected negative value) to allow during state.
    """
    stateName = "home with nucleus"
    _parameterDefaultOverrides = {
        'initialPressure': None,
        'initialPressureSource': 'regulator',
    }
    _parameterTreeConfig = {
        # for expected negative values, a maximum is the "smallest" magnitude:
        'pressureLimit': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},
        'positionName': {'type': 'str', 'default': 'extract'},
    }

    def run(self):
        self.waitFor(self.dev.pressureDevice.rampPressure(maximum=self.config['pressureLimit']), timeout=None)
        self.waitFor(self.dev.pipetteDevice.moveTo(self.config['positionName'], 'fast'), timeout=None)
        self.sleep(float("inf"))


class BlowoutState(PatchPipetteState):
    stateName = 'blowout'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'bath',
    }
    _parameterTreeConfig = {
        'blowoutPressure': {'type': 'float', 'default': 65e3, 'suffix': 'Pa'},
        'blowoutDuration': {'type': 'float', 'default': 2.0, 'suffix': 'Pa'},
    }

    def run(self):
        patchrec = self.dev.patchRecord()
        self.monitorTestPulse()
        config = self.config

        fut = self.dev.pipetteDevice.retractFromSurface()
        if fut is not None:
            self.waitFor(fut, timeout=None)

        self.dev.pressureDevice.setPressure(source='regulator', pressure=config['blowoutPressure'])
        self.sleep(config['blowoutDuration'])
        self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        # wait until we have a test pulse that ran after blowout was finished.
        start = ptime.time()
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0 or tps[-1].startTime() < start:
                continue
            break

        tp = tps[-1].analysis()
        patchrec['resistanceAfterBlowout'] = tp['steadyStateResistance']
        self.dev.finishPatchRecord()
        return config['fallbackState']
        
    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after blowout")
        PatchPipetteState.cleanup(self)


class CleanState(PatchPipetteState):
    """Pipette cleaning state.

    Cycles +/- pressure in a "clean" bath followed by an optional "rinse" bath.

    Parameters
    ----------
    cleanSequence : list
        List of (pressure (Pa), duration (s)) pairs specifying how to pulse pressure while the pipette tip is in the
        cleaning well.
    rinseSequence : list
        List of (pressure (Pa), duration (s)) pairs specifying how to pulse pressure while the pipette tip is in the
        rinse well.
    approachHeight : float
        Distance (m) above the clean/rinse wells to approach from. This is needed to ensure the pipette avoids the well
        walls when approaching.
    """
    stateName = 'clean'

    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': False,
        'fallbackState': 'out',
        'finishPatchRecord': True,
    }
    _parameterTreeConfig = {
        'cleanSequence': {'type': 'str', 'default': "[(-35e3, 1.0), (100e3, 1.0)] * 5"},  # TODO
        'rinseSequence': {'type': 'str', 'default': "[(-35e3, 3.0), (100e3, 10.0)]]"},  # TODO
        'approachHeight': {'type': 'float', 'default': 5e-3, 'suffix': 'm'},
    }

    def __init__(self, *args, **kwds):
        self.currentFuture = None
        PatchPipetteState.__init__(self, *args, **kwds)

    def run(self):
        self.monitorTestPulse()

        config = self.config.copy()
        dev = self.dev
        pip = dev.pipetteDevice

        self.setState('cleaning')

        # retract to safe position for visiting cleaning wells
        startPos = pip.globalPosition()
        safePos = pip.pathGenerator.safeYZPosition(startPos)
        path = pip.pathGenerator.safePath(startPos, safePos, 'fast')
        fut = pip._movePath(path)
        if fut is not None:
            self.waitFor(fut, timeout=None)

        for stage in ('clean', 'rinse'):
            self.checkStop()

            sequence = config[f'{stage}Sequence']
            if isinstance(sequence, str):
                sequence = eval(sequence, units.__dict__)
            if len(sequence) == 0:
                continue

            wellPos = pip.loadPosition(stage)
            if wellPos is None:
                raise ValueError(f"Device {pip.name()} does not have a stored {stage} position.")

            # lift up, then sideways, then down into well
            waypoint1 = safePos.copy()
            waypoint1[2] = wellPos[2] + config['approachHeight']
            waypoint2 = wellPos.copy()
            waypoint2[2] = waypoint1[2]
            path = [(waypoint1, 'fast', False), (waypoint2, 'fast', True), (wellPos, 'fast', False)]

            self.currentFuture = pip._movePath(path)

            # todo: if needed, we can check TP for capacitance changes here
            # and stop moving as soon as the fluid is detected
            self.waitFor(self.currentFuture, timeout=None)

            for pressure, delay in sequence:
                dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
                self.checkStop(delay)

            self.resetPosition()

        dev.pipetteRecord()['cleanCount'] += 1
        dev.setTipClean(True)
        self.resetPosition()
        dev.newPatchAttempt()
        return 'out'

    def resetPosition(self):
        if self.currentFuture is not None:
            # play in reverse
            fut = self.currentFuture
            self.currentFuture = None
            self.waitFor(fut.undo(), timeout=None)

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after clean")
        
        self.resetPosition()
            
        PatchPipetteState.cleanup(self)


class NucleusCollectState(PatchPipetteState):
    """Nucleus collection state.

    Cycles +/- pressure in a nucleus collection tube.

    Parameters
    ----------
    pressureSequence : list
        List of (pressure (Pa), duration (s)) pairs specifying how to pulse pressure while the pipette tip is in the
        cleaning well.
    approachDistance : float
        Distance (m) from collection location to approach from.
    """
    stateName = 'collect'

    _parameterDefaultOverrides = {
         'initialPressureSource': 'atmosphere',
         'initialTestPulseEnable': False,
         'fallbackState': 'out',
     }
    _parameterTreeConfig = {
        'pressureSequence': {'type': 'str', 'default': "[(60e3, 4.0), (-35e3, 1.0)] * 5"},
        'approachDistance': {'type': 'float', 'default': 30e-3, 'suffix': 's'},
    }

    def __init__(self, *args, **kwds):
        self.currentFuture = None
        PatchPipetteState.__init__(self, *args, **kwds)

    def run(self):
        config = self.config.copy()
        dev = self.dev
        pip = dev.pipetteDevice

        self.setState('nucleus collection')

         # move to top of collection tube
        self.startPos = pip.globalPosition()
        self.collectionPos = pip.loadPosition('collect')
        # self.approachPos = self.collectionPos - pip.globalDirection() * config['approachDistance']

        # self.waitFor([pip._moveToGlobal(self.approachPos, speed='fast')])
        self.waitFor(pip._moveToGlobal(self.collectionPos, speed='fast'), timeout=None)

        sequence = config['pressureSequence']
        if isinstance(sequence, str):
            sequence = eval(sequence, units.__dict__)

        for pressure, delay in sequence:
            dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            self.checkStop(delay)

        dev.pipetteRecord()['expelled_nucleus'] = True
        return 'out'

    def resetPosition(self):
        pip = self.dev.pipetteDevice
        # self.waitFor([pip._moveToGlobal(self.approachPos, speed='fast')])
        self.waitFor(pip._moveToGlobal(self.startPos, speed='fast'), timeout=None)

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after collection")
        
        self.resetPosition()
            
        PatchPipetteState.cleanup(self)
