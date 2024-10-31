from __future__ import annotations

from typing import Any

import numpy as np

from acq4.util import ptime
import pyqtgraph as pg
from acq4.util.functions import plottable_booleans
from neuroanalysis.data import TSeries
from pyqtgraph.units import kPa
from ._base import PatchPipetteState, SteadyStateAnalysisBase


class SealAnalysis(SteadyStateAnalysisBase):
    @classmethod
    def plot_items(cls, tau, success_at, hold_at):
        return {'Ω': [
            pg.InfiniteLine(movable=False, pos=success_at, angle=0, pen=pg.mkPen('g')),
            pg.InfiniteLine(movable=False, pos=hold_at, angle=0, pen=pg.mkPen('w')),
        ]}

    @classmethod
    def plots_for_data(cls, data: iter[np.void], *args, **kwargs) -> dict[str, list[dict[str, Any]]]:
        plots = {
            'Ω': [],
            '': [],
        }
        labels = False
        for d in data:
            analyzer = cls(*args, **kwargs)
            analysis = analyzer.process_measurements(d)
            plots['Ω'].append(dict(
                x=analysis["time"],
                y=analysis["resistance_avg"],
                pen=pg.mkPen('b'),
                name=None if labels else 'Resistance Avg',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=analysis["resistance_ratio"],
                pen=pg.mkPen('r'),
                name=None if labels else 'Resistance Ratio',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=plottable_booleans(analysis["success"]),
                symbol='o',
                pen=pg.mkPen('g'),
                name=None if labels else 'Seal Success',
            ))
            labels = True
        return plots

    def __init__(self, tau, success_at, hold_at):
        super().__init__()
        self._tau = tau
        self._success_at = success_at
        self._hold_at = hold_at

    def process_measurements(self, measurements: np.ndarray) -> np.ndarray:
        ret_array = np.zeros(measurements.shape[0], dtype=[
            ('time', float),
            ('steady_state_resistance', float),
            ('resistance_avg', float),
            ('resistance_ratio', float),
            ('success', bool),
            ('hold', bool),
        ])
        for i, m in enumerate(measurements):
            t, resistance = m
            if self._last_measurement is None:
                resistance_avg = resistance
                ratio = 1
            else:
                dt = t - self._last_measurement['time']
                # ratio = resistance / self._last_measurement['resistance_avg']
                resistance_avg, ratio = self.exponential_decay_avg(
                    dt, self._last_measurement['resistance_avg'], resistance, self._tau)
            success = resistance_avg > self._success_at
            hold = resistance_avg > self._hold_at
            ret_array[i] = (
                t,
                resistance,
                resistance_avg,
                ratio,
                success,
                hold,
            )
            self._last_measurement = ret_array[i]

        return ret_array

    def success(self):
        return self._last_measurement and self._last_measurement['success']

    def hold(self):
        return self._last_measurement and self._last_measurement['hold']

    def resistance_ratio(self):
        return self._last_measurement['resistance_ratio'] if self._last_measurement else float('nan')


def find_optimal_pressure(pressures, resistances) -> float:
    win = 3
    dRss = np.diff(np.log(np.convolve(resistances.data, np.ones(win) / win, mode='valid')))
    closest_indices = find_closest(pressures.time_values, resistances.time_values)
    p_like_r = pressures.data[closest_indices][1:]
    p_like_r = np.convolve(p_like_r, np.ones(win) / win, mode='valid')
    return float(p_like_r[np.argmax(dRss)])


