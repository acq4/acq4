"""PMD Magellan binary serial protocol: framing, opcodes, register bits, scaling.

Command packet (host -> IC)::

    [addr][checksum][axis][opcode][data...]

Response packet (IC -> host, multi-drop)::

    [addr][status][checksum][data...]

``addr`` is the multi-drop node ID. ``axis`` is the axis index within the
addressed IC (0 on single-axis SmartStages). Data is 0-6 bytes, MSB first.
``status`` is 0 on success; a non-zero status response is exactly the 3-byte
header with no data. The checksum makes all packet bytes sum to 0 mod 256.

References: *C-Motion Magellan Programming Reference* (CR) and *Magellan Motion
Control IC User Guide* (UG).
"""

import struct

# Magellan servo/trajectory sample period. GetSampleTime reports the truncated
# integer 51 us; scaling with 51 instead of 51.2 skews every parameter by 0.4%.
SAMPLE_TIME_S = 51.2e-6

HEADER_LENGTH = 3


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MagellanError(Exception):
    """Base class for pmdmotion errors."""


class PMDError(MagellanError):
    """Non-zero status byte in a response packet.

    Attributes:
        status: instruction error code (see ``ERROR_CODES``).
        opcode: opcode of the command that failed, or None.
    """

    def __init__(self, status, opcode=None):
        self.status = status
        self.opcode = opcode
        name = ERROR_CODES.get(status, 'unknown error')
        cmd = OPCODE_NAMES.get(opcode, None)
        where = f' in {cmd}' if cmd else ''
        super().__init__(f'PMD status {status} ({name}){where}')


class ChecksumError(MagellanError):
    """Response packet failed checksum verification.

    Attributes:
        expected: checksum byte the packet should have carried.
        actual: checksum byte actually received.
        raw: the offending packet bytes.
    """

    def __init__(self, expected, actual, raw):
        self.expected = expected
        self.actual = actual
        self.raw = bytes(raw)
        super().__init__(
            f'bad checksum: expected 0x{expected:02X}, got 0x{actual:02X}, raw={self.raw.hex(" ")}'
        )


class CommunicationError(MagellanError):
    """Truncated, absent, or misaddressed response."""


class _AxesError(MagellanError):
    """Error that may name the axes it concerns (``axes`` attribute, possibly empty)."""

    def __init__(self, *args, axes=()):
        self.axes = list(axes)
        if not args and self.axes:
            args = (f'axes: {", ".join(map(str, self.axes))}',)
        super().__init__(*args)


class CommutationError(_AxesError):
    """Phase initialization failed (Phasing Initialized clear or Commutation Error set)."""


class LimitError(_AxesError):
    """Motion stopped on a limit switch."""


class NotCommutatedError(_AxesError):
    """One or more axes have Phasing Initialized clear and need commutation."""

    def __init__(self, axes, message=None):
        axes = list(axes)
        if message is None:
            message = f'axes not commutated: {", ".join(map(str, axes))}'
        super().__init__(message, axes=axes)


# ---------------------------------------------------------------------------
# Opcodes
# ---------------------------------------------------------------------------

# Motion / profile
SET_POSITION = 0x10
GET_POSITION = 0x4A
SET_VELOCITY = 0x11
GET_VELOCITY = 0x4B
SET_ACCELERATION = 0x90
GET_ACCELERATION = 0x4C
SET_DECELERATION = 0x91
GET_DECELERATION = 0x92
SET_JERK = 0x13
GET_JERK = 0x58
SET_PROFILE_MODE = 0xA0
GET_PROFILE_MODE = 0xA1
SET_STOP_MODE = 0xD0
GET_STOP_MODE = 0xD1
SET_START_VELOCITY = 0x6A
GET_START_VELOCITY = 0x6B
UPDATE = 0x1A
MULTI_UPDATE = 0x5B
SET_UPDATE_MASK = 0xF9
GET_UPDATE_MASK = 0xFA

# Position feedback
GET_ACTUAL_POSITION = 0x37
SET_ACTUAL_POSITION = 0x4D
ADJUST_ACTUAL_POSITION = 0xF5
GET_ACTUAL_VELOCITY = 0xAD
GET_COMMANDED_POSITION = 0x1D
GET_COMMANDED_VELOCITY = 0x1E
GET_COMMANDED_ACCELERATION = 0xA7
GET_POSITION_ERROR = 0x99
SET_POSITION_ERROR_LIMIT = 0x97
GET_POSITION_ERROR_LIMIT = 0x98
CLEAR_POSITION_ERROR = 0x47

# Status registers
GET_EVENT_STATUS = 0x31
RESET_EVENT_STATUS = 0x34
GET_ACTIVITY_STATUS = 0xA6
GET_SIGNAL_STATUS = 0xA4
SET_SIGNAL_SENSE = 0xA2
GET_SIGNAL_SENSE = 0xA3
GET_DRIVE_STATUS = 0x0E
GET_DRIVE_FAULT_STATUS = 0x6D
CLEAR_DRIVE_FAULT_STATUS = 0x6C
GET_INSTRUCTION_ERROR = 0xA5

