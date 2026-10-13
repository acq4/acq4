"""MagellanPMD (driver, control thread and backend together) against the fake bus in real time."""
import threading
import time

import pytest

from acq4.drivers.pmdmotion import backend as backend_module
from acq4.drivers.pmdmotion import serial_ports
from acq4.drivers.pmdmotion.driver import MagellanPMD
from acq4.drivers.pmdmotion.protocol import CommunicationError, CommutationError, NotCommutatedError
from acq4.drivers.pmdmotion.tests.fake_bus import FakeMagellanBus
from acq4.drivers.stage import MoveCancelled, MoveInterrupted, MoveStopped, RequestFailed

AXES = {'x': 1, 'y': 2, 'z': 3}
CPM = 200_000
FAST_PHASE_INIT = {('PhaseInitializeTime',): 100}   # 20 ms per init
PROFILE = dict(acceleration=400, jerk=50_000, homing_speed=5, homing_acceleration=200,
               homing_jerk=25_000, home_offset=10, home_sweep=102)


def decline(axes, text):
    return False


def make_driver(bus, **kwds):
    opts = dict(port='COMTEST', counts_per_unit=CPM, poll_interval=0.01, serial_factory=bus.open_serial,
                timeout=0.02, resync_delay=0.001, confirm_commutation=decline, **PROFILE)
    opts.update(kwds)
    return MagellanPMD(dict(AXES), **opts)


@pytest.fixture
def bus():
    return FakeMagellanBus(nodes={1: {'position': 100_000}, 2: {'position': -200_000}, 3: {'position': 0}})


@pytest.fixture
def drivers():
    made = []
    yield made
    for d in made:
        d.close()


@pytest.fixture
def drv(bus, drivers):
    d = make_driver(bus)
    d.connect()
    drivers.append(d)
    return d


def wait_until(cond, timeout=2.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.005)
    return False


def test_connect_and_move(bus, drv):
    assert drv.axes == ('x', 'y', 'z')
    assert drv.get_position() == pytest.approx({'x': 0.5, 'y': -1.0, 'z': 0.0})
    seen = []
    drv.set_position_callback(seen.append)
    req = drv.move_to({'x': 1.0, 'y': -0.5}, 20, reason='test')
    req.wait(5)
    assert req.status == 'done'
    assert req.final_position == pytest.approx({'x': 1.0, 'y': -0.5, 'z': 0.0})
    assert seen and seen[-1]['x'] == pytest.approx(1.0)
    assert bus[1].actual_position == 200_000


def test_connect_unresponsive_node(bus):
    bus[3].responsive = False
    d = make_driver(bus, retries=1)
    with pytest.raises(CommunicationError, match='node 3'):
        d.connect()
    assert not bus.is_open
    assert d.move_to({'x': 0}, 1).status == 'failed'


def test_stop(bus, drv):
    req = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    drv.stop('test').wait()
    with pytest.raises(MoveStopped):
        req.wait()
    assert wait_until(lambda: not bus[1].in_motion)
    assert bus[1].actual_position < 2_000_000


def test_interrupting_move(bus, drv):
    first = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    second = drv.move_to({'x': 0.25}, 20)
    with pytest.raises(MoveInterrupted):
        first.wait()
    second.wait(5)
    assert bus[1].actual_position == 50_000


def test_interrupting_move_stop_first(bus, drivers):
    d = make_driver(bus)
    d._backend.stop_before_move = True
    d.connect()
    drivers.append(d)
    first = d.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    second = d.move_to({'x': 0.25}, 20)
    with pytest.raises(MoveInterrupted):
        first.wait()
    second.wait(5)
    assert bus[1].actual_position == 50_000


def test_cancel_active_move(bus, drv):
    req = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    req.cancel().wait()
    with pytest.raises(MoveCancelled):
        req.wait()
    assert wait_until(lambda: not bus[1].in_motion)


def test_unphased_move_refused(bus, drivers):
    bus[2]._phased = False
    d = make_driver(bus)
    d.connect()
    drivers.append(d)
    with pytest.raises(RequestFailed, match='not commutated') as err:
        d.move_to({'y': -1.0}, 20).wait()
    assert isinstance(err.value.__cause__, NotCommutatedError)


def test_commutate_asks_on_control_thread(bus, drivers):
    bus[2]._phased = False
    bus[2].registers.update(FAST_PHASE_INIT)
    asked = []
    d = make_driver(bus, confirm_commutation=lambda axes, text: asked.append(threading.current_thread()) or True)
    d.connect()
    drivers.append(d)
    assert d.commutate().wait(10) == {'x': None, 'y': 2048, 'z': None}
    assert asked == [d._ctrl.thread]
    d.move_to({'y': 0.0}, 20).wait(5)
    assert bus[2].actual_position == 0


def test_commutate_declined(bus, drivers):
    bus[2]._phased = False
    d = make_driver(bus)
    d.connect()
    drivers.append(d)
    fut = d.commutate()
    with pytest.raises(MoveCancelled, match='commutate axes x, y, z.*declined by user'):
        fut.wait()
    assert fut.status == 'cancelled' and not bus.commands(name='InitializePhase')


def test_commutate_failure(bus, drivers):
    bus[2]._phased = False
    bus[2].registers.update(FAST_PHASE_INIT)
    bus[2].commutation_min_drive = 30000
    d = make_driver(bus, auto_commutate=True)
    d.connect()
    drivers.append(d)
    with pytest.raises(RequestFailed, match="'commutate axes y' failed>: CommutationError") as err:
        d.commutate(axes=['y']).wait(30)
    assert isinstance(err.value.__cause__, CommutationError)


def test_commutate_does_not_interrupt_move(bus, drv):
    move = drv.move_to({'x': 1.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    assert drv.commutate().wait(5) == {'x': None, 'y': None, 'z': None}
    move.wait(5)
    assert not bus.commands(node=1, name='SetStopMode')


def test_unknown_axes_rejected_at_once(drv):
    for call in (drv.commutate, drv.home, lambda axes: drv.set_enabled(True, axes)):
        with pytest.raises(ValueError, match='unknown'):
            call(['q'])


def test_enable_and_limits(bus, drv):
    assert drv.is_enabled() == {'x': True, 'y': True, 'z': True}
    drv.set_enabled(False, axes=['y'], reason='test').wait()
    assert drv.is_enabled() == {'x': True, 'y': False, 'z': True}
    drv.set_enabled(True, axes=['y']).wait()
    assert drv.get_limits() == {ax: {'neg': False, 'pos': False} for ax in AXES}


def test_port_discovery_runs_on_control_thread(bus, monkeypatch, drivers):
    threads = []

    def find(search):
        threads.append(threading.current_thread())
        return {'COM7': None}
    monkeypatch.setattr(serial_ports, 'find_ports', find)
    d = make_driver(bus, port=None, port_search='moxa')
    d.connect()
    drivers.append(d)
    assert d._ctrl.thread in threads and bus.port == 'COM7'


def test_home_interrupts_move(bus, drivers):
    d = make_driver(bus, homing_speed=50.0, homing_acceleration=2000.0, homing_jerk=1e6)
    d.connect()
    drivers.append(d)
    move = d.move_to({'x': -10.0}, 2)
    fut = d.home(axes=['x'])
    with pytest.raises(MoveInterrupted, match='interrupted by home axes x'):
        move.wait(5)
    assert fut.wait(20)['x'] == pytest.approx(0, abs=1e-5)   # vane at 0 in the old frame
    assert bus[1].actual_position == 0
    assert wait_until(lambda: d.get_position()['x'] == pytest.approx(0, abs=1e-5))
