"""MagellanBackend called directly (no control thread) against the fake bus on a manual clock."""
import pytest

from acq4.drivers.pmdmotion import backend as backend_module
from acq4.drivers.pmdmotion import protocol as p
from acq4.drivers.pmdmotion import serial_ports
from acq4.drivers.pmdmotion.protocol import CommunicationError, NotCommutatedError, PMDError
from acq4.drivers.pmdmotion.tests.fake_bus import FakeMagellanBus
from acq4.drivers.pmdmotion.tests.sim import AXES, CPM, finish, make_backend, move, poll_until
from acq4.drivers.stage import MoveCancelled, MoveState

FAST_PHASE_INIT = {('PhaseInitializeTime',): 100}   # 20 ms per init


@pytest.fixture
def bus(clock):
    return FakeMagellanBus(nodes={1: {'position': 100_000}, 2: {'position': -200_000}, 3: {'position': 0}},
                           clock=clock, transaction_time=0.001)


@pytest.fixture
def opened():
    made = []

    def open_(b):
        b.open()
        made.append(b)
        return b

    yield open_
    for b in made:
        b.close()


@pytest.fixture
def be(bus, opened):
    return opened(make_backend(bus))


def names_since(bus, start, node=None):
    return [c.name for c in bus.log[start:] if node is None or c.node == node]


def _unphased_node(bus, node):
    bus[node]._phased = False
    bus[node].registers.update(FAST_PHASE_INIT)


# ---- connect ----

def test_open_phased(bus, be):
    assert bus.port == 'COMTEST' and bus.baudrate == 57600
    assert be.read_position() == pytest.approx({'x': 0.5, 'y': -1.0, 'z': 0.0})
    assert be.refresh_phasing() == {'x': True, 'y': True, 'z': True}
    assert not bus.commands(name=['SetPosition', 'Update', 'SetOperatingMode', 'SetStopMode'])


def test_open_unphased_never_commutates_or_asks(bus, clock, opened):
    bus[2]._phased = False
    asked = []
    b = make_backend(bus, auto_commutate=True,
                     confirm_commutation=lambda axes, text: asked.append(axes) or True)
    opened(b)
    assert asked == []
    assert not bus.commands(name='InitializePhase')
    with pytest.raises(NotCommutatedError, match='not commutated'):
        b.start_move({'y': -1.0}, 20)     # already there: still refused
    with pytest.raises(NotCommutatedError):
        b.start_move({'x': 0.6, 'y': -1.0}, 20)
    assert move(b, clock, {'x': 0.6}, 20)[0] is MoveState.DONE
    assert bus[1].actual_position == 120_000
    assert not bus.commands(node=2, name=['SetPosition', 'Update'])


@pytest.mark.parametrize('how', ['confirmed', 'auto', 'confirm=False'])
def test_commutate(bus, opened, how):
    _unphased_node(bus, 2)
    asked = []
    b = make_backend(bus, auto_commutate=how == 'auto',
                     confirm_commutation=lambda axes, text: asked.append((axes, text)) or True)
    opened(b)
    kw = {'confirm': False} if how == 'confirm=False' else {}
    assert b.commutate(**kw) == {'x': None, 'y': 2048, 'z': None}
    if how == 'confirmed':
        assert asked[0][0] == ['y'] and 'CANNOT BE INTERRUPTED' in asked[0][1]
        assert 'COMTEST' in asked[0][1]
    else:
        assert asked == []
    assert b.refresh_phasing() == {'x': True, 'y': True, 'z': True}
    assert bus.commands(node=2, name='InitializePhase')
    assert not bus.commands(node=1, name='InitializePhase')


