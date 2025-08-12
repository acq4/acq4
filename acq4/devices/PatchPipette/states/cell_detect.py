from __future__ import annotations

from threading import Lock
from typing import Any, Iterable

import numpy as np
import pyqtgraph as pg

from acq4.util import ptime
from acq4.util.functions import plottable_booleans
from acq4.util.future import future_wrap
from ._base import PatchPipetteState, SteadyStateAnalysisBase


class CellDetectAnalysis(SteadyStateAnalysisBase):
    """Class to analyze test pulses and determine cell detection behavior."""

    @classmethod
    def plots_for_data(cls, data: Iterable[np.ndarray], *args, **kwargs) -> dict[str, Iterable[dict[str, Any]]]:
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
        Distance (m) per step when advanceContinuous=False (default 1 µm)
    visualTargetTracking : bool
        If True, the pipette will visually track the cell position while advancing (default False)
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
    searchAroundAtTarget : bool
        If True, search around the target position for a cell (default True)
    searchAroundAtTargetRadius : float
        Radius (m) to search around the target position (default 1.5 µm)
    baselineResistanceTau : float
        Time constant (s) for rolling average of pipette resistance (default 20 s) from which to calculate cell
        detection
    fastDetectionThreshold : float
        Threshold for fast change in pipette resistance (Ohm) to trigger cell detection (default 1 MOhm)
    slowDetectionThreshold : float
        Threshold for slow change in pipette resistance (Ohm) to trigger cell detection (default 200 kOhm)
    slowDetectionSteps : int
        Number of test pulses to integrate for slow change detection (default 3)
    breakThreshold : float
        Threshold for change in resistance (Ohm) to detect broken pipette (default -1 MOhm),
    cellDetectTimeout : float
        Maximum time (s) to wait for cell detection before switching to fallback state (default 30 s)
    pokeDistance : float
        Distance to push pipette towards target after detecting cell surface
    reachedEndpointState : str
        State to transition to after the search endpoint has been reached, but no cell was detected.
        Default is 'seal'.
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
        'visualTargetTracking': {'default': False, 'type': 'bool'},
        'preTargetWiggle': {'default': False, 'type': 'bool'},
        'preTargetWiggleRadius': {'default': 8e-6, 'type': 'float', 'suffix': 'm'},
        'preTargetWiggleStep': {'default': 5e-6, 'type': 'float', 'suffix': 'm'},
        'preTargetWiggleDuration': {'default': 6, 'type': 'float', 'suffix': 's'},
        'preTargetWiggleSpeed': {'default': 5e-6, 'type': 'float', 'suffix': 'm/s'},
        'searchAroundAtTarget': {'default': True, 'type': 'bool'},
        'searchAroundAtTargetRadius': {'default': 1.5e-6, 'type': 'float', 'suffix': 'm'},
        'baselineResistanceTau': {'default': 20, 'type': 'float', 'suffix': 's'},
        'fastDetectionThreshold': {'default': 1e6, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionThreshold': {'default': 0.2e6, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionSteps': {'default': 3, 'type': 'int'},
        'breakThreshold': {'default': -1e6, 'type': 'float', 'suffix': 'Ω'},
        'cellDetectTimeout': {'default': 30, 'type': 'float', 'suffix': 's'},
        'minDetectionDistance': {'default': 15e-6, 'type': 'float', 'suffix': 'm'},
        'pokeDistance': {'default': 3e-6, 'type': 'float', 'suffix': 'm'},
        'reachedEndpointState': {'default': 'seal', 'type': 'str'},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._moveFuture = None
        self._analysis = CellDetectAnalysis(
            self.config['baselineResistanceTau'],
            self.config['fastDetectionThreshold'],
            self.config['slowDetectionThreshold'],
            self.config['slowDetectionSteps'],
            np.inf,  # obstacles are just cells to patch in a cell detect state
            self.config['breakThreshold'],
        )
        self._reachedEndpoint = False
        self._startTime = None
        self.direction_unit = self._calc_direction()
        self._hasWiggled = False
        self._wiggleLock = Lock()
        self._initialPos = self.dev.pipetteDevice.globalPosition()

    def run(self):
        config = self.config
        self.monitorTestPulse()

        while not self.weTookTooLong():
            if detectedThresholdSpeed := self.targetCellFound():
                if self._moveFuture is not None:
                    self._moveFuture.stop("cell detected", wait=True)
                    self._moveFuture = None
                self.pokeCell()
                return self._transition_to_seal(detectedThresholdSpeed)
            self.checkStop()
            self.processAtLeastOneTestPulse()
            self.adjustPressureForDepth()
            self.maybeVisuallyTrackTarget()
            if self._analysis.tip_is_broken():
                self._taskDone(interrupted=True, error="Pipette broken")
                self.dev.patchRecord()['detectedCell'] = False
                return 'broken'
            if config['autoAdvance']:
                if self._moveFuture is None:
                    self._moveFuture = self._move()
                if self._moveFuture.isDone() and self._reachedEndpoint:
                    return self._transition_to_fallback("No cell found before end of search path")

        return self._transition_to_fallback("Timed out waiting for cell detect.")

    def pokeCell(self):
        """Move pipette slightly deeper towards center of cell"""
        poke = self.config['pokeDistance']
        if poke == 0:
            return
        pip = self.dev.pipetteDevice
        target = pip.targetPosition()
        pos = pip.globalPosition()
        dif = target - pos
        dist = np.linalg.norm(dif)
        if dist > poke:
            goto = pos + dif * (poke / dist)
            self.waitFor(pip._moveToGlobal(goto, self.config['detectionSpeed']))

    def processAtLeastOneTestPulse(self):
        tps = super().processAtLeastOneTestPulse()
        self._analysis.process_test_pulses(tps)
        return tps

    def weTookTooLong(self):
        if self._startTime is None:
            self._startTime = ptime.time()
        return (
            self.config['cellDetectTimeout'] is not None and
            ptime.time() - self._startTime > self.config['cellDetectTimeout']
        )

    def targetCellFound(self) -> str | bool:
        if self.closeEnoughToTargetToDetectCell() and not self._wiggleLock.locked():
            if self._analysis.cell_detected_fast():
                return 'fast'
            if self._analysis.cell_detected_slow():
                return 'slow'
        return False

    def _transition_to_fallback(self, msg):
        self._taskDone(interrupted=True, error=msg)
        self.dev.patchRecord()['detectedCell'] = False
        return self.config['fallbackState']

    def _transition_to_seal(self, speed):
        self.setState(f"cell detected ({speed} criteria)")
        self._taskDone()
        self.dev.patchRecord()['detectedCell'] = True
        return self.config['reachedEndpointState']

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
            raise ValueError(
                f"advanceMode must be 'vertical', 'axial', or 'target'  (got {self.config['advanceMode']!r})")
        return direction / np.linalg.norm(direction)

    def fastTravelEndpoint(self):
        """Return the last position along the pipette search path to be traveled at full speed."""
        pip = self.dev.pipetteDevice
        target = np.array(pip.targetPosition())
        return target - (self.direction_unit * self.config['minDetectionDistance'])

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
            endpoint = self._initialPos + pip.globalDirection() * config['maxAdvanceDistance']

        # max surface depth
        if config['maxAdvanceDepthBelowSurface'] is not None and pip.globalDirection()[2] < 0:
            endDepth = surface - config['maxAdvanceDepthBelowSurface']
            depthEndpt = pip.positionAtDepth(endDepth)
            # is the surface depth endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint - pos) > np.linalg.norm(depthEndpt - pos):
                endpoint = depthEndpt

        # max distance past target
        if config['advanceMode'] == 'target' and config['maxAdvanceDistancePastTarget'] is not None:
            targetEndpt = target + pip.globalDirection() * config['maxAdvanceDistancePastTarget']
            # is the target endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint - pos) > np.linalg.norm(targetEndpt - pos):
                endpoint = targetEndpt

        if endpoint is None:
            raise ValueError(
                "Cell detect state requires one of maxAdvanceDistance, maxAdvanceDepthBelowSurface, or"
                " maxAdvanceDistancePastTarget."
            )

        return endpoint

    @future_wrap
    def _move(self, _future):
        """Move pipette along search path."""
        self.setState("pipette advance")
        config = self.config
        if self.aboveSurface():
            self._waitForMoveWhileTargetChanges(
                self.surfaceIntersectionPosition, config['aboveSurfaceSpeed'], True, _future)
            self.setState("moved to surface")
        if not self.closeEnoughToTargetToDetectCell():
            self._waitForMoveWhileTargetChanges(self.fastTravelEndpoint, config['belowSurfaceSpeed'], True, _future)
            self.setState("moved to detection area")
        if config['preTargetWiggle']:
            self._wiggle(_future, self.finalSearchEndpoint())
        self._waitForMoveWhileTargetChanges(
            self.finalSearchEndpoint,
            config['detectionSpeed'],
            config["continuousAdvance"],
            _future,
            interval=config['advanceStepInterval'],
            step=config['advanceStepDistance'],
        )
        if config['searchAroundAtTarget']:
            self._searchAround(_future)

        self._reachedEndpoint = True

    def _wiggle(self, future, endpoint):
        if self._hasWiggled:
            return
        config = self.config
        dev = self.dev
        speed = config['detectionSpeed']
        distance = np.linalg.norm(endpoint - np.array(dev.pipetteDevice.globalPosition()))
        count = int(distance / config['preTargetWiggleStep'])
        wiggle_step = self.direction_unit * config['preTargetWiggleStep']
        for _ in range(count):
            self.setState("pre-target wiggle")
            retract_pos = dev.pipetteDevice.globalPosition() - wiggle_step
            future.waitFor(dev.pipetteDevice._moveToGlobal(retract_pos, speed=speed), timeout=None)
            with self._wiggleLock:  # used to prevent cell detect
                self.waitFor(
                    dev.pipetteDevice.wiggle(
                        speed=config['preTargetWiggleSpeed'],
                        radius=config['preTargetWiggleRadius'],
                        repetitions=1,
                        duration=config['preTargetWiggleDuration'],
                        pipette_direction=self.direction_unit,
                    ),
                    timeout=None,
                )
            step_pos = dev.pipetteDevice.globalPosition() + wiggle_step
            future.waitFor(dev.pipetteDevice._moveToGlobal(step_pos, speed=speed), timeout=None)
        self._hasWiggled = True

    def _searchAround(self, future):
        """Slowly describe a circle on a vertical plane perpendicular to the yaw of the pipette."""
        radius = self.config['searchAroundAtTargetRadius']
        speed = self.config['detectionSpeed']
        vertical = np.array((0, 0, 1))
        direction = self.dev.pipetteDevice.globalDirection()
        cross = np.cross(direction, vertical)
        # down first, then back up all the way
        start = -np.pi / 2
        radian_steps = np.arange(start, start + 2 * np.pi, np.pi / 8)
        steps = (
            np.cos(radian_steps)[:, np.newaxis] * cross[np.newaxis, :] +
            np.sin(radian_steps)[:, np.newaxis] * vertical[np.newaxis, :]
        ) * radius
        for rel_pos in steps:
            pos = rel_pos + self.dev.pipetteDevice.targetPosition()
            future.waitFor(self.dev.pipetteDevice._moveToGlobal(pos, speed))
            future.sleep(1)

    def _cleanup(self):
        if self._moveFuture is not None and not self._moveFuture.isDone():
            self._moveFuture.stop()
        patchrec = self.dev.patchRecord()
        patchrec['cellDetectFinalTarget'] = tuple(self.dev.pipetteDevice.targetPosition())
        return super()._cleanup()
