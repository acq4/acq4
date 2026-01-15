from __future__ import annotations

import time

from acq4.util import ptime
from acq4.util.debug import printExc
from pyqtgraph import units
from ._base import PatchPipetteState


class BreakInSuccessful(Exception):
    pass

class BreakInFailed(Exception):
    pass


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

        try:
            while True:
                time_until_next = (lastPulse + config['pulseInterval']) - ptime.time()
                if time_until_next > 0:
                    self.sleep(time_until_next)
                nPulses = config['nPulses'][attempt]
                pdur = config['pulseDurations'][attempt]
                press = config['pulsePressures'][attempt]
                self.setState('Break in attempt %d' % attempt)
                self.attemptBreakIn(nPulses, pdur, press)
                attempt += 1
                patchrec['attemptedBreakin'] = True
                lastPulse = ptime.time()

                if attempt >= len(config['nPulses']):
                    raise BreakInFailed(f'Breakin failed after {attempt} attempts')
        except BreakInSuccessful:
            patchrec['breakinSuccessful'] = True
            patchrec['spontaneousBreakin'] = attempt == 0
            return 'whole cell'
        except BreakInFailed as exc:
            patchrec['breakinSuccessful'] = False
            self._taskDone(interrupted=True, error=exc.args[0])
            return config['fallbackState']
        except Exception as exc:
            patchrec['breakinSuccessful'] = False
            self._taskDone(interrupted=True, error=str(exc))
            return config['fallbackState']

    def attemptBreakIn(self, nPulses, duration, pressure):
        start = ptime.time()
        stop = start + duration
        for i in range(nPulses):
            # get the next test pulse
            self.dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            try:
                # while pulse is active, monitor for break-in or stop request
                while True:
                    remaining = stop - ptime.time()
                    if remaining > 0.2:
                        self.checkBreakIn()
                    elif remaining > 0:
                        time.sleep(remaining)
                    else:
                        break
            finally:
                self.dev.pressureDevice.setPressure(source='atmosphere')
            if i < nPulses - 1:
                time.sleep(0.1)  # short delay between pulses
            self.checkBreakIn()

    def checkBreakIn(self):
        """Check the status of the break-in attempt based on the latest test pulse.
        Also checks for stop requests.

        Raises BreakInSuccessful or BreakInFailed as appropriate.
        Returns None if the break in is still ongoing.
        """
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
        tp = tps[-1]

        analysis = tp.analysis
        holding = analysis['baseline_current']
        if holding < self.config['holdingCurrentThreshold']:
            raise BreakInFailed(f'Holding current {holding * 1e9:.1f}nA exceeded `holdingCurrentThreshold`.')

        if self.config['resistanceThreshold'] is not None and analysis['steady_state_resistance'] < self.config['resistanceThreshold']:
            raise BreakInSuccessful()

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after clean")
        return super().cleanup()
