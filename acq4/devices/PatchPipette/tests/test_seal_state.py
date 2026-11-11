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
    # breakInResistanceFloor disabled: this test is about the break-in -> state hand-off, not
    # about gating on how high the resistance climbed first (see test_seal_analysis.py for that).
    state = _sealState(dev, resistance=100e6, capacitance=100e-12, breakInResistanceFloor=0)
    result = state.run()
    assert result == {"state": "break in"}
    assert dev.patchRecord()['spontaneousBreakin'] is True


def test_break_in_is_suppressed_below_the_resistance_floor(dev):
    """The default *breakInResistanceFloor* must reach the analyzer: a resistance that never
    climbs anywhere near a seal must not be mistaken for a ruptured one."""
    state = _sealState(dev, resistance=100e6, capacitance=100e-12)
    assert state.config['breakInResistanceFloor'] == pytest.approx(500e6)
    assert state._analysis._break_in_resistance_floor == pytest.approx(500e6)
    state.processAtLeastOneTestPulse()
    assert not state._analysis.break_in()


def test_spontaneous_break_in_state_is_configurable(dev):
    """Like cell attached, the destination state can be redirected."""
    state = _sealState(dev, resistance=100e6, capacitance=100e-12,
                       spontaneousBreakInState='whole cell', breakInResistanceFloor=0)
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


# ---- economic early exit ----
#
# The arithmetic itself is unit tested in test_seal_economics.py. These cover the
# wiring: that the parameters reach the analysis, that the gate governs whether
# the verdict is acted on, and that the reason reaches the patch record.
#
# Every case here exits on the state's first auto-pressure iteration, before
# updatePressure() is reached. A later exit would drive the pressure-scan path,
# which wants a pressure device that reports its own changes -- these fakes do
# not, and a scan is not what is under test.

ECONOMICS = dict(
    pressureMode='auto',
    restartCost=90.0,
    sliceSealProbability=0.4,
    expectedSealDuration=12.0,
    expectedFailedSealDuration=30.0,
    minDecisionTime=0.0,
)


def test_the_economics_parameters_reach_the_analysis(dev):
    state = _sealState(dev, resistance=50e6, capacitance=np.nan, **ECONOMICS)
    state.processAtLeastOneTestPulse()
    # (90 + 0.4*12 + 0.6*30) / 0.4
    assert state._analysis.abandon_threshold() == pytest.approx(282.0)


def test_early_exit_is_disabled_by_default(dev):
    """A profile carrying the economics but not the gate must behave exactly as it
    did before any of this existed."""
    state = _sealState(dev, resistance=50e6, capacitance=np.nan, autoSealTimeout=0.0, **ECONOMICS)
    assert state.config['earlyExitEnabled'] is False
    assert state.run() == {"state": "fouled"}
    assert dev.patchRecord()['sealGiveUpReason'] == 'timeout'


def test_early_exit_abandons_a_seal_that_is_going_nowhere(dev):
    """A flat resistance projects an infinite time to seal, so continuing costs
    more than the 282 s a fresh cell is expected to take."""
    state = _sealState(
        dev, resistance=50e6, capacitance=np.nan,
        earlyExitEnabled=True, autoSealTimeout=300.0, **ECONOMICS,
    )
    assert state.run() == {"state": "fouled"}
    assert dev.patchRecord()['sealGiveUpReason'] == 'economic'
    assert dev.patchRecord()['sealSuccessful'] is False


def test_early_exit_does_nothing_without_a_seal_probability(dev):
    """No probability leaves the expected time to the next seal infinite: there is
    nothing better to go to, so the cell is kept and the timeout does its job."""
    economics = dict(ECONOMICS, sliceSealProbability=0.0)
    state = _sealState(
        dev, resistance=50e6, capacitance=np.nan,
        earlyExitEnabled=True, autoSealTimeout=0.0, **economics,
    )
    assert state.run() == {"state": "fouled"}
    assert dev.patchRecord()['sealGiveUpReason'] == 'timeout'


def test_an_economic_exit_releases_the_holding_potential(dev):
    """Same as the timeout path: a holding potential set during sealing must not
    be left applied to a pipette that is being sent off to be cleaned."""
    state = _sealState(
        dev, resistance=200e6, capacitance=np.nan,
        earlyExitEnabled=True, autoSealTimeout=300.0, **ECONOMICS,
    )
    result = state.run()
    assert result == {"state": "fouled", "initialVCHolding": None}
    assert dev.patchRecord()['sealGiveUpReason'] == 'economic'


def test_a_successful_seal_records_no_give_up_reason(dev):
    state = _sealState(
        dev, resistance=2e9, capacitance=np.nan,
        earlyExitEnabled=True, autoSealTimeout=300.0, **ECONOMICS,
    )
    assert state.run() == {"state": "cell attached"}
    # .get: a real device pre-seeds the key as None, this fake starts empty, and
    # the claim under test -- that nothing recorded a reason -- holds either way.
    assert dev.patchRecord().get('sealGiveUpReason') is None
    assert dev.patchRecord()['sealSuccessful'] is True