# Operating mode / motor output. There is no SetMotorEnable; enable/disable is
# SetOperatingMode.
SET_OPERATING_MODE = 0x65
GET_OPERATING_MODE = 0x66
GET_ACTIVE_OPERATING_MODE = 0x57
RESTORE_OPERATING_MODE = 0x2E
SET_MOTOR_COMMAND = 0x77
GET_MOTOR_COMMAND = 0x69
GET_ACTIVE_MOTOR_COMMAND = 0x3A
SET_MOTOR_LIMIT = 0x06
GET_MOTOR_LIMIT = 0x07
SET_MOTOR_TYPE = 0x02
GET_MOTOR_TYPE = 0x03
SET_CURRENT_CONTROL_MODE = 0x43
GET_CURRENT_CONTROL_MODE = 0x44

# Commutation / phasing
SET_PHASE_INITIALIZE_MODE = 0xE4
GET_PHASE_INITIALIZE_MODE = 0xE5
SET_PHASE_INITIALIZE_TIME = 0x72
GET_PHASE_INITIALIZE_TIME = 0x7C
INITIALIZE_PHASE = 0x7A
SET_PHASE_ANGLE = 0x84
GET_PHASE_ANGLE = 0x2C
SET_PHASE_COUNTS = 0x75
GET_PHASE_COUNTS = 0x7D
SET_PHASE_PRESCALE = 0xE6
GET_PHASE_PRESCALE = 0xE7
# Phase offset reads 0xFFFF until phase initialization has occurred.
SET_PHASE_OFFSET = 0x76
GET_PHASE_OFFSET = 0x7B
SET_PHASE_CORRECTION_MODE = 0xE8
GET_PHASE_CORRECTION_MODE = 0xE9
SET_COMMUTATION_MODE = 0xE2
GET_COMMUTATION_MODE = 0xE3

# Servo / settling
SET_MOTION_COMPLETE_MODE = 0xEB
GET_MOTION_COMPLETE_MODE = 0xEC
SET_SETTLE_TIME = 0xAA
GET_SETTLE_TIME = 0xAB
SET_SETTLE_WINDOW = 0xBC
GET_SETTLE_WINDOW = 0xBD
SET_TRACKING_WINDOW = 0xA8
GET_TRACKING_WINDOW = 0xA9
SET_SAMPLE_TIME = 0x3B
GET_SAMPLE_TIME = 0x3C

# Events
SET_EVENT_ACTION = 0x48
GET_EVENT_ACTION = 0x49
SET_AXIS_OUT_MASK = 0x45
GET_AXIS_OUT_MASK = 0x46
SET_FAULT_OUT_MASK = 0xFB
GET_FAULT_OUT_MASK = 0xFC

# Breakpoints: the IC compares a source register against a value and acts in
# hardware. SetBreakpointValue must be issued before SetBreakpoint.
SET_BREAKPOINT = 0xD4
GET_BREAKPOINT = 0xD5
SET_BREAKPOINT_VALUE = 0xD6
GET_BREAKPOINT_VALUE = 0xD7

# Encoder
SET_ENCODER_SOURCE = 0xDA
GET_ENCODER_SOURCE = 0xDB

# Analog calibration
CALIBRATE_ANALOG = 0x6F
GET_ANALOG_CALIBRATION = 0x2A

# Misc
NO_OPERATION = 0x00
# Reset re-zeroes ActualPosition and removes motor output.
RESET = 0x39
GET_VERSION = 0x8F
GET_TIME = 0x3E
GET_CHECKSUM = 0xF8
GET_TRACE_VALUE = 0x28
SET_SERIAL_PORT_MODE = 0x8B
GET_SERIAL_PORT_MODE = 0x8C


# ---------------------------------------------------------------------------
# Instruction table
# ---------------------------------------------------------------------------

