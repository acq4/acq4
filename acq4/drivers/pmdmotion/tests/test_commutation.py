import pytest

from acq4.drivers.pmdmotion import protocol as p
from acq4.drivers.pmdmotion.magellan import MagellanPMD
from acq4.drivers.pmdmotion.protocol import CommutationError, LimitError, NotCommutatedError
from acq4.drivers.pmdmotion.tests.fake_bus import FakeMagellanBus
from acq4.drivers.stage import MoveInterrupted, RequestFailed

AXES = {'x': 1, 'y': 2, 'z': 3}
CPM = 200_000
OM = p.OperatingMode
EV = p.EventStatus
FAST_PHASE_INIT = {('PhaseInitializeTime',): 100}   # 20 ms per init


def make_driver(bus, **kwds):
    opts = dict(port='COMTEST', counts_per_unit=CPM, poll_interval=0.01, serial_factory=bus.open_serial,
                timeout=0.02, resync_delay=0.001)
    opts.update(kwds)
    d = MagellanPMD(dict(AXES), **opts)
    # fast homing so tests run in real time
    d.homing_speed = 50.0
    d.homing_acceleration = 2000.0
    d.homing_jerk = 1e6
    return d


def unphased(registers=None, **kw):
    return dict(phased=False, operating_mode=OM.IDLE, registers={**FAST_PHASE_INIT, **(registers or {})}, **kw)


def connect(d):
    try:
        d.connect()
    except NotCommutatedError:
        pass
    return d


@pytest.fixture
def drivers():
    made = []
    yield made
    for d in made:
        d.close()


def setup(drivers, nodes, **kwds):
    bus = FakeMagellanBus(nodes=nodes, stroke=(-5_000_000, 5_000_000))
    d = connect(make_driver(bus, **kwds))
    drivers.append(d)
    return bus, d


def node_names(bus, node, start=0):
    return [c.name for c in bus.log[start:] if c.node == node]


def first(names, name, after=0):
    return names.index(name, after)


# ---- commutation ----

def test_commutation_sequence(drivers):
    bus, d = setup(drivers, {1: unphased(registers={**FAST_PHASE_INIT, ('EventAction', 1): 8,
                                                   ('EventAction', 2): 8}),
                             2: {}, 3: {}})
    assert d.unphased_axes() == ['x']
    start = len(bus.log)
    result = d.commutate(axes=['x']).wait(10)
    assert result == {'x': 2048}
    assert d.unphased_axes() == []
    assert bus[1].phased and bus[1].active_operating_mode == OM.CLOSED_LOOP

    cmds = [c for c in bus.log[start:] if c.node == 1]
    names = [c.name for c in cmds]
    cal = first(names, 'CalibrateAnalog')
    init = first(names, 'InitializePhase')
    assert cal < init
    assert 'GetDriveStatus' in names[cal:init]
    # limit guard set to 7 before init, restored to the read-back value (8) after
    guard = [i for i, c in enumerate(cmds) if c.name == 'SetEventAction']
    assert [cmds[i].args for i in guard] == [(1, 7), (2, 7), (1, 8), (2, 8)]
    assert guard[1] < init < guard[2]
    assert first(names, 'GetEventAction') < guard[0]
    assert bus[1].register('EventAction', 1) == 8 and bus[1].register('EventAction', 2) == 8
    # open-loop mode and a non-zero drive level immediately before InitializePhase
    before = [c for c in cmds[:init] if c.name in ('SetOperatingMode', 'SetMotorCommand')]
    assert before[-2].name == 'SetOperatingMode' and before[-2].args == (OM.OPEN_LOOP,)
    assert before[-1].name == 'SetMotorCommand' and before[-1].args == (2048,)
    # commutation error bit cleared before the attempt
    resets = [c.args[0] for c in cmds[:init] if c.name == 'ResetEventStatus']
    assert resets and not resets[-1] & (1 << EV.COMMUTATION_ERROR)
    # finalize, ending in full servo
    after = names[init:]
    seq = ['SetActualPosition', 'ClearPositionError', 'Update', 'SetPosition', 'Update',
           'ResetEventStatus', 'SetOperatingMode']
    i = 0
    for n in seq:
        i = first(after, n, i) + 1
    assert [c.args for c in cmds if c.name == 'SetOperatingMode'][-1] == (OM.CLOSED_LOOP,)
    assert not set(names) & {'SetPhaseCounts', 'SetPhasePrescale', 'SetPhaseInitializeTime',
                             'SetMotorType', 'SetMotorLimit', 'SetSignalSense', 'SetPositionErrorLimit',
                             'SetPhaseAngle', 'Reset'}
    # position zeroed where the axis came to rest
    assert d.get_position()['x'] == pytest.approx(0, abs=1e-3)


