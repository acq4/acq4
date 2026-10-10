"""Commutation (algorithmic phase initialization) and homing of single MagellanBackend axes.

A private part of MagellanBackend, split out for size; it freely uses MagellanBackend's
underscore helpers. Every function takes the MagellanBackend as *backend*, performs bus
I/O, and runs where that backend's methods run (the driver's control thread). Positions
are encoder counts.
"""
from __future__ import annotations

import logging
import time

from . import protocol as p
from .protocol import CommutationError, LimitError, MagellanError, NotCommutatedError

logger = logging.getLogger(__name__)

AS = p.ActivityStatus
EV = p.EventStatus
OM = p.OperatingMode

_PHASED = 1 << AS.PHASING_INITIALIZED
_IN_MOTION = 1 << AS.IN_MOTION
_POS_LIMIT = 1 << AS.IN_POSITIVE_LIMIT
_NEG_LIMIT = 1 << AS.IN_NEGATIVE_LIMIT
_LIMIT_EVENTS = (p.EventActionEvent.POSITIVE_LIMIT, p.EventActionEvent.NEGATIVE_LIMIT)
# the only limit action with any effect in open-loop mode 3 (trajectory generator off)
_GUARD_ACTION = p.EventAction.DISABLE_MOTOR_OUTPUT_AND_HIGHER

POLL_S = 0.025
CALIBRATE_TIMEOUT_S = 2.0
PHASE_TIMEOUT_MARGIN_S = 2.0
MIN_PHASE_FRACTION = 0.95
# hold times for _wait_settled; distance thresholds come from the MagellanBackend
SETTLE_S = 0.2
SETTLE_TIMEOUT_S = 1.0
HOME_SETTLE_S = 0.15
HOME_SETTLE_TIMEOUT_S = 1.0
MOVE_TIMEOUT_MARGIN_S = 5.0
START_TIMEOUT_S = 1.0


# ---------------------------------------------------------------------------
# Commutation
# ---------------------------------------------------------------------------

def commutate_axis(backend, axis, drive_levels) -> int | None:
    """Phase-initialize *axis*, escalating through *drive_levels*; return the level that worked.

    Returns None without touching the axis if it is already phased. MOVES THE AXIS a large,
    unpredictable distance and cannot be interrupted. Limit EventActions are set to
    DisableMotorOutput for the duration and restored to their prior values. On success the
    axis is in closed-loop servo with ActualPosition zeroed where it came to rest. Raises
    CommutationError (axis disarmed) when every level fails or a limit is engaged.
    """
    if backend.refresh_phasing([axis])[axis]:
        return None
    levels = [int(lvl) for lvl in drive_levels]
    if not levels or any(not 0 < lvl <= 32767 for lvl in levels):
        raise ValueError(f'drive levels must be in 1..32767, got {list(drive_levels)}')

    previous = {e: backend.axis_read(axis, p.GET_EVENT_ACTION, e) for e in _LIMIT_EVENTS}
    logger.info('commutating axis %s; limit EventActions read %s', axis, previous)
    backend._invalidate_profile([axis])
    failed = True
    backend._failed_commutation.add(axis)
    try:
        _calibrate_analog(backend, axis)
        for e in _LIMIT_EVENTS:
            backend.axis_write(axis, p.SET_EVENT_ACTION, e, _GUARD_ACTION)
        readback = [backend.axis_read(axis, p.GET_EVENT_ACTION, e) for e in _LIMIT_EVENTS]
        if readback != [_GUARD_ACTION] * len(_LIMIT_EVENTS):
            raise CommutationError(f'axis {axis}: limit EventAction readback {readback}, '
                                   f'wanted {_GUARD_ACTION}', axes=[axis])
        cycles = backend.axis_read(axis, p.GET_PHASE_INITIALIZE_TIME)
        timeout = p.phase_init_duration(cycles) + PHASE_TIMEOUT_MARGIN_S
        used = None
        reasons = []
        for level in levels:
            ok, why = _attempt_phase_init(backend, axis, level, timeout)
            if ok:
                used = level
                break
            logger.warning('axis %s phase init failed at drive level %d: %s', axis, level, why)
            reasons.append(f'{level}: {why}')
        if used is None:
            raise CommutationError(f'axis {axis}: phase initialization failed at every drive level '
                                   f'({"; ".join(reasons)})', axes=[axis])
        _finalize(backend, axis)
        failed = False
        backend._failed_commutation.discard(axis)
        logger.info('axis %s commutated at drive level %d', axis, used)
        return used
    finally:
        if failed:
            _disarm(backend, axis)
        restore_error = None
        for e, value in previous.items():
            try:
                backend.axis_write(axis, p.SET_EVENT_ACTION, e, value)
            except Exception as exc:
                logger.exception('could not restore limit EventAction %d=%d on axis %s', e, value, axis)
                restore_error = restore_error or exc
        backend._invalidate_profile([axis])
        try:
            backend.refresh_phasing([axis])
        except Exception:
            logger.exception('could not read phasing state of axis %s', axis)
        if restore_error is not None and not failed:
            raise restore_error