# opcode -> (name, argument widths, response widths), in wire order, MSB first.
_INSTRUCTIONS = {
    NO_OPERATION: ('NoOperation', (), ()),
    RESET: ('Reset', (), ()),
    GET_VERSION: ('GetVersion', (), ('u32',)),
    GET_TIME: ('GetTime', (), ('u32',)),
    GET_CHECKSUM: ('GetChecksum', (), ('u32',)),
    GET_TRACE_VALUE: ('GetTraceValue', ('u16',), ('i32',)),
    SET_SERIAL_PORT_MODE: ('SetSerialPortMode', ('u16',), ()),
    GET_SERIAL_PORT_MODE: ('GetSerialPortMode', (), ('u16',)),

    SET_POSITION: ('SetPosition', ('i32',), ()),
    GET_POSITION: ('GetPosition', (), ('i32',)),
    SET_VELOCITY: ('SetVelocity', ('i32',), ()),
    GET_VELOCITY: ('GetVelocity', (), ('i32',)),
    SET_ACCELERATION: ('SetAcceleration', ('u32',), ()),
    GET_ACCELERATION: ('GetAcceleration', (), ('u32',)),
    SET_DECELERATION: ('SetDeceleration', ('u32',), ()),
    GET_DECELERATION: ('GetDeceleration', (), ('u32',)),
    SET_JERK: ('SetJerk', ('u32',), ()),
    GET_JERK: ('GetJerk', (), ('u32',)),
    SET_START_VELOCITY: ('SetStartVelocity', ('u32',), ()),
    GET_START_VELOCITY: ('GetStartVelocity', (), ('u32',)),
    SET_PROFILE_MODE: ('SetProfileMode', ('u16',), ()),
    GET_PROFILE_MODE: ('GetProfileMode', (), ('u16',)),
    SET_STOP_MODE: ('SetStopMode', ('u16',), ()),
    GET_STOP_MODE: ('GetStopMode', (), ('u16',)),
    UPDATE: ('Update', (), ()),
    MULTI_UPDATE: ('MultiUpdate', ('u16',), ()),
    SET_UPDATE_MASK: ('SetUpdateMask', ('u16',), ()),
    GET_UPDATE_MASK: ('GetUpdateMask', (), ('u16',)),

    GET_ACTUAL_POSITION: ('GetActualPosition', (), ('i32',)),
    SET_ACTUAL_POSITION: ('SetActualPosition', ('i32',), ()),
    ADJUST_ACTUAL_POSITION: ('AdjustActualPosition', ('i32',), ()),
    GET_ACTUAL_VELOCITY: ('GetActualVelocity', (), ('i32',)),
    GET_COMMANDED_POSITION: ('GetCommandedPosition', (), ('i32',)),
    GET_COMMANDED_VELOCITY: ('GetCommandedVelocity', (), ('i32',)),
    GET_COMMANDED_ACCELERATION: ('GetCommandedAcceleration', (), ('i32',)),
    GET_POSITION_ERROR: ('GetPositionError', (), ('i32',)),
    SET_POSITION_ERROR_LIMIT: ('SetPositionErrorLimit', ('u32',), ()),
    GET_POSITION_ERROR_LIMIT: ('GetPositionErrorLimit', (), ('u32',)),
    CLEAR_POSITION_ERROR: ('ClearPositionError', (), ()),

    GET_EVENT_STATUS: ('GetEventStatus', (), ('u16',)),
    RESET_EVENT_STATUS: ('ResetEventStatus', ('u16',), ()),
    GET_ACTIVITY_STATUS: ('GetActivityStatus', (), ('u16',)),
    GET_SIGNAL_STATUS: ('GetSignalStatus', (), ('u16',)),
    SET_SIGNAL_SENSE: ('SetSignalSense', ('u16',), ()),
    GET_SIGNAL_SENSE: ('GetSignalSense', (), ('u16',)),
    GET_DRIVE_STATUS: ('GetDriveStatus', (), ('u16',)),
    GET_DRIVE_FAULT_STATUS: ('GetDriveFaultStatus', (), ('u16',)),
    CLEAR_DRIVE_FAULT_STATUS: ('ClearDriveFaultStatus', (), ()),
    GET_INSTRUCTION_ERROR: ('GetInstructionError', (), ('u16',)),

    SET_OPERATING_MODE: ('SetOperatingMode', ('u16',), ()),
    GET_OPERATING_MODE: ('GetOperatingMode', (), ('u16',)),
    GET_ACTIVE_OPERATING_MODE: ('GetActiveOperatingMode', (), ('u16',)),
    RESTORE_OPERATING_MODE: ('RestoreOperatingMode', (), ()),
    SET_MOTOR_COMMAND: ('SetMotorCommand', ('i16',), ()),
    GET_MOTOR_COMMAND: ('GetMotorCommand', (), ('i16',)),
    GET_ACTIVE_MOTOR_COMMAND: ('GetActiveMotorCommand', (), ('i16',)),
    SET_MOTOR_LIMIT: ('SetMotorLimit', ('u16',), ()),
    GET_MOTOR_LIMIT: ('GetMotorLimit', (), ('u16',)),
    SET_MOTOR_TYPE: ('SetMotorType', ('u16',), ()),
    GET_MOTOR_TYPE: ('GetMotorType', (), ('u16',)),
    SET_CURRENT_CONTROL_MODE: ('SetCurrentControlMode', ('u16',), ()),
    GET_CURRENT_CONTROL_MODE: ('GetCurrentControlMode', (), ('u16',)),

    SET_PHASE_INITIALIZE_MODE: ('SetPhaseInitializeMode', ('u16',), ()),
    GET_PHASE_INITIALIZE_MODE: ('GetPhaseInitializeMode', (), ('u16',)),
    SET_PHASE_INITIALIZE_TIME: ('SetPhaseInitializeTime', ('u16',), ()),
    GET_PHASE_INITIALIZE_TIME: ('GetPhaseInitializeTime', (), ('u16',)),
    INITIALIZE_PHASE: ('InitializePhase', (), ()),
    SET_PHASE_ANGLE: ('SetPhaseAngle', ('u16',), ()),
    GET_PHASE_ANGLE: ('GetPhaseAngle', (), ('u16',)),
    SET_PHASE_COUNTS: ('SetPhaseCounts', ('u16',), ()),
    GET_PHASE_COUNTS: ('GetPhaseCounts', (), ('u16',)),
    SET_PHASE_PRESCALE: ('SetPhasePrescale', ('u16',), ()),
    GET_PHASE_PRESCALE: ('GetPhasePrescale', (), ('u16',)),
    SET_PHASE_OFFSET: ('SetPhaseOffset', ('u16',), ()),
    GET_PHASE_OFFSET: ('GetPhaseOffset', (), ('u16',)),
    SET_PHASE_CORRECTION_MODE: ('SetPhaseCorrectionMode', ('u16',), ()),
    GET_PHASE_CORRECTION_MODE: ('GetPhaseCorrectionMode', (), ('u16',)),
    SET_COMMUTATION_MODE: ('SetCommutationMode', ('u16',), ()),
    GET_COMMUTATION_MODE: ('GetCommutationMode', (), ('u16',)),

    SET_MOTION_COMPLETE_MODE: ('SetMotionCompleteMode', ('u16',), ()),
    GET_MOTION_COMPLETE_MODE: ('GetMotionCompleteMode', (), ('u16',)),
    SET_SETTLE_TIME: ('SetSettleTime', ('u16',), ()),
    GET_SETTLE_TIME: ('GetSettleTime', (), ('u16',)),
    SET_SETTLE_WINDOW: ('SetSettleWindow', ('u16',), ()),
    GET_SETTLE_WINDOW: ('GetSettleWindow', (), ('u16',)),
    SET_TRACKING_WINDOW: ('SetTrackingWindow', ('u16',), ()),
    GET_TRACKING_WINDOW: ('GetTrackingWindow', (), ('u16',)),
    # GetSampleTime returns 4 data bytes on SmartStage (measured). The setter's
    # width is unverified.
    SET_SAMPLE_TIME: ('SetSampleTime', ('u16',), ()),
    GET_SAMPLE_TIME: ('GetSampleTime', (), ('u32',)),

    SET_EVENT_ACTION: ('SetEventAction', ('u16', 'u16'), ()),
    GET_EVENT_ACTION: ('GetEventAction', ('u16',), ('u16',)),
    SET_AXIS_OUT_MASK: ('SetAxisOutMask', ('u16', 'u16', 'u16'), ()),
    GET_AXIS_OUT_MASK: ('GetAxisOutMask', (), ('u16', 'u16', 'u16')),
    SET_FAULT_OUT_MASK: ('SetFaultOutMask', ('u16',), ()),
    GET_FAULT_OUT_MASK: ('GetFaultOutMask', (), ('u16',)),

    # Breakpoint value is one 32-bit field, high word first; for a register
    # level trigger it is (selection_mask << 16) | sense_mask.
    SET_BREAKPOINT: ('SetBreakpoint', ('u16', 'u16'), ()),
    GET_BREAKPOINT: ('GetBreakpoint', ('u16',), ('u16',)),
    SET_BREAKPOINT_VALUE: ('SetBreakpointValue', ('u16', 'u32'), ()),
    GET_BREAKPOINT_VALUE: ('GetBreakpointValue', ('u16',), ('u32',)),

    SET_ENCODER_SOURCE: ('SetEncoderSource', ('u16',), ()),
    GET_ENCODER_SOURCE: ('GetEncoderSource', (), ('u16',)),

    CALIBRATE_ANALOG: ('CalibrateAnalog', ('u16',), ()),
    GET_ANALOG_CALIBRATION: ('GetAnalogCalibration', ('u16',), ('i16',)),
}

