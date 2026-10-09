import pytest

from acq4.drivers.pmdmotion import protocol as p
from acq4.drivers.pmdmotion.tests.fake_bus import FakeMagellanBus, ManualClock, SPURIOUS_POSITION

OM = p.OperatingMode
EV = p.EventStatus
CPM = 200000


def xact(bus, node, opcode, *args):
    """Write one command, read header then data; return (status, values) or None on silence."""
    bus.write(p.encode(node, opcode, *args))
    head = bus.read(3)
    if len(head) < 3:
        return None
    raw = head
    if head[1] == 0:
        raw += bus.read(p.response_length(opcode))
    return p.parse_response(opcode, raw, node_id=node)


def get(bus, node, opcode, *args):
    status, values = xact(bus, node, opcode, *args)
    assert status == 0, p.ERROR_CODES.get(status)
    return values[0] if len(values) == 1 else values


def ok(bus, node, opcode, *args):
    status, _ = xact(bus, node, opcode, *args)
    assert status == 0, p.ERROR_CODES.get(status)


def bit(value, n):
    return bool(value & (1 << n))


def load_profile(bus, node, velocity=5.0):
    ok(bus, node, p.SET_PROFILE_MODE, p.ProfileMode.S_CURVE)
    ok(bus, node, p.SET_ACCELERATION, p.encode_acceleration(200, CPM))
    ok(bus, node, p.SET_DECELERATION, p.encode_acceleration(200, CPM))
    ok(bus, node, p.SET_JERK, p.encode_jerk(25000, CPM))
    ok(bus, node, p.SET_VELOCITY, p.encode_velocity(velocity, CPM))


def move(bus, node, target, velocity=5.0):
    ok(bus, node, p.SET_VELOCITY, p.encode_velocity(velocity, CPM))
    ok(bus, node, p.SET_POSITION, target)
    ok(bus, node, p.RESET_EVENT_STATUS, 0xFFFF & ~(1 << EV.MOTION_COMPLETE))
    return xact(bus, node, p.UPDATE)


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def bus(clock):
    return FakeMagellanBus(clock=clock)


def test_serial_interface(bus):
    assert bus.open_serial('COM12', 57600, timeout=0.1) is bus
    assert bus.port == 'COM12' and bus.timeout == 0.1 and bus.is_open
    bus.write(p.encode(1, p.GET_ACTUAL_POSITION))
    assert bus.in_waiting == 7
    bus.reset_input_buffer()
    assert bus.in_waiting == 0
    bus.close()
    assert not bus.is_open
    with pytest.raises(Exception):
        bus.write(p.encode(1, p.GET_ACTUAL_POSITION))


def test_only_addressed_node_responds(bus):
    bus.write(p.encode(2, p.GET_ACTIVITY_STATUS))
    raw = bus.read(5)
    assert raw[0] == 2 and len(raw) == 5
    bus.write(p.encode(9, p.GET_ACTIVITY_STATUS))
    assert bus.in_waiting == 0


def test_concatenated_packets_only_first_answers(bus):
    bus.write(p.encode(1, p.GET_ACTIVITY_STATUS) + p.encode(2, p.GET_ACTIVITY_STATUS))
    raw = bus.read(64)
    assert len(raw) == 5 and raw[0] == 1
    assert [c.node for c in bus.log] == [1]


def test_unknown_opcode_bad_checksum_bad_axis(bus):
    assert xact(bus, 1, 0xFF) == (p.STATUS_INVALID_INSTRUCTION, [])
    pkt = bytearray(p.encode(1, p.GET_EVENT_STATUS))
    pkt[1] ^= 1
    bus.write(pkt)
    assert p.parse_response(p.GET_EVENT_STATUS, bus.read(3)) == (p.STATUS_BAD_CHECKSUM, [])
    bus.write(p.encode(1, p.GET_EVENT_STATUS, axis=1))
    assert p.parse_response(p.GET_EVENT_STATUS, bus.read(3)) == (p.STATUS_INVALID_AXIS, [])


def test_command_log(bus, clock):
    clock.set(5.0)
    ok(bus, 3, p.SET_EVENT_ACTION, 1, 7)
    get(bus, 3, p.GET_ACTUAL_POSITION)
    cmds = bus.commands(node=3)
    assert [(c.name, c.args) for c in cmds] == [('SetEventAction', (1, 7)), ('GetActualPosition', ())]
    assert cmds[0].time == 5.0 and cmds[0].opcode == p.SET_EVENT_ACTION
    assert bus.commands(name='SetEventAction') == cmds[:1]
    bus.clear_log()
    assert bus.log == []


