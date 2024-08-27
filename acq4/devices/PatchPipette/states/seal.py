from __future__ import annotations

from collections import deque

import numpy as np
import scipy.stats
import time
import warnings

from acq4.util import ptime
from pyqtgraph import units
from ._base import PatchPipetteState


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
        'nSlopeSamples': {'type': 'int', 'default': 5},
        'autoSealTimeout': {'type': 'float', 'default': 30.0, 'suffix': 's'},
        'pressureLimit': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},
        'pressureChangeRates': {'type': 'str', 'default': "[(-1e6, 200), (0.5e6, -100), (0, 0)]"},  # TODO
        'delayBeforePressure': {'type': 'float', 'default': 0.0, 'suffix': 's'},
        'delayAfterSeal': {'type': 'float', 'default': 5.0, 'suffix': 's'},
        'afterSealPressure': {'type': 'float', 'default': -1000, 'suffix': 'Pa'},
        'resetDelay': {'type': 'float', 'default': 5.0, 'suffix': 's'},
    }

    def __init__(self, dev, config):
        super().__init__(dev, config)
        self._recentTestPulses = deque(maxlen=config['nSlopeSamples'])
        self._initialTP = None
        self._patchrec = dev.patchRecord()
        self.sealSuccessful = False
        self.readyToHold = False
        self.pressure = config['startingPressure']
        if isinstance(config['pressureChangeRates'], str):
            config['pressureChangeRates'] = eval(config['pressureChangeRates'], units.__dict__)
        # sort pressure change rates by resistance slope thresholds
        self._pressureChangeRates = sorted(config['pressureChangeRates'], key=lambda x: x[0])

    def initialize(self):
        self.dev.setTipClean(False)
        super().initialize()

    def processAtLeastOneTestPulse(self):
        tps = super().processAtLeastOneTestPulse()
        self._recentTestPulses.extend(tps)

        tp = self._initialTP = tps[-1]
        ssr = tp.analysis['steady_state_resistance']
        cap = tp.analysis['capacitance']
        if self._initialTP is None:
            initialResistance = ssr
            self._patchrec['resistanceBeforeSeal'] = initialResistance
            self._patchrec['capacitanceBeforeSeal'] = cap
            self._initialTP = tp
        self._patchrec['resistanceBeforeBreakin'] = ssr
        self._patchrec['capacitanceBeforeBreakin'] = cap
        self.sealSuccessful = ssr > self.config['sealThreshold']
        self.readyToHold = ssr > self.config['holdingThreshold']
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

        while not self.sealSuccessful:
            self.checkStop()
            self.processAtLeastOneTestPulse()

            if self.readyToHold and not holdingSet:
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
        else:
            raise ValueError(f"pressureMode must be 'auto' or 'user' (got '{mode}')")

    def resistanceSlope(self):
        res = np.array([tp.analysis['steady_state_resistance'] for tp in self._recentTestPulses])
        times = np.array([tp.start_time for tp in self._recentTestPulses])
        return scipy.stats.linregress(times, res).slope

    def updatePressure(self):
        config = self.config
        dev = self.dev
        self.pressure = np.clip(self.pressure, config['pressureLimit'], 0)

        # decide how much to adjust pressure based on rate of change in seal resistance
        slope = self.resistanceSlope()
        for max_slope, change in self._pressureChangeRates:
            if max_slope is None or slope < max_slope:
                self.pressure += change
                break

        # here, if the pressureLimit has been achieved and we are still sealing, cycle back to starting
        # pressure and redo the pressure change
        if self.pressure <= config['pressureLimit']:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
            self.sleep(config['resetDelay'])
            self.pressure = config['startingPressure']

        dev.pressureDevice.setPressure(source='regulator', pressure=self.pressure)

    def cleanup(self):
        self.dev.pressureDevice.setPressure(source='atmosphere')
        super().cleanup()
