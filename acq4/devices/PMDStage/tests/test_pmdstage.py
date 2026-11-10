"""PMDStage against the simulated Magellan bus; no hardware."""

from __future__ import annotations

import functools
import logging
import time
from unittest import mock

import pytest

from acq4.devices.PMDStage import PMDStage, PMDMoveFuture
from acq4.devices.PMDStage.pmdstage import PMDStageInterface
from acq4.drivers.pmdmotion import CommutationError, MagellanPMD
from acq4.drivers.pmdmotion import backend as backend_module
from acq4.drivers.pmdmotion import protocol as p
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

    monkeypatch.setattr(backend_module, 'qt_confirm_commutation', confirm)
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


def unphased(dev):
    """Axes the backend currently treats as unphased (read without I/O)."""
    return sorted(dev.driver._backend._unphased)


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
    assert unphased(dev) == []
    assert dev.getPosition() == pytest.approx([0.5, -1.0, 0.0])
    assert list(dev.getAxisScale()) == [1e-3, 1e-3, 1e-3]
    assert dev.retargetInterval == pytest.approx(0.1)
    assert dev.acceleration == pytest.approx(0.4)


def test_position_known_when_polls_precede_the_callback(makeStage, monkeypatch):
    from acq4.devices.Stage import Stage

    stageInit = Stage.__init__

    def slowInit(self, *args, **kwds):
        stageInit(self, *args, **kwds)
        time.sleep(0.1)  # several polls run before the position callback is set

    monkeypatch.setattr(Stage, '__init__', slowInit)
    dev = makeStage()
    assert dev.getPosition() == pytest.approx([0.5, -1.0, 0.0])


def test_startup_waits_for_a_valid_first_read(makeStage, bus):
    bus[1].drop_responses(4, opcode=p.GET_ACTUAL_POSITION)  # one failed read: all retries time out
    dev = makeStage()
    assert dev.getPosition() == pytest.approx([0.5, -1.0, 0.0])


def test_startup_fails_without_a_valid_read(makeStage, bus, monkeypatch):
    from acq4.devices.PMDStage import pmdstage

    monkeypatch.setattr(pmdstage, 'FIRST_POSITION_TIMEOUT', 0.3)
    bus[2].drop_responses(10 ** 6, opcode=p.GET_ACTUAL_POSITION)
    with pytest.raises(RuntimeError, match='no valid position'):
        makeStage()


def test_no_position_before_first_read(makeStage):
    dev = makeStage()
    dev.driver.get_position = lambda: None
    with pytest.raises(RuntimeError, match='no position has been read'):
        dev._getPosition()
    with pytest.raises(RuntimeError, match=r"no position for axes \['z'\]"):
        dev._posFromDriver({'x': 0.5, 'y': -1.0})


def test_phased_startup_commutation_is_silent(makeStage, bus, confirmations, caplog):
    caplog.set_level(logging.DEBUG)
    dev = makeStage()
    assert not dev.isBusy()
    assert confirmations['asked'] == []
    assert not bus.commands(name=['InitializePhase', 'SetOperatingMode'])
    assert not [r for r in caplog.records if r.levelno > logging.DEBUG and 'commutat' in r.getMessage()]
    # only the phasing read per axis at open
    assert len(bus.commands(name='GetActivityStatus')) == 3


def test_startup_commutation_logs_drive_levels(makeStage, bus, confirmations, caplog):
    caplog.set_level(logging.INFO)
    bus[3]._phased = False
    bus[3].registers[('PhaseInitializeTime',)] = 100
    dev = makeStage(autoCommutate=True)
    assert unphased(dev) == [] and not dev.isBusy()
    assert any("homing finished; drive levels {'z': 2048}" in r.getMessage() for r in caplog.records)
    dev.move([0.6, -1.0, 0.1], speed=20e-3).wait(timeout=3)


def test_power_cycled_stage_commutates_and_homes_before_reading_positions(makeStage, bus, confirmations,
                                                                         caplog):
    # after a power cycle an unphased axis can hold an arbitrary position
    caplog.set_level(logging.INFO)
    for node in (1, 2, 3):
        bus[node]._phased = False
        bus[node].registers[('PhaseInitializeTime',)] = 100
    bus[2]._offset += 404_503_262
    confirmations['answers'] = [True]
    dev = makeStage()
    [(axes, text)] = confirmations['asked']
    assert axes == ['x', 'y', 'z'] and 'home' in text
    assert unphased(dev) == []
    # homed: each axis rests at its vane (physical 0), zeroed there
    assert all(abs(bus[node].physical_position) < 10 for node in (1, 2, 3))
    assert all(abs(v) < 1e-4 for v in dev.getPosition())
    # unphased axes are not polled, and commutation settles rather than timing out
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert not [r for r in caplog.records if 'still moving' in r.getMessage()]


def test_confirmation_reaches_gui_thread_during_construction(makeStage, bus, monkeypatch):
    from acq4.util.task import run_in_gui_thread

    # the real dialog's route: control thread -> GUI thread, which construction is blocking
    asked = []
    monkeypatch.setattr(backend_module, 'qt_confirm_commutation',
                        lambda axes, text: run_in_gui_thread(lambda: asked.append(axes) or True))
    bus[3]._phased = False
    bus[3].registers[('PhaseInitializeTime',)] = 100
    dev = makeStage()
    assert asked == [['z']]
    assert unphased(dev) == []


def test_no_commutation_outside_startup(makeStage):
    dev = makeStage()
    assert not hasattr(dev, 'commutate')
    assert not hasattr(PMDStageInterface(dev, None), 'commutateBtn')