def test_commutate_declined(bus, opened):
    _unphased_node(bus, 2)
    asked = []
    b = make_backend(bus, confirm_commutation=lambda axes, text: asked.append(axes) or False)
    opened(b)
    with pytest.raises(MoveCancelled, match='declined by user'):
        b.commutate()
    assert asked == [['y']] and not bus.commands(name='InitializePhase')
    # nothing to commutate: no question, only phasing read
    n = len(bus.log)
    assert b.commutate(axes=['x']) == {'x': None}
    assert asked == [['y']]
    assert set(names_since(bus, n)) == {'GetActivityStatus'}
    # auto_commutate overridden by confirm=True
    b.auto_commutate = True
    with pytest.raises(MoveCancelled):
        b.commutate(confirm=True)
    assert asked == [['y'], ['y']]


def test_commutate_default_confirmation_is_qt(bus, opened, monkeypatch):
    _unphased_node(bus, 2)
    asked = []
    monkeypatch.setattr(backend_module, 'qt_confirm_commutation', lambda axes, text: asked.append(axes))
    b = make_backend(bus, confirm_commutation=None)
    opened(b)
    with pytest.raises(MoveCancelled):
        b.commutate()
    assert asked == [['y']]


def test_commutate_failure_raises(bus, clock, opened):
    _unphased_node(bus, 2)
    bus[2].commutation_min_drive = 30000
    b = make_backend(bus, auto_commutate=True)
    opened(b)
    with pytest.raises(p.CommutationError):
        b.commutate(axes=['y'])
    assert b.refresh_phasing(['y']) == {'y': False}
    with pytest.raises(NotCommutatedError):
        b.start_move({'y': 0.0}, 20)
    assert move(b, clock, {'x': 0.6}, 20)[0] is MoveState.DONE
    with pytest.raises(ValueError, match='unknown'):
        b.commutate(axes=['q'])


def test_open_unresponsive_node(bus):
    bus[3].responsive = False
    b = make_backend(bus, retries=1)
    with pytest.raises(CommunicationError, match='node 3'):
        b.open()
    b.close()
    assert not bus.is_open


def test_port_busy(bus):
    import serial

    def busy(*args, **kwds):
        raise serial.SerialException("could not open port 'COM12': PermissionError(13, 'Access is denied.')")

    with pytest.raises(CommunicationError, match='another program'):
        make_backend(bus, serial_factory=busy).open()


class _Port:
    def __init__(self, description='', hwid=''):
        self.description, self.hwid = description, hwid


def _ports(monkeypatch, **ports):
    import serial.tools.list_ports as lp
    monkeypatch.setattr(lp, 'comports', lambda: [_mk(k, *v) for k, v in ports.items()])


def _mk(device, description, hwid=''):
    port = _Port(description, hwid)
    port.device = device
    return port


def test_port_search_description(bus, monkeypatch, opened):
    _ports(monkeypatch, COM3=('USB Serial Port',), COM7=('Moxa USB Serial Port', r'MXUPORT\COM\1'))
    b = make_backend(bus, port=None, port_search='moxa')
    opened(b)
    assert bus.port == 'COM7'
    assert 'COM7' in repr(b) and 'COM7' in b.commutation_warning(['x'])


@pytest.mark.parametrize('hwid', ['USB VID:PID=0403:6010 SER=1', r'FTDIBUS\VID_0403+PID_6010+A', r'USB\VID_0403&PID_6010\5'])
def test_port_search_vid_pid(bus, monkeypatch, opened, hwid):
    _ports(monkeypatch, COM3=('Other', 'USB VID:PID=10C4:EA70'), COM5=('Serial', hwid))
    opened(make_backend(bus, port=None, port_search='0403:6010'))
    assert bus.port == 'COM5'


def test_port_search_none_found(bus, monkeypatch):
    _ports(monkeypatch, COM3=('USB Serial Port',))
    with pytest.raises(CommunicationError, match='no serial port'):
        make_backend(bus, port=None, port_search='moxa').open()


def test_port_search_ambiguous(bus, monkeypatch):
    _ports(monkeypatch, COM7=('Moxa A',), COM8=('Moxa B',))
    with pytest.raises(CommunicationError, match='multiple serial ports'):
        make_backend(bus, port=None, port_search='moxa').open()