def _calibrate_analog(backend, axis):
    """Zero the leg-current sense offsets (needs motor command 0 and a still motor)."""
    backend.axis_write(axis, p.SET_MOTOR_COMMAND, 0)
    backend.axis_write(axis, p.SET_OPERATING_MODE, OM.OPEN_LOOP)
    backend.axis_write(axis, p.CALIBRATE_ANALOG, p.CalibrateAnalogOption.LEG_CURRENTS)
    deadline = time.monotonic() + CALIBRATE_TIMEOUT_S
    while True:
        time.sleep(0.02)
        if backend.axis_read(axis, p.GET_DRIVE_STATUS) & (1 << p.DriveStatus.CALIBRATED):
            break
        if time.monotonic() > deadline:
            raise CommutationError(f'axis {axis}: CalibrateAnalog did not complete within '
                                   f'{CALIBRATE_TIMEOUT_S} s', axes=[axis])
    backend.axis_write(axis, p.SET_OPERATING_MODE, OM.IDLE)


def _attempt_phase_init(backend, axis, level, timeout):
    """Run one InitializePhase at drive *level*; return ``(ok, reason)``.

    Leaves the motor command at 0. Raises CommutationError (no point escalating) if a
    limit is engaged before or during the attempt.
    """
    backend.axis_write(axis, p.SET_MOTOR_COMMAND, 0)
    backend.axis_write(axis, p.SET_OPERATING_MODE, OM.OPEN_LOOP)
    backend.axis_write(axis, p.RESET_EVENT_STATUS, p.reset_event_mask(EV.COMMUTATION_ERROR))
    if backend._read_activity(axis) & (_POS_LIMIT | _NEG_LIMIT):
        raise CommutationError(f'axis {axis} is on a limit switch; no room to commutate', axes=[axis])
    backend.axis_write(axis, p.SET_MOTOR_COMMAND, level)
    try:
        backend.axis_write(axis, p.INITIALIZE_PHASE)
        t0 = time.monotonic()
        deadline = t0 + timeout
        # Phasing Initialized may still be set from an earlier failed init; trust it only near the end
        earliest = t0 + MIN_PHASE_FRACTION * (timeout - PHASE_TIMEOUT_MARGIN_S)
        seen_clear = False
        while True:
            time.sleep(POLL_S)
            act = backend._read_activity(axis)
            seen_clear = seen_clear or not act & _PHASED
            if act & _PHASED and (seen_clear or time.monotonic() >= earliest):
                logger.info('axis %s: Phasing Initialized after %.2f s (bit 0 seen clear: %s)',
                            axis, time.monotonic() - t0, seen_clear)
                break
            if act & (_POS_LIMIT | _NEG_LIMIT):
                raise CommutationError(f'axis {axis} reached a limit during phase initialization '
                                       f'(motor output disabled)', axes=[axis])
            if time.monotonic() > deadline:
                return False, f'Phasing Initialized still clear after {timeout:.1f} s'
    finally:
        backend.axis_write(axis, p.SET_MOTOR_COMMAND, 0)
    if backend.axis_read(axis, p.GET_EVENT_STATUS) & (1 << EV.COMMUTATION_ERROR):
        return False, 'Commutation Error set'
    return True, None


def _wait_settled(backend, axis, counts, hold=SETTLE_S, timeout=SETTLE_TIMEOUT_S):
    """Wait until *axis* moves less than *counts* over *hold* seconds; returns the position.

    Logs a warning and returns the last read after *timeout*.
    """
    deadline = time.monotonic() + timeout
    ref = backend._read_counts(axis)
    ref_t = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(POLL_S)
        pos = backend._read_counts(axis)
        if pos is None or ref is None or abs(pos - ref) > counts:
            ref, ref_t = pos, time.monotonic()
        elif time.monotonic() - ref_t >= hold:
            return pos
    logger.info("axis %s still moving after %.1f s", axis, timeout)
    return ref


