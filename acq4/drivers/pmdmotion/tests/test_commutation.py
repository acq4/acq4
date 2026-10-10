"""Commutation and homing on MagellanBackend, called directly against the fake bus on a manual clock."""
import pytest

from acq4.drivers.pmdmotion import protocol as p
from acq4.drivers.pmdmotion.protocol import CommutationError, LimitError, MagellanError, NotCommutatedError
from acq4.drivers.pmdmotion.tests.fake_bus import FakeMagellanBus
from acq4.drivers.pmdmotion.tests.sim import CPM, make_backend, move
from acq4.drivers.stage import MoveState

OM = p.OperatingMode
EV = p.EventStatus
FAST_PHASE_INIT = {('PhaseInitializeTime',): 100}   # 20 ms per init
# fast homing keeps the simulated sweeps short
HOMING = dict(homing_speed=50.0, homing_acceleration=2000.0, homing_jerk=1e6)


def unphased(registers=None, **kw):
    return dict(phased=False, operating_mode=OM.IDLE, registers={**FAST_PHASE_INIT, **(registers or {})}, **kw)


@pytest.fixture
def setup(clock):
    """setup(nodes, **kwds) -> (bus, backend): opened, approving every commutation."""
    made = []

    def make(nodes, **kwds):
        bus = FakeMagellanBus(nodes=nodes, stroke=(-5_000_000, 5_000_000), clock=clock, transaction_time=0.001)
        b = make_backend(bus, **{**HOMING, 'confirm_commutation': lambda axes, text: True, **kwds})
        b.open()
        made.append(b)
        return bus, b

    yield make
    for b in made:
        b.close()


def unphased_axes(b):
    return [ax for ax, ok in b.refresh_phasing().items() if not ok]


def position(b):
    return b.read_position()


def node_names(bus, node, start=0):
    return [c.name for c in bus.log[start:] if c.node == node]


def first(names, name, after=0):
    return names.index(name, after)


# ---- commutation ----

def test_commutation_sequence(setup):
    bus, d = setup({1: unphased(registers={**FAST_PHASE_INIT, ('EventAction', 1): 8,
                                         ('EventAction', 2): 8}),
                   2: {}, 3: {}})
    assert unphased_axes(d) == ['x']
    start = len(bus.log)
    result = d.commutate(axes=['x'])
    assert result == {'x': 2048}
    assert unphased_axes(d) == []
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
    assert position(d)['x'] == pytest.approx(0, abs=1e-3)


def test_commutation_escalates(setup):
    bus, d = setup({1: unphased(commutation_min_drive=4096), 2: {}, 3: {}})
    start = len(bus.log)
    assert d.commutate() == {'x': 4096, 'y': None, 'z': None}
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
def test_commutation_exhausted(setup, failure):
    bus, d = setup({1: unphased(commutation_min_drive=30000, commutation_failure=failure),
                   2: {}, 3: {}})
    with pytest.raises(CommutationError) as err:
        d.commutate(axes=['x'], drive_levels=(1000, 2000))
    assert err.value.axes == ['x']
    assert len(bus.commands(node=1, name='InitializePhase')) == 2
    assert bus[1].register('EventAction', 1) == p.EventAction.ABRUPT_STOP
    assert bus[1].register('EventAction', 2) == p.EventAction.ABRUPT_STOP
    assert bus[1].active_operating_mode == OM.IDLE
    assert bus[1].register('MotorCommand') == 0
    # a failed init can leave Phasing Initialized set; the axis must still count as unphased
    assert unphased_axes(d) == ['x']
    with pytest.raises(NotCommutatedError):
        move(d, bus.clock, {'x': 1.0}, 20)
    with pytest.raises(NotCommutatedError):
        d.set_enabled(True, axes=['x'])
    with pytest.raises(NotCommutatedError):
        d.home(axes=['x'])
    # and a retry is not skipped
    bus[1].commutation_min_drive = 2048
    assert d.commutate(axes=['x']) == {'x': 2048}
    assert unphased_axes(d) == []


def test_commutation_limit_aborts(setup):
    bus, d = setup({1: unphased(phase_init_ramps=(-6_000_000, 1_270_016)), 2: {}, 3: {}})
    with pytest.raises(CommutationError, match='limit'):
        d.commutate(axes=['x'])
    # no escalation after a limit hit; guard restored
    assert len(bus.commands(node=1, name='InitializePhase')) == 1
    assert bus[1].register('EventAction', 1) == p.EventAction.ABRUPT_STOP
    assert not bus[1].phased


def test_commutation_skips_phased(setup):
    bus, d = setup({1: {}, 2: {}, 3: {}})
    start = len(bus.log)
    assert d.commutate() == {'x': None, 'y': None, 'z': None}
    names = {c.name for c in bus.log[start:]}
    assert not names & {'InitializePhase', 'SetEventAction', 'CalibrateAnalog', 'SetOperatingMode',
                        'SetMotorCommand'}


def test_commutate_z_with_sag(setup):
    # vertical axis: drops when output is removed, then commutates and holds where it rests
    bus, d = setup({1: {}, 2: {}, 3: unphased(sag=3_000_000)})
    assert d.commutate(axes=['z']) == {'z': 2048}
    assert bus[3].active_operating_mode == OM.CLOSED_LOOP
    assert position(d)['z'] == pytest.approx(0, abs=1e-3)
    move(d, bus.clock, {'z': -1.0}, 20)
    assert bus[3].actual_position == -200_000


def test_moves_after_commutate(setup):
    bus, d = setup({1: unphased(), 2: unphased(), 3: {}})
    assert d.commutate() == {'x': 2048, 'y': 2048, 'z': None}
    assert move(d, bus.clock, {'x': 1.0, 'y': -0.5}, 20)[0] is MoveState.DONE
    assert bus[1].actual_position == 200_000 and bus[2].actual_position == -100_000


