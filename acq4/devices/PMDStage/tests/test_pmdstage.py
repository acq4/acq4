"""PMDStage against the simulated Magellan bus; no hardware."""

from __future__ import annotations

import functools
import sys
import time
from unittest import mock

import pytest

from acq4.devices.PMDStage import PMDStage, PMDMoveFuture
from acq4.devices.PMDStage.pmdstage import PMDStageInterface
from acq4.drivers.pmdmotion import CommutationError, MagellanPMD, NotCommutatedError
from acq4.drivers.pmdmotion import magellan
from acq4.drivers.pmdmotion.tests.fake_bus import FakeMagellanBus
from acq4.drivers.stage import MoveInterrupted, RequestFailed, RequestFuture
from acq4.panic import GlobalHalt
from acq4.util import Qt
from acq4.util.task import Stopped


class FakeDM:
    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.devices = {}

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def readConfigFile(self, fn):
        return {}


def pump(n=5):
    for _ in range(n):
        Qt.QApplication.processEvents()


def wait_until(cond, timeout=3.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        pump(1)
        if cond():
            return True
        time.sleep(0.005)
    return False


BASE_CONFIG = {
    'driver': 'PMDStage', 'port': 'COMTEST', 'poll_interval': 0.01, 'counts_per_unit': 200_000,
    'axes': {'x': 1, 'y': 2, 'z': 3},
    'acceleration': 0.4, 'jerk': 50, 'homingSpeed': 5e-3, 'homingAcceleration': 0.2,
    'homingJerk': 25, 'homeOffset': 10e-3, 'homeSweep': 102e-3,
}


@pytest.fixture
def bus():
    return FakeMagellanBus(nodes={1: {'position': 100_000}, 2: {'position': -200_000}, 3: {'position': 0}})


@pytest.fixture
def confirmations(monkeypatch):
    """Answers (pop from the front) for the driver's commutation question; records each ask."""
    state = {'answers': [], 'asked': []}

    def confirm(axes, text):
        state['asked'].append((axes, text))
        return state['answers'].pop(0) if state['answers'] else False

    monkeypatch.setattr(magellan, 'qt_confirm_commutation', confirm)
    return state


@pytest.fixture
def makeStage(qapp, bus, monkeypatch, confirmations):
    driverClass = functools.partial(
        MagellanPMD, serial_factory=bus.open_serial, timeout=0.02, resync_delay=0.001
    )
    monkeypatch.setattr(PMDStage, 'driverClass', driverClass)
    dm = FakeDM()
    devices = []

    def make(**config):
        cfg = dict(BASE_CONFIG)
        cfg.update(config)
        with mock.patch('acq4.Manager.Manager.single', dm):
            dev = PMDStage(dm, cfg, 'Stage')
        devices.append(dev)
        return dev

    yield make
    for dev in devices:
        dev.quit()


def fakeAction(dev, name, outcome=None):
    """Replace driver.<name> with a recorder returning a future finished with *outcome*."""
    calls = []

    def action(axes=None, **kwds):
        calls.append(axes)
        fut = RequestFuture('call', dev.driver)
        if outcome is None:
            fut._finish('done', result='ok')
        else:
            fut._finish('failed', message=outcome)
        return fut

    setattr(dev.driver, name, action)
    return calls


# ---- loading and units ----

def test_loads_when_phased(makeStage, bus):
    dev = makeStage()
    assert dev.axes() == ('x', 'y', 'z')
    assert dev.unphasedAxes() == []
    assert dev.getPosition() == pytest.approx([0.5, -1.0, 0.0])
    assert list(dev.getAxisScale()) == [1e-3, 1e-3, 1e-3]
    assert dev.canRetargetInFlight
    assert dev.acceleration == pytest.approx(0.4)


def test_phased_startup_commutation_is_silent(makeStage, bus, confirmations):
    dev = makeStage()
    pump()
    assert confirmations['asked'] == [] and not dev.isBusy()
    assert not bus.commands(name=['InitializePhase', 'SetOperatingMode'])


def test_loads_unphased_then_asks_when_declined(makeStage, bus, confirmations):
    bus[3]._phased = False
    dev = makeStage()
    # construction neither asks nor commutates; the post-construction step asks
    assert confirmations['asked'] == []
    assert dev.unphasedAxes() == ['z']
    pump()
    assert [a for a, _ in confirmations['asked']] == [['z']]
    assert wait_until(lambda: not dev.isBusy())
    assert not bus.commands(name='InitializePhase')
    assert dev.unphasedAxes() == ['z']
    assert dev.getPosition() == pytest.approx([0.5, -1.0, 0.0])

    # the driver refuses any move including z, even to where it already is
    with pytest.raises(RequestFailed, match='not commutated') as err:
        dev.move([0.6, -1.0, 0.0], speed=20e-3).wait(timeout=3)
    assert isinstance(err.value.__cause__, NotCommutatedError)
    dev.move([0.6, None, None], speed=20e-3).wait(timeout=3)
    assert bus[1].actual_position == pytest.approx(120_000, abs=1000)
    assert not bus.commands(node=3, name=['SetPosition', 'Update'])


def test_startup_commutation_failure_is_raised(makeStage, bus, confirmations, monkeypatch):
    bus[3]._phased = False
    bus[3].registers[('PhaseInitializeTime',)] = 100
    bus[3].commutation_min_drive = 30000
    raised = []
    monkeypatch.setattr(sys, 'excepthook', lambda *args: raised.append(args[1]))
    dev = makeStage(autoCommutate=True)
    assert wait_until(lambda: raised, timeout=20)
    assert confirmations['asked'] == []
    assert 'commutation after startup failed' in str(raised[0])
    assert isinstance(raised[0].__cause__, RequestFailed)
    assert isinstance(raised[0].__cause__.__cause__, CommutationError)
    assert dev.unphasedAxes() == ['z']


def test_missing_required_config(makeStage):
    with pytest.raises(KeyError, match='homeSweep'):
        makeStage(homeSweep=None)
    with pytest.raises(KeyError, match='axes'):
        makeStage(axes=None)


def test_auto_commutate_passed_through(makeStage):
    dev = makeStage(autoCommutate=True)
    assert dev.driver.auto_commutate is True
    assert makeStage().driver.auto_commutate is False


def test_config_converted_to_mm(makeStage):
    d = makeStage(homeOffset=3e-3).driver
    assert (d.homing_speed, d.homing_acceleration, d.homing_jerk, d.home_offset, d.home_sweep) == \
        pytest.approx((5, 200, 25_000, 3, 102))
    assert d.default_jerk == pytest.approx(50_000)


def test_threshold_config(makeStage):
    d = makeStage().driver
    # defaults: 5 um arrival window, others in counts
    assert d._arrival_counts == pytest.approx({'x': 1000, 'y': 1000, 'z': 1000})
    assert d._position_limit_counts['x'] == 2 ** 27
    assert (d._motion_counts['x'], d._settle_counts['x'], d._home_settle_counts['x']) == (100, 100, 10)
    d = makeStage(arrivalWindow=1e-6, positionLimit=0.5, motionThreshold=1e-6, settleThreshold=2e-6,
                  homeSettleThreshold=1e-7, positionChangeThreshold=1e-6).driver
    assert d._arrival_counts['y'] == pytest.approx(200)
    assert d._position_limit_counts['y'] == pytest.approx(100_000_000)
    assert (d._motion_counts['z'], d._settle_counts['z'], d._home_settle_counts['z']) == \
        pytest.approx((200, 400, 20))
    assert d.position_change_threshold == pytest.approx(1e-3)


def test_unit_conversion(makeStage, bus):
    dev = makeStage(acceleration=0.2, profile='scurve')
    assert dev.driver.default_acceleration == pytest.approx(200)
    assert not dev.canRetargetInFlight
    fut = dev.move([1.0, None, None], speed=10e-3)
    assert isinstance(fut, PMDMoveFuture)
    assert fut.request.target == {'x': 1.0}
    assert fut.request.speed == pytest.approx(10.0)  # mm/s
    assert list(fut.targetPos) == pytest.approx([1.0, -1.0, 0.0])
    fut.wait(timeout=3)
    assert bus[1].actual_position == pytest.approx(200_000, abs=1000)
    assert wait_until(lambda: abs(dev.getPosition()[0] - 1.0) < 0.005)
    assert dev.globalPosition()[0] == pytest.approx(1.0e-3, abs=5e-6)


def test_position_callback_updates_stage(makeStage, bus):
    dev = makeStage()
    seen = []
    dev.sigPositionChanged.connect(lambda d, new, old: seen.append(new))
    bus[2].set_physical_position(-100_000)
    assert wait_until(lambda: seen and seen[-1][1] == pytest.approx(-0.5))
    assert dev.getPosition()[1] == pytest.approx(-0.5)


def test_position_noise_below_threshold_is_not_reported(makeStage, bus):
    dev = makeStage()
    assert dev.driver.position_change_threshold == pytest.approx(2.5e-4)
    seen = []
    dev.sigPositionChanged.connect(lambda d, new, old: seen.append(new))
    bus[3].set_physical_position(20)  # 100 nm
    time.sleep(0.1)
    pump()
    assert seen == []


# ---- move outcomes ----

def test_move_success(makeStage, bus):
    dev = makeStage()
    fut = dev.move([0.6, -0.9, 0.1], speed=20e-3)
    assert fut.wait(timeout=3) is None
    assert dev.getPosition() == pytest.approx([0.6, -0.9, 0.1], abs=0.006)


def test_move_failure_carries_reason(makeStage, bus):
    dev = makeStage()
    bus[1].stroke = (-5_000_000, 150_000)
    fut = dev.move([2.0, None, None], speed=20e-3)
    with pytest.raises(RequestFailed, match='limit'):
        fut.wait(timeout=3)


def test_move_interrupted(makeStage, bus):
    dev = makeStage()
    first = dev.move([5.0, None, None], speed=1e-3)
    assert wait_until(lambda: bus[1].in_motion)
    second = dev.move([0.5, None, None], speed=20e-3)
    with pytest.raises(MoveInterrupted):
        first.wait(timeout=3)
    second.wait(timeout=5)


def test_device_stop_completes_move_as_stopped(makeStage, bus):
    dev = makeStage()
    fut = dev.move([5.0, None, None], speed=1e-3)
    assert wait_until(lambda: bus[1].in_motion)
    n = len(bus.commands(name='SetStopMode'))
    dev.stop()
    with pytest.raises(Stopped):
        fut.wait(timeout=3)
    assert len(bus.commands(name='SetStopMode')) > n


def test_future_stop_stops_driver(makeStage, bus):
    dev = makeStage()
    fut = dev.move([5.0, None, None], speed=1e-3)
    assert wait_until(lambda: bus[1].in_motion)
    with mock.patch.object(dev.driver, 'stop', wraps=dev.driver.stop) as stop:
        fut.stop(wait=True)
    stop.assert_called()
    with pytest.raises(Stopped):
        fut.wait(timeout=1)
    assert wait_until(lambda: not bus[1].in_motion)


# ---- commutate / home ----

def test_commutate_invokes_driver(makeStage, bus):
    dev = makeStage()
    calls = fakeAction(dev, 'commutate')
    task = dev.commutate(['z'])
    assert task.wait(timeout=2) == 'ok'
    assert calls == [['z']]
    assert not dev.isBusy()


def test_home_invokes_driver(makeStage, bus):
    dev = makeStage()
    calls = fakeAction(dev, 'home')
    dev.home().wait(timeout=2)
    assert calls == [None]


def test_action_failure_is_reported(makeStage, bus):
    dev = makeStage()
    fakeAction(dev, 'commutate', outcome='CommutationError: z')
    finished = []
    dev.sigActionFinished.connect(lambda action, exc: finished.append((action, exc)))
    with pytest.raises(RequestFailed, match='CommutationError'):
        dev.commutate().wait(timeout=2)
    assert wait_until(lambda: finished)
    assert finished[0][0] == 'commutation'


def test_moves_refused_while_action_runs(makeStage, bus):
    dev = makeStage()
    pending = RequestFuture('call', dev.driver)
    dev.driver.home = lambda axes=None: pending
    task = dev.home()
    with pytest.raises(RuntimeError, match='homing'):
        dev.move([0.6, None, None], speed=20e-3)
    with pytest.raises(RuntimeError, match='already running'):
        dev.commutate()
    pending._finish('done')
    task.wait(timeout=2)
    dev.move([0.6, None, None], speed=20e-3).wait(timeout=3)


def test_gui_commutate_uses_driver_confirmation(makeStage, bus, confirmations):
    bus[3]._phased = False
    bus[3].registers[('PhaseInitializeTime',)] = 100
    dev = makeStage()
    pump()   # post-construction commutation step: declined
    assert wait_until(lambda: not dev.isBusy())
    gui = PMDStageInterface(dev, None)
    assert 'Z' in gui.phaseLabel.text()
    confirmations['asked'].clear()

    gui.commutateBtn.click()   # declined
    assert [a for a, _ in confirmations['asked']] == [['z']]
    assert wait_until(lambda: gui.commutateBtn._task is None)
    assert not bus.commands(name='InitializePhase') and not dev.isBusy()

    confirmations['answers'].append(True)
    gui.commutateBtn.click()
    assert wait_until(lambda: dev.unphasedAxes() == [] and not dev.isBusy(), timeout=10)
    assert bus.commands(node=3, name='InitializePhase')
    assert wait_until(lambda: gui.phaseLabel.text() == 'All axes commutated')


def test_gui_home_confirms(makeStage, bus):
    dev = makeStage()
    calls = fakeAction(dev, 'home')
    gui = PMDStageInterface(dev, None)
    asked = []
    gui.confirm = lambda title, text: asked.append(text) or False
    gui.homeBtn.click()
    assert calls == [] and 'CANNOT BE INTERRUPTED' in asked[0]
    assert wait_until(lambda: gui.homeBtn._task is None)
    gui.confirm = lambda title, text: True
    gui.homeBtn.click()
    assert wait_until(lambda: calls == [['x', 'y', 'z']])


def test_quit_closes_driver(makeStage, bus):
    dev = makeStage()
    with mock.patch.object(dev.driver, 'close', wraps=dev.driver.close) as close:
        dev.quit()
    close.assert_called_once()
