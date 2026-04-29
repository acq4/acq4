from __future__ import annotations

from acq4.util import ptime
from acq4.util.future import sleep
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
        'pulseInterval': {'type': 'float', 'default': 2, 'suffix': 's'},
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

        patchrec['attemptedBreakin'] = True
        patchrec['breakinSuccessful'] = False

        try:
            while True:
                time_until_next = (lastPulse + config['pulseInterval']) - ptime.time()
                if time_until_next > 0:
                    sleep(time_until_next)
                self.checkBreakIn()
                nPulses = config['nPulses'][attempt]
                pdur = config['pulseDurations'][attempt]
                press = config['pulsePressures'][attempt]
                self.set_state('Break in attempt %d' % attempt)
                self.attemptBreakIn(nPulses, pdur, press)
                attempt += 1
                lastPulse = ptime.time()

                if attempt >= len(config['nPulses']):
                    raise BreakInFailed(f'Breakin attempted {attempt} times without success')
        except BreakInSuccessful:
            patchrec['breakinSuccessful'] = True
            patchrec['spontaneousBreakin'] = attempt == 0
            return {"state": 'whole cell'}
        except BreakInFailed as exc:
            patchrec['breakinSuccessful'] = False
            self.set_state(str(exc))
            return {"state": self.config['fallbackState']}

    def attemptBreakIn(self, nPulses, duration, pressure):
        for i in range(nPulses):
            # get the next test pulse
            self.dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            start = ptime.time()
            stop = start + duration
            try:
                # while pulse is active, monitor for break-in or stop request
                while True:
                    remaining = stop - ptime.time()
                    if remaining > 0.2:
                        self.checkBreakIn()
                    elif remaining > 0:
                        sleep(remaining)
                    else:
                        break
            finally:
                self.dev.pressureDevice.setPressure(source='atmosphere')
            if i < nPulses - 1:
                sleep(0.1)  # short delay between pulses
            self.checkBreakIn()

    def checkBreakIn(self):
        """Check the status of the break-in attempt based on the latest test pulse.
        Also checks for stop requests.

        Raises BreakInSuccessful or BreakInFailed as appropriate.
        Returns None if the break in is still ongoing.
        """
        start = ptime.time()
        while True:
            self.check_stop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
            if ptime.time() - start > 10:
                raise BreakInFailed('No test pulse received for 10 seconds during break-in attempt.')
        tp = tps[-1]

        analysis = tp.analysis
        holding = analysis['baseline_current']
        if holding < self.config['holdingCurrentThreshold']:
            raise BreakInFailed(f'Holding current {holding * 1e9:.1f}nA exceeded `holdingCurrentThreshold`.')

        if self.config['resistanceThreshold'] is not None and analysis['steady_state_resistance'] < self.config['resistanceThreshold']:
            raise BreakInSuccessful()

    def _cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            dev.logger.exception("Error resetting pressure after clean")
        return super()._cleanup()
