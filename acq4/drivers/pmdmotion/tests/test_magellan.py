import time

import pytest

from acq4.drivers.pmdmotion import magellan
from acq4.drivers.pmdmotion import protocol as p
from acq4.drivers.pmdmotion.magellan import MagellanPMD
from acq4.drivers.pmdmotion.protocol import CommunicationError, NotCommutatedError, PMDError
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
def drv(bus):
    d = make_driver(bus)
    d.connect()
    yield d
    d.close()


def wait_until(cond, timeout=2.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.005)
    return False


def names_since(bus, start, node=None):
    return [c.name for c in bus.log[start:] if node is None or c.node == node]


# ---- connect ----

def test_connect_phased(bus, drv):
    assert bus.port == 'COMTEST' and bus.baudrate == 57600
    assert drv.get_position() == pytest.approx({'x': 0.5, 'y': -1.0, 'z': 0.0})
    assert drv.unphased_axes() == []
    assert not bus.commands(name=['SetPosition', 'Update', 'SetOperatingMode', 'SetStopMode'])


def test_connect_unphased_never_commutates_or_asks(bus):
    bus[2]._phased = False
    asked = []
    d = make_driver(bus, auto_commutate=True,
                    confirm_commutation=lambda axes, text: asked.append(axes) or True)
    d.connect()
    try:
        assert asked == []
        assert d.unphased_axes() == ['y']
        assert d.get_position() is not None
        assert not bus.commands(name='InitializePhase')
        with pytest.raises(RequestFailed, match='not commutated') as err:
            d.move_to({'y': -1.0}, 20).wait()     # already there: still refused
        assert isinstance(err.value.__cause__, NotCommutatedError)
        with pytest.raises(RequestFailed, match='not commutated'):
            d.move_to({'x': 0.6, 'y': -1.0}, 20).wait()
        d.move_to({'x': 0.6}, 20).wait()
        assert bus[1].actual_position == 120_000
        assert not bus.commands(node=2, name=['SetPosition', 'Update'])
    finally:
        d.close()


def _unphased_node(bus, node):
    bus[node]._phased = False
    bus[node].registers.update(FAST_PHASE_INIT)


@pytest.mark.parametrize('how', ['confirmed', 'auto', 'confirm=False'])
def test_commutate(bus, how):
    _unphased_node(bus, 2)
    asked = []
    d = make_driver(bus, auto_commutate=how == 'auto',
                    confirm_commutation=lambda axes, text: asked.append((axes, text)) or True)
    d.connect()
    try:
        kw = {'confirm': False} if how == 'confirm=False' else {}
        assert d.commutate(**kw).wait(10) == {'x': None, 'y': 2048, 'z': None}
        if how == 'confirmed':
            assert asked[0][0] == ['y'] and 'CANNOT BE INTERRUPTED' in asked[0][1]
        else:
            assert asked == []
        assert d.unphased_axes() == []
        assert bus.commands(node=2, name='InitializePhase')
        assert not bus.commands(node=1, name='InitializePhase')
    finally:
        d.close()


def test_commutate_declined(bus):
    _unphased_node(bus, 2)
    asked = []
    d = make_driver(bus, confirm_commutation=lambda axes, text: asked.append(axes) or False)
    d.connect()
    try:
        fut = d.commutate()
        assert fut.status == 'cancelled'
        with pytest.raises(MoveCancelled, match='commutate axes x, y, z.*declined by user'):
            fut.wait()
        assert asked == [['y']] and not bus.commands(name='InitializePhase')
        # nothing to commutate: no question, nothing sent
        n = len(bus.log)
        assert d.commutate(axes=['x']).wait() == {'x': None}
        assert asked == [['y']]
        assert set(names_since(bus, n)) == {'GetActivityStatus'}
        # auto_commutate overridden by confirm=True
        d.auto_commutate = True
        with pytest.raises(MoveCancelled):
            d.commutate(confirm=True).wait()
        assert asked == [['y'], ['y']]
    finally:
        d.close()


def test_commutate_failure_raises(bus):
    _unphased_node(bus, 2)
    bus[2].commutation_min_drive = 30000
    d = make_driver(bus, auto_commutate=True)
    d.connect()
    try:
        with pytest.raises(RequestFailed, match="'commutate axes y' failed>: CommutationError") as err:
            d.commutate(axes=['y']).wait(30)
        assert isinstance(err.value.__cause__, p.CommutationError)
        assert d.unphased_axes() == ['y']
        d.move_to({'x': 0.6}, 20).wait()
        with pytest.raises(ValueError, match='unknown'):
            d.commutate(axes=['q'])
    finally:
        d.close()


