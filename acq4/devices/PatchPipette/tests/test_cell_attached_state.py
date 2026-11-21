"""Integration tests for the cell attached state's spontaneous break-in detection and its hold.

A cell in cell-attached configuration can rupture on its own; the state watches membrane
capacitance to notice. Test pulses report NaN capacitance whenever there is no transient to fit,
so these cover the NaN handling as much as the detection itself.
"""
from __future__ import annotations

import logging
import time
from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.cell_attached import CellAttachedState
from acq4.panic import GlobalHalt
from acq4.util import Qt


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


# -- hold -----------------------------------------------------------------------


def _runInTask(state):
    from acq4.util.task import ThreadTask

    return ThreadTask(state.run, name="cell attached test", detach=True)


def _stopAndExpectStopped(task):
    from acq4.util.task import Stopped

    task.stop("test done")
    with pytest.raises(Stopped):
        task.wait(timeout=2)


def test_held_from_config_ignores_a_rupture(dev):
    """A held state never reacts to test pulses: it stays until stopped."""
    state = _cellAttached(dev, [RUPTURED], hold=True)
    assert state.isHolding()
    task = _runInTask(state)
    time.sleep(0.5)
    assert not task.is_done
    _stopAndExpectStopped(task)
    assert 'spontaneousBreakin' not in dev.patchRecord()


def test_held_state_ignores_auto_break_in_delay(dev):
    state = _cellAttached(dev, [SEALED], hold=True, autoBreakInDelay=0.0)
    task = _runInTask(state)
    time.sleep(0.3)
    assert not task.is_done
    _stopAndExpectStopped(task)


def test_hold_on_a_running_state_suspends_monitoring(dev):
    """hold() takes effect on a state already monitoring test pulses."""
    # Rupture after ~0.5 s of seal at 60 Hz; the hold lands before it.
    state = _cellAttached(dev, [(30, *SEALED[1:]), RUPTURED])
    task = _runInTask(state)
    time.sleep(0.1)
    state.hold()
    time.sleep(1.5)
    assert not task.is_done
    _stopAndExpectStopped(task)
    assert 'spontaneousBreakin' not in dev.patchRecord()


def test_hold_persists_in_config(dev):
    """A state rebuilt from a held state's config (e.g. on reactivation) also holds."""
    state = _cellAttached(dev, [SEALED])
    assert not state.isHolding()
    state.hold()
    assert state.config['hold'] is True
    assert CellAttachedState(dev, config=dict(state.config)).isHolding()


def test_unheld_state_still_detects_rupture(dev):
    state = _cellAttached(dev, [RUPTURED], hold=False)
    assert state.run() == {"state": "break in"}


class _ManagedDev(Qt.QObject):
    """Enough PatchPipette for the real PatchPipetteStateManager to run a state job."""

    sigStateChanged = Qt.Signal(object, object, object)
    sigActiveChanged = Qt.Signal(object, object)
    sigTargetChanged = Qt.Signal(object, object)

    def __init__(self):
        super().__init__()
        self.active = True
        self.clampDevice = None
        self.pressureDevice = None
        self.cell = None
        self.config = {}
        self.dm = SimpleNamespace(globalHalt=GlobalHalt())
        self.logger = logging.getLogger(__name__)

    def name(self):
        return "PatchPipette1"

    def patchRecord(self):
        return {}

    def emitNewEvent(self, *args):
        pass

    def _setState(self, state, oldState):
        self.sigStateChanged.emit(self, state, oldState)


def test_hold_from_the_state_change_signal_precedes_the_job(qapp):
    """Holding from sigStateChanged, as actions.fsm.seal does, holds before run() starts.

    With no clamp, an unheld cell attached state fails as soon as it monitors test pulses.
    """
    from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager

    dev = _ManagedDev()
    with patch("acq4.Manager.Manager.single", SimpleNamespace(config={})):
        manager = PatchPipetteStateManager(dev)

    def holdCellAttached(_dev, state, _old):
        if state == "cell attached":
            manager.getState().hold()

    dev.sigStateChanged.connect(holdCellAttached, Qt.Qt.DirectConnection)
    try:
        job = manager.configureState("cell attached")
        time.sleep(0.3)
        assert manager.getState() is job
        assert job.isHolding()
        assert not job.is_done
        manager.configureState("out")
        assert job.is_done
        assert manager.getState().stateName == "out"
    finally:
        manager.quit()