OPCODE_NAMES = {op: info[0] for op, info in _INSTRUCTIONS.items()}
OPCODES = {info[0]: op for op, info in _INSTRUCTIONS.items()}

_WIDTH_BYTES = {'u16': 2, 'i16': 2, 'u32': 4, 'i32': 4}
_WIDTH_PACK = {'u16': '>H', 'i16': '>h', 'u32': '>I', 'i32': '>i'}


# ---------------------------------------------------------------------------
# Register bit definitions
# ---------------------------------------------------------------------------


class ActivityStatus:
    """Bit positions in the Activity Status register. Bits are live, not latched."""

    PHASING_INITIALIZED = 0
    AT_MAX_VELOCITY = 1
    POSITION_TRACKING = 2
    PROFILE_MODE_MASK = 0x0078  # bits 3-6
    PROFILE_MODE_SHIFT = 3
    AXIS_SETTLED = 7
    POSITION_LOOP_ENABLED = 8
    POSITION_CAPTURE = 9
    IN_MOTION = 10
    IN_POSITIVE_LIMIT = 11
    IN_NEGATIVE_LIMIT = 12


class EventStatus:
    """Bit positions in the Event Status register.

    Bits latch until cleared by ``ResetEventStatus``, which clears the bits that
    are 0 in its mask. Motion Complete re-latches shortly after being cleared
    while the axis is at rest. Commutation Error is set when the second ramp of
    an algorithmic phase init misses PhaseCounts/4 by more than the tolerance.
    """

    MOTION_COMPLETE = 0
    POSITION_WRAPAROUND = 1
    BREAKPOINT1 = 2
    CAPTURE_RECEIVED = 3
    MOTION_ERROR = 4
    POSITIVE_LIMIT = 5
    NEGATIVE_LIMIT = 6
    INSTRUCTION_ERROR = 7
    DISABLE = 8
    OVERTEMPERATURE_FAULT = 9
    DRIVE_EXCEPTION = 10
    COMMUTATION_ERROR = 11
    CURRENT_FOLDBACK = 12
    BREAKPOINT2 = 14