def test_powered_default_state(bus):
    act = get(bus, 1, p.GET_ACTIVITY_STATUS)
    assert bit(act, p.ActivityStatus.PHASING_INITIALIZED)
    assert not bit(act, p.ActivityStatus.IN_MOTION)
    assert get(bus, 1, p.GET_SIGNAL_SENSE) == 0x30
    sig = get(bus, 1, p.GET_SIGNAL_STATUS)
    # limits not engaged read 1 with sense 0x30; position 0 is at the vane
    assert bit(sig, p.SignalStatus.POSITIVE_LIMIT) and bit(sig, p.SignalStatus.NEGATIVE_LIMIT)
    assert get(bus, 1, p.GET_SAMPLE_TIME) == 51
    assert get(bus, 1, p.GET_EVENT_ACTION, 1) == 2
    assert get(bus, 1, p.GET_OPERATING_MODE) == OM.CLOSED_LOOP


def test_move_completes(bus, clock):
    load_profile(bus, 1)
    assert move(bus, 1, CPM) == (0, [])        # 1 mm at 5 mm/s
    clock.advance(0.1)
    act = get(bus, 1, p.GET_ACTIVITY_STATUS)
    assert bit(act, p.ActivityStatus.IN_MOTION)
    assert not bit(get(bus, 1, p.GET_EVENT_STATUS), EV.MOTION_COMPLETE)
    assert 0 < get(bus, 1, p.GET_ACTUAL_POSITION) < CPM
    assert get(bus, 1, p.GET_ACTUAL_VELOCITY) == p.encode_velocity(5, CPM)
    clock.advance(1.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == CPM
    assert not bit(get(bus, 1, p.GET_ACTIVITY_STATUS), p.ActivityStatus.IN_MOTION)
    assert bit(get(bus, 1, p.GET_EVENT_STATUS), EV.MOTION_COMPLETE)
    # other nodes did not move
    assert bus[2].actual_position == 0


def test_set_position_is_buffered_until_update(bus, clock):
    load_profile(bus, 1)
    ok(bus, 1, p.SET_POSITION, CPM)
    clock.advance(1.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == 0
    assert get(bus, 1, p.GET_POSITION) == CPM
    ok(bus, 1, p.UPDATE)
    clock.advance(2.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == CPM


def test_motion_complete_relatches_at_rest(bus, clock):
    ok(bus, 1, p.RESET_EVENT_STATUS, 0xFFFE)
    assert not bit(get(bus, 1, p.GET_EVENT_STATUS), EV.MOTION_COMPLETE)
    clock.advance(0.03)
    assert bit(get(bus, 1, p.GET_EVENT_STATUS), EV.MOTION_COMPLETE)


def test_reset_event_status_mask(bus):
    bus[1].inject_event((1 << EV.BREAKPOINT1) | (1 << EV.COMMUTATION_ERROR))
    ok(bus, 1, p.RESET_EVENT_STATUS, 0xFFFF & ~(1 << EV.BREAKPOINT1))
    ev = get(bus, 1, p.GET_EVENT_STATUS)
    assert not bit(ev, EV.BREAKPOINT1) and bit(ev, EV.COMMUTATION_ERROR)


def test_stop_mode_is_one_shot_and_zeroes_velocity(bus, clock):
    load_profile(bus, 1)
    move(bus, 1, 10 * CPM)
    clock.advance(0.5)
    ok(bus, 1, p.SET_STOP_MODE, p.StopMode.ABRUPT)
    ok(bus, 1, p.UPDATE)
    stopped = get(bus, 1, p.GET_ACTUAL_POSITION)
    clock.advance(1.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == stopped
    assert get(bus, 1, p.GET_STOP_MODE) == 0
    assert get(bus, 1, p.GET_VELOCITY) == 0
    # a move without re-issuing SetVelocity does nothing
    ok(bus, 1, p.SET_POSITION, 0)
    ok(bus, 1, p.UPDATE)
    clock.advance(1.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == stopped
    # buffered stop discards the SetPosition committed by the same Update
    ok(bus, 1, p.SET_VELOCITY, p.encode_velocity(5, CPM))
    ok(bus, 1, p.SET_STOP_MODE, p.StopMode.SMOOTH)
    ok(bus, 1, p.SET_POSITION, 0)
    ok(bus, 1, p.UPDATE)
    clock.advance(2.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == stopped


def test_smooth_stop_decelerates(bus, clock):
    load_profile(bus, 1)
    move(bus, 1, 10 * CPM)
    clock.advance(0.5)
    ok(bus, 1, p.SET_STOP_MODE, p.StopMode.SMOOTH)
    ok(bus, 1, p.UPDATE)
    at_stop = get(bus, 1, p.GET_ACTUAL_POSITION)
    assert bit(get(bus, 1, p.GET_ACTIVITY_STATUS), p.ActivityStatus.IN_MOTION)
    clock.advance(1.0)
    final = get(bus, 1, p.GET_ACTUAL_POSITION)
    # 5 mm/s at 200 mm/s^2 stops in 62.5 um
    assert final - at_stop == pytest.approx(12500, abs=500)
    assert not bit(get(bus, 1, p.GET_ACTIVITY_STATUS), p.ActivityStatus.IN_MOTION)


def test_limit_abrupt_stop_and_move_into_limit(clock):
    bus = FakeMagellanBus(nodes=[1], clock=clock, stroke=(-CPM, CPM))
    load_profile(bus, 1)
    move(bus, 1, 3 * CPM)
    clock.advance(2.0)
    pos = get(bus, 1, p.GET_ACTUAL_POSITION)
    assert pos == pytest.approx(CPM, abs=10)
    act = get(bus, 1, p.GET_ACTIVITY_STATUS)
    assert bit(act, p.ActivityStatus.IN_POSITIVE_LIMIT) and not bit(act, p.ActivityStatus.IN_MOTION)
    assert bit(get(bus, 1, p.GET_EVENT_STATUS), EV.POSITIVE_LIMIT)
    assert not bit(get(bus, 1, p.GET_SIGNAL_STATUS), p.SignalStatus.POSITIVE_LIMIT)
    assert get(bus, 1, p.GET_VELOCITY) == 0
    assert move(bus, 1, 2 * CPM) == (p.STATUS_MOVE_INTO_LIMIT, [])
    assert move(bus, 1, 0) == (0, [])
    clock.advance(1.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == 0


def test_operating_mode_and_disable_action(bus, clock):
    ok(bus, 1, p.SET_OPERATING_MODE, OM.IDLE)
    assert get(bus, 1, p.GET_ACTIVE_OPERATING_MODE) == OM.IDLE
    load_profile(bus, 1)
    move(bus, 1, CPM)
    clock.advance(1.0)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == 0
    ok(bus, 1, p.SET_OPERATING_MODE, OM.CLOSED_LOOP)
    bus[1].trigger_motion_error()
    assert get(bus, 1, p.GET_ACTIVE_OPERATING_MODE) == OM.IDLE
    assert get(bus, 1, p.GET_OPERATING_MODE) == OM.CLOSED_LOOP
    ok(bus, 1, p.RESET_EVENT_STATUS, 0)
    ok(bus, 1, p.RESTORE_OPERATING_MODE)
    assert get(bus, 1, p.GET_ACTIVE_OPERATING_MODE) == OM.CLOSED_LOOP


def test_calibrate_analog(bus, clock):
    ok(bus, 1, p.CALIBRATE_ANALOG, 0)
    assert not bit(get(bus, 1, p.GET_DRIVE_STATUS), p.DriveStatus.CALIBRATED)
    clock.advance(0.1)
    assert bit(get(bus, 1, p.GET_DRIVE_STATUS), p.DriveStatus.CALIBRATED)
    assert get(bus, 1, p.GET_ANALOG_CALIBRATION, 0) == -115


def commutate(bus, clock, node, drive):
    """Spec's commutation sequence up to and including the phase-init wait."""
    ok(bus, node, p.SET_MOTOR_COMMAND, 0)
    ok(bus, node, p.SET_OPERATING_MODE, OM.OPEN_LOOP)
    ok(bus, node, p.CALIBRATE_ANALOG, 0)
    clock.advance(0.1)
    assert bit(get(bus, node, p.GET_DRIVE_STATUS), 0)
    ok(bus, node, p.SET_OPERATING_MODE, OM.IDLE)
    ok(bus, node, p.SET_CURRENT_CONTROL_MODE, 1)
    ok(bus, node, p.SET_EVENT_ACTION, 1, 7)
    ok(bus, node, p.SET_EVENT_ACTION, 2, 7)
    ok(bus, node, p.SET_OPERATING_MODE, OM.OPEN_LOOP)
    ok(bus, node, p.RESET_EVENT_STATUS, 0xFFFF & ~(1 << EV.COMMUTATION_ERROR))
    ok(bus, node, p.SET_MOTOR_COMMAND, drive)
    ok(bus, node, p.INITIALIZE_PHASE)
    duration = p.phase_init_duration(get(bus, node, p.GET_PHASE_INITIALIZE_TIME))
    clock.advance(duration / 2)
    assert not bit(get(bus, node, p.GET_ACTIVITY_STATUS), 0)
    clock.advance(duration / 2 + 0.01)
    return get(bus, node, p.GET_ACTIVITY_STATUS), get(bus, node, p.GET_EVENT_STATUS)


def test_commutation_escalation(clock):
    bus = FakeMagellanBus(nodes=[3], clock=clock, phased=False, operating_mode=OM.IDLE,
                          commutation_min_drive=4096)
    act, ev = commutate(bus, clock, 3, 2048)
    assert bit(act, 0) and bit(ev, EV.COMMUTATION_ERROR)
    start = bus[3].actual_position
    act, ev = commutate(bus, clock, 3, 4096)
    assert bit(act, 0) and not bit(ev, EV.COMMUTATION_ERROR)
    # successful init travels ramp1 + ramp2
    assert bus[3].actual_position - start == pytest.approx(sum(bus[3].phase_init_ramps), abs=1)
    # finalize and close the loop
    ok(bus, 3, p.SET_MOTOR_COMMAND, 0)
    ok(bus, 3, p.SET_ACTUAL_POSITION, 0)
    ok(bus, 3, p.CLEAR_POSITION_ERROR)
    ok(bus, 3, p.UPDATE)
    load_profile(bus, 3)
    ok(bus, 3, p.SET_POSITION, get(bus, 3, p.GET_ACTUAL_POSITION))
    ok(bus, 3, p.UPDATE)
    ok(bus, 3, p.RESET_EVENT_STATUS, 0)
    ok(bus, 3, p.SET_OPERATING_MODE, OM.CLOSED_LOOP)
    ok(bus, 3, p.SET_EVENT_ACTION, 1, 2)
    ok(bus, 3, p.SET_EVENT_ACTION, 2, 2)
    assert get(bus, 3, p.GET_ACTUAL_POSITION) == 0
    move(bus, 3, CPM)
    clock.advance(2.0)
    assert get(bus, 3, p.GET_ACTUAL_POSITION) == CPM
    names = bus.command_names(3)
    assert names.count('InitializePhase') == 2


def test_commutation_unphased_failure(clock):
    bus = FakeMagellanBus(nodes=[1], clock=clock, phased=False, operating_mode=OM.IDLE,
                          commutation_failure='unphased')
    act, ev = commutate(bus, clock, 1, 1000)
    assert not bit(act, 0) and not bit(ev, EV.COMMUTATION_ERROR)


def test_limit_guard_disables_output_during_phase_init(clock):
    bus = FakeMagellanBus(nodes=[1], clock=clock, phased=False, operating_mode=OM.IDLE,
                          stroke=(-500_000, 5_000_000), phase_init_ramps=(-1_000_000, 0))
    act, ev = commutate(bus, clock, 1, 8192)
    assert not bit(act, 0)
    assert bit(ev, EV.NEGATIVE_LIMIT)
    assert get(bus, 1, p.GET_ACTIVE_OPERATING_MODE) == OM.IDLE


def test_limit_abrupt_stop_is_noop_during_phase_init(clock):
    bus = FakeMagellanBus(nodes=[1], clock=clock, phased=False, operating_mode=OM.OPEN_LOOP,
                          stroke=(-500_000, 5_000_000), phase_init_ramps=(-1_000_000, 0),
                          commutation_outcome=lambda drive: 'ok')
    ok(bus, 1, p.SET_MOTOR_COMMAND, 8192)
    ok(bus, 1, p.INITIALIZE_PHASE)
    clock.advance(4.0)
    assert bit(get(bus, 1, p.GET_ACTIVITY_STATUS), 0)
    assert bus[1].physical_position == -600_000     # reached the hard stop
    assert get(bus, 1, p.GET_ACTIVE_OPERATING_MODE) == OM.OPEN_LOOP


def sweep_to_vane(bus, clock, node, distance, want_set):
    ok(bus, node, p.RESET_EVENT_STATUS, 0)
    value = p.breakpoint_level_value(p.SignalStatus.AXIS_IN, want_set)
    word = p.breakpoint_word(p.BreakpointTrigger.SIGNAL_STATUS, p.BreakpointAction.ABRUPT_STOP)
    ok(bus, node, p.SET_BREAKPOINT_VALUE, 0, value)
    ok(bus, node, p.SET_BREAKPOINT, 0, word)
    move(bus, node, get(bus, node, p.GET_ACTUAL_POSITION) + distance)
    for _ in range(100):
        clock.advance(0.1)
        if bit(get(bus, node, p.GET_EVENT_STATUS), EV.BREAKPOINT1):
            break
    assert get(bus, node, p.GET_BREAKPOINT, 0) >> 8 == 0      # trigger cleared on fire
    ok(bus, node, p.SET_BREAKPOINT, 0, 0)
    ok(bus, node, p.SET_BREAKPOINT_VALUE, 0, 0)
    return get(bus, node, p.GET_ACTUAL_POSITION)


def test_homing_with_breakpoint(clock):
    bus = FakeMagellanBus(nodes=[1], clock=clock, position=3 * CPM, vane_position=CPM // 2,
                          vane_hysteresis=12_000)
    load_profile(bus, 1)
    assert bit(get(bus, 1, p.GET_SIGNAL_STATUS), p.SignalStatus.AXIS_IN)
    ok(bus, 1, p.SET_ACTUAL_POSITION, 0)      # arbitrary frame
    low, high = bus[1]._vane_edges()
    stopped = sweep_to_vane(bus, clock, 1, -10 * CPM, False)
    assert not bit(get(bus, 1, p.GET_SIGNAL_STATUS), p.SignalStatus.AXIS_IN)
    assert bus[1].physical_position == pytest.approx(low, abs=1)
    # stop zeroed velocity; offset move needs SetVelocity again (move() re-issues it)
    assert get(bus, 1, p.GET_VELOCITY) == 0
    move(bus, 1, stopped - 2 * CPM)
    clock.advance(2.0)
    sweep_to_vane(bus, clock, 1, 10 * CPM, True)
    assert bus[1].physical_position == pytest.approx(high, abs=1)
    ok(bus, 1, p.SET_ACTUAL_POSITION, 0)
    ok(bus, 1, p.SET_POSITION, 0)
    ok(bus, 1, p.UPDATE)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == 0
    assert get(bus, 1, p.GET_COMMANDED_POSITION) == 0


def test_reset(clock):
    bus = FakeMagellanBus(nodes=[3], clock=clock, position=12345, sag=3_030_000,
                          spurious_reads_after_reset=1)
    ok(bus, 3, p.RESET)
    assert xact(bus, 3, p.GET_VERSION) is None          # silent while rebooting
    clock.advance(0.3)
    assert get(bus, 3, p.GET_ACTUAL_POSITION) == SPURIOUS_POSITION
    assert get(bus, 3, p.GET_ACTUAL_POSITION) == 3_030_000   # re-zeroed, then sagged
    assert not bit(get(bus, 3, p.GET_ACTIVITY_STATUS), 0)
    assert get(bus, 3, p.GET_ACTIVE_OPERATING_MODE) == OM.IDLE


def test_fault_injection(bus, clock):
    bus.timeout = 0.25
    bus[1].drop_responses(1)
    t0 = clock()
    assert xact(bus, 1, p.GET_ACTUAL_POSITION) is None
    assert clock() - t0 == pytest.approx(0.25)       # read waited out the timeout
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == 0

    bus[1].drop_responses(1, opcode=p.SET_POSITION, execute=True)
    assert xact(bus, 1, p.GET_EVENT_STATUS) is not None
    assert xact(bus, 1, p.SET_POSITION, 77) is None
    assert get(bus, 1, p.GET_POSITION) == 77

    bus[2].corrupt_checksum()
    with pytest.raises(p.ChecksumError):
        xact(bus, 2, p.GET_ACTUAL_POSITION)
    assert get(bus, 2, p.GET_ACTUAL_POSITION) == 0

    bus[3].responsive = False
    assert xact(bus, 3, p.GET_ACTUAL_POSITION) is None
    assert bus.commands(node=3)[-1].name == 'GetActualPosition'

    bus[1].spurious_position(2)
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == SPURIOUS_POSITION
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == SPURIOUS_POSITION
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == 0


def test_real_clock_default():
    bus = FakeMagellanBus(nodes=[1])
    bus.timeout = 0.01
    assert get(bus, 1, p.GET_ACTUAL_POSITION) == 0
    bus[1].drop_responses()
    assert xact(bus, 1, p.GET_ACTUAL_POSITION) is None