def _finalize(backend, axis):
    """Zero position where the axis rests and close the servo loop."""
    backend.axis_write(axis, p.SET_MOTOR_COMMAND, 0)
    _wait_settled(backend, axis, backend._settle_counts[axis])
    backend.axis_write(axis, p.SET_ACTUAL_POSITION, 0)
    backend.axis_write(axis, p.CLEAR_POSITION_ERROR)
    backend.axis_write(axis, p.UPDATE)
    actual = backend._read_counts(axis) or 0
    _load_homing_profile(backend, axis)
    backend.axis_write(axis, p.SET_VELOCITY, _homing_velocity(backend, axis))
    # executed by the Update below: the trajectory adopts the rest position
    backend.axis_write(axis, p.SET_STOP_MODE, p.StopMode.SMOOTH)
    backend.axis_write(axis, p.SET_POSITION, actual)
    backend.axis_write(axis, p.UPDATE)
    backend.axis_write(axis, p.RESET_EVENT_STATUS, 0)
    backend.axis_write(axis, p.SET_OPERATING_MODE, OM.CLOSED_LOOP)
    mode = backend.axis_read(axis, p.GET_ACTIVE_OPERATING_MODE)
    if mode != OM.CLOSED_LOOP:
        raise CommutationError(f'axis {axis}: active operating mode 0x{mode:04X} after finalize, '
                               f'expected 0x{OM.CLOSED_LOOP:04X}', axes=[axis])


def _disarm(backend, axis):
    """Motor command 0, outputs off. Never raises."""
    for args in ((p.SET_MOTOR_COMMAND, 0), (p.SET_OPERATING_MODE, OM.IDLE)):
        try:
            backend.axis_write(axis, *args)
        except Exception:
            logger.exception('disarm of axis %s failed', axis)


# ---------------------------------------------------------------------------
# Homing
# ---------------------------------------------------------------------------

def _homing_velocity(backend, axis):
    return max(1, p.encode_velocity(abs(backend.homing_speed), backend._cpu(axis)))


def _load_homing_profile(backend, axis):
    cpu = backend._cpu(axis)
    acc = max(1, p.encode_acceleration(abs(backend.homing_acceleration), cpu))
    jerk = max(1, p.encode_jerk(abs(backend.homing_jerk), cpu))
    backend._write_profile(axis, (p.ProfileMode.S_CURVE, acc, acc, jerk))


def _axis_in(backend, axis) -> bool:
    """True if the centre-vane flag (Signal Status AxisIn) reports the positive half."""
    return bool(backend.axis_read(axis, p.GET_SIGNAL_STATUS) & (1 << p.SignalStatus.AXIS_IN))


def _position(backend, axis):
    pos = backend._read_counts(axis)
    if pos is None:
        raise MagellanError(f'no valid position for axis {axis}')
    return pos


def home_axis(backend, axis):
    """Home *axis* on the centre vane, approaching from the negative side; return the vane position.

    The returned value (caller units) is where the vane was in the previous frame, after
    which ActualPosition is set to 0 there. Requires the axis phased (NotCommutatedError)
    and in closed-loop servo (MagellanError). MOVES THE AXIS over up to ``backend.home_sweep``
    each way. Raises LimitError if a limit is reached during a sweep or offset move.
    """
    if not backend.refresh_phasing([axis])[axis]:
        raise NotCommutatedError([axis])
    mode = backend.axis_read(axis, p.GET_ACTIVE_OPERATING_MODE)
    if mode & OM.CLOSED_LOOP != OM.CLOSED_LOOP:
        raise MagellanError(f'axis {axis} is not servoing (mode 0x{mode:04X}); enable it before homing')
    if backend._read_activity(axis) & _IN_MOTION:
        backend._stop_axes([axis])
        backend._wait_stopped(axis, backend.stop_timeout)

    sweep = abs(backend._to_counts(axis, backend.home_sweep))
    offset = -abs(backend._to_counts(axis, backend.home_offset))
    backend._invalidate_profile([axis])
    try:
        _load_homing_profile(backend, axis)
        if _axis_in(backend, axis) or backend._read_activity(axis) & _POS_LIMIT:
            _sweep_to_vane(backend, axis, -sweep, want_axis_in=False)
            _run_trajectory(backend, axis, offset, 'homing offset move')
        if _axis_in(backend, axis):
            raise MagellanError(f'axis {axis} is still in the positive half before the final approach')
        _sweep_to_vane(backend, axis, sweep, want_axis_in=True)
        # let the servo pull actual onto the commanded stop point before zeroing
        vane = _wait_settled(backend, axis, backend._home_settle_counts[axis], HOME_SETTLE_S, HOME_SETTLE_TIMEOUT_S)
        if vane is None:
            vane = _position(backend, axis)
        backend.axis_write(axis, p.SET_ACTUAL_POSITION, 0)
        backend.axis_write(axis, p.SET_POSITION, 0)
        backend.axis_write(axis, p.UPDATE)
        backend.axis_write(axis, p.RESET_EVENT_STATUS, p.reset_event_mask(EV.MOTION_COMPLETE))
    except Exception:
        try:
            backend._stop_axes([axis])
        except Exception:
            pass
        raise
    finally:
        backend._invalidate_profile([axis])
    logger.info('axis %s homed; vane was at %d counts in the previous frame', axis, vane)
    return backend._to_units(axis, vane)