def test_commutation_escalates(drivers):
    bus, d = setup(drivers, {1: unphased(commutation_min_drive=4096), 2: {}, 3: {}})
    start = len(bus.log)
    assert d.commutate().wait(10) == {'x': 4096, 'y': None, 'z': None}
    cmds = [c for c in bus.log[start:] if c.node == 1]
    assert len([c for c in cmds if c.name == 'InitializePhase']) == 2
    drives = [cmds[i - 1].args[0] for i, c in enumerate(cmds) if c.name == 'InitializePhase']
    assert drives == [2048, 4096]
    # Commutation Error cleared before each attempt
    for i in [i for i, c in enumerate(cmds) if c.name == 'InitializePhase']:
        resets = [c.args[0] for c in cmds[:i] if c.name == 'ResetEventStatus']
        assert not resets[-1] & (1 << EV.COMMUTATION_ERROR)
    assert not bus[1].event_status & (1 << EV.COMMUTATION_ERROR)
    assert not bus.commands(node=2, name='InitializePhase')


@pytest.mark.parametrize('failure', ['error', 'unphased'])
def test_commutation_exhausted(drivers, failure):
    bus, d = setup(drivers, {1: unphased(commutation_min_drive=30000, commutation_failure=failure),
                             2: {}, 3: {}})
    with pytest.raises(RequestFailed) as err:
        d.commutate(axes=['x'], drive_levels=(1000, 2000)).wait(30)
    cause = err.value.__cause__
    assert isinstance(cause, CommutationError) and cause.axes == ['x']
    assert len(bus.commands(node=1, name='InitializePhase')) == 2
    assert bus[1].register('EventAction', 1) == p.EventAction.ABRUPT_STOP
    assert bus[1].register('EventAction', 2) == p.EventAction.ABRUPT_STOP
    assert bus[1].active_operating_mode == OM.IDLE
    assert bus[1].register('MotorCommand') == 0
    # a failed init can leave Phasing Initialized set; the axis must still count as unphased
    assert d.unphased_axes() == ['x']
    with pytest.raises(RequestFailed, match='not commutated'):
        d.move_to({'x': 1.0}, 20).wait(5)
    with pytest.raises(RequestFailed, match='not commutated'):
        d.set_enabled(True, axes=['x']).wait(5)
    with pytest.raises(RequestFailed, match='not commutated'):
        d.home(axes=['x']).wait(5)
    # and a retry is not skipped
    bus[1].commutation_min_drive = 2048
    assert d.commutate(axes=['x']).wait(10) == {'x': 2048}
    assert d.unphased_axes() == []


def test_commutation_limit_aborts(drivers):
    bus, d = setup(drivers, {1: unphased(phase_init_ramps=(-6_000_000, 1_270_016)), 2: {}, 3: {}})
    with pytest.raises(RequestFailed, match='limit') as err:
        d.commutate(axes=['x']).wait(10)
    assert isinstance(err.value.__cause__, CommutationError)
    # no escalation after a limit hit; guard restored
    assert len(bus.commands(node=1, name='InitializePhase')) == 1
    assert bus[1].register('EventAction', 1) == p.EventAction.ABRUPT_STOP
    assert not bus[1].phased


def test_commutation_skips_phased(drivers):
    bus, d = setup(drivers, {1: {}, 2: {}, 3: {}})
    start = len(bus.log)
    assert d.commutate().wait(5) == {'x': None, 'y': None, 'z': None}
    names = {c.name for c in bus.log[start:]}
    assert not names & {'InitializePhase', 'SetEventAction', 'CalibrateAnalog', 'SetOperatingMode',
                        'SetMotorCommand'}


