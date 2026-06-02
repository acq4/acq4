"""Integration tests for the whole cell -> clear access -> (whole cell | fouled) state wiring.

These drive the real state ``run()`` methods against a lightweight fake device, feeding test
pulses through the state's queue and asserting on the returned next-state transition. They cover
the state machine glue; the rolling-average decision logic itself is unit tested separately.
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.whole_cell import WholeCellState
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

    def patchRecord(self):
        return self._patchrec


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


def test_whole_cell_hands_off_to_clear_access_when_access_climbs(dev):
    state = _make_state(
        WholeCellState, dev,
        accessResistanceThreshold=30e6, detectionTau=1.0, troubleState='clear access',
    )
    # A ramp of rising access resistance ending well above threshold.
    for i, ra in enumerate(np.linspace(10e6, 80e6, 30)):
        state.testPulseResults.put(_FakeTestPulse(i * 0.5, ra))
    result = state.run()
    assert result == {"state": "clear access"}


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
    # Access still high (not recovered), input resistance collapsed -> cell lost.
    state.testPulseResults.put(_FakeTestPulse(0.0, 80e6, input_resistance=20e6))
    result = state.run()
    assert result == {"state": "fouled"}
    assert dev.patchRecord()['clearAccessSuccessful'] is False
