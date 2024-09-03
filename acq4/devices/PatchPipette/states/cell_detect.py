from __future__ import annotations

from threading import Lock

from typing import Any

import contextlib
import numpy as np

import pyqtgraph as pg
from acq4 import getManager
from acq4.util import ptime
from acq4.util.functions import plottable_booleans
from acq4.util.future import future_wrap
from ._base import PatchPipetteState, SteadyStateAnalysisBase


class CellDetectAnalysis(SteadyStateAnalysisBase):
    """Class to analyze test pulses and determine cell detection behavior."""
    @classmethod
    def plots_for_data(cls, data: iter[np.void], *args, **kwargs) -> dict[str, iter[dict[str, Any]]]:
        plots = {'Ω': [], '': []}
        names = False
        for d in data:
            analyzer = cls(*args, **kwargs)
            analysis = analyzer.process_measurements(d)
            plots['Ω'].append(dict(
                x=analysis["time"],
                y=analysis["baseline_avg"],
                pen=pg.mkPen('#88F'),
                name=None if names else 'Baseline Detect Avg',
            ))
            plots['Ω'].append(dict(
                x=analysis["time"],
                y=analysis["slow_avg"],
                pen=pg.mkPen('b'),
                name=None if names else 'Slow Detection Avg',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=plottable_booleans(analysis["obstacle_detected"]),
                pen=pg.mkPen('r'),
                symbol='x',
                name=None if names else 'Obstacle Detected',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=plottable_booleans(analysis["cell_detected_fast"] | analysis["cell_detected_slow"]),
                pen=pg.mkPen('g'),
                symbol='o',
                name=None if names else 'Cell Detected',
            ))
            names = True
        return plots

    def __init__(
            self,
            baseline_tau: float,
            cell_threshold_fast: float,
            cell_threshold_slow: float,
            slow_detection_steps: int,
            obstacle_threshold: float,
            break_threshold: float,
    ):
        super().__init__()
        self._baseline_tau = baseline_tau
        self._cell_threshold_fast = cell_threshold_fast
        self._cell_threshold_slow = cell_threshold_slow
        self._slow_detection_steps = slow_detection_steps
        self._obstacle_threshold = obstacle_threshold
        self._break_threshold = break_threshold
        self._measurment_count = 0

    def process_measurements(self, measurements: np.ndarray) -> np.ndarray:
        ret_array = np.zeros(
            len(measurements),
            dtype=[
                ('time', float),
                ('resistance', float),
                ('baseline_avg', float),
                ('slow_avg', float),
                ('cell_detected_fast', bool),
                ('cell_detected_slow', bool),
                ('obstacle_detected', bool),
                ('tip_is_broken', bool),
            ])
        for i, measurement in enumerate(measurements):
            start_time, resistance = measurement
            self._measurment_count += 1
            if i == 0:
                if self._last_measurement is None:
                    ret_array[i] = (start_time, resistance, resistance, resistance, False, False, False, False)
                    self._last_measurement = ret_array[i]
                    continue
                last_measurement = self._last_measurement
            else:
                last_measurement = ret_array[i - 1]

            dt = start_time - last_measurement['time']
            baseline_avg, _ = self.exponential_decay_avg(
                dt, last_measurement['baseline_avg'], resistance, self._baseline_tau)
            cell_detected_fast = resistance > self._cell_threshold_fast + baseline_avg
            slow_avg, _ = self.exponential_decay_avg(
                dt, last_measurement['slow_avg'], resistance, dt * self._slow_detection_steps)
            cell_detected_slow = (
                    self._measurment_count >= self._slow_detection_steps and
                    slow_avg > self._cell_threshold_slow + baseline_avg
            )
            obstacle_detected = resistance > self._obstacle_threshold + baseline_avg
            tip_is_broken = resistance < baseline_avg + self._break_threshold

            ret_array[i] = (
                start_time,
                resistance,
                baseline_avg,
                slow_avg,
                cell_detected_fast,
                cell_detected_slow,
                obstacle_detected,
                tip_is_broken,
            )
        self._last_measurement = ret_array[-1]
        return ret_array

    def cell_detected_fast(self):
        return self._last_measurement and self._last_measurement['cell_detected_fast']

    def cell_detected_slow(self):
        return self._last_measurement and self._last_measurement['cell_detected_slow']

    def obstacle_detected(self):
        return self._last_measurement and self._last_measurement['obstacle_detected']

    def tip_is_broken(self):
        return self._last_measurement and self._last_measurement['tip_is_broken']


