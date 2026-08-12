"""Integration tests for the seal -> 'break in' wiring on spontaneous break-in.

A cell can rupture into whole-cell while the seal state is still applying suction. Without this
wiring the seal state keeps sucking on an established whole-cell until its timeout and then
reports the attempt as fouled. These drive the real state logic against a lightweight fake device;
the detection rule itself is unit tested in test_seal_analysis.py.
"""
from __future__ import annotations

from queue import Queue

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.seal import SealState


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
        self.holdings = []
        self.capCompCount = 0

    def setHolding(self, **kwargs):
        self.holdings.append(kwargs)

    def autoCapComp(self):
        self.capCompCount += 1


class _FakePressure:
    def __init__(self):
        self.sigPressureChanged = _FakeSignal()
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
        self.sigActiveChanged = _FakeSignal()
        self.clampDevice = _FakeClamp()
        self.pressureDevice = _FakePressure()
        self.pipetteDevice = _FakePipette()
        self._patchrec = {}

    def patchRecord(self):
        return self._patchrec

    def setTipClean(self, clean):
        pass


class _FakeTestPulse:
    def __init__(self, start_time, steady_state_resistance, capacitance):
        self.recording = type("rec", (), {"start_time": start_time})()
        self.analysis = {
            "steady_state_resistance": steady_state_resistance,
            "capacitance": capacitance,
        }


class _TestPulseStream(Queue):
    """Stands in for the clamp's endless test pulse feed.

    The state drains this queue every loop iteration and blocks when it runs dry, so a fixed
    list of pulses would hang run(). This synthesizes the next pulse in a steady series on
    demand, one per call, the way a running clamp supplies them.
    """

    def __init__(self, resistance, capacitance, rate=6.0):
        super().__init__()
        self._resistance = resistance
        self._capacitance = capacitance
        self._rate = rate
        self._count = 0

    def get(self, *args, **kwargs):
        tp = _FakeTestPulse(self._count / self._rate, self._resistance, self._capacitance)
        self._count += 1
        return tp

    def empty(self):
        # One pulse per getTestPulses() call, so each loop iteration advances time by 1/rate.
        return True


@pytest.fixture
def dev(qapp):
    # qapp ensures a QApplication exists for the QObject-based Future base class.
    return _FakeDev()


def _sealState(dev, resistance, capacitance, **config):
    # 'user' pressure and no focus move keep run() off the hardware paths.
    config.setdefault('pressureMode', 'user')
    config.setdefault('focusOnCell', False)
    config.setdefault('delayAfterSeal', 0)
    state = SealState(dev, config=config)
    state.testPulseResults = _TestPulseStream(resistance, capacitance)
    return state


def test_seal_goes_to_break_in_when_the_cell_ruptures(dev):
    """Sustained membrane capacitance with the seal gone must hand off to 'break in'."""
    state = _sealState(dev, resistance=100e6, capacitance=100e-12)
    result = state.run()
    assert result == {"state": "break in"}
    assert dev.patchRecord()['spontaneousBreakin'] is True


def test_spontaneous_break_in_state_is_configurable(dev):
    """Like cell attached, the destination state can be redirected."""
    state = _sealState(dev, resistance=100e6, capacitance=100e-12,
                       spontaneousBreakInState='whole cell')
    assert state.run() == {"state": "whole cell"}


def test_normal_sealing_reaches_cell_attached_without_reporting_break_in(dev):
    """A seal past threshold with no capacitance must succeed, not report a break-in."""
    state = _sealState(dev, resistance=2e9, capacitance=np.nan)
    assert state.run() == {"state": "cell attached"}
    assert 'spontaneousBreakin' not in dev.patchRecord()


def test_capacitance_while_still_sealed_is_not_a_break_in(dev):
    """Above the seal threshold the pipette is sealed; capacitance there must not divert it."""
    state = _sealState(dev, resistance=2e9, capacitance=100e-12)
    assert state.run() == {"state": "cell attached"}
    assert 'spontaneousBreakin' not in dev.patchRecord()