def test_port_xor_search(bus):
    with pytest.raises(ValueError):
        make_backend(bus, port=None)
    with pytest.raises(ValueError):
        make_backend(bus, port='COM1', port_search='moxa')


def test_rs485_only_when_requested(bus, monkeypatch, opened):
    calls = []
    monkeypatch.setattr(backend_module, 'ensure_rs485_4w', calls.append)
    opened(make_backend(bus))
    assert calls == []
    opened(make_backend(bus, set_rs485_4w=True))
    assert calls == ['COMTEST']


# ---- position ----

def test_counts_per_unit_dict(bus, opened):
    with pytest.raises(NotImplementedError):
        make_backend(bus, counts_per_unit={'x': 100_000, 'y': 200_000, 'z': 1_000})
    b = make_backend(bus, counts_per_unit={'x': 100_000, 'y': 100_000, 'z': 100_000})
    opened(b)
    assert b.read_position() == pytest.approx({'x': 1.0, 'y': -2.0, 'z': 0.0})


def test_position_raw_counts(bus, opened):
    b = make_backend(bus, counts_per_unit=None)
    opened(b)
    pos = b.read_position()
    assert pos == {'x': 100_000, 'y': -200_000, 'z': 0}
    assert all(isinstance(v, int) for v in pos.values())


def test_polling_does_not_flush(bus, be, monkeypatch):
    flushes = []
    monkeypatch.setattr(bus, 'reset_input_buffer', lambda: flushes.append(1))
    for _ in range(10):
        be.read_position()
    assert flushes == []


def test_spurious_position_fails_the_read(bus, be):
    be.read_position()
    bus[1].spurious_position(2)
    for _ in range(2):
        with pytest.raises(CommunicationError, match='axis x'):
            be.read_position()
    assert be.read_position() == pytest.approx({'x': 0.5, 'y': -1.0, 'z': 0.0})


def test_spurious_first_position_fails_the_read(bus, opened):
    bus[2].spurious_position(1)
    b = opened(make_backend(bus))
    with pytest.raises(CommunicationError, match='axis y'):
        b.read_position()
    assert b.read_position() == pytest.approx({'x': 0.5, 'y': -1.0, 'z': 0.0})


# ---- moves ----

def test_move_completes(bus, be, clock):
    start = len(bus.log)
    state, reason, final = move(be, clock, {'x': 1.0, 'y': -0.5}, 20)
    assert state is MoveState.DONE and reason is None
    assert bus[1].actual_position == 200_000 and bus[2].actual_position == -100_000
    assert bus[3].actual_position == 0
    assert final == pytest.approx({'x': 1.0, 'y': -0.5, 'z': 0.0})
    names = names_since(bus, start, node=1)
    for n in ('SetProfileMode', 'SetAcceleration', 'SetJerk', 'SetVelocity', 'SetPosition',
              'ResetEventStatus', 'Update'):
        assert n in names
    assert 'SetStopMode' not in names_since(bus, start)
    assert not bus.commands(node=3, name=['SetPosition', 'Update'])
    assert bus.commands(node=1, name='SetPosition')[-1].args == (200_000,)


def test_linear_speed_scaling(bus, be, clock):
    start = len(bus.log)
    move(be, clock, {'x': 0.5 + 0.3, 'y': -1.0 + 0.4}, 10)
    vel = {c.node: c.args[0] for c in bus.log[start:] if c.name == 'SetVelocity'}
    assert vel[1] == p.encode_velocity(10 * 0.6, CPM)
    assert vel[2] == p.encode_velocity(10 * 0.8, CPM)
    move(be, clock, {'x': 0.5, 'y': -1.0}, {'x': 10, 'y': 10})
    vel = [c.args[0] for c in bus.log if c.name == 'SetVelocity'][-2:]
    assert vel == [p.encode_velocity(10, CPM)] * 2


