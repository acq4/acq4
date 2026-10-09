import pytest

from acq4.drivers.pmdmotion import protocol as p


def _response(node, status, data=b''):
    head = bytes((node, status))
    return head + bytes((p.checksum(head + data),)) + data


def test_checksum_makes_packet_sum_to_zero():
    payload = bytes((1, 0, 0x37))
    chk = p.checksum(payload)
    assert (sum(payload) + chk) & 0xFF == 0
    assert p.checksum(b'') == 0
    assert p.checksum(bytes((0xFF,))) == 1


def test_encode_layout():
    pkt = p.encode(2, p.GET_ACTUAL_POSITION)
    assert pkt == bytes((2, p.checksum(bytes((2, 0, 0x37))), 0, 0x37))
    assert sum(pkt) & 0xFF == 0


def test_encode_arguments_big_endian():
    pkt = p.encode(1, p.SET_POSITION, -2)
    assert pkt[0] == 1 and pkt[2] == 0 and pkt[3] == p.SET_POSITION
    assert pkt[4:] == (-2).to_bytes(4, 'big', signed=True)
    assert sum(pkt) & 0xFF == 0

    pkt = p.encode(3, p.SET_BREAKPOINT_VALUE, 0, 0x00400040)
    assert pkt[4:] == bytes((0, 0, 0x00, 0x40, 0x00, 0x40))

    pkt = p.encode(1, p.SET_EVENT_ACTION, 1, 7, axis=1)
    assert pkt[2] == 1 and pkt[4:] == bytes((0, 1, 0, 7))


def test_encode_rejects_bad_arguments():
    with pytest.raises(ValueError):
        p.encode(1, p.SET_POSITION)
    with pytest.raises(ValueError):
        p.encode(1, p.SET_OPERATING_MODE, 0x10000)
    with pytest.raises(ValueError):
        p.encode(1, p.SET_MOTOR_COMMAND, 40000)


def test_response_length_is_data_bytes():
    assert p.response_length(p.GET_ACTUAL_POSITION) == 4
    assert p.response_length(p.GET_ACTIVITY_STATUS) == 2
    assert p.response_length(p.UPDATE) == 0
    assert p.response_length(p.GET_SAMPLE_TIME) == 4
    assert p.response_length(p.GET_AXIS_OUT_MASK) == 6
    assert p.packet_length(p.GET_ACTUAL_POSITION) == 7
    assert p.packet_length(p.GET_ACTUAL_POSITION, status=4) == 3
    with pytest.raises(KeyError):
        p.response_length(0xFF)


@pytest.mark.parametrize('opcode,values', [
    (p.GET_ACTUAL_POSITION, [-123456]),
    (p.GET_ACTUAL_POSITION, [2 ** 28]),
    (p.GET_EVENT_STATUS, [0x0801]),
    (p.GET_MOTOR_COMMAND, [-2118]),
    (p.GET_AXIS_OUT_MASK, [1, 2, 3]),
    (p.UPDATE, []),
])
def test_parse_round_trip(opcode, values):
    data = p.pack_values(p.response_widths(opcode), values)
    status, out = p.parse_response(opcode, _response(1, 0, data), node_id=1)
    assert status == 0
    assert out == values


def test_error_status_response_is_three_bytes():
    raw = _response(2, 14)
    assert len(raw) == 3
    status, values = p.parse_response(p.UPDATE, raw)
    assert (status, values) == (14, [])
    # error status responses carry no data even for opcodes that return data
    assert p.parse_response(p.GET_ACTUAL_POSITION, raw) == (14, [])
    with pytest.raises(p.CommunicationError):
        p.parse_response(p.GET_ACTUAL_POSITION, _response(2, 14, b'\x00\x01'))


def test_check_status_raises_pmd_error():
    p.check_status(0, p.UPDATE)
    with pytest.raises(p.PMDError) as info:
        p.check_status(14, p.UPDATE)
    assert info.value.status == 14
    assert info.value.opcode == p.UPDATE
    assert 'Update' in str(info.value) and 'limit' in str(info.value)


def test_checksum_error_carries_raw():
    raw = bytearray(_response(1, 0, (1000).to_bytes(4, 'big')))
    good = raw[2]
    raw[2] ^= 0x01
    with pytest.raises(p.ChecksumError) as info:
        p.parse_response(p.GET_ACTUAL_POSITION, raw)
    assert info.value.expected == good
    assert info.value.actual == good ^ 0x01
    assert info.value.raw == bytes(raw)


def test_parse_rejects_short_wrong_length_and_wrong_node():
    with pytest.raises(p.CommunicationError):
        p.parse_response(p.GET_ACTUAL_POSITION, b'\x01\x00')
    with pytest.raises(p.CommunicationError):
        p.parse_response(p.GET_ACTUAL_POSITION, _response(1, 0, b'\x00\x01'))
    with pytest.raises(p.CommunicationError):
        p.parse_response(p.GET_EVENT_STATUS, _response(2, 0, b'\x00\x01'), node_id=1)


def test_exceptions_name_axes():
    err = p.NotCommutatedError(['x', 'z'])
    assert err.axes == ['x', 'z']
    assert 'x' in str(err) and 'z' in str(err)
    assert isinstance(err, p.MagellanError)
    assert p.CommutationError(axes=['y']).axes == ['y']
    assert p.LimitError('hit', axes=['x']).axes == ['x']
    for cls in (p.PMDError, p.ChecksumError, p.CommunicationError, p.LimitError):
        assert issubclass(cls, p.MagellanError)


def test_scaling_golden_values():
    # MotionSynergy's wire values for a 5 nm/count stage at 51.2 us.
    assert p.SAMPLE_TIME_S == 51.2e-6
    assert p.encode_velocity(5, 200000) == 3355443
    assert p.encode_acceleration(200, 200000) == 6872
    assert p.encode_jerk(25000, 200000) == 2882304


def test_scaling_decode_inverts_encode():
    v = p.encode_velocity(5, 200000)
    assert p.decode_velocity(v) == pytest.approx(5 * 200000, rel=1e-6)
    a = p.encode_acceleration(200, 200000)
    assert p.decode_acceleration(a) == pytest.approx(200 * 200000, rel=1e-3)


def test_breakpoint_packing():
    assert p.breakpoint_word(p.BreakpointTrigger.SIGNAL_STATUS, p.BreakpointAction.ABRUPT_STOP) == 0x0A20
    assert p.breakpoint_level_value(p.SignalStatus.AXIS_IN, True) == 0x00400040
    assert p.breakpoint_level_value(p.SignalStatus.AXIS_IN, False) == 0x00400000


def test_operating_modes_and_phase_bounds():
    assert p.OperatingMode.IDLE == 0x01
    assert p.OperatingMode.OPEN_LOOP == 0x03
    assert p.OperatingMode.CLOSED_LOOP == 0x37
    first, second, tol, worst = p.phase_init_bounds(19844, 256)
    assert worst == 4128512
    assert p.phase_init_duration(15000) == pytest.approx(3.072)
