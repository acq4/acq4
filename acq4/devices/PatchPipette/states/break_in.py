from __future__ import annotations

import time

from gentletask import check_stop

from acq4.util import ptime
from acq4.util.debug import log_and_ignore_exception
from acq4.util.task import sleep
from pyqtgraph import units
from ._base import PatchPipetteState


class BreakInSuccessful(Exception):
    pass

class BreakInFailed(Exception):
    pass

class ResistanceThresholdReached(Exception):
    """Raised when steady-state resistance drops below ``resistanceThreshold``.

    Signals that break-in pulses should pause so access resistance can be confirmed;
    it does not by itself end the state.
    """
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
        Steady-state resistance (Ohms) below which break-in pulses are paused so access
        resistance can be confirmed. This alone does not complete break-in; access
        resistance must also drop below ``accessResistanceThreshold``.
    accessResistanceThreshold : float
        Access resistance (Ohms) below which (averaged over ``accessAverageDuration``, and
        only while ``resistanceThreshold`` is also met) break-in is considered successful and
        the state transitions to 'whole cell'. If access resistance stays above this, break-in
        pulses resume.
    accessAverageDuration : float
        Duration (seconds) over which to average access and steady-state resistance when
        confirming break-in after ``resistanceThreshold`` is tripped.
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
        'accessResistanceThreshold': {'type': 'float', 'default': 20e6, 'suffix': 'Ω'},
        'accessAverageDuration': {'type': 'float', 'default': 3, 'suffix': 's'},
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
                try:
                    self.checkBreakIn()
                    nPulses = config['nPulses'][attempt]
                    pdur = config['pulseDurations'][attempt]
                    press = config['pulsePressures'][attempt]
                    self.setState('Break in attempt %d' % attempt)
                    self.attemptBreakIn(nPulses, pdur, press)
                except ResistanceThresholdReached:
                    # Steady-state resistance dropped below threshold: pulses are already
                    # paused (attemptBreakIn restores atmosphere on the way out). Confirm the
                    # break-in by averaging access resistance before either succeeding or
                    # resuming pulses.
                    if self.confirmBreakIn():
                        raise BreakInSuccessful()
                    self.setState('resistance below threshold but access resistance too high; resuming break in')
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
            self.setState(str(exc))
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

        Raises BreakInFailed if the cell is lost, or ResistanceThresholdReached when the
        steady-state resistance drops below ``resistanceThreshold`` (signalling that pulses
        should pause so access resistance can be confirmed).
        Returns None if the break in is still ongoing.
        """
        start = ptime.time()
        while True:
            check_stop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
            if ptime.time() - start > 10:
                raise BreakInFailed('No test pulse received for 10 seconds during break-in attempt.')
        tp = tps[-1]

        analysis = tp.analysis
        self._checkHoldingCurrent(analysis)

        if self.config['resistanceThreshold'] is not None and analysis['steady_state_resistance'] < self.config['resistanceThreshold']:
            raise ResistanceThresholdReached()

    def _checkHoldingCurrent(self, analysis):
        """Raise BreakInFailed if the holding current indicates the cell has been lost."""
        holding = analysis['baseline_current']
        if holding < self.config['holdingCurrentThreshold']:
            raise BreakInFailed(f'Holding current {holding * 1e9:.1f}nA exceeded `holdingCurrentThreshold`.')

    def confirmBreakIn(self):
        """Average access and steady-state resistance over ``accessAverageDuration``.

        Called with pulses paused after ``resistanceThreshold`` is tripped. Returns True only
        if *both* thresholds are met on the averaged values: mean access resistance below
        ``accessResistanceThreshold`` and mean steady-state resistance below
        ``resistanceThreshold``. Otherwise returns False so break-in pulses resume.

        Raises BreakInFailed if the cell is lost (holding current) during the averaging window.
        """
        self.setState('resistance below threshold; measuring access resistance')
        start = ptime.time()
        accessValues = []
        resistanceValues = []
        while ptime.time() - start < self.config['accessAverageDuration']:
            check_stop()
            for tp in self.getTestPulses(timeout=0.2):
                analysis = tp.analysis
                self._checkHoldingCurrent(analysis)
                accessValues.append(analysis['access_resistance'])
                resistanceValues.append(analysis['steady_state_resistance'])

        if len(accessValues) == 0:
            return False

        meanAccess = sum(accessValues) / len(accessValues)
        meanResistance = sum(resistanceValues) / len(resistanceValues)
        accessOk = meanAccess < self.config['accessResistanceThreshold']
        resistanceOk = (self.config['resistanceThreshold'] is None
                        or meanResistance < self.config['resistanceThreshold'])
        return accessOk and resistanceOk

    def _cleanup(self):
        with log_and_ignore_exception(Exception, "Error resetting pressure after clean"):
            self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        super()._cleanup()
