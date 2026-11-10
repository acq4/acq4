"""Tests for break-in zaps: ordering against pressure pulses, the post-zap check, and config."""
from __future__ import annotations

import threading
import time

import pytest

from acq4.devices.PatchPipette.states.break_in import BreakInState

SEALED = {
    'steady_state_resistance': 2e9, 'access_resistance': 1e9,
    'capacitance': 1e-12, 'baseline_current': -10e-12,
}
BROKEN_IN = {
    'steady_state_resistance': 200e6, 'access_resistance': 10e6,
    'capacitance': 30e-12, 'baseline_current': -50e-12,
}


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _FakeTestPulse:
    def __init__(self, analysis):
        self.analysis = dict(analysis)


class _FakeDev:
    """Records zap / pressure events and switches the cell to broken-in on *breakOn*."""

    def __init__(self, breakOn=None):
        self.active = True
        self.sigTargetChanged = _FakeSignal()
        self.sigActiveChanged = _FakeSignal()
        self.clampDevice = self
        self.pressureDevice = self
        self.sigTestPulseFinished = _FakeSignal()
        self._patchrec = {}
        self.breakOn = breakOn
        self.brokenIn = False
        self.events = []

    def patchRecord(self):
        return self._patchrec

    def zap(self, **kwargs):
        self.events.append(('zap', time.perf_counter(), kwargs))
        if self.breakOn == 'zap':
            self.brokenIn = True

    def setPressure(self, **kwargs):
        self.events.append(('pressure', time.perf_counter(), kwargs))
        if self.breakOn == 'pressure' and kwargs.get('source') == 'regulator':
            self.brokenIn = True

    def eventNames(self):
        return [(name, kw.get('source', kw.get('duration'))) for name, _, kw in self.events]


@pytest.fixture
def dev(qapp):
    return _FakeDev()


def _run(dev, tpInterval=0.05, **config):
    config.setdefault('nPulses', [1, 1])
    config.setdefault('pulseDurations', [0.05, 0.05])
    config.setdefault('pulsePressures', [-30e3, -40e3])
    config.setdefault('pulseInterval', 0.1)
    config.setdefault('fallbackState', 'fouled')
    state = BreakInState(dev, config=config)
    done = threading.Event()

    def feed():
        while not done.is_set():
            state.testPulseResults.put(_FakeTestPulse(BROKEN_IN if dev.brokenIn else SEALED))
            time.sleep(tpInterval)

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    try:
        return state.run()
    finally:
        done.set()
        feeder.join()


def test_no_zap_durations_disables_zaps(dev):
    dev.breakOn = 'pressure'
    assert _run(dev) == {'state': 'whole cell'}
    assert not [e for e in dev.events if e[0] == 'zap']
    assert dev.patchRecord()['breakinZaps'] == 0
    assert dev.patchRecord()['spontaneousBreakin'] is False


def test_zap_break_in_skips_pressure_pulses(dev):
    dev.breakOn = 'zap'
    assert _run(dev, zapDurations=[1e-3, 1e-3], zapAmplitude=0.8) == {'state': 'whole cell'}
    assert dev.eventNames() == [('zap', 1e-3)]
    assert dev.events[0][2]['amplitude'] == 0.8
    assert dev.patchRecord()['breakinZaps'] == 1
    assert dev.patchRecord()['spontaneousBreakin'] is False


def test_one_zap_per_attempt_before_pulses_and_zero_skips(dev):
    result = _run(
        dev, nPulses=[2, 2], pulseDurations=[0.05, 0.05], pulsePressures=[-30e3, -40e3],
        zapDurations=[0, 2e-3], tpInterval=0.6)
    assert result == {'state': 'fouled'}
    assert dev.eventNames() == [
        ('pressure', 'regulator'), ('pressure', 'atmosphere'),
        ('pressure', 'regulator'), ('pressure', 'atmosphere'),
        ('zap', 2e-3),
        ('pressure', 'regulator'), ('pressure', 'atmosphere'),
        ('pressure', 'regulator'), ('pressure', 'atmosphere'),
    ]
    zapTime = dev.events[4][1]
    nextPulseTime = dev.events[5][1]
    # 3 test pulses at 0.6 s spacing (>= 1.2 s) outlast the 1 s minimum.
    assert nextPulseTime - zapTime >= 1.15
    assert dev.patchRecord()['breakinZaps'] == 1


def test_post_zap_check_lasts_at_least_one_second(dev):
    _run(dev, nPulses=[1], pulseDurations=[0.05], pulsePressures=[-30e3], zapDurations=[1e-3])
    zapTime = dev.events[0][1]
    nextPulseTime = dev.events[1][1]
    assert dev.eventNames()[:2] == [('zap', 1e-3), ('pressure', 'regulator')]
    assert nextPulseTime - zapTime >= 1.0


def test_mismatched_list_lengths_raise(dev):
    with pytest.raises(ValueError, match='same length'):
        _run(dev, zapDurations=[1e-3])
    assert dev.events == []
