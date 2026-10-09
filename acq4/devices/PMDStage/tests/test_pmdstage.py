"""PMDStage against the simulated Magellan bus; no hardware."""

from __future__ import annotations

import functools
import time
from unittest import mock

import pytest

from acq4.devices.PMDStage import PMDStage, PMDMoveFuture
from acq4.devices.PMDStage.pmdstage import PMDStageInterface
from acq4.drivers.pmdmotion import MagellanPMD, NotCommutatedError
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


@pytest.fixture
def bus():
    return FakeMagellanBus(nodes={1: {'position': 100_000}, 2: {'position': -200_000}, 3: {'position': 0}})


@pytest.fixture
def makeStage(qapp, bus, monkeypatch):
    driverClass = functools.partial(
        MagellanPMD, serial_factory=bus.open_serial, timeout=0.02, resync_delay=0.001
    )
    monkeypatch.setattr(PMDStage, 'driverClass', driverClass)
    dm = FakeDM()
    devices = []

    def make(**config):
        cfg = {'driver': 'PMDStage', 'port': 'COMTEST', 'poll_interval': 0.01}
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


def test_loads_with_warning_when_unphased(makeStage, bus):
    bus[3]._phased = False
    dev = makeStage()
    assert dev.unphasedAxes() == ['z']
    assert dev.getPosition() == pytest.approx([0.5, -1.0, 0.0])

    with pytest.raises(NotCommutatedError, match='Commutate'):
        dev.move([0.5, -1.0, 1.0], speed=20e-3)
    # z target unchanged: dropped, so x can still move
    dev.move([0.6, -1.0, 0.0], speed=20e-3).wait(timeout=3)
    assert bus[1].actual_position == pytest.approx(120_000, abs=1000)
    assert not bus.commands(node=3, name=['SetPosition', 'Update'])


def test_unphased_warning_is_logged(makeStage, bus, caplog):
    bus[3]._phased = False
    makeStage()
    assert any('not commutated' in r.getMessage() and 'Commutate' in r.getMessage()
               for r in caplog.records if r.levelname == 'WARNING')


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


def test_move_end_reports_position_below_threshold(makeStage, bus):
    dev = makeStage(positionChangeThreshold=10.0)
    dev.move([1.0, None, None], speed=20e-3).wait(timeout=3)
    assert dev.globalPosition()[0] == pytest.approx(1.0e-3, abs=5e-6)


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


def test_warnings_mention_travel_and_z_drop(makeStage):
    dev = makeStage()
    text = dev.actionWarning('commutation', ['x', 'z'])
    assert '20.64 mm' in text and 'CANNOT BE INTERRUPTED' in text
    assert 'Z drops about 15 mm' in text
    assert 'Z WARNING' not in dev.actionWarning('commutation', ['x'])
    assert 'full travel' in dev.actionWarning('homing', ['x'])


def test_gui_commutate_confirms_and_runs(makeStage, bus):
    bus[3]._phased = False
    dev = makeStage()
    calls = fakeAction(dev, 'commutate')
    gui = PMDStageInterface(dev, None)
    assert 'Z' in gui.phaseLabel.text()

    asked = []
    gui.confirm = lambda title, text: asked.append(text) or False
    gui.commutateBtn.click()
    assert calls == [] and 'Z drops' in asked[0]
    assert wait_until(lambda: gui.commutateBtn._task is None)

    gui.confirm = lambda title, text: True
    gui.commutateBtn.click()
    assert wait_until(lambda: calls == [['z']])


def test_gui_home_refused_when_unphased(makeStage, bus):
    bus[3]._phased = False
    dev = makeStage()
    calls = fakeAction(dev, 'home')
    gui = PMDStageInterface(dev, None)
    shown = []
    gui.showMessage = lambda title, text: shown.append(text)
    gui.confirm = lambda title, text: True
    gui.homeBtn.click()
    assert calls == [] and 'commutated' in shown[0]


def test_quit_closes_driver(makeStage, bus):
    dev = makeStage()
    with mock.patch.object(dev.driver, 'close', wraps=dev.driver.close) as close:
        dev.quit()
    close.assert_called_once()