def test_commutate_z_with_sag(drivers):
    # vertical axis: drops when output is removed, then commutates and holds where it rests
    bus, d = setup(drivers, {1: {}, 2: {}, 3: unphased(sag=3_000_000)})
    assert d.commutate(axes=['z']).wait(10) == {'z': 2048}
    assert bus[3].active_operating_mode == OM.CLOSED_LOOP
    assert d.get_position()['z'] == pytest.approx(0, abs=1e-3)
    d.move_to({'z': -1.0}, 20).wait(5)
    assert bus[3].actual_position == -200_000


def test_moves_after_commutate(drivers):
    bus, d = setup(drivers, {1: unphased(), 2: unphased(), 3: {}})
    assert d.commutate().wait(10) == {'x': 2048, 'y': 2048, 'z': None}
    seen = []
    d.set_position_callback(seen.append)
    d.move_to({'x': 1.0, 'y': -0.5}, 20).wait(5)
    assert bus[1].actual_position == 200_000 and bus[2].actual_position == -100_000
    assert seen and seen[-1]['x'] == pytest.approx(1.0)


def test_unknown_axis(drivers):
    bus, d = setup(drivers, {1: {}, 2: {}, 3: {}})
    with pytest.raises(RequestFailed, match='unknown'):
        d.commutate(axes=['q']).wait(5)
    with pytest.raises(RequestFailed, match='unknown'):
        d.home(axes=['q']).wait(5)


# ---- homing ----

HYST = 12_000


def homing_nodes(x_pos, **x_kw):
    return {1: dict(position=x_pos, vane_position=400_000, vane_hysteresis=HYST, **x_kw), 2: {}, 3: {}}


def check_homed(bus, d, start):
    node = bus[1]
    # stopped at the upper switch point, i.e. approached from the negative side
    assert node.physical_position == pytest.approx(400_000 + HYST / 2, abs=2)
    assert node.actual_position == 0
    assert d.get_position()['x'] == pytest.approx(0, abs=1e-5)
    cmds = [c for c in bus.log[start:] if c.node == 1]
    names = [c.name for c in cmds]
    # every arm sets the value before the breakpoint; disarm reverses it
    for i, c in enumerate(cmds):
        if c.name == 'SetBreakpoint' and c.args[1]:
            assert names[i - 1] == 'SetBreakpointValue' and cmds[i - 1].args[1]
            assert c.args == (0, 0x0A20)
        if c.name == 'SetBreakpoint' and not c.args[1]:
            assert names[i + 1] == 'SetBreakpointValue' and cmds[i + 1].args == (0, 0)
    arms = [c.args[1] for c in cmds if c.name == 'SetBreakpointValue' and c.args[1]]
    assert arms[-1] == 0x00400040
    assert node.register('Breakpoint', 0) == 0
    tail = names[len(names) - 1 - names[::-1].index('SetActualPosition'):]
    assert tail[:3] == ['SetActualPosition', 'SetPosition', 'Update']
    assert [c.args for c in cmds if c.name == 'SetProfileMode'][0] == (p.ProfileMode.S_CURVE,)
    # SetVelocity before every move issued during homing
    for i, c in enumerate(cmds):
        if c.name == 'SetPosition' and i + 3 < len(cmds) and names[i + 2] == 'Update':
            assert names[i - 1] == 'SetVelocity'
    return arms


def test_home_from_negative_half(drivers):
    bus, d = setup(drivers, homing_nodes(-200_000))
    start = len(bus.log)
    result = d.home(axes=['x']).wait(20)
    assert result['x'] == pytest.approx((400_000 + HYST / 2) / CPM, abs=1e-5)
    arms = check_homed(bus, d, start)
    assert arms == [0x00400040]


def test_home_from_positive_half(drivers):
    bus, d = setup(drivers, homing_nodes(1_000_000))
    start = len(bus.log)
    d.home(axes=['x']).wait(20)
    arms = check_homed(bus, d, start)
    assert arms == [0x00400000, 0x00400040]
    # backed off 10 mm past the vane before the final approach
    pos = [c.args[0] for c in bus.commands(node=1, name='SetPosition')]
    assert pos[1] == pytest.approx(400_000 - HYST / 2 - 2_000_000, abs=2)