#: Event Status bits that mean the axis faulted, with display names.
HARD_FAULT_EVENTS = {
    EventStatus.MOTION_ERROR: 'MotionError',
    EventStatus.DISABLE: 'Disable',
    EventStatus.OVERTEMPERATURE_FAULT: 'OvertemperatureFault',
    EventStatus.DRIVE_EXCEPTION: 'DriveException',
}


def reset_event_mask(*bits):
    """ResetEventStatus argument that clears *bits* (it clears the bits that are 0)."""
    mask = 0xFFFF
    for b in bits:
        mask &= ~(1 << b)
    return mask


class SignalStatus:
    """Bit positions in the Signal Status register.

    Values are pin levels after the SignalSense mask. Dover axes read
    SignalSense 0x0030, so a limit bit reads 0 when that limit is engaged.
    AxisIn (the centre vane) reads 1 in the positive half of travel.
    """

    ENCODER_A = 0
    ENCODER_B = 1
    ENCODER_INDEX = 2
    HOME_CAPTURE = 3
    POSITIVE_LIMIT = 4
    NEGATIVE_LIMIT = 5
    AXIS_IN = 6
    HALL1 = 7
    HALL2 = 8
    HALL3 = 9
    AXIS_OUT = 10
    ENABLE_IN = 13
    FAULT_OUT = 14


class DriveStatus:
    """Bit positions in the Drive Status register (CR p.38). Read-only to the host."""

    CALIBRATED = 0          # cleared by CalibrateAnalog, set on completion
    IN_FOLDBACK = 1
    OVERTEMPERATURE = 2
    SHUNT_ACTIVE = 3
    IN_HOLDING = 4
    OVERVOLTAGE = 5
    UNDERVOLTAGE = 6
    ATLAS_DISABLED = 7
    OUTPUT_CLIPPED = 12
    ATLAS_NOT_CONNECTED = 15


class OperatingMode:
    """SetOperatingMode bits and the composite modes this driver uses."""

    AXIS_ENABLED = 0x0001
    MOTOR_OUTPUT = 0x0002
    CURRENT_CONTROL = 0x0004
    POSITION_LOOP = 0x0010
    TRAJECTORY = 0x0020

    IDLE = AXIS_ENABLED                                 # 0x01, outputs off
    OPEN_LOOP = AXIS_ENABLED | MOTOR_OUTPUT             # 0x03, for commutation
    CLOSED_LOOP = (AXIS_ENABLED | MOTOR_OUTPUT | CURRENT_CONTROL
                   | POSITION_LOOP | TRAJECTORY)        # 0x37, full servo


class ProfileMode:
    TRAPEZOIDAL = 0
    VELOCITY_CONTOURING = 1
    S_CURVE = 2
    ELECTRONIC_GEAR = 3


class StopMode:
    """SetStopMode argument. SetStopMode is a buffered stop command, not a setting.

    A buffered ABRUPT or SMOOTH stop is executed by the next Update and discards
    the SetPosition that Update would have committed. The IC then resets it to
    NO_STOP. A stop also zeroes the velocity register; re-issue SetVelocity
    before the next move.
    """

    NO_STOP = 0
    ABRUPT = 1
    SMOOTH = 2


class PhaseInitializeMode:
    ALGORITHMIC = 0
    HALL_BASED = 1
    PULSE = 2


class PhasePrescale:
    """Divisor applied to encoder counts for commutation only.

    Counts per electrical cycle = PhaseCounts * divisor. Must not change while
    the motor is moving.
    """

    OFF = 0
    DIV_64 = 1
    DIV_128 = 2
    DIV_256 = 3


PHASE_PRESCALE_DIVISOR = {0: 1, 1: 64, 2: 128, 3: 256}


class MotorType:
    BRUSHLESS_DC_3PHASE = 0
    CLOSED_LOOP_STEPPER = 1
    MICROSTEPPING_3PHASE = 2
    MICROSTEPPING_2PHASE = 3
    PULSE_AND_DIRECTION = 4
    DC_BRUSH = 7


class CommutationMode:
    SINUSOIDAL = 0
    HALL_BASED = 1
    MICROSTEPPING = 2


class CurrentControlMode:
    PHASE_AB_LOOPS = 0
    FOC = 1
    THIRD_LEG_FLOATING = 2


class PhaseCorrectionMode:
    DISABLED = 0
    INDEX = 1
    HALL = 2


class EventActionEvent:
    """``event`` argument of Set/GetEventAction (CR p.138). IMMEDIATE cannot be read back."""

    IMMEDIATE = 0
    POSITIVE_LIMIT = 1
    NEGATIVE_LIMIT = 2
    MOTION_ERROR = 3
    CURRENT_FOLDBACK = 4
    BRAKE_SIGNAL = 13


