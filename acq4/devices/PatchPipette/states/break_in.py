from __future__ import annotations

import time

from acq4.util import ptime
from acq4.util.debug import printExc
from pyqtgraph import units
from ._base import PatchPipetteState


class BreakInState(PatchPipetteState):
    """State using pressure pulses to rupture membrane for whole cell recording.

    State name: "break in"

    - applies a sequence of pressure pulses of increasing strength
    - monitors for break-in

    Parameters
    ----------
    nPulses : list of int
        Number of pressure pulses to apply on each break-in attempt
    pulseDurations : list of float
        Duration (seconds) of pulses to apply on each break in attempt
    pulsePressures : list of float
        Pressure (Pascals) of pulses to apply on each break in attempt
    pulseInterval : float
        Delay (seconds) between break in attempts
    capacitanceThreshold : float
        Capacitance (Farads) above which to transition to the 'whole cell' state
        (note that resistance threshold must also be met)
    resistanceThreshold : float
        Resistance (Ohms) below which to transition to the 'whole cell' state if
        capacitance threshold is met, or fail otherwise.
    holdingCurrentThreshold : float
        Holding current (Amps) below which the cell is considered to be lost and the state fails.
    """
    stateName = 'break in'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': -70e-3,
        'initialTestPulseEnable': True,
        'fallbackState': 'fouled',
    }
    _parameterTreeConfig = {
        # idea!
        # 'pulses', 'type': 'table', 'columns': [
        #     'nPulses', 'type': 'int'},
        #     'duration', 'type': 'float', 'suffix': 's'},
        #     'pressure', 'type': 'float', 'suffix': 'Pa'},
        # ]},
        'nPulses': {'type': 'str', 'default': "[1, 1, 1, 1, 1, 2, 2, 3, 3, 5]"},
        'pulseDurations': {'type': 'str', 'default': "[0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.7, 1.5]"},
        'pulsePressures': {'type': 'str', 'default': "[-30e3, -35e3, -40e3, -50e3, -60e3, -60e3, -60e3, -60e3, -60e3, -60e3]"},
        'pulseInterval': {'type': 'float', 'default': 2},
        'resistanceThreshold': {'type': 'float', 'default': 650e6, 'suffix': 'Ω'},
        'capacitanceThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'holdingCurrentThreshold': {'type': 'float', 'default': -1e-9, 'suffix': 'A'},
    }

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
        lastPulse = ptime.time()
        attempt = 0

        while True:
            status = self.checkBreakIn()
            if status is True:
                patchrec['spontaneousBreakin'] = True
                patchrec['breakinSuccessful'] = True
                return 'whole cell'
            elif status is False:
                return

            if ptime.time() - lastPulse > config['pulseInterval']:
                nPulses = config['nPulses'][attempt]
                pdur = config['pulseDurations'][attempt]
                press = config['pulsePressures'][attempt]
                self.setState('Break in attempt %d' % attempt)
                status = self.attemptBreakIn(nPulses, pdur, press)
                patchrec['attemptedBreakin'] = True
                if status is True:
                    patchrec['breakinSuccessful'] = True
                    patchrec['spontaneousBreakin'] = False
                    return 'whole cell'
                elif status is False:
                    patchrec['breakinSuccessful'] = False
                    return config['fallbackState']
                lastPulse = ptime.time()
                attempt += 1

            if attempt >= len(config['nPulses']):
                self._taskDone(interrupted=True, error='Breakin failed after %d attempts' % attempt)
                patchrec['breakinSuccessful'] = False
                return config['fallbackState']

    def attemptBreakIn(self, nPulses, duration, pressure):
        for _ in range(nPulses):
            # get the next test pulse
            status = self.checkBreakIn()
            if status is not None:
                return status
            self.dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            time.sleep(duration)
            self.dev.pressureDevice.setPressure(source='atmosphere')

    def checkBreakIn(self):
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
        tp = tps[-1]

        analysis = tp.analysis
        holding = analysis['baseline_current']
        if holding < self.config['holdingCurrentThreshold']:
            self._taskDone(interrupted=True, error='Holding current exceeded threshold.')
            return False

        # If ssr and cap cross threshold => successful break in
        # If only ssr crosses threshold => lost cell
        # If only cap crosses threshold => partial break in, keep trying
        ssr = analysis['steady_state_resistance']
        cap = analysis['capacitance']
        if self.config['resistanceThreshold'] is not None and ssr < self.config['resistanceThreshold']:
            return True
            # if cap > self.config['capacitanceThreshold']:
            #     return True
            # else:
            #     self._taskDone(interrupted=True, error="Resistance dropped below threshold but no cell detected.")
            #     return False

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after clean")
        return super().cleanup()