class CellDetectState(PatchPipetteState):
    """Handles cell detection:

    - monitor resistance for cell proximity and switch to seal mode
    - monitor resistance for pipette break

    TODO:
    - Cell tracking

    Parameters
    ----------
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
    obstacleDetection : bool
        If True, sidestep obstacles (default False)
    obstacleRecoveryTime : float
        Time (s) allowed after retreating from an obstacle to let resistance to return to normal (default 1 s)
    obstacleResistanceThreshold : float
        Resistance (Ohm) threshold above the initial resistance measurement for detecting an obstacle (default 1 MOhm)
    sidestepLateralDistance : float
        Distance (m) to sidestep an obstacle (default 10 µm)
    sidestepBackupDistance : float
        Distance (m) to backup before sidestepping (default 10 µm)
    sidestepPassDistance : float
        Distance (m) to pass an obstacle (default 20 µm)
    minDetectionDistance : float
        Minimum distance (m) from target before cell detection can be considered (default 15 µm)
    maxAdvanceDistance : float | None
        Maximum distance (m) to advance past starting point (default None)
    maxAdvanceDistancePastTarget : float | None
        Maximum distance (m) to advance past target (default 10 um)
    maxAdvanceDepthBelowSurface : float | None
        Maximum depth (m) to advance below the sample surface (default None)
    aboveSurfaceSpeed : float
        Speed (m/s) to advance the pipette when above the surface (default 20 um/s)
    belowSurfaceSpeed : float
        Speed (m/s) to advance the pipette when below the surface (default 5 um/s)
    detectionSpeed : float
        Speed (m/s) to advance the pipette if advanceContinuous=True and when close to the target/area-of-search
        (default 2 um/s)
    preTargetWiggle : bool
        If True, wiggle the pipette before reaching the target (default False)
    preTargetWiggleRadius : float
        Radius (m) of the wiggle (default 8 µm)
    preTargetWiggleStep : float
        Distance (m) to move between each wiggle (default 5 µm)
    preTargetWiggleDuration : float
        Time (s) to spend wiggling at each step (default 6 s)
    preTargetWiggleSpeed : float
        Speed (m/s) to move during the wiggle (default 5 µm/s)
    baselineResistanceTau : float
        Time constant (s) for rolling average of pipette resistance (default 20 s) from which to calculate cell detection
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
    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'bath',
    }
    _parameterTreeConfig = {
        'autoAdvance': {'default': True, 'type': 'bool'},
        'advanceMode': {'default': 'target', 'type': 'str', 'limits': ['target', 'axial', 'vertical']},
        'advanceContinuous': {'default': True, 'type': 'bool'},
        'advanceStepInterval': {'default': 0.1, 'type': 'float', 'suffix': 's'},
        'advanceStepDistance': {'default': 1e-6, 'type': 'float', 'suffix': 'm'},
        'maxAdvanceDistance': {'default': None, 'type': 'float', 'optional': True, 'suffix': 'm'},
        'maxAdvanceDistancePastTarget': {'default': 10e-6, 'type': 'float', 'suffix': 'm'},
        'maxAdvanceDepthBelowSurface': {'default': None, 'type': 'float', 'optional': True, 'suffix': 'm'},
        'aboveSurfaceSpeed': {'default': 20e-6, 'type': 'float', 'suffix': 'm/s'},
        'belowSurfaceSpeed': {'default': 5e-6, 'type': 'float', 'suffix': 'm/s'},
        'detectionSpeed': {'default': 2e-6, 'type': 'float', 'suffix': 'm/s'},
        'preTargetWiggle': {'default': False, 'type': 'bool'},
        'preTargetWiggleRadius': {'default': 8e-6, 'type': 'float', 'suffix': 'm'},
        'preTargetWiggleStep': {'default': 5e-6, 'type': 'float', 'suffix': 'm'},
        'preTargetWiggleDuration': {'default': 6, 'type': 'float', 'suffix': 's'},
        'preTargetWiggleSpeed': {'default': 5e-6, 'type': 'float', 'suffix': 'm/s'},
        'baselineResistanceTau': {'default': 20, 'type': 'float', 'suffix': 's'},
        'fastDetectionThreshold': {'default': 1e6, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionThreshold': {'default': 0.2e6, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionSteps': {'default': 3, 'type': 'int'},
        'breakThreshold': {'default': -1e6, 'type': 'float', 'suffix': 'Ω'},
        'reserveDAQ': {'default': False, 'type': 'bool'},
        'cellDetectTimeout': {'default': 30, 'type': 'float', 'suffix': 's'},
        'DAQReservationTimeout': {'default': 30, 'type': 'float', 'suffix': 's'},
        'obstacleDetection': {'default': False, 'type': 'bool'},
        'obstacleRecoveryTime': {'default': 1, 'type': 'float', 'suffix': 's'},
        'obstacleResistanceThreshold': {'default': 1e6, 'type': 'float', 'suffix': 'Ω'},
        'sidestepLateralDistance': {'default': 10e-6, 'type': 'float', 'suffix': 'm'},
        'sidestepBackupDistance': {'default': 10e-6, 'type': 'float', 'suffix': 'm'},
        'sidestepPassDistance': {'default': 20e-6, 'type': 'float', 'suffix': 'm'},
        'minDetectionDistance': {'default': 15e-6, 'type': 'float', 'suffix': 'm'},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._continuousAdvanceFuture = None
        self.lastMove = 0.0
        self.stepCount = 0
        self.advanceSteps = None
        self._analysis = CellDetectAnalysis(
            self.config['baselineResistanceTau'],
            self.config['fastDetectionThreshold'],
            self.config['slowDetectionThreshold'],
            self.config['slowDetectionSteps'],
            self.config['obstacleResistanceThreshold'],
            self.config['breakThreshold'],
        )
        self._lastTestPulse = None
        self._startTime = None
        self.direction = self._calc_direction()
        self._wiggleLock = Lock()

    def run(self):
        with contextlib.ExitStack() as stack:
            if self.config["reserveDAQ"]:
                daq_name = self.dev.clampDevice.getDAQName("primary")
                self.setState(f"cell detect: waiting for {daq_name} lock")
                stack.enter_context(
                    getManager().reserveDevices([daq_name], timeout=self.config["DAQReservationTimeout"]))
                self.setState(f"cell detect: {daq_name} lock acquired")

            return self._run()

    def _run(self):
        config = self.config
        self.monitorTestPulse()

        while not self.weTookTooLong():
            if speed := self.targetCellFound():
                return self._transition_to_seal(speed)
            self.checkStop()
            self.processAtLeastOneTestPulse()
            if self._analysis.tip_is_broken():
                self._taskDone(interrupted=True, error="Pipette broken")
                self.dev.patchRecord()['detectedCell'] = False
                return 'broken'
            if self.obstacleDetected():
                try:
                    self.avoidObstacle()
                except TimeoutError:
                    self._taskDone(interrupted=True, error="Fouled by obstacle")
                    return 'fouled'
            if config['autoAdvance']:
                if config['advanceContinuous']:
                    # Start continuous move if needed
                    if self._continuousAdvanceFuture is None:
                        self._continuousAdvanceFuture = self.continuousMove()
                    if self._continuousAdvanceFuture.isDone():
                        self._continuousAdvanceFuture.wait()  # check for move errors
                        return self._transition_to_fallback()
                else:
                    # advance to next position if stepping
                    if self.advanceSteps is None:
                        self.setState("cell detection: stepping pipette")
                        self.advanceSteps = self.getAdvanceSteps()
                    if self.stepCount >= len(self.advanceSteps):
                        return self._transition_to_fallback()
                    # make sure we obey advanceStepInterval
                    now = ptime.time()
                    if now - self.lastMove < config['advanceStepInterval']:
                        continue
                    self.lastMove = now

                    self.singleStep()
        self._taskDone(interrupted=True, error="Timed out waiting for cell detect.")
        return config['fallbackState']

    def avoidObstacle(self, already_retracted=False):
        self.setState("avoiding obstacle" + (" (recursively)" if already_retracted else ""))
        if self._continuousAdvanceFuture is not None:
            self._continuousAdvanceFuture.stop("Obstacle detected")
            self._continuousAdvanceFuture = None

        pip = self.dev.pipetteDevice
        speed = self.config['belowSurfaceSpeed']

        init_pos = np.array(pip.globalPosition())
        direction = self.direction
        if already_retracted:
            retract_pos = init_pos
        else:
            retract_pos = init_pos - self.config['sidestepBackupDistance'] * direction
            self.waitFor(pip._moveToGlobal(retract_pos, speed=speed))

        start_time = ptime.time()
        while self._analysis.obstacle_detected():
            self.processAtLeastOneTestPulse()
            if ptime.time() - start_time > self.config['obstacleRecoveryTime']:
                raise TimeoutError("Pipette fouled by obstacle")

        # pick a sidestep point orthogonal to the pipette direction on the xy plane
        xy_perpendicular = np.array([-direction[1], direction[0], 0])
        sidestep = self.config['sidestepLateralDistance'] * xy_perpendicular / np.linalg.norm(xy_perpendicular)
        sidestep_pos = retract_pos + sidestep
        self.waitFor(pip._moveToGlobal(sidestep_pos, speed=speed))

        go_past_pos = sidestep_pos + self.config['sidestepPassDistance'] * direction
        move = pip._moveToGlobal(go_past_pos, speed=speed)
        while not move.isDone():
            self.processAtLeastOneTestPulse()
            if self._analysis.obstacle_detected():
                move.stop("Obstacle detected while sidestepping")
                self.waitFor(pip._moveToGlobal(retract_pos, speed=speed))
                return self.avoidObstacle(already_retracted=True)
            self.checkStop()
        self.waitFor(move)
        pos = np.array(pip.globalPosition())
        self.waitFor(pip._moveToGlobal(pos - sidestep, speed=speed))

    def obstacleDetected(self):
        return self.config['obstacleDetection'] and not self.closeEnoughToTargetToDetectCell() and self._analysis.obstacle_detected()

    def processAtLeastOneTestPulse(self):
        tps = super().processAtLeastOneTestPulse()
        self._analysis.process_test_pulses(tps)
        self._lastTestPulse = tps[-1]
        return tps

    def weTookTooLong(self):
        if self._startTime is None:
            self._startTime = ptime.time()
        return self.config['cellDetectTimeout'] is not None and ptime.time() - self._startTime > self.config['cellDetectTimeout']

    def targetCellFound(self) -> str | bool:
        if self.closeEnoughToTargetToDetectCell() and not self._wiggleLock.locked():
            if self._analysis.cell_detected_fast():
                return 'fast'
            if self._analysis.cell_detected_slow():
                return 'slow'
        return False

    def aboveSurface(self, pos=None):
        if pos is None:
            pos = self.dev.pipetteDevice.globalPosition()
        surface = self.dev.pipetteDevice.scopeDevice().getSurfaceDepth()
        return pos[2] > surface

    def closeEnoughToTargetToDetectCell(self, pos=None):
        pip = self.dev.pipetteDevice
        target = np.array(pip.targetPosition())
        if pos is None:
            pos = np.array(pip.globalPosition())
        return np.linalg.norm(target - pos) < self.config['minDetectionDistance']

    def _transition_to_fallback(self):
        self._taskDone(interrupted=True, error="No cell found before end of search path")
        self.dev.patchRecord()['detectedCell'] = False
        return self.config['fallbackState']

    def _transition_to_seal(self, speed):
        self.setState(f"cell detected ({speed} criteria)")
        self._taskDone()
        self.dev.patchRecord()['detectedCell'] = True
        return "seal"

    def _calc_direction(self):
        # what direction are we moving?
        pip = self.dev.pipetteDevice
        if self.config['advanceMode'] == 'vertical':
            direction = np.array([0.0, 0.0, -1.0])
        elif self.config['advanceMode'] == 'axial':
            direction = pip.globalDirection()
        elif self.config['advanceMode'] == 'target':
            direction = np.array(pip.targetPosition()) - np.array(pip.globalPosition())
        else:
            raise ValueError(f"advanceMode must be 'vertical', 'axial', or 'target'  (got {self.config['advanceMode']!r})")
        return direction / np.linalg.norm(direction)

    def fastTravelEndpoint(self):
        """Return the last position along the pipette search path to be traveled at full speed."""
        pip = self.dev.pipetteDevice
        target = np.array(pip.targetPosition())
        return target - (self.direction * self.config['minDetectionDistance'])

    def finalSearchEndpoint(self):
        """Return the final position along the pipette search path, taking into account
        maxAdvanceDistance, maxAdvanceDepthBelowSurface, and maxAdvanceDistancePastTarget.
        """
        config = self.config
        dev = self.dev
        pip = dev.pipetteDevice
        pos = np.array(pip.globalPosition())
        surface = pip.scopeDevice().getSurfaceDepth()
        target = np.array(pip.targetPosition())

        endpoint = None

        # max search distance
        if config['maxAdvanceDistance'] is not None:
            endpoint = pos + self.direction * config['maxAdvanceDistance']

        # max surface depth
        if config['maxAdvanceDepthBelowSurface'] is not None and self.direction[2] < 0:
            endDepth = surface - config['maxAdvanceDepthBelowSurface']
            dz = endDepth - pos[2]
            depthEndpt = pos + self.direction * (dz / self.direction[2])
            # is the surface depth endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint-pos) > np.linalg.norm(depthEndpt-pos):
                endpoint = depthEndpt

        # max distance past target
        if config['advanceMode'] == 'target' and config['maxAdvanceDistancePastTarget'] is not None:
            targetEndpt = target + self.direction * config['maxAdvanceDistancePastTarget']
            # is the target endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint-pos) > np.linalg.norm(targetEndpt-pos):
                endpoint = targetEndpt

        if endpoint is None:
            raise ValueError(
                "Cell detect state requires one of maxAdvanceDistance, maxAdvanceDepthBelowSurface, or"
                " maxAdvanceDistancePastTarget."
            )

        return endpoint

    @future_wrap
    def continuousMove(self, _future):
        """Begin moving pipette continuously along search path.
        """
        self.setState("continuous pipette advance")
        if self.aboveSurface():
            speed = self.config['aboveSurfaceSpeed']
            surface = self.surfaceIntersectionPosition(self.direction)
            _future.waitFor(self.dev.pipetteDevice._moveToGlobal(surface, speed=speed), timeout=None)
            self.setState("moved to surface")
        if not self.closeEnoughToTargetToDetectCell():
            speed = self.config['belowSurfaceSpeed']
            midway = self.fastTravelEndpoint()
            _future.waitFor(self.dev.pipetteDevice._moveToGlobal(midway, speed=speed), timeout=None)
            self.setState("moved to detection area")
        speed = self.config['detectionSpeed']
        endpoint = self.finalSearchEndpoint()
        if self.config['preTargetWiggle']:
            distance = np.linalg.norm(endpoint - np.array(self.dev.pipetteDevice.globalPosition()))
            count = int(distance / self.config['preTargetWiggleStep'])
            for _ in range(count):
                self.setState("pre-target wiggle")
                retract_pos = self.dev.pipetteDevice.globalPosition() - self.direction * self.config['preTargetWiggleStep']
                _future.waitFor(self.dev.pipetteDevice._moveToGlobal(retract_pos, speed=speed), timeout=None)
                with self._wiggleLock:
                    self.waitFor(
                        self.dev.pipetteDevice.wiggle(
                            speed=self.config['preTargetWiggleSpeed'],
                            radius=self.config['preTargetWiggleRadius'],
                            repetitions=1,
                            duration=self.config['preTargetWiggleDuration'],
                            pipette_direction=self.direction,
                        ),
                        timeout=None,
                    )
                step_pos = self.dev.pipetteDevice.globalPosition() + self.direction * self.config['preTargetWiggleStep']
                _future.waitFor(self.dev.pipetteDevice._moveToGlobal(step_pos, speed=speed), timeout=None)
        _future.waitFor(self.dev.pipetteDevice._moveToGlobal(endpoint, speed=speed), timeout=None)

    def getAdvanceSteps(self):
        """Return the list of step positions to take along the search path.
        """
        config = self.config
        endpoint = self.finalSearchEndpoint()
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
        if self.aboveSurface(stepPos):
            speed = config['aboveSurfaceSpeed']
        elif self.closeEnoughToTargetToDetectCell(stepPos):
            speed = config['detectionSpeed']
        else:
            speed = config['belowSurfaceSpeed']
        self.waitFor(dev.pipetteDevice._moveToGlobal(stepPos, speed=speed))

    def cleanup(self):
        if self._continuousAdvanceFuture is not None:
            self._continuousAdvanceFuture.stop()
        patchrec = self.dev.patchRecord()
        patchrec['cellDetectFinalTarget'] = tuple(self.dev.pipetteDevice.targetPosition())
        super().cleanup()