def find_closest(data, values):
    indices = np.searchsorted(data, values, side="left")
    indices = np.clip(indices, 1, len(data) - 1)
    left = data[indices - 1]
    right = data[indices]
    indices -= values - left < right - values  # this is why we can't have nice things, LLM
    return indices


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
    resistanceMonitorTau : float
        Time constant (seconds) for exponential averaging of resistance measurements. Default 1s.
    autoSealTimeout : float
        Maximum timeout (seconds) before the seal attempt is aborted,
        transitioning to *fallbackState*.
    pressureLimit : float
        The largest allowable vacuum pressure (pascals, expected negative value) to apply during sealing.
    delayBeforePressure : float
        Wait time (seconds) at beginning of seal state before applying negative pressure.
    delayAfterSeal : float
        Wait time (seconds) after GOhm seal is acquired, before transitioning to next state.
    afterSealPressure : float
        Pressure (Pascals) to apply during *delayAfterSeal* interval. This can help to stabilize the seal after initial
        formation.
    pressureScanInterval : float
        Interval (seconds) between pressure scans during automatic pressure control. Default 10s.
    pressureScanRadius : float
        Maximum distance (Pascals) from current pressure to scan during automatic pressure control. Default 5kPa.
    pressureScanDuration : float
        Duration (seconds) for each pressure scan during automatic pressure control. Default 5s.
    """
    stateName = 'seal'

    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'fouled',
    }
    _parameterTreeConfig = {
        'pressureMode': {'type': 'str', 'default': 'user', 'limits': ['auto', 'user']},
        'startingPressure': {'type': 'float', 'default': -1000},
        'holdingThreshold': {'type': 'float', 'default': 100e6},
        'holdingPotential': {'type': 'float', 'default': -70e-3},
        'sealThreshold': {'type': 'float', 'default': 1e9},
        'breakInThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'autoSealTimeout': {'type': 'float', 'default': 30.0, 'suffix': 's'},
        'pressureLimit': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},
        'resistanceMonitorTau': {'type': 'float', 'default': 1, 'suffix': 's'},
        'delayBeforePressure': {'type': 'float', 'default': 0.0, 'suffix': 's'},
        'delayAfterSeal': {'type': 'float', 'default': 5.0, 'suffix': 's'},
        'afterSealPressure': {'type': 'float', 'default': -1000, 'suffix': 'Pa'},
        'pressureScanInterval': {'type': 'float', 'default': 10.0, 'suffix': 's'},
        'pressureScanRadius': {'type': 'float', 'default': 5 * kPa, 'suffix': 'Pa'},
        'pressureScanDuration': {'type': 'float', 'default': 5.0, 'suffix': 's'},
    }

    def __init__(self, dev, config):
        super().__init__(dev, config)
        self._analysis = SealAnalysis(
            tau=config['resistanceMonitorTau'],
            success_at=config['sealThreshold'],
            hold_at=config['holdingThreshold'],
        )
        self._initialized = False
        self._patchrec = dev.patchRecord()
        self.pressure = config['startingPressure']
        self._lastPressureScan = None
        self._pressures = [[], []]
        self._resistances = [np.zeros(0), np.zeros(0)]

    def initialize(self):
        self.dev.setTipClean(False)
        self.dev.pressureDevice.sigPressureChanged.connect(self._handlePressureChanged)
        super().initialize()

    def _handlePressureChanged(self, dev, source, pressure):
        self._pressures[0].append(ptime.time())
        self._pressures[1].append(pressure)

    def processAtLeastOneTestPulse(self):
        tps = super().processAtLeastOneTestPulse()
        analysis = self._analysis.process_test_pulses(tps)
        self._resistances[0] = np.concatenate([self._resistances[0], analysis['time']])
        self._resistances[1] = np.concatenate([self._resistances[1], analysis['steady_state_resistance']])

        tp = tps[-1]
        ssr = tp.analysis['steady_state_resistance']
        cap = tp.analysis['capacitance']
        if not self._initialized:
            self._patchrec['resistanceBeforeSeal'] = ssr
            self._patchrec['capacitanceBeforeSeal'] = cap
            self._initialized = True
        self._patchrec['resistanceBeforeBreakin'] = ssr
        self._patchrec['capacitanceBeforeBreakin'] = cap
        return tps

    def run(self):
        config = self.config
        dev = self.dev
        holdingSet = False

        self.monitorTestPulse()
        self.processAtLeastOneTestPulse()

        startTime = ptime.time()
        self.setState(f'beginning seal (mode: {config["pressureMode"] !r})')
        self.setInitialPressure()

        self._patchrec['attemptedSeal'] = True

        while not self._analysis.success():
            self.checkStop()
            self.processAtLeastOneTestPulse()

            if not holdingSet and self._analysis.hold():
                self.setState(f'enable holding potential {config["holdingPotential"] * 1000:0.1f} mV')
                dev.clampDevice.setHolding(mode="VC", value=config['holdingPotential'])
                holdingSet = True

            if config['pressureMode'] == 'auto':
                dt = ptime.time() - startTime
                if dt < config['delayBeforePressure']:
                    # delay at atmospheric pressure before starting suction
                    continue

                if dt > config['autoSealTimeout']:
                    self._patchrec['sealSuccessful'] = False
                    self._taskDone(interrupted=True, error=f"Seal failed after {dt:f} seconds")
                    return config['fallbackState']

                self.updatePressure()

        # Success!
        self.setState('gigaohm seal detected')

        # delay for a short period, possibly applying pressure to allow seal to stabilize
        if config['delayAfterSeal'] > 0:
            if config['afterSealPressure'] == 0:
                dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
            else:
                dev.pressureDevice.setPressure(source='regulator', pressure=config['afterSealPressure'])
            self.sleep(config['delayAfterSeal'])

        dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        dev.clampDevice.autoCapComp()

        self._taskDone()
        self._patchrec['sealSuccessful'] = True
        return 'cell attached'

    def setInitialPressure(self):
        mode = self.config['pressureMode']
        if mode == 'user':
            self.dev.pressureDevice.setPressure(source='user', pressure=0)
        elif mode == 'auto':
            if self.config['delayBeforePressure'] == 0:
                self.dev.pressureDevice.setPressure(source='regulator', pressure=self.pressure)
            else:
                self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

    def updatePressure(self):
        config = self.config
        dev = self.dev

        # every few seconds, slowly scan across the pressure neighborhood to find the best pressure
        if self._lastPressureScan is None or ptime.time() - self._lastPressureScan > self.config['pressureScanInterval']:
            low = max(self.pressure - self.config['pressureScanRadius'], self.config['pressureLimit'])
            high = min(self.pressure + self.config['pressureScanRadius'], 0)
            self.dev.pressureDevice.setPressure(source='regulator', pressure=low)
            self.processAtLeastOneTestPulse()
            start = ptime.time()
            self.waitFor(self.dev.pressureDevice.rampPressure(target=high, duration=self.config['pressureScanDuration']))
            turnaround = ptime.time()
            self.waitFor(self.dev.pressureDevice.rampPressure(target=low, duration=self.config['pressureScanDuration']))
            end = ptime.time()
            self.processAtLeastOneTestPulse()
            self.pressure = self.best_pressure(start, turnaround, end)
            self.setState(f'scanned for pressure: {self.pressure / kPa:0.1f} kPa')
            self._lastPressureScan = end

        self.pressure = np.clip(self.pressure, config['pressureLimit'], 0)
        dev.pressureDevice.setPressure(source='regulator', pressure=self.pressure)

    def best_pressure(self, start: float, turnaround: float, end: float) -> float:
        pressures, resistances = self._trim_data_caches(start)

        best_forwards = find_optimal_pressure(
            pressures.time_slice(start, turnaround),
            resistances.time_slice(start, turnaround),
        )
        best_backwards = find_optimal_pressure(
            pressures.time_slice(turnaround, end),
            resistances.time_slice(turnaround, end),
        )

        return np.clip((best_forwards + best_backwards) / 2, self.config['pressureLimit'], 0)

    def _trim_data_caches(self, start):
        pressures = TSeries(np.array(self._pressures[1]), time_values=np.array(self._pressures[0]))
        pressures = pressures.time_slice(start, pressures.t_end)
        self._pressures = [pressures.time_values.tolist(), pressures.data.tolist()]
        resistances = TSeries(self._resistances[1], time_values=self._resistances[0])
        resistances = resistances.time_slice(start, resistances.t_end)
        self._resistances = [resistances.time_values, resistances.data]
        return pressures, resistances

    def cleanup(self):
        self.dev.pressureDevice.setPressure(source='atmosphere')
        super().cleanup()
