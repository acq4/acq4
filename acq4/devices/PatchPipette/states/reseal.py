from __future__ import annotations

import contextlib
import numpy as np

import pyqtgraph as pg
from acq4.util import ptime
from acq4.util.functions import plottable_booleans
from acq4.util.future import Future, future_wrap
from ._base import PatchPipetteState, SteadyStateAnalysisBase


class ResealAnalysis(SteadyStateAnalysisBase):
    """Class to analyze test pulses and determine reseal behavior."""

    @classmethod
    def plot_items(cls, *args, **kwargs):
        representative = cls(*args, **kwargs)
        return {
            '': [
                pg.InfiniteLine(movable=False, pos=representative._stretch_threshold, angle=0, pen=pg.mkPen('w')),
                pg.InfiniteLine(movable=False, pos=representative._tearing_threshold, angle=0, pen=pg.mkPen('w'))
            ]
        }

    @classmethod
    def plots_for_data(cls, data, *args, **kwargs):
        plots = {'Ω': [], '': []}
        names = False
        for d in data:
            analyzer = ResealAnalysis(*args, **kwargs)
            analysis = analyzer.process_measurements(d)
            plots['Ω'].append(dict(x=analysis["time"], y=analysis["detect_avg"], pen=pg.mkPen('b'), name=None if names else 'Detect Avg'))
            plots['Ω'].append(dict(x=analysis["time"], y=analysis["repair_avg"], pen=pg.mkPen(90, 140, 255), name=None if names else 'Repair Avg'))
            plots[''].append(dict(x=analysis["time"], y=analysis["detect_ratio"], pen=pg.mkPen('b'), name=None if names else 'Detect Ratio'))
            plots[''].append(dict(x=analysis["time"], y=analysis["repair_ratio"], pen=pg.mkPen(90, 140, 255), name=None if names else 'Repair Ratio'))
            plots[''].append(dict(x=analysis["time"], y=plottable_booleans(analysis["stretching"]), pen=pg.mkPen('y'), symbol='x', name=None if names else 'Stretching'))
            plots[''].append(dict(x=analysis["time"], y=plottable_booleans(analysis["tearing"]), pen=pg.mkPen('r'), symbol='o', name=None if names else 'Tearing'))
            plots[''].append(dict(x=analysis["time"], y=plottable_booleans(analysis["torn"]), pen=pg.mkPen('r'), symbol='x', name=None if names else 'Torn'))
            names = True
        return plots

    def __init__(self, stretch_threshold: float, tearing_threshold: float, torn_threshold: float, detection_tau: float, repair_tau: float):
        super().__init__()
        self._stretch_threshold = stretch_threshold
        self._tearing_threshold = tearing_threshold
        self._torn_threshold = torn_threshold
        self._detection_tau = detection_tau
        self._repair_tau = repair_tau

    def is_stretching(self) -> bool:
        """Return True if the resistance is increasing too quickly."""
        return self._last_measurement and self._last_measurement['stretching']

    def is_tearing(self) -> bool:
        """Return True if the resistance is decreasing."""
        return self._last_measurement and self._last_measurement['tearing']

    def is_torn(self) -> bool:
        """Return True if the resistance is consistently too low."""
        return self._last_measurement and self._last_measurement['torn']

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
                ('torn', bool),
            ])
        for i, measurement in enumerate(measurements):
            start_time, resistance = measurement
            if i == 0:
                if self._last_measurement is None:
                    ret_array[i] = (start_time, resistance, 1, 1, 0, 0, False, False, False)
                    self._last_measurement = ret_array[i]
                    continue
                else:
                    last_measurement = self._last_measurement
            else:
                last_measurement = ret_array[i - 1]

            dt = start_time - last_measurement['time']

            detect_avg, detection_ratio = self.exponential_decay_avg(
                dt, last_measurement['detect_avg'], resistance, self._detection_tau)
            repair_avg, repair_ratio = self.exponential_decay_avg(
                dt, last_measurement['repair_avg'], resistance, self._repair_tau)

            is_stretching = detection_ratio > self._stretch_threshold or repair_ratio > self._stretch_threshold
            is_tearing = detection_ratio < self._tearing_threshold or repair_ratio < self._tearing_threshold
            is_torn = repair_avg < self._torn_threshold
            ret_array[i] = (
                start_time,
                resistance,
                detect_avg,
                repair_avg,
                detection_ratio,
                repair_ratio,
                is_stretching,
                is_tearing,
                is_torn,
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
        Largest vacuum pressure (pascals, expected negative) to apply during nuzzling (default is -2 kPa)
    nuzzleDuration : float
        Duration (seconds) to spend nuzzling (default is 30s)
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
        Pressure (Pa) to apply during retraction (default is -7 kPa)
    pressureChangeRate : float
        Rate at which pressure should change from initial/nuzzleLimit to retraction (default is 0.5 kPa / min)
    maxRetractionSpeed : float
        Speed in m/s to move pipette during each stepwise movement of the retraction (default is 10 um / s)
    retractionStepInterval : float
        Interval (seconds) between stepwise movements of the retraction (default is 5s)
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
    tornDetectionThreshold : float
        Ratio of resistance divided by initial resistance below which the membrane is considered to be torn, using the
        repairTau (default is 0.5)
    retractionSuccessDistance : float
        Distance (meters) to retract before checking for successful reseal (default is 200 µm)
    resealSuccessResistanceMultiplier : float
        The reseal is considered successful when resistance exceeds initial resistance times this value (default is 4)
    resealSuccessDuration : float
        Duration (seconds) to wait after successful reseal before transitioning to the slurp (default is 5s)
    postSuccessRetractionSpeed : float
        Speed in m/s to move pipette after successful reseal (default is 6 µm / s)
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
        'initialVCHolding': -55e-3,
        'initialTestPulseEnable': True,
        'initialPressure': -0.5e3,
        'initialPressureSource': 'regulator',
    }
    _parameterTreeConfig = {
        'extractNucleus': {'type': 'bool', 'default': True},
        'fallbackState': {'type': 'str', 'default': 'whole cell'},
        'nuzzleDuration': {'type': 'float', 'default': 30, 'suffix': 's'},
        'nuzzleInitialPressure': {'type': 'float', 'default': 0, 'suffix': 'Pa'},
        'nuzzleLateralWiggleRadius': {'type': 'float', 'default': 5e-6, 'suffix': 'm'},
        'nuzzlePressureLimit': {'type': 'float', 'default': -2e3, 'suffix': 'Pa'},
        'nuzzleRepetitions': {'type': 'int', 'default': 2},
        'nuzzleSpeed': {'type': 'float', 'default': 5e-6, 'suffix': 'm/s'},
        'pressureChangeRate': {'type': 'float', 'default': 0.5e3 / 60, 'suffix': 'Pa/s'},
        'resealTimeout': {'type': 'float', 'default': 10 * 60, 'suffix': 's'},
        'retractionPressure': {'type': 'float', 'default': -7e3, 'suffix': 'Pa'},
        'maxRetractionSpeed': {'type': 'float', 'default': 10e-6, 'suffix': 'm/s'},
        'retractionStepInterval': {'type': 'float', 'default': 5, 'suffix': 's'},
        'retractionSuccessDistance': {'type': 'float', 'default': 200e-6, 'suffix': 'm'},
        'resealSuccessResistanceMultiplier': {'type': 'float', 'default': 4.0},
        'resealSuccessDuration': {'type': 'float', 'default': 5, 'suffix': 's'},
        'postSuccessRetractionSpeed': {'type': 'float', 'default': 6e-6, 'suffix': 'm/s'},
        'detectionTau': {'type': 'float', 'default': 1, 'suffix': 's'},
        'repairTau': {'type': 'float', 'default': 10, 'suffix': 's'},
        'stretchDetectionThreshold': {'type': 'float', 'default': 0.005},
        'tearDetectionThreshold': {'type': 'float', 'default': -0.00128},
        'tornDetectionThreshold': {'type': 'float', 'default': 0.5},
        'slurpPressure': {'type': 'float', 'default': -10e3, 'suffix': 'Pa'},
        'slurpRetractionSpeed': {'type': 'float', 'default': 10e-6, 'suffix': 'm/s'},
        'slurpDuration': {'type': 'float', 'default': 10, 'suffix': 's'},
        'slurpHeight': {'type': 'float', 'default': 50e-6, 'suffix': 'm'},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._pressureFuture = None
        self._moveFuture = None
        self._lastResistance = None
        self._firstSuccessTime = None
        self._startPosition = np.array(self.dev.pipetteDevice.globalPosition())
        self._analysis = None
        self._preAnalysisTpss = []

    def nuzzle(self):
        """Wiggle the pipette around inside the cell to clear space for a nucleus to be extracted."""
        self.setState("nuzzling")

        @contextlib.contextmanager
        def pressure_ramp():
            self.dev.pressureDevice.setPressure(source='regulator', pressure=self.config['nuzzleInitialPressure'])
            self._pressureFuture = self.dev.pressureDevice.rampPressure(
                target=self.config['nuzzlePressureLimit'], duration=self.config['nuzzleDuration'])
            yield
            self.waitFor(self._pressureFuture)

        self.waitFor(
            self.dev.pipetteDevice.wiggle(
                speed=self.config['nuzzleSpeed'],
                radius=self.config['nuzzleLateralWiggleRadius'],
                duration=self.config['nuzzleDuration'],
                repetitions=self.config['nuzzleRepetitions'],
                extra=pressure_ramp,
            ),
            timeout=None,
        )

    @future_wrap
    def startRollingResistanceThresholds(self, _future: Future):
        """Start a rolling average of the resistance to detect stretching and tearing. Load the first 20s of data."""
        self.monitorTestPulse()
        start = ptime.time()
        while ptime.time() - start < self.config['repairTau']:
            _future.checkStop()
            self.processAtLeastOneTestPulse()

    def isStretching(self) -> bool:
        """Return True if the resistance is increasing too quickly."""
        return self._analysis and self._analysis.is_stretching()

    def isTearing(self) -> bool:
        """Return True if the resistance is decreasing."""
        return self._analysis and self._analysis.is_tearing()

    def isTorn(self) -> bool:
        """Return True if the resistance is way too low."""
        return self._analysis and self._analysis.is_torn()

    def successResistanceThreshold(self):
        """Return the resistance threshold for a successful reseal."""
        if self._lastResistance is None:
            return np.inf
        return self.config["resealSuccessResistanceMultiplier"] * self.preAnalysisResistance()

    def preAnalysisResistance(self):
        if len(self._preAnalysisTpss) < 10:
            return np.inf
        return np.mean([tp.analysis['steady_state_resistance'] for tp in self._preAnalysisTpss])

    def isRetractionSuccessful(self):
        if self.retractionDistance() > self.config['retractionSuccessDistance'] or (
                self._lastResistance is not None and self._lastResistance > self.successResistanceThreshold()
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
        tps = super().processAtLeastOneTestPulse()
        if self._analysis is None:
            self._preAnalysisTpss += tps
            if len(self._preAnalysisTpss) >= 10:
                self._analysis = ResealAnalysis(
                    stretch_threshold=self.config['stretchDetectionThreshold'],
                    tearing_threshold=self.config['tearDetectionThreshold'],
                    torn_threshold=self.preAnalysisResistance() * self.config['tornDetectionThreshold'],
                    detection_tau=self.config['detectionTau'],
                    repair_tau=self.config['repairTau'],
                )
        else:
            self._lastResistance = self._analysis.process_test_pulses(tps)['resistance'][-1]
        return tps

    def run(self):
        config = self.config
        dev = self.dev
        baseline_future = self.startRollingResistanceThresholds()
        if config['extractNucleus'] is True:
            self.nuzzle()
        self.checkStop()
        self.setState("measuring baseline resistance")
        self.waitFor(baseline_future, timeout=self.config['repairTau'])
        dev.pressureDevice.setPressure(source='regulator', pressure=config['retractionPressure'])

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
                    self._moveFuture = recovery_future = dev.pipetteDevice.stepwiseAdvance(
                        self._startPosition[2],
                        maxSpeed=self.config['maxRetractionSpeed'],
                        interval=config['retractionStepInterval'],
                    )
            elif self.isTorn():
                if retraction_future and not retraction_future.isDone():
                    retraction_future.stop()
                self.setState("tissue is torn beyond repair")
                self._taskDone(interrupted=True, error="Tissue is torn beyond repair.")
                return config['fallbackState']
            elif retraction_future is None or retraction_future.wasInterrupted():
                if recovery_future is not None and not recovery_future.isDone():
                    recovery_future.stop()
                self.setState("retracting")
                self._moveFuture = retraction_future = dev.pipetteDevice.stepwiseAdvance(
                    dev.pipetteDevice.approachDepth(),
                    maxSpeed=config['maxRetractionSpeed'],
                    interval=config['retractionStepInterval'],
                )

            self.sleep(0.2)

        self.setState("reseal deemed successful")
        self.cleanup()
        self._moveFuture = self._retractFromTissue()
        self.waitFor(self._moveFuture)

        self.setState("slurping in nucleus")
        dev.pressureDevice.setPressure(source='regulator', pressure=config['slurpPressure'])
        self._moveFuture = dev.pipetteDevice.goAboveTarget(config['slurpRetractionSpeed'])
        self.sleep(config['slurpDuration'])
        self.waitFor(self._moveFuture, timeout=90)
        dev.pipetteDevice.focusTip()
        dev.pressureDevice.setPressure(source='regulator', pressure=config['initialPressure'])
        self.sleep(np.inf)

    def _retractFromTissue(self):
        # move out of the tissue more quickly
        pip = self.dev.pipetteDevice
        surface = pip.scopeDevice().surfaceDepth()
        return pip.advance(surface, speed=self.config['postSuccessRetractionSpeed'])

    def retractionDistance(self):
        return np.linalg.norm(np.array(self.dev.pipetteDevice.globalPosition()) - self._startPosition)

    def cleanup(self):
        if self._moveFuture is not None:
            self._moveFuture.stop()
        if self._pressureFuture is not None:
            self._pressureFuture.stop()
        return super().cleanup()