def test_unknown_axis(setup):
    bus, d = setup({1: {}, 2: {}, 3: {}})
    with pytest.raises(ValueError, match='unknown'):
        d.commutate(axes=['q'])
    with pytest.raises(ValueError, match='unknown'):
        d.home(axes=['q'])


# ---- homing ----

HYST = 12_000


def homing_nodes(x_pos, **x_kw):
    return {1: dict(position=x_pos, vane_position=400_000, vane_hysteresis=HYST, **x_kw), 2: {}, 3: {}}


def check_homed(bus, d, start):
    node = bus[1]
    # stopped at the upper switch point, i.e. approached from the negative side
    assert node.physical_position == pytest.approx(400_000 + HYST / 2, abs=2)
    assert node.actual_position == 0
    assert position(d)['x'] == pytest.approx(0, abs=1e-5)
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


def test_home_from_negative_half(setup):
    bus, d = setup(homing_nodes(-200_000))
    start = len(bus.log)
    result = d.home(axes=['x'])
    assert result['x'] == pytest.approx((400_000 + HYST / 2) / CPM, abs=1e-5)
    arms = check_homed(bus, d, start)
    assert arms == [0x00400040]


def test_home_from_positive_half(setup):
    bus, d = setup(homing_nodes(1_000_000))
    start = len(bus.log)
    d.home(axes=['x'])
    arms = check_homed(bus, d, start)
    assert arms == [0x00400000, 0x00400040]
    # backed off 10 mm past the vane before the final approach
    pos = [c.args[0] for c in bus.commands(node=1, name='SetPosition')]
    assert pos[1] == pytest.approx(400_000 - HYST / 2 - 2_000_000, abs=2)


def test_home_from_positive_limit(setup):
    bus, d = setup(homing_nodes(5_000_000))
    assert d.get_limits()['x']['pos']
    start = len(bus.log)
    d.home(axes=['x'])
    check_homed(bus, d, start)


def test_home_repeatable(setup):
    bus, d = setup(homing_nodes(-1_000_000))
    d.home(axes=['x'])
    move(d, bus.clock, {'x': 3.0}, 50)
    result = d.home(axes=['x'])
    assert result['x'] == pytest.approx(0, abs=1e-5)
    assert bus[1].physical_position == pytest.approx(400_000 + HYST / 2, abs=2)


def test_home_refuses_unphased(setup):
    bus, d = setup({1: unphased(), 2: {}, 3: {}})
    start = len(bus.log)
    with pytest.raises(NotCommutatedError):
        d.home(axes=['x'])
    assert not bus.commands(node=1, name=['SetPosition', 'Update', 'SetBreakpoint'])[0:] or \
        all(c.time < bus.log[start].time for c in bus.commands(node=1, name=['SetBreakpoint']))


def test_home_refuses_disabled(setup):
    bus, d = setup({1: {}, 2: {}, 3: {}})
    d.set_enabled(False, ['x'])
    with pytest.raises(MagellanError, match='not servoing'):
        d.home(axes=['x'])


def test_home_limit_is_error(setup):
    # vane beyond the positive limit: the sweep reaches the limit instead
    bus, d = setup({1: dict(position=0, vane_position=6_000_000), 2: {}, 3: {}})
    bus[1].set_physical_position(0)
    with pytest.raises(LimitError, match='positive limit'):
        d.home(axes=['x'])
    assert bus[1].register('Breakpoint', 0) == 0
    assert bus[1].register('BreakpointValue', 0) == 0
    # backend still usable
    assert move(d, bus.clock, {'x': 0.0}, 50)[0] is MoveState.DONE


def test_home_stops_motion_and_moves_after(setup):
    bus, d = setup(homing_nodes(-200_000))
    d.start_move({'x': -10.0}, 2)
    bus.clock.advance(0.05)
    assert bus[1].in_motion
    d.home(axes=['x'])
    assert bus[1].actual_position == 0
    move(d, bus.clock, {'x': 1.0}, 20, profile='trapezoidal')
    assert bus[1].actual_position == 200_000
    # the move's own profile was re-sent after homing's S-curve
    assert bus.commands(node=1, name='SetProfileMode')[-1].args == (p.ProfileMode.TRAPEZOIDAL,)


def test_commutate_then_home(setup):
    bus, d = setup({1: unphased(position=-300_000, vane_position=0, vane_hysteresis=HYST),
                   2: {}, 3: {}})
    d.commutate(axes=['x'])
    d.home(axes=['x'])
    assert bus[1].physical_position == pytest.approx(HYST / 2, abs=2)
    assert position(d)['x'] == pytest.approx(0, abs=1e-5)
    move(d, bus.clock, {'x': -2.0}, 20)
    assert bus[1].actual_position == -400_000


def test_stale_phased_bit_not_trusted(setup):
    bus, d = setup({1: unphased(commutation_min_drive=4096,
                               registers={('PhaseInitializeTime',): 2000}), 2: {}, 3: {}})
    node = bus[1]
    real = node._op_InitializePhase

    def keeps_bit0():
        was = node._phased
        real()
        node._phased = was     # IC that leaves bit 0 set from a previous init

    node._op_InitializePhase = keeps_bit0
    assert d.commutate(axes=['x']) == {'x': 4096}
    inits = bus.commands(node=1, name='InitializePhase')
    zeros = [c for c in bus.commands(node=1, name='SetMotorCommand') if c.args == (0,) and c.time > inits[1].time]
    assert zeros[0].time - inits[1].time >= 0.95 * p.phase_init_duration(2000)