def test_connect_unresponsive_node(bus):
    bus[3].responsive = False
    d = make_driver(bus, retries=1)
    with pytest.raises(CommunicationError, match='node 3'):
        d.connect()
    assert not bus.is_open
    assert d.move_to({'x': 0}, 1).status == 'failed'


def test_port_busy(bus):
    import serial

    def busy(*args, **kwds):
        raise serial.SerialException("could not open port 'COM12': PermissionError(13, 'Access is denied.')")

    d = make_driver(bus, serial_factory=busy)
    with pytest.raises(CommunicationError, match='another program'):
        d.connect()


def _write_cfg(tmp_path, port):
    sup = tmp_path / 'SupportFolder'
    sup.mkdir()
    (sup / 'Instrument.cfg').write_text(f'[SerialComms1Options]\nbaud=57600\nhwid={port}\n')


def test_port_discovery(bus, tmp_path, monkeypatch):
    _write_cfg(tmp_path, 'COM7')
    calls = []
    monkeypatch.setattr(magellan, '_update_com_port', lambda path: calls.append(path))
    d = make_driver(bus, port=None, motion_synergy_path=str(tmp_path))
    d.connect()
    try:
        assert calls == [str(tmp_path)]
        assert bus.port == 'COM7'
    finally:
        d.close()


def test_port_discovery_error(bus, tmp_path, monkeypatch):
    _write_cfg(tmp_path, 'COM7')
    monkeypatch.setattr(magellan, '_update_com_port', lambda path: 'No Moxa COM ports found')
    d = make_driver(bus, port=None, motion_synergy_path=str(tmp_path))
    with pytest.raises(CommunicationError, match='No Moxa'):
        d.connect()


def test_port_required(bus):
    with pytest.raises(ValueError):
        make_driver(bus, port=None).connect()


# ---- position ----

def test_counts_per_unit_dict(bus):
    with pytest.raises(NotImplementedError):
        make_driver(bus, counts_per_unit={'x': 100_000, 'y': 200_000, 'z': 1_000})
    d = make_driver(bus, counts_per_unit={'x': 100_000, 'y': 100_000, 'z': 100_000})
    d.connect()
    try:
        assert d.get_position() == pytest.approx({'x': 1.0, 'y': -2.0, 'z': 0.0})
    finally:
        d.close()


def test_position_raw_counts(bus):
    d = make_driver(bus, counts_per_unit=None)
    d.connect()
    try:
        pos = d.get_position()
        assert pos == {'x': 100_000, 'y': -200_000, 'z': 0}
        assert all(isinstance(v, int) for v in pos.values())
    finally:
        d.close()


def test_polling_does_not_flush(bus, drv, monkeypatch):
    flushes = []
    monkeypatch.setattr(bus, 'reset_input_buffer', lambda: flushes.append(1))
    n = len(bus.log)
    assert wait_until(lambda: len(bus.commands(name='GetActualPosition')) > n + 9)
    assert flushes == []


def test_spurious_position_filtered(bus, drv):
    seen = []
    drv.set_position_callback(lambda pos: seen.append(pos['x']))
    bus[1].spurious_position(2)
    n = len(bus.commands(node=1, name='GetActualPosition'))
    assert wait_until(lambda: len(bus.commands(node=1, name='GetActualPosition')) > n + 4)
    assert all(abs(v) < 1 for v in seen)
    assert drv.get_position()['x'] == pytest.approx(0.5)


# ---- moves ----

def test_move_completes(bus, drv):
    start = len(bus.log)
    req = drv.move_to({'x': 1.0, 'y': -0.5}, 20, reason='test')
    req.wait(5)
    assert req.status == 'done'
    assert bus[1].actual_position == 200_000 and bus[2].actual_position == -100_000
    assert bus[3].actual_position == 0
    assert req.final_position == pytest.approx({'x': 1.0, 'y': -0.5, 'z': 0.0})
    names = names_since(bus, start, node=1)
    for n in ('SetProfileMode', 'SetAcceleration', 'SetJerk', 'SetVelocity', 'SetPosition',
              'ResetEventStatus', 'Update'):
        assert n in names
    assert 'SetStopMode' not in names_since(bus, start)
    assert not bus.commands(node=3, name=['SetPosition', 'Update'])
    assert bus.commands(node=1, name='SetPosition')[-1].args == (200_000,)