def _issue(backend, axis, target):
    # a stop (including a breakpoint stop) zeroes the velocity register; _buffer_target resends it
    backend._buffer_target(axis, _homing_velocity(backend, axis), target)
    backend.axis_write(axis, p.UPDATE)


def _move_timeout(backend, axis, distance):
    speed = abs(backend.homing_speed) * backend._cpu(axis)
    return abs(distance) / speed + MOVE_TIMEOUT_MARGIN_S


def _check_events(backend, axis, event, direction, pos):
    """Raise LimitError for a limit in the direction of travel, MagellanError for a fault."""
    bit, name = (EV.POSITIVE_LIMIT, 'positive') if direction > 0 else (EV.NEGATIVE_LIMIT, 'negative')
    here = 'unknown' if pos is None else backend._to_units(axis, pos)
    if event & (1 << bit):
        raise LimitError(f'axis {axis} hit the {name} limit at {here} while homing', axes=[axis])
    faults = [n for b, n in p.HARD_FAULT_EVENTS.items() if event & (1 << b)]
    if faults:
        raise MagellanError(f'axis {axis} faulted ({", ".join(faults)}) at {here} while homing')


def _sweep_to_vane(backend, axis, distance, want_axis_in):
    """Move up to *distance* counts, stopped in hardware by Breakpoint 1 when AxisIn == *want_axis_in*.

    Returns the stopped position. Raises MagellanError if the full distance runs without
    the flag, LimitError on a limit.
    """
    backend.axis_write(axis, p.RESET_EVENT_STATUS, 0)
    value = p.breakpoint_level_value(p.SignalStatus.AXIS_IN, want_axis_in)
    word = p.breakpoint_word(p.BreakpointTrigger.SIGNAL_STATUS, p.BreakpointAction.ABRUPT_STOP, 0)
    bp = p.BreakpointID.BREAKPOINT1
    try:
        # breakpoint value must be set before the breakpoint is armed
        backend.axis_write(axis, p.SET_BREAKPOINT_VALUE, bp, value)
        backend.axis_write(axis, p.SET_BREAKPOINT, bp, word)
        _run_trajectory(backend, axis, distance, 'homing sweep', until_breakpoint=True)
    finally:
        # disarm in reverse order
        for args in ((p.SET_BREAKPOINT, bp, 0), (p.SET_BREAKPOINT_VALUE, bp, 0)):
            try:
                backend.axis_write(axis, *args)
            except Exception:
                logger.exception('could not disarm breakpoint on axis %s', axis)
    backend._wait_stopped(axis, backend.stop_timeout)
    if _axis_in(backend, axis) != want_axis_in:
        raise MagellanError(f'axis {axis}: breakpoint fired but AxisIn is not {int(want_axis_in)}')
    backend.axis_write(axis, p.RESET_EVENT_STATUS, p.reset_event_mask(EV.MOTION_COMPLETE, EV.BREAKPOINT1))
    return _position(backend, axis)


def _run_trajectory(backend, axis, distance, what, until_breakpoint=False):
    """Move *distance* counts from the actual position at homing speed and wait for it to end.

    Ends when the axis is at rest within the arrival window of the target, or, with
    *until_breakpoint*, when Breakpoint 1 fires (reaching the target is then an error).
    Returns the last position read. Raises LimitError on a limit in the direction of travel,
    MagellanError on a fault, a timeout, or a trajectory that never starts. *what* names
    the move in errors.
    """
    start = _position(backend, axis)
    target = start + distance
    _issue(backend, axis, target)
    t0 = time.monotonic()
    deadline = t0 + _move_timeout(backend, axis, distance)
    started = False
    while True:
        time.sleep(POLL_S)
        act = backend._read_activity(axis)
        pos = backend._read_counts(axis)
        if act & _IN_MOTION or (pos is not None and abs(pos - start) > backend._motion_counts[axis]):
            started = True
        event = backend.axis_read(axis, p.GET_EVENT_STATUS)
        if until_breakpoint and event & (1 << EV.BREAKPOINT1):
            return pos
        _check_events(backend, axis, event, distance, pos)
        at_rest = event & (1 << EV.MOTION_COMPLETE) and not act & _IN_MOTION
        if at_rest and started:
            if until_breakpoint:
                raise MagellanError(f'axis {axis} swept {backend._to_units(axis, distance)} without '
                                    f'finding the centre vane')
            if pos is not None and abs(pos - target) <= backend._arrival_counts[axis]:
                return pos
        if at_rest and not started and time.monotonic() - t0 > START_TIMEOUT_S:
            raise MagellanError(f'axis {axis}: {what} never started')
        if time.monotonic() > deadline:
            raise MagellanError(f'axis {axis}: {what} timed out')
