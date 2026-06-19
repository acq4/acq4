"""Whole cell patch state: hold the recording and watch for access resistance climbing.

When the access resistance (Ra) rises past a threshold the cell is starting to be lost. The state
does not act on this itself; it raises a passive warning in the UI so the user can decide whether
to manually initiate a 'clear access' recovery attempt.
"""
from __future__ import annotations

import numpy as np

import pyqtgraph as pg
from acq4.util import ptime
from acq4.util.debug import log_and_ignore_exception
from acq4.util.functions import plottable_booleans
from ._base import PatchPipetteState, SteadyStateAnalysisBase, exponential_decay_avg


class WholeCellAnalysis(SteadyStateAnalysisBase):
    """Track a rolling average of access resistance to detect when whole cell access is being lost.

    The whole cell state only *detects* trouble; recovery is left to the user (who may manually
    initiate the 'clear access' state). This analysis emits a single ``losing_access`` flag that is
    True once the smoothed access resistance climbs above ``access_resistance_threshold``.

    Whole cell holds the actual ephys recording, which reserves the clamp/DAQ and suspends test
    pulses for extended periods. A gap longer than ``max_test_pulse_gap`` is therefore treated as a
    fresh start: the rolling average is re-seeded and a new detection window begins, so a single
    stale reading when test pulses resume cannot trip the warning. The flag is only honored once at
    least ``detection_tau`` of continuous test pulses have accrued since the last (re)start.
    """

    @classmethod
    def plot_items(cls, *args, **kwargs):
        representative = cls(*args, **kwargs)
        return {
            'Ω': [
                pg.InfiniteLine(
                    movable=False, pos=representative._access_resistance_threshold, angle=0, pen=pg.mkPen('w')
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
                dict(
                    x=analysis["time"],
                    y=analysis["access_avg"],
                    pen=pg.mkPen('b'),
                    name=None if names else 'Access Avg',
                )
            )
            plots[''].append(
                dict(
                    x=analysis["time"],
                    y=plottable_booleans(analysis["losing_access"]),
                    pen=pg.mkPen('r'),
                    symbol='x',
                    name=None if names else 'Losing Access',
                )
            )
            names = True
        return plots

    def __init__(self, access_resistance_threshold: float, detection_tau: float, max_test_pulse_gap: float):
        super().__init__()
        self._access_resistance_threshold = access_resistance_threshold
        self._detection_tau = detection_tau
        self._max_test_pulse_gap = max_test_pulse_gap
        # Start time of the current continuous detection window; reset whenever test pulses resume
        # after a gap longer than max_test_pulse_gap, so stale pre-gap data is discarded.
        self._window_start_time = None

    def is_losing_access(self) -> bool:
        """Return True if the smoothed access resistance is above threshold."""
        return bool(self._last_measurement is not None and self._last_measurement['losing_access'])

    def process_test_pulses(self, tps) -> np.ndarray:
        return self.process_measurements(
            np.array([(tp.recording.start_time, tp.analysis['access_resistance']) for tp in tps]))

    def process_measurements(self, measurements: np.ndarray) -> np.ndarray:
        ret_array = np.zeros(
            len(measurements),
            dtype=[
                ('time', float),
                ('access_resistance', float),
                ('access_avg', float),
                ('losing_access', bool),
            ],
        )
        for i, measurement in enumerate(measurements):
            start_time, access_resistance = measurement
            if self._last_measurement is None:
                access_avg = access_resistance
                self._window_start_time = start_time
            else:
                dt = start_time - self._last_measurement['time']
                if dt > self._max_test_pulse_gap:
                    # Test pulses resumed after a long gap (e.g. an ephys recording held the
                    # clamp): drop the stale average and begin a fresh detection window.
                    access_avg = access_resistance
                    self._window_start_time = start_time
                else:
                    access_avg, _ = exponential_decay_avg(
                        dt, self._last_measurement['access_avg'], access_resistance, self._detection_tau
                    )
            # Only honor the flag once the window has filled, so a single reading after a gap or
            # at startup can't trip it before the rolling average is meaningful.
            settled = (start_time - self._window_start_time) >= self._detection_tau
            losing_access = settled and access_avg > self._access_resistance_threshold
            ret_array[i] = (start_time, access_resistance, access_avg, losing_access)
            self._last_measurement = ret_array[i]
        return ret_array


class WholeCellState(PatchPipetteState):
    """Pipette in whole cell configuration.

    State name: "whole cell"

    Holds the whole cell recording and monitors access resistance (Ra). When Ra climbs past
    ``accessResistanceThreshold`` for long enough (smoothed over ``detectionTau``) the cell is
    starting to be lost. The state does not switch away on its own; it raises a passive warning on
    the device (shown with a red border in the MultiPatch window) so the user can decide whether to
    manually initiate the 'clear access' state. The warning clears automatically if Ra falls back
    below the threshold. Set ``monitorAccessResistance`` to False to disable monitoring entirely
    and simply hold the recording.

    Parameters
    ----------
    monitorAccessResistance : bool
        If True (default), monitor access resistance and raise a UI warning when it climbs past
        ``accessResistanceThreshold``.
    accessResistanceThreshold : float
        Access resistance (Ohms) above which (smoothed over ``detectionTau``) the cell is
        considered to be losing access (default 30 MΩ).
    detectionTau : float
        Time constant (seconds) for smoothing the access resistance measurement (default 5 s).
    maxTestPulseGap : float
        Gap (seconds) between test pulses beyond which monitoring restarts with a fresh detection
        window, so a long pause (e.g. during an ephys recording that reserves the clamp) does not
        leave stale data that trips the warning when test pulses resume (default 5 s).
    """
    stateName = 'whole cell'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': -70e-3,
        'initialTestPulseEnable': True,
        'initialAutoBiasEnable': True,
        'initialAutoBiasTarget': -70e-3,
    }
    _parameterTreeConfig = {
        'monitorAccessResistance': {'type': 'bool', 'default': True},
        'accessResistanceThreshold': {'type': 'float', 'default': 30e6, 'suffix': 'Ω'},
        'detectionTau': {'type': 'float', 'default': 5, 'suffix': 's'},
        'maxTestPulseGap': {'type': 'float', 'default': 5, 'suffix': 's'},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._analysis = None
        self._warningActive = False

    def run(self):
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStartTime'] = ptime.time()
        patchrec['wholeCellPosition'] = tuple(self.dev.pipetteDevice.globalPosition())

        # TODO: Option to switch to I=0 for a few seconds to get initial RMP decay

        if not self.config['monitorAccessResistance']:
            while True:
                self.sleep(0.1)

        self.dev.setAccessWarning(False)  # clear any stale warning when (re)entering whole cell
        self.monitorTestPulse()
        self._analysis = WholeCellAnalysis(
            access_resistance_threshold=self.config['accessResistanceThreshold'],
            detection_tau=self.config['detectionTau'],
            max_test_pulse_gap=self.config['maxTestPulseGap'],
        )
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue
            self.updateAccessWarning(tps)

    def updateAccessWarning(self, tps):
        """Update the device's access-resistance warning from the latest test pulses.

        Whole cell stays put either way; the warning is purely advisory so the user can choose to
        manually initiate 'clear access'. The warning clears itself once Ra recovers.
        """
        self._analysis.process_test_pulses(tps)
        losing = self._analysis.is_losing_access()
        if losing and not self._warningActive:
            self._warningActive = True
            message = (
                f"access resistance climbed above `accessResistanceThreshold` "
                f"({self.config['accessResistanceThreshold'] / 1e6:.1f}MΩ); "
                f"consider manually initiating 'clear access'"
            )
            self.setState(message)
            self.dev.setAccessWarning(True, message)
        elif not losing and self._warningActive:
            self._warningActive = False
            self.setState("access resistance recovered")
            self.dev.setAccessWarning(False)

    def _cleanup(self):
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStopTime'] = ptime.time()
        with log_and_ignore_exception(Exception, "Error clearing access warning after whole cell"):
            self.dev.setAccessWarning(False)
        return super()._cleanup()