def test_home_from_positive_limit(drivers):
    bus, d = setup(drivers, homing_nodes(5_000_000))
    assert d.get_limits()['x']['pos']
    start = len(bus.log)
    d.home(axes=['x']).wait(20)
    check_homed(bus, d, start)


def test_home_repeatable(drivers):
    bus, d = setup(drivers, homing_nodes(-1_000_000))
    d.home(axes=['x']).wait(20)
    d.move_to({'x': 3.0}, 50).wait(5)
    result = d.home(axes=['x']).wait(20)
    assert result['x'] == pytest.approx(0, abs=1e-5)
    assert bus[1].physical_position == pytest.approx(400_000 + HYST / 2, abs=2)


def test_home_refuses_unphased(drivers):
    bus, d = setup(drivers, {1: unphased(), 2: {}, 3: {}})
    start = len(bus.log)
    with pytest.raises(RequestFailed) as err:
        d.home(axes=['x']).wait(5)
    assert isinstance(err.value.__cause__, NotCommutatedError)
    assert not bus.commands(node=1, name=['SetPosition', 'Update', 'SetBreakpoint'])[0:] or \
        all(c.time < bus.log[start].time for c in bus.commands(node=1, name=['SetBreakpoint']))


def test_home_refuses_disabled(drivers):
    bus, d = setup(drivers, {1: {}, 2: {}, 3: {}})
    d.set_enabled(False, axes=['x']).wait()
    with pytest.raises(RequestFailed, match='not servoing'):
        d.home(axes=['x']).wait(5)


def test_home_limit_is_error(drivers):
    # vane beyond the positive limit: the sweep reaches the limit instead
    bus, d = setup(drivers, {1: dict(position=0, vane_position=6_000_000), 2: {}, 3: {}})
    bus[1].set_physical_position(0)
    with pytest.raises(RequestFailed, match='positive limit') as err:
        d.home(axes=['x']).wait(20)
    assert isinstance(err.value.__cause__, LimitError)
    assert bus[1].register('Breakpoint', 0) == 0
    assert bus[1].register('BreakpointValue', 0) == 0
    # driver still usable
    d.move_to({'x': 0.0}, 50).wait(5)


def test_home_interrupts_move_and_moves_after(drivers):
    bus, d = setup(drivers, homing_nodes(-200_000))
    move = d.move_to({'x': -10.0}, 2)
    fut = d.home(axes=['x'])
    with pytest.raises(MoveInterrupted):
        move.wait(5)
    fut.wait(20)
    assert bus[1].actual_position == 0
    d.move_to({'x': 1.0}, 20, profile='trapezoidal').wait(5)
    assert bus[1].actual_position == 200_000
    # the driver's own profile was re-sent after homing's S-curve
    assert bus.commands(node=1, name='SetProfileMode')[-1].args == (p.ProfileMode.TRAPEZOIDAL,)


def test_commutate_then_home(drivers):
    bus, d = setup(drivers, {1: unphased(position=-300_000, vane_position=0, vane_hysteresis=HYST),
                             2: {}, 3: {}})
    d.commutate(axes=['x']).wait(10)
    d.home(axes=['x']).wait(20)
    assert bus[1].physical_position == pytest.approx(HYST / 2, abs=2)
    assert d.get_position()['x'] == pytest.approx(0, abs=1e-5)
    d.move_to({'x': -2.0}, 20).wait(5)
    assert bus[1].actual_position == -400_000


def test_stale_phased_bit_not_trusted(drivers):
    bus, d = setup(drivers, {1: unphased(commutation_min_drive=4096,
                                         registers={('PhaseInitializeTime',): 2000}), 2: {}, 3: {}})
    node = bus[1]
    real = node._op_InitializePhase

    def keeps_bit0():
        was = node._phased
        real()
        node._phased = was     # IC that leaves bit 0 set from a previous init

    node._op_InitializePhase = keeps_bit0
    assert d.commutate(axes=['x']).wait(20) == {'x': 4096}
    inits = bus.commands(node=1, name='InitializePhase')
    zeros = [c for c in bus.commands(node=1, name='SetMotorCommand') if c.args == (0,) and c.time > inits[1].time]
    assert zeros[0].time - inits[1].time >= 0.95 * p.phase_init_duration(2000)
