from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
from gentletask import check_stop

import pyqtgraph as pg
from acq4.util import ptime, Qt
from acq4.util.debug import log_and_ignore_exception
from acq4.util.functions import plottable_booleans
from acq4.util.task import Stopped, sleep
from neuroanalysis.data import TSeries
from pyqtgraph.units import kPa
from ._base import PatchPipetteState, SteadyStateAnalysisBase, exponential_decay_avg


def _finite_or_nan(values: np.ndarray) -> np.ndarray:
    """`values` with the infinities replaced by NaN, so a plot skips them.

    The economic columns are deliberately infinite wherever the seal is going
    nowhere or the slice offers nothing better, which is meaningful in the record
    and unplottable in a curve.
    """
    return np.where(np.isfinite(values), values, np.nan)


class SealAnalysis(SteadyStateAnalysisBase):
    @classmethod
    def plot_items(
        cls,
        success_tau,
        success_at,
        hold_tau,
        hold_at,
        failure_tau,
        failure_resistance_threshold,
        failure_dRdt_threshold,
        break_in_tau,
        break_in_capacitance_threshold,
        break_in_resistance_ceiling,
        break_in_resistance_floor,
    ):
        return {'Ω': [
            pg.InfiniteLine(movable=False, pos=success_at, angle=0, pen=pg.mkPen('g')),
            pg.InfiniteLine(movable=False, pos=hold_at, angle=0, pen=pg.mkPen('w')),
        ]}

    @classmethod
    def plots_for_data(cls, data: iter[np.void], *args, **kwargs) -> dict[str, list[dict[str, Any]]]:
        plots = {
            'Ω': [],
            '': [],
            # The economic columns are durations, so they get their own axis
            # rather than being squeezed onto the resistance one.
            's': [],
        }
        labels = False
        for d in data:
            analyzer = cls(*args, **kwargs)
            analysis = analyzer.process_measurements(d)
            # TODO this plot looks to have already been broken
            plots['Ω'].append(dict(
                x=analysis["time"],
                y=analysis["resistance_avg_for_success"],
                pen=pg.mkPen('b'),
                name=None if labels else 'Resistance Avg for Seal',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=plottable_booleans(analysis["success"]),
                symbol='o',
                pen=pg.mkPen('g'),
                name=None if labels else 'Seal Success',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=plottable_booleans(analysis["failure"]),
                symbol='x',
                pen=pg.mkPen('r'),
                name=None if labels else 'Seal Failure',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=plottable_booleans(analysis["break_in"]),
                symbol='t',
                pen=pg.mkPen('y'),
                name=None if labels else 'Spontaneous Break-in',
            ))
            plots['s'].append(dict(
                x=analysis["time"],
                y=_finite_or_nan(analysis["projected_seal_time"]),
                pen=pg.mkPen('c'),
                name=None if labels else 'Projected Seal Time',
            ))
            plots['s'].append(dict(
                x=analysis["time"],
                y=_finite_or_nan(analysis["continue_cost"]),
                pen=pg.mkPen(255, 170, 0),
                name=None if labels else 'Cost of Continuing',
            ))
            plots['s'].append(dict(
                x=analysis["time"],
                y=_finite_or_nan(analysis["abandon_threshold"]),
                pen=pg.mkPen('w', style=Qt.Qt.DashLine),
                name=None if labels else 'Cost of Starting Over',
            ))
            plots[''].append(dict(
                x=analysis["time"],
                y=plottable_booleans(analysis["give_up"]),
                symbol='d',
                pen=pg.mkPen('m'),
                name=None if labels else 'Give Up',
            ))
            labels = True
        return plots

    def __init__(
        self,
        success_tau,
        success_at,
        hold_tau,
        hold_at,
        failure_tau,
        failure_resistance_threshold,
        failure_dRdt_threshold,
        break_in_tau,
        break_in_capacitance_threshold,
        break_in_resistance_ceiling,
        break_in_resistance_floor,
        slope_tau=2.0,
        min_decision_time=5.0,
        restart_cost=0.0,
        seal_probability=0.0,
        expected_seal_duration=0.0,
        expected_failed_seal_duration=0.0,
        probability_decay_tau=0.0,
    ):
        super().__init__()
        self._success_tau = success_tau
        self._success_at = success_at
        self._hold_tau = hold_tau
        self._hold_at = hold_at
        self._failure_tau = failure_tau
        self._failure_resistance_threshold = failure_resistance_threshold
        self._failure_dRdt_threshold = failure_dRdt_threshold
        self._break_in_tau = break_in_tau
        self._break_in_capacitance_threshold = break_in_capacitance_threshold
        self._break_in_resistance_ceiling = break_in_resistance_ceiling
        self._break_in_resistance_floor = break_in_resistance_floor
        self._slope_tau = slope_tau
        self._min_decision_time = min_decision_time
        self._seal_probability = seal_probability
        self._probability_decay_tau = probability_decay_tau
        # The expected wall-clock from abandoning this cell to the next gigaseal:
        #     W = (R + p*T_s + (1-p)*T_f) / p
        # one cycle's overhead plus whichever seal episode it buys, divided by the
        # share of cycles that end in a seal. Constant for the whole episode --
        # it describes the alternative, which this cell cannot change -- so it is
        # computed once here rather than per test pulse.
        #
        # No seal probability leaves it infinite, and the rule below then never
        # fires: a slice believed to seal nothing offers nothing better to go to.
        # That is the shipped default, so an unconfigured or half-pinned profile
        # behaves exactly as it did before this existed.
        if seal_probability > 0:
            self._abandon_threshold = (
                restart_cost
                + seal_probability * expected_seal_duration
                + (1 - seal_probability) * expected_failed_seal_duration
            ) / seal_probability
        else:
            self._abandon_threshold = np.inf
        # The first measurement's timestamp, for measuring elapsed time into this
        # episode. The measurement clock is the clamp's, not this object's, so
        # there is nothing to read until a pulse arrives.
        self._start_time = None
        # Spontaneous break-in is only plausible once the seal has gotten well underway; below
        # the floor a rising capacitance reading is noise, not a ruptured membrane. This latches
        # once crossed so a later dip back below the floor doesn't re-disarm the check.
        self._break_in_floor_reached = False

    def _logSlope(self, dt, previous_avg, current_avg, previous_slope) -> float:
        """d(ln Rss)/dt, exponentially averaged over *slope_tau*.

        Taken from the averaged resistance rather than the raw reading, because a
        slope read off unsmoothed test pulses is dominated by their noise.

        Holds the previous estimate when there is no interval to divide by or no
        positive pair to take a logarithm of, so a duplicated timestamp or a
        nonpositive reading stalls the estimate rather than destroying it.
        """
        if dt <= 0 or previous_avg <= 0 or current_avg <= 0:
            return float(previous_slope)
        raw = (np.log(current_avg) - np.log(previous_avg)) / dt
        slope, _ = exponential_decay_avg(dt, previous_slope, raw, self._slope_tau)
        return float(slope)

    def process_test_pulses(self, tps) -> np.ndarray:
        # The base implementation reads resistance only; break-in detection also needs the
        # membrane capacitance, so the measurement rows carry a third column here.
        return self.process_measurements(np.array([
            (
                tp.recording.start_time,
                tp.analysis['steady_state_resistance'],
                tp.analysis['capacitance'],
            )
            for tp in tps
        ]))

    def process_measurements(self, measurements: np.ndarray) -> np.ndarray:
        ret_array = np.zeros(measurements.shape[0], dtype=[
            ('time', float),
            ('steady_state_resistance', float),
            ('capacitance', float),
            ('resistance_avg_for_success', float),
            ('resistance_avg_for_hold', float),
            ('resistance_avg_for_failure', float),
            ('capacitance_avg_for_break_in', float),
            ('dRdt_for_failure', float),
            ('success', bool),
            ('failure', bool),
            ('hold', bool),
            ('break_in', bool),
            ('log_rss_slope', float),
            ('projected_seal_time', float),
            ('survival_q', float),
            ('continue_cost', float),
            ('abandon_threshold', float),
            ('give_up', bool),
        ])
        for i, m in enumerate(measurements):
            t, resistance, capacitance = m
            # A test pulse with no membrane transient to fit reports NaN rather than zero. That
            # is the normal reading for an intact seal, so it counts as "no capacitance" here;
            # letting it into the average would poison it permanently and silently disable
            # break-in detection for the rest of the state.
            capacitance_for_avg = 0.0 if np.isnan(capacitance) else capacitance
            if self._last_measurement is None:
                resistance_avg_for_success = resistance
                resistance_avg_for_hold = resistance
                resistance_avg_for_failure = resistance
                capacitance_avg_for_break_in = capacitance_for_avg
                # give it a while to settle
                dRdt_for_failure = self._failure_dRdt_threshold * 10 * self._failure_tau
                log_rss_slope = 0.0
            else:
                dt = t - self._last_measurement['time']
                resistance_avg_for_success, _ = exponential_decay_avg(
                    dt, self._last_measurement['resistance_avg_for_success'], resistance, self._success_tau)
                resistance_avg_for_hold, _ = exponential_decay_avg(
                    dt, self._last_measurement['resistance_avg_for_hold'], resistance, self._hold_tau)
                resistance_avg_for_failure, _ = exponential_decay_avg(
                    dt, self._last_measurement['resistance_avg_for_failure'], resistance, self._failure_tau)
                capacitance_avg_for_break_in, _ = exponential_decay_avg(
                    dt,
                    self._last_measurement['capacitance_avg_for_break_in'],
                    capacitance_for_avg,
                    self._break_in_tau,
                )
                dRdt = (resistance - self._last_measurement['steady_state_resistance']) / dt
                dRdt_for_failure, _ = exponential_decay_avg(
                    dt, self._last_measurement['dRdt_for_failure'], dRdt, self._failure_tau)
                log_rss_slope = self._logSlope(
                    dt,
                    self._last_measurement['resistance_avg_for_success'],
                    resistance_avg_for_success,
                    self._last_measurement['log_rss_slope'],
                )
            success = resistance_avg_for_success > self._success_at
            hold = resistance_avg_for_hold > self._hold_at
            failure = (
                resistance_avg_for_failure < self._failure_resistance_threshold
                and dRdt_for_failure < self._failure_dRdt_threshold
            )
            if resistance_avg_for_success >= self._break_in_resistance_floor:
                self._break_in_floor_reached = True
            # Membrane capacitance sustained while the resistance sits below a sealed pipette's
            # means the cell ruptured into whole-cell on its own. Above the ceiling the pipette
            # is sealed rather than broken in, and *success* is the right answer instead. Gated
            # behind the floor latch: below it, a capacitance blip is measurement noise, not a
            # real membrane rupture, and would otherwise fire before the seal has gotten anywhere.
            break_in = (
                self._break_in_floor_reached
                and capacitance_avg_for_break_in > self._break_in_capacitance_threshold
                and resistance < self._break_in_resistance_ceiling
            )
            if self._start_time is None:
                self._start_time = t
            elapsed = t - self._start_time
            if resistance_avg_for_success >= self._success_at:
                projected_seal_time = 0.0
            elif log_rss_slope > 0 and resistance_avg_for_success > 0:
                projected_seal_time = (
                    np.log(self._success_at) - np.log(resistance_avg_for_success)
                ) / log_rss_slope
            else:
                # Flat or falling: on this trajectory the seal never arrives, so
                # the cost of continuing is unbounded however cheap the slice is.
                projected_seal_time = np.inf
            if self._seal_probability <= 0:
                survival_q = 0.0
            elif self._probability_decay_tau > 0:
                survival_q = self._seal_probability * np.exp(
                    -elapsed / self._probability_decay_tau
                )
            else:
                survival_q = self._seal_probability
            continue_cost = (
                projected_seal_time / survival_q if survival_q > 0 else np.inf
            )
            # Both sides infinite compares False, which is the behaviour wanted:
            # an unsealable slice has nothing better to offer than this cell.
            give_up = bool(
                elapsed >= self._min_decision_time
                and continue_cost > self._abandon_threshold
            )
            ret_array[i] = (
                t,
                resistance,
                capacitance,
                resistance_avg_for_success,
                resistance_avg_for_hold,
                resistance_avg_for_failure,
                capacitance_avg_for_break_in,
                dRdt_for_failure,
                success,
                failure,
                hold,
                break_in,
                log_rss_slope,
                projected_seal_time,
                survival_q,
                continue_cost,
                self._abandon_threshold,
                give_up,
            )
            self._last_measurement = ret_array[i]

        return ret_array

    def success(self):
        return self._last_measurement and self._last_measurement['success']

    def failure(self):
        return self._last_measurement and self._last_measurement['failure']

    def hold(self):
        return self._last_measurement and self._last_measurement['hold']

    def break_in(self):
        return self._last_measurement is not None and self._last_measurement['break_in']

    def give_up(self) -> bool:
        """Whether continuing this seal now costs more than starting over would.

        Always answerable, and always answered, whether or not the state is
        configured to act on it -- a run with early exit disabled still records
        what this would have decided, which is what the offline calibration pass
        reads back.
        """
        return bool(
            self._last_measurement is not None and self._last_measurement['give_up']
        )


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

    - monitor resistance to detect loose seal and GΩ seal
    - set holding potential after loose seal
    - modulate pressure to improve likelihood of forming seal
    - cut pressure after GΩ and transition to cell attached

    Parameters
    ----------
    focusOnCell : bool
        Whether to focus the microscope on the target at the beginning of the seal state. Default True.
    pressureMode : str
        'auto' enables automatic pressure control during sealing;
        'user' simply switches to user control for sealing.
    startingPressure : float
        Initial pressure (Pascals) to apply when beginning sealing in 'auto' mode.
    holdingThreshold : float
        Seal resistance (ohms) above which the holding potential will switch
        from its initial value to the value specified in the *holdingPotential*
        parameter. Default 100MΩ
    holdingPotential : float
        Holding potential (volts) to apply to the pipette after the seal resistance
        becomes greater than *holdingThreshold*.
    sealThreshold : float
        Seal resistance (ohms) above which the pipette is considered sealed and
        transitions to the 'cell attached' state.  Default 1e9
    breakInThreshold : float
        Capacitance (Farads) above which the pipette is considered to be whole-cell and
        transitions to *spontaneousBreakInState* (in case of partial break-in, we don't want to
        transition directly to 'whole cell' state). Only applies while the resistance is below
        *sealThreshold* and above *breakInResistanceFloor*. Default 10pF.
    breakInResistanceFloor : float
        Seal resistance (ohms) below which spontaneous break-in is never reported, regardless of
        capacitance. A cell that has barely started sealing can show a spurious capacitance
        transient; this keeps that from being mistaken for a whole-cell rupture. Once resistance
        has crossed this floor, break-in detection stays armed for the rest of the seal attempt.
        Default 500MΩ.
    breakInMonitorTau : float
        Time constant (seconds) for exponential averaging of capacitance measurements when
        determining whether the cell has spontaneously broken in. Test pulses report NaN
        capacitance when there is no membrane transient to fit, which is counted as zero here, so
        this constant sets how long a real capacitance must persist before it is believed.
        Default 3s.
    spontaneousBreakInState : str
        Name of state to transition to when the membrane breaks in spontaneously during sealing.
        Default is 'break in' so that partial break-ins will be completed. Consider 'whole cell'
        to avoid the break-in protocol.
    failureResistanceThreshold : float
        If the resistance hangs out for too long (*failureTau*) below this value (Ωs) without growing faster than
        *failureDRDTThreshold*, the seal is considered a failure. Default 100MΩ.
    failureDRDTThreshold : float
        See *failureResistanceThreshold*. dR/dt. Default 1MΩ/s
    successMonitorTau : float
        Time constant (seconds) for exponential averaging of resistance measurements when determining whether seal
        resistance has crossed *sealThreshold*. Default 1s.
    holdMonitorTau : float
        Time constant (seconds) for exponential averaging of resistance measurements when determining whether seal
        resistance has crossed *holdingThreshold*. Default 0.1s.
    failureTau : float
        See *failureResistanceThreshold*. Default 10s.
    autoSealTimeout : float
        Maximum timeout (seconds) before the seal attempt is aborted,
        transitioning to *fallbackState*.
    pressureLimit : float
        The largest allowable vacuum pressure (pascals, expected negative value) to apply during sealing.
    delayBeforePressure : float
        Wait time (seconds) at beginning of seal state before applying negative pressure.
    delayAfterSeal : float
        Wait time (seconds) after GΩ seal is acquired, before transitioning to next state.
    afterSealPressure : float
        Pressure (Pascals) to apply during *delayAfterSeal* interval. This can help to stabilize the seal after initial
        formation.
    pressureScanInterval : float
        Interval (seconds) between pressure scans during automatic pressure control. Default 10s.
    pressureScanRadius : float
        Maximum distance (Pascals) from current pressure to scan during automatic pressure control. Default 2kPa.
    pressureScanDuration : float
        Duration (seconds) for each pressure scan during automatic pressure control. Default 5s.
    pressureScanTrust : float
        Trust factor for pressure scans. Default 0.25. Resulting pressure is a weighted average of the current pressure
        and the optimal pressure found during the scan. Should be between 0 and 1.
    """
    stateName = 'seal'

    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'fouled',
    }
    _parameterTreeConfig = {
        'focusOnCell': {'type': 'bool', 'default': True},
        'pressureMode': {'type': 'str', 'default': 'user', 'limits': ['auto', 'user']},
        'startingPressure': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},
        'holdingThreshold': {'type': 'float', 'default': 100e6, 'suffix': 'Ω'},
        'holdingPotential': {'type': 'float', 'default': -70e-3, 'suffix': 'V'},
        'sealThreshold': {'type': 'float', 'default': 1e9, 'suffix': 'Ω'},
        'breakInThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'breakInResistanceFloor': {'type': 'float', 'default': 500e6, 'suffix': 'Ω'},
        'failureResistanceThreshold': {'type': 'float', 'default': 50e6, 'suffix': 'Ω'},
        'failureDRDTThreshold': {'type': 'float', 'default': 1e6, 'suffix': 'Ω/s'},
        'autoSealTimeout': {'type': 'float', 'default': 30.0, 'suffix': 's'},
        'pressureLimit': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},
        'successMonitorTau': {'type': 'float', 'default': 1, 'suffix': 's'},
        'holdMonitorTau': {'type': 'float', 'default': 0.1, 'suffix': 's'},
        'failureTau': {'type': 'float', 'default': 10, 'suffix': 's'},
        'breakInMonitorTau': {'type': 'float', 'default': 3.0, 'suffix': 's'},
        'spontaneousBreakInState': {'type': 'str', 'default': 'break in'},
        'delayBeforePressure': {'type': 'float', 'default': 0.0, 'suffix': 's'},
        'delayAfterSeal': {'type': 'float', 'default': 5.0, 'suffix': 's'},
        'afterSealPressure': {'type': 'float', 'default': -1e3, 'suffix': 'Pa'},
        'pressureScanInterval': {'type': 'float', 'default': 10.0, 'suffix': 's'},
        'pressureScanRadius': {'type': 'float', 'default': 2 * kPa, 'suffix': 'Pa'},
        'pressureScanDuration': {'type': 'float', 'default': 5.0, 'suffix': 's'},
        'pressureScanTrust': {'type': 'float', 'default': 0.25, 'suffix': '%'},
    }

    def __init__(self, dev, config):
        super().__init__(dev, config)
        # self.config, not the argument: the base class merged the argument over the defaults.
        config = self.config
        self._analysis = SealAnalysis(
            success_tau=config['successMonitorTau'],
            success_at=config['sealThreshold'],
            hold_tau=config['holdMonitorTau'],
            hold_at=config['holdingThreshold'],
            failure_tau=config['failureTau'],
            failure_resistance_threshold=config['failureResistanceThreshold'],
            failure_dRdt_threshold=config['failureDRDTThreshold'],
            break_in_tau=config['breakInMonitorTau'],
            break_in_capacitance_threshold=config['breakInThreshold'],
            break_in_resistance_ceiling=config['sealThreshold'],
            break_in_resistance_floor=config['breakInResistanceFloor'],
        )
        self._initialized = False
        self._patchrec = dev.patchRecord()
        self.pressure = config['startingPressure']
        self._lastPressureScan = None
        self._pressures = [[], []]
        self._pressures_lock = threading.Lock()
        self._resistances = [np.zeros(0), np.zeros(0)]

    def initialize(self):
        self.dev.setTipClean(False)
        self.dev.pressureDevice.sigPressureChanged.connect(self._handlePressureChanged, Qt.Qt.DirectConnection)
        super().initialize()

    def _handlePressureChanged(self, dev, source, pressure):
        with self._pressures_lock:
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
        if config['focusOnCell']:
            dev.focusOnTarget('slow').wait()

        self._patchrec['attemptedSeal'] = True

        while True:
            check_stop()
            self.processAtLeastOneTestPulse()

            if not holdingSet and self._analysis.hold():
                self.setState(f'enable holding potential {config["holdingPotential"] * 1000:0.1f} mV')
                dev.clampDevice.setHolding(mode="VC", value=config['holdingPotential'])
                holdingSet = True

            # Checked before success and outside the pressure-mode branch: a cell that ruptured
            # on its own will never reach the seal threshold, and in 'user' mode there is no
            # timeout to fall back on, so missing this leaves suction on a whole-cell.
            if self._analysis.break_in():
                self.setState('spontaneous break-in detected during seal')
                self._patchrec['spontaneousBreakin'] = True
                self._patchrec['sealSuccessful'] = True
                return {"state": config['spontaneousBreakInState']}

            if self._analysis.success():
                break

            if config['pressureMode'] == 'auto':
                dt = ptime.time() - startTime
                if dt < config['delayBeforePressure']:
                    # delay at atmospheric pressure before starting suction
                    continue

                if self._analysis.failure() or dt > config['autoSealTimeout']:
                    self._patchrec['sealSuccessful'] = False
                    if self._analysis.failure():
                        self.setState("Resistance hung up below threshold without improving")
                    else:
                        self.setState(f"Seal took longer than `autoSealTimeout` ({dt:f}s)")
                    next_state = {"state": config["fallbackState"]}
                    if holdingSet:
                        next_state["initialVCHolding"] = None
                    return next_state

                self.updatePressure()

        # Success!
        self.setState('gigaohm seal detected')

        # delay for a short period, possibly applying pressure to allow seal to stabilize
        if config['delayAfterSeal'] > 0:
            if config['afterSealPressure'] == 0:
                dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
            else:
                dev.pressureDevice.setPressure(source='regulator', pressure=config['afterSealPressure'])
            duration = config['delayAfterSeal']
            sleep(duration)

        dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        dev.clampDevice.autoCapComp()

        self._patchrec['sealSuccessful'] = True
        return {"state": 'cell attached'}

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
        if (
            self._lastPressureScan is None
            or ptime.time() - self._lastPressureScan > self.config['pressureScanInterval']
        ):
            low = max(
                self.pressure - self.config['pressureScanRadius'], self.config['pressureLimit']
            )
            high = min(self.pressure + self.config['pressureScanRadius'], 0)
            self.dev.pressureDevice.setPressure(source='regulator', pressure=low)
            self.processAtLeastOneTestPulse()
            start = ptime.time()
            self.waitForFutureOrSuccess(
                self.dev.pressureDevice.rampPressure(
                    target=high, duration=self.config['pressureScanDuration']
                )
            )
            if self._analysis.success():
                return  # already sealed during pressure scan
            turnaround = ptime.time()
            self.waitForFutureOrSuccess(
                self.dev.pressureDevice.rampPressure(
                    target=low, duration=self.config['pressureScanDuration']
                )
            )
            end = ptime.time()
            self.processAtLeastOneTestPulse()
            if self._analysis.success():
                return  # already sealed during pressure scan
            self.pressure = self.best_pressure(start, turnaround, end)
            self.setState(f'scanned for pressure: {self.pressure / kPa:0.1f} kPa')
            self._lastPressureScan = end

        self.pressure = np.clip(self.pressure, config['pressureLimit'], 0)
        dev.pressureDevice.setPressure(source='regulator', pressure=self.pressure)

    def waitForFutureOrSuccess(self, future, timeout=20):
        """Reimplemented waitFor that also checks for success"""
        start = time.time()
        while True:
            try:
                check_stop()
            except Stopped:
                future.stop(reason="parent task stop requested")
                raise
            self.processAtLeastOneTestPulse()
            if self._analysis.success():
                future.stop(reason="seal acquired")
                break
            # wait(timeout) raises future.Timeout on the 0.1s loopbeat and re-raises
            # any error from the future; break once the future has actually finished.
            try:
                future.wait(0.1)
            except future.Timeout:
                pass
            if future.is_done:
                break
            if timeout is not None and time.time() - start > timeout:
                raise RuntimeError(f"Timed out waiting {timeout}s for {future!r}")

    def best_pressure(self, start: float, turnaround: float, end: float) -> float:
        pressures, resistances = self._trim_data_caches(start)

        resist_forward = resistances.time_slice(start, turnaround)
        resist_backward = resistances.time_slice(turnaround, end)
        if len(resist_forward) < 2 or len(resist_backward) < 2:
            self.setState('insufficient resistance data for pressure scan')
            return self.pressure
        best_forwards = find_optimal_pressure(
            pressures.time_slice(start, turnaround),
            resist_forward,
        )
        best_backwards = find_optimal_pressure(
            pressures.time_slice(turnaround, end),
            resist_backward,
        )

        best = (best_forwards + best_backwards) / 2
        best = self.config['pressureScanTrust'] * best + (1 - self.config['pressureScanTrust']) * self.pressure
        return np.clip(best, self.config['pressureLimit'], 0)

    def _trim_data_caches(self, start):
        with self._pressures_lock:
            pressures = TSeries(np.array(self._pressures[1]), time_values=np.array(self._pressures[0]))
            pressures = pressures.time_slice(start, pressures.t_end)
            self._pressures = [pressures.time_values.tolist(), pressures.data.tolist()]
        resistances = TSeries(self._resistances[1], time_values=self._resistances[0])
        resistances = resistances.time_slice(start, resistances.t_end)
        self._resistances = [resistances.time_values, resistances.data]
        return pressures, resistances

    def _cleanup(self):
        with log_and_ignore_exception(Exception, "Error during pressure state cleanup"):
            self.dev.pressureDevice.setPressure(source='atmosphere')
        with log_and_ignore_exception(Exception, "Error during pressure signal disconnect"):
            self.dev.pressureDevice.sigPressureChanged.disconnect(self._handlePressureChanged)
        super()._cleanup()