class EventAction:
    """``action`` argument of SetEventAction (CR p.138).

    The stopping actions (2, 3, 8) need the trajectory generator enabled (UG
    p.72); in open-loop mode 3 they and actions 5/6 are no-ops, leaving only
    DISABLE_MOTOR_OUTPUT_AND_HIGHER effective. Recover from a module-disabling
    action with RestoreOperatingMode after clearing the event bit.
    """

    NONE = 0
    ABRUPT_STOP = 2
    SMOOTH_STOP = 3
    DISABLE_POSITION_LOOP_AND_HIGHER = 5
    DISABLE_CURRENT_LOOP_AND_HIGHER = 6
    DISABLE_MOTOR_OUTPUT_AND_HIGHER = 7
    ABRUPT_STOP_WITH_POSITION_ERROR_CLEAR = 8
    PASSIVE_BRAKING = 10


EVENT_ACTION_NAMES = {
    0: 'None', 2: 'AbruptStop', 3: 'SmoothStop',
    5: 'DisablePositionLoopAndHigher', 6: 'DisableCurrentLoopAndHigher',
    7: 'DisableMotorOutputAndHigher', 8: 'AbruptStopWithPositionErrorClear',
    10: 'PassiveBraking',
}


class CommutationErrorCause:
    """Values of the Commutation Error Cause trace variable, ID 119 (CR p.212).

    Readable only via the trace mechanism; reading clears it.
    """

    NO_ERROR = 0
    PHASE_CORRECTION_TOO_LARGE = 1
    INVALID_HALL_STATE = 2
    ALGORITHMIC_SECOND_RAMP_MOTION = 3
    PULSE_SIGNAL_TOO_LOW = 4
    PULSE_TOO_MUCH_MOVEMENT = 5


TRACE_VAR_COMMUTATION_ERROR_CAUSE = 119


class CalibrateAnalogOption:
    LEG_CURRENTS = 0    # requires motor command 0 and no motion
    SIN_COS = 4         # requires motion during calibration


class BreakpointID:
    BREAKPOINT1 = 0     # reports in EventStatus bit 2
    BREAKPOINT2 = 1     # reports in EventStatus bit 14


class BreakpointTrigger:
    NONE = 0
    GE_COMMANDED_POSITION = 1
    LE_COMMANDED_POSITION = 2
    GE_ACTUAL_POSITION = 3
    LE_ACTUAL_POSITION = 4
    COMMANDED_POSITION_CROSSED = 5
    ACTUAL_POSITION_CROSSED = 6
    TIME = 7
    EVENT_STATUS = 8
    ACTIVITY_STATUS = 9
    SIGNAL_STATUS = 0x0A
    DRIVE_STATUS = 0x0B


class BreakpointAction:
    NONE = 0
    UPDATE = 1
    ABRUPT_STOP = 2
    SMOOTH_STOP = 3
    DISABLE_POSITION_LOOP_AND_HIGHER = 5
    DISABLE_CURRENT_LOOP_AND_HIGHER = 6
    DISABLE_MOTOR_OUTPUT_AND_HIGHER = 7
    ABRUPT_STOP_WITH_POSITION_ERROR_CLEAR = 8


def breakpoint_word(trigger, action, source_axis=0):
    """Pack the ``(trigger << 8) | (action << 4) | source_axis`` word for SetBreakpoint."""
    return ((trigger & 0xFF) << 8) | ((action & 0x0F) << 4) | (source_axis & 0x0F)


def breakpoint_level_value(bit, want_set):
    """Pack a SetBreakpointValue for a register-level trigger on one bit.

    High word selects the bit, low word is the level it must match; ``want_set``
    True breaks when the bit reads 1.
    """
    selection = 1 << bit
    sense = (1 << bit) if want_set else 0
    return (selection << 16) | sense


class UpdateMask:
    """Parameter groups an Update copies from their buffers (CR p.215). SmartStage reads 0x000B."""

    TRAJECTORY = 0x0001
    POSITION_LOOP = 0x0002
    CURRENT_LOOP = 0x0008


# ---------------------------------------------------------------------------
# Algorithmic phase initialization geometry
# ---------------------------------------------------------------------------

# One InitializePhase runs four segments (ramp 1, settle, ramp 2, settle), each
# PhaseInitializeTime sample periods long (CR p.170).
PHASE_INIT_SEGMENTS = 4
PHASE_INIT_FIRST_RAMP_SEGMENTS = 2   # ramp 1 and its settle


def phase_init_duration(init_time_cycles, sample_time_s=SAMPLE_TIME_S):
    """Total runtime of one algorithmic InitializePhase, in seconds."""
    return PHASE_INIT_SEGMENTS * init_time_cycles * sample_time_s


def phase_init_segment_duration(init_time_cycles, sample_time_s=SAMPLE_TIME_S):
    """Duration of one of the four phase-initialization segments, in seconds."""
    return init_time_cycles * sample_time_s


