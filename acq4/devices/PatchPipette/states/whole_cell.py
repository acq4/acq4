"""Whole cell patch state: hold the recording and watch for access resistance climbing.

When the access resistance (Ra) rises past a threshold the cell is starting to be lost, so
this state hands off the repair work to the 'clear access' state rather than fixing it here.
"""
from __future__ import annotations

import numpy as np

import pyqtgraph as pg
from acq4.util import ptime
from acq4.util.functions import plottable_booleans
from ._base import PatchPipetteState, SteadyStateAnalysisBase, exponential_decay_avg


class WholeCellAnalysis(SteadyStateAnalysisBase):
    """Track a rolling average of access resistance to detect when whole cell access is being lost.

    The whole cell state only *detects* trouble; the actual recovery is delegated to the
    'clear access' state. This analysis emits a single ``losing_access`` flag that is True once
    the smoothed access resistance climbs above ``access_resistance_threshold``.
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

    def __init__(self, access_resistance_threshold: float, detection_tau: float):
        super().__init__()
        self._access_resistance_threshold = access_resistance_threshold
        self._detection_tau = detection_tau

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
            else:
                dt = start_time - self._last_measurement['time']
                access_avg, _ = exponential_decay_avg(
                    dt, self._last_measurement['access_avg'], access_resistance, self._detection_tau
                )
            losing_access = access_avg > self._access_resistance_threshold
            ret_array[i] = (start_time, access_resistance, access_avg, losing_access)
            self._last_measurement = ret_array[i]
        return ret_array


class WholeCellState(PatchPipetteState):
    """Pipette in whole cell configuration.

    State name: "whole cell"

    Holds the whole cell recording and monitors access resistance (Ra). When Ra climbs past
    ``accessResistanceThreshold`` for long enough (smoothed over ``detectionTau``) the cell is
    starting to be lost, and the state hands off to ``troubleState`` (default 'clear access')
    to attempt recovery. Set ``monitorAccessResistance`` to False to disable the handoff and
    simply hold the recording.

    Parameters
    ----------
    monitorAccessResistance : bool
        If True (default), monitor access resistance and transition to ``troubleState`` when it
        climbs past ``accessResistanceThreshold``.
    accessResistanceThreshold : float
        Access resistance (Ohms) above which (smoothed over ``detectionTau``) the cell is
        considered to be losing access (default 30 MΩ).
    detectionTau : float
        Time constant (seconds) for smoothing the access resistance measurement (default 5 s).
    troubleState : str
        Name of the state to transition to when access resistance climbs too high
        (default 'clear access').
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
        'troubleState': {'type': 'str', 'default': 'clear access'},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._analysis = None

    def run(self):
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStartTime'] = ptime.time()
        patchrec['wholeCellPosition'] = tuple(self.dev.pipetteDevice.globalPosition())

        # TODO: Option to switch to I=0 for a few seconds to get initial RMP decay

        if not self.config['monitorAccessResistance']:
            while True:
                self.sleep(0.1)

        self.monitorTestPulse()
        self._analysis = WholeCellAnalysis(
            access_resistance_threshold=self.config['accessResistanceThreshold'],
            detection_tau=self.config['detectionTau'],
        )
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue
            self._analysis.process_test_pulses(tps)
            if self._analysis.is_losing_access():
                self.setState(
                    f"access resistance climbed above `accessResistanceThreshold` "
                    f"({self.config['accessResistanceThreshold'] / 1e6:.1f}MΩ); attempting recovery"
                )
                return {"state": self.config['troubleState']}

    def _cleanup(self):
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStopTime'] = ptime.time()
        return super()._cleanup()
