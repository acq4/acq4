"""Integration tests for the whole cell warning and clear access -> (whole cell | fouled) wiring.

These drive the real state logic against a lightweight fake device, feeding test pulses through the
state's queue and asserting on the resulting warning or next-state transition. They cover the state
machine glue; the rolling-average decision logic itself is unit tested separately.
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.whole_cell import WholeCellAnalysis, WholeCellState
from acq4.devices.PatchPipette.states.clear_access import ClearAccessState


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _FakeClamp:
    def __init__(self):
        self.sigTestPulseFinished = _FakeSignal()
        self.zaps = []

    def zap(self, **kwargs):
        self.zaps.append(kwargs)


class _FakePressure:
    def __init__(self):
        self.calls = []

    def setPressure(self, **kwargs):
        self.calls.append(kwargs)


class _FakePipette:
    def globalPosition(self):
        return (0.0, 0.0, 0.0)


class _FakeDev:
    def __init__(self):
        self.active = True
        self.sigTargetChanged = _FakeSignal()
        self.clampDevice = _FakeClamp()
        self.pressureDevice = _FakePressure()
        self.pipetteDevice = _FakePipette()
        self._patchrec = {}
        self.accessWarnings = []

    def patchRecord(self):
        return self._patchrec

    def setAccessWarning(self, active, message=""):
        self.accessWarnings.append((bool(active), message))


class _FakeTestPulse:
    def __init__(self, start_time, access_resistance, input_resistance=300e6):
        self.recording = type("rec", (), {"start_time": start_time})()
        self.analysis = {
            "access_resistance": access_resistance,
            "input_resistance": input_resistance,
        }


def _make_state(cls, dev, **config):
    # Skip the base initializePressure/initializeClamp (hardware) and drive run() directly.
    return cls(dev, config=config)


@pytest.fixture
def dev(qapp):
    # qapp ensures a QApplication exists for the QObject-based Future base class.
    return _FakeDev()


def _wholeCellMonitor(dev, **config):
    """Build a WholeCellState wired with its analysis the way run() does, ready for
    updateAccessWarning() without entering the infinite hold loop."""
    config.setdefault('accessResistanceThreshold', 30e6)
    config.setdefault('detectionTau', 1.0)
    config.setdefault('maxTestPulseGap', 5.0)
    state = _make_state(WholeCellState, dev, **config)
    state._analysis = WholeCellAnalysis(
        access_resistance_threshold=config['accessResistanceThreshold'],
        detection_tau=config['detectionTau'],
        max_test_pulse_gap=config['maxTestPulseGap'],
    )
    state._warningActive = False
    return state


def test_whole_cell_warns_but_does_not_switch_when_access_climbs(dev):
    state = _wholeCellMonitor(dev)
    # A ramp of rising access resistance ending well above threshold.
    tps = [_FakeTestPulse(i * 0.5, ra) for i, ra in enumerate(np.linspace(10e6, 80e6, 30))]
    result = state.updateAccessWarning(tps)
    # Whole cell stays put (no state transition) and raises a warning instead.
    assert result is None
    assert state._warningActive
    active, message = dev.accessWarnings[-1]
    assert active is True
    assert "clear access" in message


def test_whole_cell_warning_clears_when_access_recovers(dev):
    state = _wholeCellMonitor(dev)
    # Climb past threshold -> warn.
    state.updateAccessWarning([_FakeTestPulse(i * 0.5, ra) for i, ra in enumerate(np.linspace(10e6, 80e6, 30))])
    assert dev.accessWarnings[-1][0] is True
    assert state._warningActive
    # Then Ra falls back down -> the warning clears on its own.
    state.updateAccessWarning([_FakeTestPulse(15.0 + i * 0.5, 10e6) for i in range(30)])
    assert dev.accessWarnings[-1][0] is False
    assert not state._warningActive


def test_clear_access_returns_to_whole_cell_on_recovery(dev):
    state = _make_state(
        ClearAccessState, dev,
        accessRecoveredThreshold=25e6, detectionTau=1.0,
    )
    # Access already back down, input resistance healthy -> immediate success.
    state.testPulseResults.put(_FakeTestPulse(0.0, 10e6, input_resistance=300e6))
    result = state.run()
    assert result == {"state": "whole cell"}
    assert dev.patchRecord()['clearAccessSuccessful'] is True


def test_clear_access_fouls_when_cell_is_lost(dev):
    state = _make_state(
        ClearAccessState, dev,
        accessRecoveredThreshold=25e6, inputResistanceLossThreshold=50e6,
        detectionTau=1.0, repairTau=10.0, fallbackState='fouled',
    )
    # Access still high (not recovered) while input resistance collapses and stays down past one
    # repair tau -> cell lost. A single low reading is intentionally not enough (see analysis tests).
    for i in range(30):  # 15s of data at 0.5s spacing, well past the 10s repair tau
        state.testPulseResults.put(_FakeTestPulse(i * 0.5, 80e6, input_resistance=20e6))
    result = state.run()
    assert result == {"state": "fouled"}
    assert dev.patchRecord()['clearAccessSuccessful'] is False