def phase_init_bounds(phase_counts, prescale_divisor):
    """Worst-case displacement of one algorithmic phase init, in encoder counts.

    Returns ``(first_ramp, second_ramp, tolerance, worst_case)``: ramp 1 can
    travel half an electrical cycle; ramp 2 travels PhaseCounts/4 within
    PhaseCounts/16 + 4 (UG p.132); the ramps are additive.
    """
    cycle = phase_counts * prescale_divisor
    first = cycle // 2
    second = (phase_counts // 4) * prescale_divisor
    tolerance = (phase_counts // 16 + 4) * prescale_divisor
    return first, second, tolerance, first + second + tolerance


# ---------------------------------------------------------------------------
# Trajectory parameter scaling
# ---------------------------------------------------------------------------

# Trajectory parameters are counts per sample time in fixed point: velocity and
# acceleration 16.16, jerk 32.32. Not counts per second.


def counts_per_sample(mm_per_s, counts_per_mm, sample_time_s=SAMPLE_TIME_S):
    return mm_per_s * counts_per_mm * sample_time_s


def encode_velocity(mm_per_s, counts_per_mm, sample_time_s=SAMPLE_TIME_S):
    """units/s -> SetVelocity argument (counts/sample, 16.16 fixed point)."""
    return int(round(mm_per_s * counts_per_mm * sample_time_s * 2 ** 16))


def encode_acceleration(mm_per_s2, counts_per_mm, sample_time_s=SAMPLE_TIME_S):
    """units/s^2 -> SetAcceleration/SetDeceleration argument (counts/sample^2, 16.16)."""
    return int(round(mm_per_s2 * counts_per_mm * sample_time_s ** 2 * 2 ** 16))


def encode_jerk(mm_per_s3, counts_per_mm, sample_time_s=SAMPLE_TIME_S):
    """units/s^3 -> SetJerk argument (counts/sample^3, 32.32 fixed point)."""
    return int(round(mm_per_s3 * counts_per_mm * sample_time_s ** 3 * 2 ** 32))


def decode_velocity(value, sample_time_s=SAMPLE_TIME_S):
    """SetVelocity/GetVelocity register value -> counts/s."""
    return value / 2 ** 16 / sample_time_s


def decode_acceleration(value, sample_time_s=SAMPLE_TIME_S):
    """Acceleration/deceleration register value -> counts/s^2."""
    return value / 2 ** 16 / sample_time_s ** 2


def decode_jerk(value, sample_time_s=SAMPLE_TIME_S):
    """Jerk register value -> counts/s^3."""
    return value / 2 ** 32 / sample_time_s ** 3


# Instruction error codes returned in the response status byte.
ERROR_CODES = {
    0: 'no error',
    1: 'processor reset',
    2: 'invalid instruction',
    3: 'invalid axis',
    4: 'invalid parameter',
    5: 'trace running',
    7: 'block out of bounds',
    8: 'trace buffer zero',
    9: 'bad serial checksum',
    11: 'invalid negative value',
    12: 'invalid parameter change',
    13: 'invalid move after event-triggered stop',
    14: 'invalid move into limit',
    16: 'invalid operating mode restore after event-triggered change',
    17: 'invalid operating mode for command',
    18: 'invalid register state for command',
    19: 'ION/CME hard fault',
    20: 'command invalid without Atlas amplifier',
    21: 'incorrect Atlas command checksum',
    22: 'invalid Atlas command protocol',
    23: 'invalid Atlas command timing',
    24: 'invalid Atlas torque command detected',
    26: 'Atlas command invalid in flash mode',
    28: 'command valid only when executed from internal memory',
    29: 'wrong command data count',
    30: 'attempted move with motion error event signaled',
    31: 'wait timed out',
    32: 'NVRAM initialization busy',
    33: 'invalid clock signal',
    34: 'NVRAM initialization skipped',
    35: 'command not valid when executed from internal memory',
    36: 'encoder error',
    37: 'value representation error',
    39: 'NVRAM format error',
}

STATUS_INVALID_INSTRUCTION = 2
STATUS_INVALID_AXIS = 3
STATUS_BAD_CHECKSUM = 9
# Update while an S-curve profile is in motion (measured on SmartStage).
STATUS_INVALID_PARAMETER_CHANGE = 12
STATUS_MOVE_INTO_LIMIT = 14
STATUS_WRONG_DATA_COUNT = 29
STATUS_MOVE_WITH_MOTION_ERROR = 30


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def checksum(payload):
    """Return the checksum byte for ``payload`` (the packet without its checksum byte).

    Two's complement of the byte sum, low 8 bits.
    """
    return (-sum(payload)) & 0xFF


def instruction_word(opcode, axis=0):
    """Return the two instruction bytes, axis byte first."""
    return bytes(((axis & 0xFF), (opcode & 0xFF)))


def arg_widths(opcode):
    """Return the declared argument widths for ``opcode``, or None if unknown."""
    info = _INSTRUCTIONS.get(opcode)
    return None if info is None else info[1]


def response_widths(opcode):
    """Return the declared response data widths for ``opcode``, or None if unknown."""
    info = _INSTRUCTIONS.get(opcode)
    return None if info is None else info[2]


def width_bytes(widths):
    """Total byte count of a sequence of widths such as ``('u16', 'i32')``."""
    return sum(_WIDTH_BYTES[w] for w in widths)


def pack_values(widths, values):
    """Pack ``values`` MSB first per ``widths``. Raises ValueError if one does not fit."""
    data = bytearray()
    for width, value in zip(widths, values):
        try:
            data += struct.pack(_WIDTH_PACK[width], int(value))
        except struct.error as exc:
            raise ValueError(f'value {value} does not fit in {width}') from exc
    return bytes(data)


def unpack_values(widths, data):
    """Unpack ``data`` per ``widths``; ``data`` must be exactly the right length."""
    values = []
    offset = 0
    for width in widths:
        values.append(struct.unpack_from(_WIDTH_PACK[width], data, offset)[0])
        offset += _WIDTH_BYTES[width]
    return values


def encode(node_id, opcode, *args, axis=0):
    """Pack one PMD command packet.

    Arguments are given at their declared width (a 32-bit argument is one int).
    For an opcode not in the instruction table each argument is packed as u16.

    Args:
        node_id: multi-drop address of the target IC.
        opcode: instruction code, e.g. ``GET_ACTUAL_POSITION``.
        axis: axis index within the addressed IC; 0 for single-axis products.

    Raises:
        ValueError: wrong argument count, or a value does not fit its width.
    """
    widths = arg_widths(opcode)
    if widths is None:
        widths = ('u16',) * len(args)
    elif len(args) != len(widths):
        name = OPCODE_NAMES.get(opcode, f'0x{opcode:02X}')
        raise ValueError(f'{name} takes {len(widths)} argument(s), got {len(args)}')

    body = bytes((node_id & 0xFF,)) + instruction_word(opcode, axis) + pack_values(widths, args)
    return body[:1] + bytes((checksum(body),)) + body[1:]


def header_length(multi_drop=True):
    """Return the byte count of a response header."""
    return HEADER_LENGTH if multi_drop else HEADER_LENGTH - 1


def response_length(opcode):
    """Return the number of data bytes in an OK response to ``opcode``.

    Raises:
        KeyError: opcode is not in the instruction table.
    """
    return width_bytes(_INSTRUCTIONS[opcode][2])


def packet_length(opcode, status=0, multi_drop=True):
    """Return the total byte count of a response packet, header included."""
    header = header_length(multi_drop)
    return header if status != 0 else header + response_length(opcode)


def parse_response(opcode, raw, multi_drop=True, node_id=None):
    """Unpack and verify one complete response packet.

    Returns ``(status, values)``; ``values`` are decoded per the opcode's
    response widths and empty when ``status`` is non-zero. A non-zero status is
    returned, not raised (see ``check_status``). Unknown opcodes decode as u16 words.

    Args:
        node_id: if given (multi-drop), the expected responder address.

    Raises:
        ChecksumError: packet bytes do not sum to 0 mod 256.
        CommunicationError: packet is truncated, overlong, or from another node.
    """
    raw = bytes(raw)
    header = header_length(multi_drop)
    if len(raw) < header:
        raise CommunicationError(
            f'short response: got {len(raw)} bytes, need at least {header}: {raw.hex(" ")}'
        )

    if multi_drop:
        addr, status, chk = raw[0], raw[1], raw[2]
    else:
        addr, status, chk = None, raw[0], raw[1]

    if sum(raw) & 0xFF:
        raise ChecksumError(checksum(raw[:header - 1] + raw[header:]), chk, raw)

    if node_id is not None and addr is not None and addr != node_id:
        raise CommunicationError(f'response from node {addr}, expected {node_id}: {raw.hex(" ")}')

    data = raw[header:]
    if status != 0:
        if data:
            raise CommunicationError(
                f'error status {status} carried {len(data)} data bytes: {raw.hex(" ")}'
            )
        return status, []

    widths = response_widths(opcode)
    if widths is None:
        if len(data) % 2:
            raise CommunicationError(f'odd data length for unknown opcode: {raw.hex(" ")}')
        return status, list(struct.unpack(f'>{len(data) // 2}H', data))

    expected = width_bytes(widths)
    if len(data) != expected:
        name = OPCODE_NAMES.get(opcode, f'0x{opcode:02X}')
        raise CommunicationError(
            f'{name} returned {len(data)} data bytes, expected {expected}: {raw.hex(" ")}'
        )
    return status, unpack_values(widths, data)


def check_status(status, opcode=None):
    """Raise ``PMDError`` if ``status`` is non-zero."""
    if status != 0:
        raise PMDError(status, opcode)


def decode_bits(value, bit_class):
    """Return ``{name: bool}`` for the single-bit attributes of a register class.

    Attributes whose names end in ``_MASK`` or ``_SHIFT`` are skipped.
    """
    out = {}
    for name in dir(bit_class):
        if name.startswith('_') or name.endswith(('_MASK', '_SHIFT')):
            continue
        bit = getattr(bit_class, name)
        if isinstance(bit, int):
            out[name] = bool(value & (1 << bit))
    return out