def test_declined_commutation_fails_construction(makeStage, bus, confirmations):
    bus[3]._phased = False
    with pytest.raises(RuntimeError, match=r"commutation declined; axes \['z'\]"):
        makeStage()
    assert [a for a, _ in confirmations['asked']] == [['z']]
    assert not bus.commands(name='InitializePhase')


def test_startup_commutation_failure_fails_construction(makeStage, bus, confirmations):
    bus[3]._phased = False
    bus[3].registers[('PhaseInitializeTime',)] = 100
    bus[3].commutation_min_drive = 30000
    with pytest.raises(RuntimeError, match='startup commutation and homing failed') as err:
        makeStage(autoCommutate=True)
    assert confirmations['asked'] == []
    assert isinstance(err.value.__cause__, RequestFailed)
    assert isinstance(err.value.__cause__.__cause__, CommutationError)


def test_missing_required_config(makeStage):
    with pytest.raises(KeyError, match='homeSweep'):
        makeStage(homeSweep=None)
    with pytest.raises(KeyError, match='axes'):
        makeStage(axes=None)


def test_auto_commutate_passed_through(makeStage):
    dev = makeStage(autoCommutate=True)
    assert dev.driver._backend.auto_commutate is True
    assert makeStage().driver._backend.auto_commutate is False


def test_config_converted_to_mm(makeStage):
    d = makeStage(homeOffset=3e-3).driver._backend
    assert (d.homing_speed, d.homing_acceleration, d.homing_jerk, d.home_offset, d.home_sweep) == \
        pytest.approx((5, 200, 25_000, 3, 102))
    assert d.default_jerk == pytest.approx(50_000)


def test_threshold_config(makeStage):
    d = makeStage().driver._backend
    # defaults: 5 um arrival window, others in counts
    assert d._arrival_counts == pytest.approx({'x': 1000, 'y': 1000, 'z': 1000})
    assert d._position_limit_counts['x'] == 2 ** 27
    assert (d._motion_counts['x'], d._settle_counts['x'], d._home_settle_counts['x']) == (100, 100, 10)
    dev = makeStage(arrivalWindow=1e-6, positionLimit=0.5, motionThreshold=1e-6, settleThreshold=2e-6,
                    homeSettleThreshold=1e-7, positionChangeThreshold=1e-6)
    d = dev.driver._backend
    assert d._arrival_counts['y'] == pytest.approx(200)
    assert d._position_limit_counts['y'] == pytest.approx(100_000_000)
    assert (d._motion_counts['z'], d._settle_counts['z'], d._home_settle_counts['z']) == \
        pytest.approx((200, 400, 20))
    assert dev.driver.position_change_threshold == pytest.approx(1e-3)


def test_unit_conversion(makeStage, bus):
    dev = makeStage(acceleration=0.2, profile='scurve', poll_interval=0.02, retargetInterval=0.3)
    assert dev.driver._backend.default_acceleration == pytest.approx(200)
    assert dev.acceleration == pytest.approx(0.2)
    assert dev.driver.poll_interval == pytest.approx(0.02) and dev.positionUpdatesPerSecond == pytest.approx(50)
    assert dev.retargetInterval == pytest.approx(0.3)
    fut = dev.move([1.0, None, None], speed=10e-3)
    assert isinstance(fut, PMDMoveFuture)
    assert fut.request.target == {'x': 1.0}
    assert fut.request.speed == pytest.approx(10.0)  # mm/s
    assert list(fut.targetPos) == pytest.approx([1.0, -1.0, 0.0])
    fut.wait(timeout=3)
    assert bus[1].actual_position == pytest.approx(200_000, abs=1000)
    assert wait_until(lambda: abs(dev.getPosition()[0] - 1.0) < 0.005)
    assert dev.globalPosition()[0] == pytest.approx(1.0e-3, abs=5e-6)


def test_scurve_needs_a_configured_retarget_interval(makeStage):
    with pytest.raises(NotImplementedError, match='retargetInterval'):
        makeStage(profile='scurve')


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


def test_move_beyond_position_limit_refused(makeStage, bus):
    dev = makeStage(positionLimit=1e-3)
    with pytest.raises(RequestFailed, match='position limit'):
        dev.move([2.0, None, None], speed=20e-3).wait(timeout=3)
    assert not bus.commands(node=1, name='SetPosition')


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


# ---- home ----

def test_home_invokes_driver(makeStage, bus):
    dev = makeStage()
    calls = fakeAction(dev, 'home')
    dev.home().wait(timeout=2)
    assert calls == [None]


def test_homing_failure_is_reported(makeStage, bus):
    dev = makeStage()
    fakeAction(dev, 'home', outcome='LimitError: z')
    finished = []
    dev.sigHomingFinished.connect(finished.append)
    with pytest.raises(RequestFailed, match='LimitError'):
        dev.home().wait(timeout=2)
    assert wait_until(lambda: finished)
    assert isinstance(finished[0], RequestFailed)


def test_moves_refused_while_homing(makeStage, bus):
    dev = makeStage()
    pending = RequestFuture('call', dev.driver)
    dev.driver.home = lambda axes=None: pending
    task = dev.home()
    with pytest.raises(RuntimeError, match='homing'):
        dev.move([0.6, None, None], speed=20e-3)
    with pytest.raises(RuntimeError, match='already running'):
        dev.home()
    pending._finish('done')
    task.wait(timeout=2)
    dev.move([0.6, None, None], speed=20e-3).wait(timeout=3)


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