def test_profile_kwds(bus, be, clock):
    move(be, clock, {'x': 0.6}, 20, acceleration=1000, jerk=1e5, profile='trapezoidal')
    assert bus.commands(node=1, name='SetAcceleration')[-1].args == (p.encode_acceleration(1000, CPM),)
    assert bus.commands(node=1, name='SetJerk')[-1].args == (p.encode_jerk(1e5, CPM),)
    assert bus.commands(node=1, name='SetProfileMode')[-1].args == (p.ProfileMode.TRAPEZOIDAL,)
    # unchanged profile is not resent
    n = len(bus.commands(node=1, name='SetAcceleration'))
    move(be, clock, {'x': 0.5}, 20, acceleration=1000, jerk=1e5, profile='trapezoidal')
    assert len(bus.commands(node=1, name='SetAcceleration')) == n
    with pytest.raises(TypeError):
        be.start_move({'x': 0.6}, 20, bogus=1)
    with pytest.raises(ValueError, match='speed'):
        be.start_move({'x': 0.6}, None)
    with pytest.raises(ValueError, match='unknown'):
        be.start_move({'q': 0.6}, 20)


def test_move_to_current_position(bus, be, clock):
    assert move(be, clock, {'x': 0.5}, 20)[0] is MoveState.DONE
    assert bus[1].actual_position == 100_000


def test_stop(bus, be, clock):
    h = be.start_move({'x': 10.0}, 2)
    assert poll_until(be, clock, lambda: bus[1].in_motion)
    assert be.is_moving(h)
    be.stop('test')
    assert bus.commands(node=1, name='SetStopMode')[-1].args == (p.StopMode.SMOOTH,)
    assert poll_until(be, clock, lambda: not be.is_moving(h))
    assert not bus[1].in_motion
    assert bus[1].actual_position < 2_000_000


def test_velocity_reissued_after_stop(bus, be, clock):
    be.start_move({'x': 10.0}, 2)
    assert poll_until(be, clock, lambda: bus[1].in_motion)
    be.stop('test')
    assert poll_until(be, clock, lambda: not bus[1].in_motion)
    assert bus[1].register('Velocity') == 0
    start = len(bus.log)
    move(be, clock, {'x': 0.5}, 20)
    assert 'SetVelocity' in names_since(bus, start, node=1)
    assert bus[1].actual_position == 100_000


def test_retarget_in_motion(bus, be, clock):
    be.start_move({'x': 10.0}, 2)
    assert poll_until(be, clock, lambda: bus[1].in_motion)
    start = len(bus.log)
    assert move(be, clock, {'x': 0.25}, 20)[0] is MoveState.DONE
    assert 'SetStopMode' not in names_since(bus, start)
    assert bus[1].actual_position == 50_000


def test_scurve_retarget_stops_first(bus, be, clock):
    be.start_move({'x': 10.0}, 2, profile='scurve')
    assert poll_until(be, clock, lambda: bus[1].in_motion)
    start = len(bus.log)
    assert move(be, clock, {'x': 0.25}, 20, profile='scurve')[0] is MoveState.DONE
    names = names_since(bus, start, node=1)
    assert names.index('SetStopMode') < len(names) - 1 - names[::-1].index('Update')
    assert bus[1].actual_position == 50_000


def test_limit_hit_fails_move(bus, be, clock):
    bus[1].stroke = (-5_000_000, 300_000)
    state, reason, _ = move(be, clock, {'x': 5.0}, 20)
    assert state is MoveState.FAILED and 'LimitError' in reason and 'positive' in reason
    assert be.get_limits()['x'] == {'neg': False, 'pos': True}
    # moving into the limit is refused by the IC; moving away works
    with pytest.raises(PMDError) as err:
        move(be, clock, {'x': 5.0}, 20)
    assert err.value.status == p.STATUS_MOVE_INTO_LIMIT
    assert move(be, clock, {'x': 0.5}, 20)[0] is MoveState.DONE
    assert be.get_limits()['x'] == {'neg': False, 'pos': False}


def test_motion_error_fails_move(bus, be, clock):
    h = be.start_move({'x': 10.0}, 2)
    assert poll_until(be, clock, lambda: bus[1].in_motion)
    bus[1].trigger_motion_error()
    state, reason, _ = finish(be, clock, h)
    assert state is MoveState.FAILED and 'MotionError' in reason
    assert be.is_enabled()['x'] is False


