from __future__ import annotations

import math

from gentletask import check_stop

from acq4.util import ptime
from acq4.util.debug import log_and_ignore_exception
from ._base import PULSE_ATTEMPT_COLUMNS, PatchPipetteState


class BreakInFailed(Exception):
    pass


class BreakInState(PatchPipetteState):
    """State using pressure pulses to rupture membrane for whole cell recording.

    State name: "break in"

    - applies a sequence of pressure pulses of increasing strength
    - optionally zaps once at the start of each attempt, before its pressure pulses
    - monitors for break-in

    A test pulse passes when it meets all of ``resistanceThreshold``,
    ``accessResistanceThreshold`` and ``capacitanceThreshold``. A single passing test pulse
    ends the current pressure pulse; ``breakInConfirmCount`` consecutive passing test pulses
    complete break-in and transition to 'whole cell'.

    Parameters
    ----------
    pulses : list of (nPulses, duration, pressure, zapDuration) tuples
        One row per break-in attempt: the number of pressure pulses, their duration (seconds)
        and pressure (Pascals), and the duration (seconds) of the zap applied at the start of
        the attempt (0 skips the zap). After a zap, break-in is checked for at least 1 s and
        3 test pulses before the pressure pulses begin. The deprecated parallel lists
        ``nPulses``, ``pulseDurations``, ``pulsePressures`` and ``zapDurations`` are still
        accepted in patch profiles.
    zapAmplitude : float
        Amplitude (Volts) of each zap, relative to the holding potential (default 1 V).
    pulseInterval : float
        Delay (seconds) between break in attempts
    resistanceThreshold : float
        Steady-state resistance (Ohms) below which a test pulse passes
    accessResistanceThreshold : float
        Access resistance (Ohms) below which a test pulse passes
    capacitanceThreshold : float
        Capacitance (Farads) above which a test pulse passes. NaN capacitance counts as 0.
    breakInConfirmCount : int
        Number of consecutive passing test pulses required to complete break-in
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
        'pulses': {
            'type': 'table',
            'columns': PULSE_ATTEMPT_COLUMNS + [
                {'name': 'zapDuration', 'type': 'float', 'suffix': 's', 'siPrefix': True, 'limits': (0, None)},
            ],
            'default': [
                (1, 0.2, -30e3, 0), (1, 0.2, -35e3, 0), (1, 0.2, -40e3, 0), (1, 0.2, -50e3, 0),
                (1, 0.2, -60e3, 0), (2, 0.2, -60e3, 0), (2, 0.3, -60e3, 0), (3, 0.5, -60e3, 0),
                (3, 0.7, -60e3, 0), (5, 1.5, -60e3, 0),
            ],
        },
        'zapAmplitude': {'type': 'float', 'default': 1.0, 'suffix': 'V'},
        'pulseInterval': {'type': 'float', 'default': 2, 'suffix': 's'},
        'resistanceThreshold': {'type': 'float', 'default': 650e6, 'suffix': 'Ω'},
        'accessResistanceThreshold': {'type': 'float', 'default': 20e6, 'suffix': 'Ω'},
        'capacitanceThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'breakInConfirmCount': {'type': 'int', 'default': 2},
        'holdingCurrentThreshold': {'type': 'float', 'default': -1e-9, 'suffix': 'A'},
    }

    def run(self):
        patchrec = self.dev.patchRecord()
        self.monitorTestPulse()
        patchrec['attemptedBreakin'] = True
        patchrec['breakinSuccessful'] = False
        self._pulsesApplied = 0
        self._zapsApplied = 0

        try:
            self._breakIn()
        except BreakInFailed as exc:
            self.setState(str(exc))
            return {"state": self.config['fallbackState']}
        finally:
            patchrec['breakinZaps'] = self._zapsApplied

        patchrec['breakinSuccessful'] = True
        patchrec['spontaneousBreakin'] = self._pulsesApplied == 0 and self._zapsApplied == 0
        return {"state": 'whole cell'}

    @classmethod
    def upgradeConfig(cls, config, profile):
        config = super().upgradeConfig(config, profile)
        return cls._mergeLegacyLists(
            config, profile, 'pulses', ('nPulses', 'pulseDurations', 'pulsePressures', 'zapDurations'),
            zeroFill=('zapDurations',))

    def _breakIn(self):
        """Apply zaps and pressure pulses until break-in is confirmed.

        Raises BreakInFailed if the cell is lost or all attempts are used up.
        """
        config = self.config
        attempts = config['pulses']
        self._lastTestPulseTime = ptime.time()
        self._testPulseCount = 0
        passCount = 0
        lastPulseEnd = ptime.time()
        for attempt, (nPulses, duration, pressure, zapDuration) in enumerate(attempts):
            self.setState('Break in attempt %d' % attempt)
            for i in range(nPulses):
                interval = config['pulseInterval'] if i == 0 else 0.1
                if self._waitForBreakIn(lastPulseEnd + interval, passCount):
                    return
                if i == 0 and zapDuration > 0:
                    self.dev.clampDevice.zap(duration=zapDuration, amplitude=config['zapAmplitude'])
                    self._zapsApplied += 1
                    if self._waitForBreakIn(ptime.time() + 1.0, 0, minTestPulses=3):
                        return
                passCount = self.applyPulse(duration, pressure)
                lastPulseEnd = ptime.time()
                self._pulsesApplied += 1

        if self._waitForBreakIn(lastPulseEnd + config['pulseInterval'], passCount):
            return
        raise BreakInFailed(f'Breakin attempted {len(attempts)} times without success')

    def applyPulse(self, duration, pressure):
        """Apply one pressure pulse, then return to atmosphere.

        Ends the pulse early when a test pulse passes the break-in thresholds. Returns the
        number of consecutive passing test pulses at the end of the pulse (0 if it ran its
        full duration). Raises BreakInFailed if the cell is lost.
        """
        passCount = 0
        self.dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
        stop = ptime.time() + duration
        try:
            while (remaining := stop - ptime.time()) > 0:
                passCount = self._readTestPulses(min(0.2, remaining), passCount)
                if passCount > 0:
                    break
        finally:
            self.dev.pressureDevice.setPressure(source='atmosphere')
        return passCount

    def _waitForBreakIn(self, until, passCount, minTestPulses=0):
        """Process test pulses until time *until* and at least *minTestPulses* test pulses have
        arrived, and past that while a passing run is unresolved.

        *passCount* is the number of consecutive passing test pulses already seen.
        Returns True once ``breakInConfirmCount`` consecutive test pulses pass, or False
        once the wait is over with no passing run in progress.
        """
        startCount = self._testPulseCount
        confirming = False
        while True:
            if passCount >= self.config['breakInConfirmCount']:
                return True
            if passCount > 0 and not confirming:
                self.setState('test pulse passed break-in thresholds; confirming')
                confirming = True
            elif passCount == 0 and confirming:
                self.setState('break in not confirmed; resuming')
                confirming = False
            remaining = until - ptime.time()
            if remaining <= 0 and passCount == 0 and self._testPulseCount - startCount >= minTestPulses:
                return False
            passCount = self._readTestPulses(min(0.2, remaining) if remaining > 0 else 0.2, passCount)

    def _readTestPulses(self, timeout, passCount):
        """Process test pulses arriving within *timeout* (s).

        Returns *passCount* (consecutive passing test pulses so far) updated with the new
        test pulses. Also checks for stop requests. Raises BreakInFailed if the cell is lost
        or no test pulse has arrived for 10 s.
        """
        check_stop()
        tps = self.getTestPulses(timeout=timeout)
        now = ptime.time()
        self._testPulseCount += len(tps)
        if len(tps) > 0:
            self._lastTestPulseTime = now
        elif now - self._lastTestPulseTime > 10:
            raise BreakInFailed('No test pulse received for 10 seconds during break-in attempt.')
        for tp in tps:
            self._checkHoldingCurrent(tp.analysis)
            passCount = passCount + 1 if self._passesThresholds(tp.analysis) else 0
        return passCount

    def _passesThresholds(self, analysis):
        """Return True if a test pulse analysis meets all break-in thresholds."""
        cap = analysis['capacitance']
        if math.isnan(cap):
            cap = 0.0
        config = self.config
        return (
            analysis['steady_state_resistance'] < config['resistanceThreshold']
            and analysis['access_resistance'] < config['accessResistanceThreshold']
            and cap > config['capacitanceThreshold']
        )

    def _checkHoldingCurrent(self, analysis):
        """Raise BreakInFailed if the holding current indicates the cell has been lost."""
        holding = analysis['baseline_current']
        if holding < self.config['holdingCurrentThreshold']:
            raise BreakInFailed(f'Holding current {holding * 1e9:.1f}nA exceeded `holdingCurrentThreshold`.')

    def _cleanup(self):
        with log_and_ignore_exception(Exception, "Error resetting pressure after clean"):
            self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        super()._cleanup()