def test_linear_speed_scaling(bus, drv):
    start = len(bus.log)
    drv.move_to({'x': 0.5 + 0.3, 'y': -1.0 + 0.4}, 10).wait(5)
    vel = {c.node: c.args[0] for c in bus.log[start:] if c.name == 'SetVelocity'}
    assert vel[1] == p.encode_velocity(10 * 0.6, CPM)
    assert vel[2] == p.encode_velocity(10 * 0.8, CPM)
    drv.move_to({'x': 0.5, 'y': -1.0}, {'x': 10, 'y': 10}).wait(5)
    vel = [c.args[0] for c in bus.log if c.name == 'SetVelocity'][-2:]
    assert vel == [p.encode_velocity(10, CPM)] * 2


def test_profile_kwds(bus, drv):
    drv.move_to({'x': 0.6}, 20, acceleration=1000, jerk=1e5, profile='trapezoidal').wait(5)
    assert bus.commands(node=1, name='SetAcceleration')[-1].args == (p.encode_acceleration(1000, CPM),)
    assert bus.commands(node=1, name='SetJerk')[-1].args == (p.encode_jerk(1e5, CPM),)
    assert bus.commands(node=1, name='SetProfileMode')[-1].args == (p.ProfileMode.TRAPEZOIDAL,)
    # unchanged profile is not resent
    n = len(bus.commands(node=1, name='SetAcceleration'))
    drv.move_to({'x': 0.5}, 20, acceleration=1000, jerk=1e5, profile='trapezoidal').wait(5)
    assert len(bus.commands(node=1, name='SetAcceleration')) == n


def test_move_to_current_position(bus, drv):
    drv.move_to({'x': 0.5}, 20).wait(5)
    assert bus[1].actual_position == 100_000


def test_stop(bus, drv):
    req = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    drv.stop('test').wait()
    with pytest.raises(MoveStopped):
        req.wait()
    assert bus.commands(node=1, name='SetStopMode')[-1].args == (p.StopMode.SMOOTH,)
    assert wait_until(lambda: not bus[1].in_motion)
    assert bus[1].actual_position < 2_000_000


def test_velocity_reissued_after_stop(bus, drv):
    req = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    drv.stop().wait()
    assert wait_until(lambda: not bus[1].in_motion)
    assert bus[1].register('Velocity') == 0
    start = len(bus.log)
    drv.move_to({'x': 0.5}, 20).wait(5)
    assert 'SetVelocity' in names_since(bus, start, node=1)
    assert bus[1].actual_position == 100_000


def test_interrupting_move(bus, drv):
    first = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    start = len(bus.log)
    second = drv.move_to({'x': 0.25}, 20)
    with pytest.raises(MoveInterrupted):
        first.wait()
    second.wait(5)
    assert 'SetStopMode' not in names_since(bus, start)
    assert bus[1].actual_position == 50_000


def test_interrupting_move_stop_first(bus):
    d = make_driver(bus)
    d.stop_before_move = True
    d.connect()
    try:
        first = d.move_to({'x': 10.0}, 2)
        assert wait_until(lambda: bus[1].in_motion)
        second = d.move_to({'x': 0.25}, 20)
        with pytest.raises(MoveInterrupted):
            first.wait()
        second.wait(5)
        assert bus[1].actual_position == 50_000
    finally:
        d.close()


def test_limit_hit_fails_move(bus, drv):
    bus[1].stroke = (-5_000_000, 300_000)
    req = drv.move_to({'x': 5.0}, 20)
    with pytest.raises(RequestFailed, match='LimitError.*positive'):
        req.wait(5)
    assert drv.get_limits()['x'] == {'neg': False, 'pos': True}
    # moving into the limit is refused by the IC; moving away works
    with pytest.raises(RequestFailed) as err:
        drv.move_to({'x': 5.0}, 20).wait(5)
    assert isinstance(err.value.__cause__, PMDError)
    assert err.value.__cause__.status == p.STATUS_MOVE_INTO_LIMIT
    drv.move_to({'x': 0.5}, 20).wait(5)
    assert drv.get_limits()['x'] == {'neg': False, 'pos': False}


def test_motion_error_fails_move(bus, drv):
    req = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    bus[1].trigger_motion_error()
    with pytest.raises(RequestFailed, match='MotionError'):
        req.wait(5)
    assert drv.is_enabled()['x'] is False


def test_trajectory_never_started(bus, drv):
    drv.settle_timeout = 0.05
    # an active stop-mode left buffered would swallow the move's Update
    bus[1].registers[('StopMode',)] = p.StopMode.SMOOTH
    with pytest.raises(RequestFailed, match='never started'):
        drv.move_to({'x': 1.0}, 20).wait(5)