def test_trajectory_never_started(bus, be, clock):
    be.settle_timeout = 0.05
    # an active stop-mode left buffered would swallow the move's Update
    bus[1].registers[('StopMode',)] = p.StopMode.SMOOTH
    state, reason, _ = move(be, clock, {'x': 1.0}, 20)
    assert state is MoveState.FAILED and 'never started' in reason


def test_failed_start_stops_axes(bus, be, clock, monkeypatch):
    be.start_move({'x': 10.0}, 2)
    assert poll_until(be, clock, lambda: bus[1].in_motion)
    real = be.axis_write

    def failing(axis, opcode, *args):
        if opcode == p.UPDATE and axis == 'y':
            raise PMDError(4, opcode)
        return real(axis, opcode, *args)

    monkeypatch.setattr(be, 'axis_write', failing)
    with pytest.raises(PMDError, match='invalid parameter'):
        be.start_move({'x': 0.25, 'y': 0.0}, {'x': 20, 'y': 20})
    assert bus.commands(node=1, name='SetStopMode')
    assert poll_until(be, clock, lambda: not bus[1].in_motion)


# ---- transport ----

def test_retry_dropped_and_corrupt(bus, be):
    bus[2].drop_responses(1, opcode=p.GET_EVENT_STATUS)
    assert be.transact(2, p.GET_EVENT_STATUS)[0] == 0
    bus[2].corrupt_checksum(2, opcode=p.GET_EVENT_STATUS)
    assert be.transact(2, p.GET_EVENT_STATUS)[0] == 0
    assert be.axis_read('y', p.GET_ACTUAL_POSITION) == -200_000


def test_retry_exhausted(bus, be):
    bus[2].corrupt_checksum(10, opcode=p.GET_EVENT_STATUS)
    with pytest.raises(CommunicationError, match='GetEventStatus.*node 2'):
        be.transact(2, p.GET_EVENT_STATUS)


def test_unresponsive_node_fails_move(bus, be):
    bus[1].responsive = False
    with pytest.raises(CommunicationError):
        be.start_move({'x': 1.0}, 20)


def test_pmd_error_status(bus, be):
    bus[1].inject_event(1 << p.EventStatus.MOTION_ERROR)
    with pytest.raises(PMDError) as err:
        be.transact(1, p.UPDATE)
    assert err.value.status == p.STATUS_MOVE_WITH_MOTION_ERROR


def test_closed_port(bus, be):
    be.close()
    with pytest.raises(CommunicationError, match='not open'):
        be.read_position()


# ---- enable / limits ----

def test_set_enabled(bus, be, clock):
    assert be.is_enabled() == {'x': True, 'y': True, 'z': True}
    be.set_enabled(False, axes=['y'], reason='test')
    assert bus[2].active_operating_mode == p.OperatingMode.IDLE
    assert be.is_enabled() == {'x': True, 'y': False, 'z': True}
    assert move(be, clock, {'y': 0.0}, 20)[0] is MoveState.FAILED
    be.set_enabled(True, axes=['y'])
    assert bus[2].active_operating_mode == p.OperatingMode.CLOSED_LOOP
    assert move(be, clock, {'y': 0.0}, 20)[0] is MoveState.DONE
    assert bus[2].actual_position == 0


def test_set_enabled_refuses_unphased(bus, be):
    be.set_enabled(False, axes=['z'])
    bus[3]._phased = False
    with pytest.raises(NotCommutatedError):
        be.set_enabled(True)
    with pytest.raises(NotCommutatedError):
        be.start_move({'z': 1.0}, 20)


def test_get_limits(bus, be):
    assert be.get_limits() == {ax: {'neg': False, 'pos': False} for ax in AXES}
    bus[3].set_physical_position(-6_000_000)
    assert be.get_limits()['z'] == {'neg': True, 'pos': False}
