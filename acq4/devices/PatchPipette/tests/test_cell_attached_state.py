"""Integration tests for the cell attached state's spontaneous break-in detection.

A cell in cell-attached configuration can rupture on its own; the state watches membrane
capacitance to notice. Test pulses report NaN capacitance whenever there is no transient to fit,
so these cover the NaN handling as much as the detection itself.
"""
from __future__ import annotations

import time
from queue import Queue

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.cell_attached import CellAttachedState


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


class _FakePressure:
    def __init__(self):
        self.sigPressureChanged = _FakeSignal()

    def setPressure(self, **kwargs):
        pass


class _FakeDev:
    def __init__(self):
        self.active = True
        self.sigTargetChanged = _FakeSignal()
        self.sigActiveChanged = _FakeSignal()
        self.clampDevice = _FakeClamp()
        self.pressureDevice = _FakePressure()
        self._patchrec = {}

    def patchRecord(self):
        return self._patchrec


class _FakeTestPulse:
    def __init__(self, steady_state_resistance, capacitance, baseline_current=-20e-12):
        self.recording = type("rec", (), {"start_time": 0.0})()
        self.analysis = {
            "steady_state_resistance": steady_state_resistance,
            "capacitance": capacitance,
            "baseline_current": baseline_current,
        }


class _TestPulseStream(Queue):
    """Stands in for the clamp's endless test pulse feed, paced like a real one.

    The state derives its averaging interval from the wall clock between loop iterations, so an
    instant stream would collapse every dt to zero and the averages would never move. Sleeping
    between pulses reproduces the real ~60Hz-or-slower pacing at test speed.

    *segments* is a list of (count, resistance, capacitance); the last one repeats forever.
    """

    def __init__(self, segments, rate=60.0):
        super().__init__()
        self._segments = list(segments)
        self._interval = 1.0 / rate
        self._index = 0

    def get(self, *args, **kwargs):
        time.sleep(self._interval)
        remaining = self._index
        for count, resistance, capacitance in self._segments[:-1]:
            if remaining < count:
                self._index += 1
                return _FakeTestPulse(resistance, capacitance)
            remaining -= count
        self._index += 1
        _, resistance, capacitance = self._segments[-1]
        return _FakeTestPulse(resistance, capacitance)

    def empty(self):
        # One pulse per getTestPulses() call, so each iteration advances by one interval.
        return True


@pytest.fixture
def dev(qapp):
    # qapp ensures a QApplication exists for the QObject-based Future base class.
    return _FakeDev()


def _cellAttached(dev, segments, **config):
    state = CellAttachedState(dev, config=config)
    state.testPulseResults = _TestPulseStream(segments)
    return state


# A sealed cell-attached patch: gigaseal resistance, no fittable membrane transient.
SEALED = (0, 2e9, np.nan)
# The same patch after rupturing into whole cell.
RUPTURED = (0, 150e6, 100e-12)


def test_sustained_membrane_capacitance_is_break_in(dev):
    """Capacitance appearing while resistance falls off gigaseal is a spontaneous break-in."""
    state = _cellAttached(dev, [RUPTURED])
    assert state.run() == {"state": "break in"}
    assert dev.patchRecord()['spontaneousBreakin'] is True


def test_nan_capacitance_does_not_disable_later_detection(dev):
    """A long NaN stretch must not permanently disable break-in detection.

    NaN is what a test pulse reports when there is no membrane transient to fit, which is the
    normal reading for an intact seal. Averaging it in makes the running average NaN forever,
    silently disabling detection for the rest of the state.
    """
    state = _cellAttached(dev, [(60, *SEALED[1:]), RUPTURED])
    assert state.run() == {"state": "break in"}
    assert dev.patchRecord()['spontaneousBreakin'] is True


def test_isolated_capacitance_artifact_does_not_trip_break_in(dev):
    """A lone bad capacitance fit must not be mistaken for a rupture."""
    state = _cellAttached(
        dev,
        [(20, *SEALED[1:]), (1, 2e9, 55e-12), SEALED],
        autoBreakInDelay=1.0,
    )
    # autoBreakInDelay provides the exit; reaching it means no spontaneous break-in was declared.
    assert state.run() == {"state": "break in"}
    assert 'spontaneousBreakin' not in dev.patchRecord()


def test_intact_seal_reports_no_spontaneous_break_in(dev):
    """A healthy cell-attached patch must run to its delay without claiming a break-in."""
    state = _cellAttached(dev, [SEALED], autoBreakInDelay=0.5)
    assert state.run() == {"state": "break in"}
    assert 'spontaneousBreakin' not in dev.patchRecord()


def test_break_in_monitor_tau_is_configurable(dev):
    """The averaging constant is exposed rather than hard-coded."""
    assert 'breakInMonitorTau' in CellAttachedState.defaultConfig()
