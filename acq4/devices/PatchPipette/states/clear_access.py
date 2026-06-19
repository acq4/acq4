"""Clear access patch state: recover a whole cell recording whose access resistance has climbed.

Applies a sequence of escalating negative pressure pulses (and optionally voltage zaps) to
re-open access to the cell, while watching input resistance (Ri). If Ri starts dropping the
pulsing is paused until the membrane repairs; if Ri collapses the cell is considered lost.
"""
from __future__ import annotations

import time

import numpy as np

import pyqtgraph as pg
from acq4.util import ptime
from acq4.util.debug import log_and_ignore_exception
from acq4.util.functions import plottable_booleans
from pyqtgraph import units
from ._base import PatchPipetteState, SteadyStateAnalysisBase, exponential_decay_avg


class ClearAccessAnalysis(SteadyStateAnalysisBase):
    """Analyze test pulses to drive whole-cell access recovery.

    Emits three flags from rolling averages of access resistance (Ra) and input resistance (Ri):

    - ``recovered``: smoothed Ra has dropped back below ``access_recovered_threshold`` while the
      cell is not simultaneously being lost (success).
    - ``repairing``: smoothed Ri is dropping faster than ``input_resistance_decline_threshold``
      (a log10 ratio, expected negative), meaning the membrane is being damaged and pulsing
      should pause until it recovers. Note this ratio is computed *per test pulse step*, so it
      scales with the test-pulse interval; the threshold's tuning assumes a roughly steady
      test-pulse cadence and would need rescaling if that cadence changes substantially.
    - ``lost``: the slow (``repair_tau``) average of Ri has fallen below
      ``input_resistance_loss_threshold``, meaning the cell is gone. Only honored after at least
      one ``repair_tau`` has elapsed since the first measurement, so a transient low Ri reading
      on entry cannot prematurely declare the cell lost.
    """

    @classmethod
    def plot_items(cls, *args, **kwargs):
        representative = cls(*args, **kwargs)
        return {
            'Ω': [
                pg.InfiniteLine(
                    movable=False, pos=representative._access_recovered_threshold, angle=0, pen=pg.mkPen('g')
                ),
                pg.InfiniteLine(
                    movable=False, pos=representative._input_resistance_loss_threshold, angle=0, pen=pg.mkPen('r')
                ),
            ]
        }

    @classmethod
    def plots_for_data(cls, data, *args, **kwargs):
        plots = {'Ω': [], '': []}
        names = False
        for d in data:
            analyzer = cls(*args, **kwargs)
            analysis = analyzer.process_measurements(d)
            plots['Ω'].append(
                dict(x=analysis["time"], y=analysis["access_avg"], pen=pg.mkPen('b'),
                     name=None if names else 'Access Avg')
            )
            plots['Ω'].append(
                dict(x=analysis["time"], y=analysis["input_repair_avg"], pen=pg.mkPen(90, 140, 255),
                     name=None if names else 'Input Repair Avg')
            )
            plots[''].append(
                dict(x=analysis["time"], y=analysis["input_ratio"], pen=pg.mkPen('y'),
                     name=None if names else 'Input Ratio')
            )
            plots[''].append(
                dict(x=analysis["time"], y=plottable_booleans(analysis["recovered"]), pen=pg.mkPen('g'),
                     symbol='o', name=None if names else 'Recovered')
            )
            plots[''].append(
                dict(x=analysis["time"], y=plottable_booleans(analysis["repairing"]), pen=pg.mkPen('y'),
                     symbol='x', name=None if names else 'Repairing')
            )
            plots[''].append(
                dict(x=analysis["time"], y=plottable_booleans(analysis["lost"]), pen=pg.mkPen('r'),
                     symbol='x', name=None if names else 'Lost')
            )
            names = True
        return plots

    def __init__(
        self,
        access_recovered_threshold: float,
        input_resistance_loss_threshold: float,
        input_resistance_decline_threshold: float,
        detection_tau: float,
        repair_tau: float,
    ):
        super().__init__()
        self._access_recovered_threshold = access_recovered_threshold
        self._input_resistance_loss_threshold = input_resistance_loss_threshold
        self._input_resistance_decline_threshold = input_resistance_decline_threshold
        self._detection_tau = detection_tau
        self._repair_tau = repair_tau
        # Time of the first measurement, so cell loss is only honored once the slow repair
        # average has had at least one repair tau to settle (a single low Ri reading on entry
        # must not be enough to declare the cell lost).
        self._first_time = None

    def access_recovered(self) -> bool:
        """Return True if the smoothed access resistance has dropped back below threshold."""
        return bool(self._last_measurement is not None and self._last_measurement['recovered'])

    def is_repairing(self) -> bool:
        """Return True if the input resistance is dropping and pulsing should pause."""
        return bool(self._last_measurement is not None and self._last_measurement['repairing'])

    def cell_lost(self) -> bool:
        """Return True if the input resistance has collapsed below the loss floor."""
        return bool(self._last_measurement is not None and self._last_measurement['lost'])

    def process_test_pulses(self, tps) -> np.ndarray:
        return self.process_measurements(
            np.array([
                (tp.recording.start_time, tp.analysis['access_resistance'], tp.analysis['input_resistance'])
                for tp in tps
            ]))

    def process_measurements(self, measurements: np.ndarray) -> np.ndarray:
        ret_array = np.zeros(
            len(measurements),
            dtype=[
                ('time', float),
                ('access_resistance', float),
                ('input_resistance', float),
                ('access_avg', float),
                ('input_detect_avg', float),
                ('input_repair_avg', float),
                ('input_ratio', float),
                ('recovered', bool),
                ('repairing', bool),
                ('lost', bool),
            ],
        )
        for i, measurement in enumerate(measurements):
            start_time, access_resistance, input_resistance = measurement
            if self._first_time is None:
                self._first_time = start_time
            if self._last_measurement is None:
                access_avg = access_resistance
                input_detect_avg = input_resistance
                input_repair_avg = input_resistance
                input_ratio = 0.0
            else:
                last = self._last_measurement
                dt = start_time - last['time']
                access_avg, _ = exponential_decay_avg(
                    dt, last['access_avg'], access_resistance, self._detection_tau)
                input_detect_avg, detect_ratio = exponential_decay_avg(
                    dt, last['input_detect_avg'], input_resistance, self._detection_tau)
                input_ratio = np.log10(detect_ratio) if detect_ratio > 0 else 0.0
                input_repair_avg, _ = exponential_decay_avg(
                    dt, last['input_repair_avg'], input_resistance, self._repair_tau)

            # Only trust the loss verdict once the slow repair average has had at least one
            # repair tau to settle, so a transient low Ri reading on entry can't declare loss.
            settled = (start_time - self._first_time) >= self._repair_tau
            lost = settled and input_repair_avg < self._input_resistance_loss_threshold
            repairing = input_ratio < self._input_resistance_decline_threshold
            # A falling Ra only counts as recovery if the cell is not simultaneously being lost.
            recovered = (access_avg < self._access_recovered_threshold) and not lost
            ret_array[i] = (
                start_time, access_resistance, input_resistance,
                access_avg, input_detect_avg, input_repair_avg, input_ratio,
                recovered, repairing, lost,
            )
            self._last_measurement = ret_array[i]
        return ret_array