# ---- transport ----

def on_ctrl(drv, fn, *args):
    """Run fn on the driver's control thread; re-raise its exception."""
    try:
        return drv._submit(fn, *args).wait()
    except RequestFailed as exc:
        raise exc.__cause__


def test_retry_dropped_and_corrupt(bus, drv):
    bus[2].drop_responses(1, opcode=p.GET_EVENT_STATUS)
    assert on_ctrl(drv, drv.transact, 2, p.GET_EVENT_STATUS)[0] == 0
    bus[2].corrupt_checksum(2, opcode=p.GET_EVENT_STATUS)
    assert on_ctrl(drv, drv.transact, 2, p.GET_EVENT_STATUS)[0] == 0
    assert on_ctrl(drv, drv.axis_read, 'y', p.GET_ACTUAL_POSITION) == -200_000


def test_retry_exhausted(bus, drv):
    bus[2].corrupt_checksum(10, opcode=p.GET_EVENT_STATUS)
    with pytest.raises(CommunicationError, match='GetEventStatus.*node 2'):
        on_ctrl(drv, drv.transact, 2, p.GET_EVENT_STATUS)


def test_unresponsive_node_fails_move(bus, drv):
    bus[1].responsive = False
    with pytest.raises(RequestFailed) as err:
        drv.move_to({'x': 1.0}, 20).wait(5)
    assert isinstance(err.value.__cause__, CommunicationError)


def test_pmd_error_status(bus, drv):
    bus[1].inject_event(1 << p.EventStatus.MOTION_ERROR)
    with pytest.raises(PMDError) as err:
        on_ctrl(drv, drv.transact, 1, p.UPDATE)
    assert err.value.status == p.STATUS_MOVE_WITH_MOTION_ERROR


# ---- enable / limits ----

def test_set_enabled(bus, drv):
    assert drv.is_enabled() == {'x': True, 'y': True, 'z': True}
    drv.set_enabled(False, axes=['y'], reason='test').wait()
    assert bus[2].active_operating_mode == p.OperatingMode.IDLE
    assert drv.is_enabled() == {'x': True, 'y': False, 'z': True}
    with pytest.raises(RequestFailed):
        drv.move_to({'y': 0.0}, 20).wait(5)
    drv.set_enabled(True, axes=['y']).wait()
    assert bus[2].active_operating_mode == p.OperatingMode.CLOSED_LOOP
    drv.move_to({'y': 0.0}, 20).wait(5)
    assert bus[2].actual_position == 0


def test_set_enabled_refuses_unphased(bus, drv):
    drv.set_enabled(False, axes=['z']).wait()
    bus[3]._phased = False
    with pytest.raises(RequestFailed, match='not commutated'):
        drv.set_enabled(True).wait()
    assert drv.unphased_axes() == ['z']


def test_get_limits(bus, drv):
    assert drv.get_limits() == {ax: {'neg': False, 'pos': False} for ax in AXES}
    bus[3].set_physical_position(-6_000_000)
    assert drv.get_limits()['z'] == {'neg': True, 'pos': False}


def test_scurve_interrupt_stops_first(bus, drv):
    first = drv.move_to({'x': 10.0}, 2, profile='scurve')
    assert wait_until(lambda: bus[1].in_motion)
    start = len(bus.log)
    second = drv.move_to({'x': 0.25}, 20, profile='scurve')
    with pytest.raises(MoveInterrupted):
        first.wait()
    second.wait(5)
    names = names_since(bus, start, node=1)
    assert names.index('SetStopMode') < len(names) - 1 - names[::-1].index('Update')
    assert bus[1].actual_position == 50_000


def test_failed_send_stops_axes(bus, drv, monkeypatch):
    first = drv.move_to({'x': 10.0}, 2)
    assert wait_until(lambda: bus[1].in_motion)
    real = drv.axis_write

    def failing(axis, opcode, *args):
        if opcode == p.UPDATE and axis == 'y':
            raise PMDError(4, opcode)
        return real(axis, opcode, *args)

    monkeypatch.setattr(drv, 'axis_write', failing)
    with pytest.raises(RequestFailed, match='invalid parameter'):
        drv.move_to({'x': 0.25, 'y': 0.0}, {'x': 20, 'y': 20}).wait(5)
    with pytest.raises(MoveInterrupted):
        first.wait()
    assert bus.commands(node=1, name='SetStopMode')
    assert wait_until(lambda: not bus[1].in_motion)
