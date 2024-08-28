from __future__ import annotations

import numpy as np

from acq4.util import ptime
from pyqtgraph import units
from ._base import PatchPipetteState, SteadyStateAnalysisBase


class SealAnalysis(SteadyStateAnalysisBase):
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
            else:
                dt = t - self._last_measurement['time']
                resistance_avg = self.exponential_decay_avg(
                    dt, self._last_measurement['resistance_avg'], resistance, self._tau)
            success = resistance_avg > self._success_at
            hold = resistance_avg > self._hold_at
            ret_array[i] = (
                t,
                resistance,
                resistance_avg,
                resistance / resistance_avg,
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
        The largest vacuum pressure (pascals, expected negative value) to apply during sealing.
        When this pressure is reached, the pressure is reset to 0 and the ramp starts over after a delay.
    pressureChangeByRatio : list
        A list of (ssr_ratio_threshold, pressure_change) tuples that determine how much to change the current
        seal pressure based on the rate of change in seal resistance. For each iteration, the rate of change will
        be selected as the one associated with the lowest ssr_ratio_threshold that is less than the current
        ratio. Default is [(1, -100), (1.05, 0), (float('inf'), 200)] ("increase suction if we're losing
        resistance, no change if resistance is growing slowly, decrease it otherwise").
    delayBeforePressure : float
        Wait time (seconds) at beginning of seal state before applying negative pressure.
    delayAfterSeal : float
        Wait time (seconds) after GOhm seal is acquired, before transitioning to next state.
    afterSealPressure : float
        Pressure (Pascals) to apply during *delayAfterSeal* interval. This can help to stabilize the seal after initial
        formation.
    resetDelay : float
        Wait time (seconds) after pressureLimit is reached, before restarting pressure ramp.
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
        'pressureChangeByRatio': {'type': 'str', 'default': "[(1, -100), (1.05, 0), (float('inf'), 200)]"},
        'delayBeforePressure': {'type': 'float', 'default': 0.0, 'suffix': 's'},
        'delayAfterSeal': {'type': 'float', 'default': 5.0, 'suffix': 's'},
        'afterSealPressure': {'type': 'float', 'default': -1000, 'suffix': 'Pa'},
        'resetDelay': {'type': 'float', 'default': 5.0, 'suffix': 's'},
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
        if isinstance(config['pressureChangeByRatio'], str):
            config['pressureChangeByRatio'] = eval(config['pressureChangeByRatio'], units.__dict__)
        # sort pressure change rates by resistance slope thresholds
        self._pressureChangeByRatio = sorted(config['pressureChangeByRatio'], key=lambda x: x[0])

    def initialize(self):
        self.dev.setTipClean(False)
        super().initialize()

    def processAtLeastOneTestPulse(self):
        tps = super().processAtLeastOneTestPulse()
        self._analysis.process_test_pulses(tps)

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
        self.pressure = np.clip(self.pressure, config['pressureLimit'], 0)

        if self.pressure <= config['pressureLimit']:
            # if the pressureLimit has been achieved, cycle back to starting pressure and redo the
            # pressure change process.
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
            self.sleep(config['resetDelay'])
            self.pressure = config['startingPressure']
        else:
            # decide how much to adjust pressure based on rate of change in seal resistance
            ratio = self._analysis.resistance_ratio()
            for max_ratio, change in self._pressureChangeByRatio:
                if max_ratio is None or ratio < max_ratio:
                    self.pressure += change
                    break

        dev.pressureDevice.setPressure(source='regulator', pressure=self.pressure)

    def cleanup(self):
        self.dev.pressureDevice.setPressure(source='atmosphere')
        super().cleanup()