class ClearAccessState(PatchPipetteState):
    """Recover a whole cell recording whose access resistance has climbed too high.

    State name: "clear access"

    The whole cell state hands off here when access resistance (Ra) climbs past its threshold.
    This state applies a sequence of escalating negative pressure pulses (and, if ``useZaps`` is
    enabled, brief voltage zaps) to re-open access, like a gentle break-in. It watches input
    resistance (Ri): while Ri is dropping it pauses pulsing until the membrane repairs, and if
    Ri collapses below ``inputResistanceLossThreshold`` it gives up and transitions to
    ``fallbackState`` (default 'fouled'). On success (Ra back below
    ``accessRecoveredThreshold``) it returns to 'whole cell'.

    Parameters
    ----------
    nPulses : list of int
        Number of pressure pulses to apply on each recovery attempt.
    pulseDurations : list of float
        Duration (seconds) of pulses to apply on each recovery attempt.
    pulsePressures : list of float
        Pressure (Pascals, expected negative) of pulses to apply on each recovery attempt.
    pulseInterval : float
        Minimum delay (seconds) between recovery attempts.
    accessRecoveredThreshold : float
        Access resistance (Ohms) below which (smoothed over ``detectionTau``) access is
        considered recovered and the state returns to 'whole cell' (default 25 MΩ).
    inputResistanceLossThreshold : float
        Input resistance (Ohms) below which (smoothed over ``repairTau``) the cell is considered
        lost and the state transitions to ``fallbackState`` (default 50 MΩ).
    inputResistanceDeclineThreshold : float
        Maximum log10 of the input-resistance ratio (expected negative) before the membrane is
        considered to be tearing, pausing recovery pulses until it repairs (default -0.01). This
        ratio is measured between successive test pulses, so it scales with the test-pulse
        interval; the default assumes a roughly steady cadence and should be rescaled if the
        test-pulse rate changes substantially.
    detectionTau : float
        Time constant (seconds) for smoothing Ra (recovery) and the Ri decline ratio (default 1 s).
    repairTau : float
        Time constant (seconds) for the slow Ri average used to detect cell loss (default 10 s).
    clearTimeout : float
        Maximum time (seconds) to spend attempting recovery before failing to ``fallbackState``
        (default 60 s).
    useZaps : bool
        If True, fire a brief voltage zap before each pressure pulse (default False).
    zapDuration : float
        Duration (seconds) of each voltage zap (default 1 ms).
    zapAmplitude : float
        Amplitude (Volts) of each voltage zap, relative to the holding potential (default 1 V).
        1 V is the conventional break-in "zap" amplitude in the patch-clamp literature (e.g. Axon
        instrumentation); some protocols go higher (up to ~5 V) with correspondingly briefer
        pulses to rupture without over-stressing the cell.
    fallbackState : str
        State to transition to if recovery fails (default 'fouled').
    """
    stateName = 'clear access'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': -70e-3,
        'initialTestPulseEnable': True,
        'initialAutoBiasEnable': True,
        'initialAutoBiasTarget': -70e-3,
        'fallbackState': 'fouled',
    }
    _parameterTreeConfig = {
        'nPulses': {'type': 'str', 'default': "[1, 1, 2, 2, 3]"},
        'pulseDurations': {'type': 'str', 'default': "[0.2, 0.2, 0.3, 0.5, 0.7]"},
        'pulsePressures': {'type': 'str', 'default': "[-20e3, -30e3, -40e3, -50e3, -60e3]"},
        'pulseInterval': {'type': 'float', 'default': 2, 'suffix': 's'},
        'accessRecoveredThreshold': {'type': 'float', 'default': 25e6, 'suffix': 'Ω'},
        'inputResistanceLossThreshold': {'type': 'float', 'default': 50e6, 'suffix': 'Ω'},
        'inputResistanceDeclineThreshold': {'type': 'float', 'default': -0.01, 'suffix': '', 'siPrefix': False},
        'detectionTau': {'type': 'float', 'default': 1, 'suffix': 's'},
        'repairTau': {'type': 'float', 'default': 10, 'suffix': 's'},
        'clearTimeout': {'type': 'float', 'default': 60, 'suffix': 's'},
        'useZaps': {'type': 'bool', 'default': False},
        'zapDuration': {'type': 'float', 'default': 1e-3, 'suffix': 's'},
        'zapAmplitude': {'type': 'float', 'default': 1.0, 'suffix': 'V'},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._analysis = None

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

        self._analysis = ClearAccessAnalysis(
            access_recovered_threshold=config['accessRecoveredThreshold'],
            input_resistance_loss_threshold=config['inputResistanceLossThreshold'],
            input_resistance_decline_threshold=config['inputResistanceDeclineThreshold'],
            detection_tau=config['detectionTau'],
            repair_tau=config['repairTau'],
        )

        patchrec['attemptedClearAccess'] = True
        patchrec['clearAccessSuccessful'] = False

        start_time = ptime.time()
        lastPulse = -np.inf
        attempt = 0
        while True:
            self.checkStop()

            if ptime.time() - start_time > config['clearTimeout']:
                self.setResult(error="Took longer than `clearTimeout` to recover access.")
                return {"state": config['fallbackState']}

            self._analysis.process_test_pulses(self.processAtLeastOneTestPulse())

            if self._analysis.access_recovered():
                self.setState("access resistance recovered")
                patchrec['clearAccessSuccessful'] = True
                return {"state": 'whole cell'}

            if self._analysis.cell_lost():
                self.setResult(error="Input resistance collapsed below `inputResistanceLossThreshold`; cell lost.")
                return {"state": config['fallbackState']}

            if self._analysis.is_repairing():
                # Ri is dropping; pause pulsing until the membrane repairs.
                self.setState("input resistance declining; pausing recovery pulses until repair")
                lastPulse = ptime.time()  # restart the interval timer once repair finishes
                continue

            if ptime.time() - lastPulse < config['pulseInterval']:
                continue

            if attempt >= len(config['nPulses']):
                self.setResult(error=f"Access not recovered after {attempt} clearing attempts.")
                return {"state": config['fallbackState']}

            self.setState('Clear access attempt %d' % attempt)
            self.attemptClear(
                config['nPulses'][attempt],
                config['pulseDurations'][attempt],
                config['pulsePressures'][attempt],
            )
            attempt += 1
            lastPulse = ptime.time()

    def attemptClear(self, nPulses, duration, pressure):
        """Apply a burst of negative pressure pulses (and optional zaps) to re-open access."""
        for i in range(nPulses):
            if self.config['useZaps']:
                self.dev.clampDevice.zap(
                    duration=self.config['zapDuration'], amplitude=self.config['zapAmplitude'])
            self.dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            stop = ptime.time() + duration
            try:
                while True:
                    remaining = stop - ptime.time()
                    if remaining <= 0:
                        break
                    self.checkStop()
                    time.sleep(min(0.1, remaining))
            finally:
                self.dev.pressureDevice.setPressure(source='atmosphere')
            if i < nPulses - 1:
                time.sleep(0.1)  # short delay between pulses

    def _cleanup(self):
        with log_and_ignore_exception(Exception, "Error resetting pressure after clear access"):
            self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        super()._cleanup()
