"""MagellanPMD: StageDriver for a multi-drop RS-485 bus of PMD Magellan axes (Dover SmartStage)."""
from __future__ import annotations

import logging
import math
import os
import re
import threading
import time

from acq4.drivers.stage import MoveRequest, MoveState, StageDriver
from . import commutation
from . import protocol as p
from .protocol import (
    ChecksumError,
    CommunicationError,
    MagellanError,
    NotCommutatedError,
    PMDError,
)

logger = logging.getLogger(__name__)

AS = p.ActivityStatus
EV = p.EventStatus
OM = p.OperatingMode

_IN_MOTION = 1 << AS.IN_MOTION
_PHASED = 1 << AS.PHASING_INITIALIZED
_LIMIT_EVENTS = (1 << EV.POSITIVE_LIMIT) | (1 << EV.NEGATIVE_LIMIT)
# ResetEventStatus clears the bits that are 0 in its mask.
_PRE_MOVE_RESET_MASK = 0xFFFF & ~((1 << EV.MOTION_COMPLETE) | _LIMIT_EVENTS | (1 << EV.INSTRUCTION_ERROR))
_HARD_FAULTS = {
    EV.MOTION_ERROR: 'MotionError',
    EV.DISABLE: 'Disable',
    EV.OVERTEMPERATURE_FAULT: 'OvertemperatureFault',
    EV.DRIVE_EXCEPTION: 'DriveException',
}

# Vendor StandardMoveProfile: 400 mm/s^2, 50000 mm/s^3 at 200000 counts/mm.
DEFAULT_ACCELERATION_COUNTS = 400 * 200_000
DEFAULT_JERK_COUNTS = 50_000 * 200_000
# Vendor XAxisHomingProfile (S-curve) and homing distances at 200000 counts/mm.
HOMING_SPEED_COUNTS = 5 * 200_000
HOMING_ACCELERATION_COUNTS = 200 * 200_000
HOMING_JERK_COUNTS = 25_000 * 200_000
HOME_OFFSET_COUNTS = 10 * 200_000
HOME_SWEEP_COUNTS = 102 * 200_000
# 5 um at 5 nm/count; the IC's own settle window is 20 counts.
DEFAULT_ARRIVAL_WINDOW_COUNTS = 1000
# Reads beyond this are never accepted; 2**28 (the post-Reset artifact) is far outside any stroke.
DEFAULT_POSITION_LIMIT_COUNTS = 2 ** 27
# Movement that proves a trajectory ran; holding dither is +/-1 count.
MOTION_CONFIRM_COUNTS = 100

_PROFILE_MODES = {'scurve': p.ProfileMode.S_CURVE, 's-curve': p.ProfileMode.S_CURVE,
                  'trapezoidal': p.ProfileMode.TRAPEZOIDAL}


def _update_com_port(path):
    """Call dovermotion's ``update_com_port`` (imported lazily: the module loads pythonnet and Qt)."""
    from acq4.drivers.dovermotion.motionsynergy_api import update_com_port
    return update_com_port(path)


def read_instrument_cfg_port(motion_synergy_path) -> str:
    """Return the ``hwid=COMn`` port from ``<path>/SupportFolder/Instrument.cfg``."""
    cfg = os.path.join(motion_synergy_path, 'SupportFolder', 'Instrument.cfg')
    with open(cfg, 'r') as fh:
        text = fh.read()
    match = re.search(r'^\s*hwid\s*=\s*(\w+)\s*$', text, re.MULTILINE)
    if match is None:
        raise CommunicationError(f'no hwid= line in {cfg}')
    return match.group(1)


class _AxisMove:
    __slots__ = ('start', 'target', 'started', 'settle_since')

    def __init__(self, start, target):
        self.start = start
        self.target = target
        self.started = False
        self.settle_since = None


class MagellanPMD(StageDriver):
    """One RS-485 bus of single-axis Magellan ICs, addressed by node ID.

    Positions, speeds, accelerations and jerks are in caller units (``counts_per_unit``
    counts each), or raw encoder counts when ``counts_per_unit`` is None.

    ``move_to(pos, speed, acceleration=None, jerk=None, profile=None)``: a scalar *speed*
    (units/s) is the vector speed of a straight-line move, with each axis's speed,
    acceleration and jerk scaled by its share of the distance; a dict gives independent
    per-axis speeds. *acceleration* (units/s^2) and *jerk* (units/s^3) default to the
    constructor values; *profile* is 'scurve' or 'trapezoidal'. A trapezoidal move retargets
    an axis in motion directly; the IC rejects that for S-curve (or a profile change), so
    the axis is first stopped, blocking the control thread until it halts (~0.1-0.3 s).

    If ``connect()`` raises NotCommutatedError the driver stays connected and polling, so
    commutation can run without reconnecting; moves of unphased axes are refused and
    ``close()`` must still be called.

    Homing uses the attributes ``homing_speed``, ``homing_acceleration``, ``homing_jerk``
    (S-curve; default 5 mm/s, 200 mm/s^2, 25000 mm/s^3), ``home_offset`` (distance backed
    off past the vane before the final approach, default 10 mm) and ``home_sweep``
    (longest sweep, default 102 mm), all in caller units at 5 nm/count by default.

    Parameters
    ----------
    axes : dict
        Axis name -> node ID.
    port : str | None
        Serial port. None discovers it via ``update_com_port(motion_synergy_path)`` and
        the ``hwid=`` line of that folder's ``SupportFolder/Instrument.cfg``.
    counts_per_unit : float | dict | None
        Scalar or per-axis encoder counts per caller unit.
    acceleration, jerk : float | None
        Default profile, caller units; None = 400 mm/s^2 and 50000 mm/s^3 at 5 nm/count.
    profile : str
        Default profile, 'trapezoidal' or 'scurve'.
    arrival_window : float | None
        Distance from target within which a move counts as arrived; None = 1000 counts.
    position_limit : float | dict | None
        Reads with larger magnitude are discarded; None = 2**27 counts.
    serial_factory : callable
        Called like ``serial.Serial(port, baudrate=..., timeout=..., write_timeout=...)``.
    timeout : float
        Per-read serial timeout, seconds.
    retries : int
        Extra attempts after a timeout, corrupt response or bad-checksum status.
    settle_timeout : float
        Seconds after motion stops to wait for Motion Complete and arrival before failing.
    """

    def __init__(self, axes: dict, port: str | None = None, motion_synergy_path: str | None = None,
                 baudrate: int = 57600, counts_per_unit=None, poll_interval: float = 0.025, *,
                 acceleration=None, jerk=None, profile: str = 'trapezoidal', arrival_window=None,
                 position_limit=None, position_change_threshold=None, serial_factory=None,
                 timeout: float = 0.1, retries: int = 3, settle_timeout: float = 0.5,
                 resync_delay: float = 0.02):
        super().__init__()
        if not axes:
            raise ValueError('at least one axis is required')
        self.axes = dict(axes)
        self.port = port
        self.motion_synergy_path = motion_synergy_path
        self.baudrate = baudrate
        self.counts_per_unit = counts_per_unit
        self.poll_interval = poll_interval
        self.position_change_threshold = position_change_threshold
        self.timeout = timeout
        self.retries = retries
        self.settle_timeout = settle_timeout
        self.resync_delay = resync_delay
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        self._serial_factory = serial_factory
        self._serial = None
        self._open_port = None      # port actually opened (port may be None = discovered)
        self._io_lock = threading.RLock()

        self.default_acceleration = (DEFAULT_ACCELERATION_COUNTS / self._cpu_any()
                                     if acceleration is None else acceleration)
        self.default_jerk = DEFAULT_JERK_COUNTS / self._cpu_any() if jerk is None else jerk
        self.default_profile = self._profile_mode(profile)
        cpu = self._cpu_any()
        self.homing_speed = HOMING_SPEED_COUNTS / cpu
        self.homing_acceleration = HOMING_ACCELERATION_COUNTS / cpu
        self.homing_jerk = HOMING_JERK_COUNTS / cpu
        self.home_offset = HOME_OFFSET_COUNTS / cpu
        self.home_sweep = HOME_SWEEP_COUNTS / cpu
        self._arrival_counts = {
            ax: (DEFAULT_ARRIVAL_WINDOW_COUNTS if arrival_window is None
                 else abs(self._per_axis(arrival_window, ax)) * self._cpu(ax))
            for ax in self.axes}
        self._position_limit_counts = {
            ax: (DEFAULT_POSITION_LIMIT_COUNTS if position_limit is None
                 else abs(self._per_axis(position_limit, ax)) * self._cpu(ax))
            for ax in self.axes}

        self._static = {}           # (node, opcode) -> encoded no-argument packet
        self._counts = {}           # axis -> last accepted position, counts
        self._bad_reads = {ax: 0 for ax in self.axes}
        self._limits = {ax: {'neg': False, 'pos': False} for ax in self.axes}
        self._unphased: set = set()
        self._failed_commutation: set = set()   # phase angle untrustworthy whatever bit 0 says
        self._profile_cache = {}    # axis -> (mode, acc, dec, jerk) last sent

    # ---- units ----

    @staticmethod
    def _per_axis(value, axis):
        return value[axis] if isinstance(value, dict) else value

    def _cpu(self, axis):
        cpu = self.counts_per_unit
        return 1 if cpu is None else self._per_axis(cpu, axis)

    def _cpu_any(self):
        cpu = self.counts_per_unit
        if cpu is None:
            return 1
        return next(iter(cpu.values())) if isinstance(cpu, dict) else cpu

    def _to_units(self, axis, counts):
        return counts if self.counts_per_unit is None else counts / self._cpu(axis)

    def _to_counts(self, axis, value):
        return int(round(value * self._cpu(axis)))

    @staticmethod
    def _profile_mode(profile):
        if isinstance(profile, int):
            return profile
        try:
            return _PROFILE_MODES[profile.lower()]
        except KeyError:
            raise ValueError(f'unknown profile {profile!r}; use "scurve" or "trapezoidal"') from None

    # ---- connection ----

    def connect(self) -> None:
        """Open the port, check every node, start polling, and report commutation state.

        Never moves the stage. Raises CommunicationError if the port cannot be opened (e.g.
        held by MotionSynergy) or a node does not respond, and NotCommutatedError (after
        connecting) if any axis has Phasing Initialized clear.
        """
        port = self._resolve_port()
        try:
            ser = self._serial_factory(port, baudrate=self.baudrate, timeout=self.timeout,
                                       write_timeout=self.timeout)
        except Exception as exc:
            raise CommunicationError(
                f'cannot open serial port {port}: {exc}. If MotionSynergy (DoverStage) is running '
                f'it holds this port; only one process can own it.') from exc
        try:
            ser.reset_input_buffer()
            self._serial = ser
            self._open_port = port
            self._static = {(node, op): p.encode(node, op)
                            for node in self.axes.values()
                            for op in (p.GET_ACTUAL_POSITION, p.GET_ACTIVITY_STATUS,
                                       p.GET_EVENT_STATUS, p.UPDATE, p.GET_ACTIVE_OPERATING_MODE)}
            self._profile_cache.clear()
            self._counts.clear()
            phased = self._refresh_phasing()
            pos = self._read_position()
            with self._pos_lock:
                self._position = pos
            super().connect()
        except Exception:
            self._close_serial()
            raise
        unphased = [ax for ax, ok in phased.items() if not ok]
        if unphased:
            raise NotCommutatedError(unphased)

    def close(self) -> None:
        """Stop the control thread, then close the port. Sends no stop. Idempotent."""
        super().close()
        self._close_serial()

    def _close_serial(self):
        with self._io_lock:
            ser, self._serial = self._serial, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                logger.exception('error closing serial port')

    def _resolve_port(self) -> str:
        if self.port:
            return self.port
        if not self.motion_synergy_path:
            raise ValueError('either port or motion_synergy_path is required')
        err = _update_com_port(self.motion_synergy_path)
        if err:
            raise CommunicationError(f'serial port discovery failed: {err}')
        return read_instrument_cfg_port(self.motion_synergy_path)

    # ---- transport (thread-safe; normally used from the control thread) ----

    def transact(self, node_id: int, opcode: int, *args) -> tuple[int, list]:
        """Send one command and return ``(status, values)``; status is always 0.

        Retries after a timeout, corrupt response or bad-checksum status, flushing input
        first. Raises CommunicationError when attempts run out, PMDError on any other
        non-zero status.
        """
        pkt = None if args else self._static.get((node_id, opcode))
        if pkt is None:
            pkt = p.encode(node_id, opcode, *args)
        nbytes = p.response_length(opcode)
        name = p.OPCODE_NAMES.get(opcode, f'0x{opcode:02X}')
        last = None
        with self._io_lock:
            ser = self._serial
            if ser is None:
                raise CommunicationError('serial port is not open')
            for attempt in range(self.retries + 1):
                if attempt:
                    self._resync(ser)
                try:
                    ser.write(pkt)
                    raw = ser.read(p.HEADER_LENGTH)
                    if len(raw) < p.HEADER_LENGTH:
                        raise CommunicationError(
                            f'timeout: {len(raw)} of {p.HEADER_LENGTH} header bytes ({raw.hex(" ")})')
                    if raw[1] == 0 and nbytes:
                        data = ser.read(nbytes)
                        raw += data
                        if len(data) < nbytes:
                            raise CommunicationError(f'timeout: short response {raw.hex(" ")}')
                    status, values = p.parse_response(opcode, raw, node_id=node_id)
                except (ChecksumError, CommunicationError) as exc:
                    last = exc
                    logger.debug('%s to node %d attempt %d failed: %s', name, node_id, attempt + 1, exc)
                    continue
                if status == p.STATUS_BAD_CHECKSUM:
                    last = PMDError(status, opcode)
                    continue
                p.check_status(status, opcode)
                return status, values
        raise CommunicationError(
            f'no valid response to {name} from node {node_id} after {self.retries + 1} attempts: {last}'
        ) from last

    def _resync(self, ser):
        # let a late response finish arriving, then discard it (~12 ms on the Moxa adapter)
        time.sleep(self.resync_delay)
        ser.reset_input_buffer()

    def axis_read(self, axis: str, opcode: int, *args):
        """Send a command to *axis*; return its single response value, a list of several, or None."""
        _, values = self.transact(self.axes[axis], opcode, *args)
        if not values:
            return None
        return values[0] if len(values) == 1 else values

    def axis_write(self, axis: str, opcode: int, *args) -> None:
        """Send a command with no response data to *axis*."""
        self.transact(self.axes[axis], opcode, *args)

    # ---- state helpers (control thread) ----

    def _read_activity(self, axis) -> int:
        act = self.axis_read(axis, p.GET_ACTIVITY_STATUS)
        self._limits[axis] = {'neg': bool(act & (1 << AS.IN_NEGATIVE_LIMIT)),
                              'pos': bool(act & (1 << AS.IN_POSITIVE_LIMIT))}
        return act

    def _refresh_phasing(self, axes=None) -> dict:
        """Read Activity Status; update the unphased set; return axis -> phased.

        Axes whose last commutation failed count as unphased even if Phasing Initialized is set.
        """
        out = {}
        for ax in (self.axes if axes is None else axes):
            out[ax] = bool(self._read_activity(ax) & _PHASED) and ax not in self._failed_commutation
            if out[ax]:
                self._unphased.discard(ax)
            else:
                self._unphased.add(ax)
        return out

    def _invalidate_profile(self, axes=None):
        """Force the next move to resend profile mode, acceleration, deceleration and jerk."""
        for ax in (list(self._profile_cache) if axes is None else axes):
            self._profile_cache.pop(ax, None)

    def _read_counts(self, axis):
        """Read GetActualPosition; return accepted counts, or the last accepted value if implausible."""
        raw = self.axis_read(axis, p.GET_ACTUAL_POSITION)
        if abs(raw) > self._position_limit_counts[axis]:
            self._bad_reads[axis] += 1
            if self._bad_reads[axis] == 1:
                logger.warning('discarding implausible position %d counts on axis %s', raw, axis)
            return self._counts.get(axis)
        self._bad_reads[axis] = 0
        self._counts[axis] = raw
        return raw

    def unphased_axes(self) -> list:
        """Axes known to need commutation (as of connect or the last phasing check)."""
        return [ax for ax in self.axes if ax in self._unphased]

    # ---- hooks ----

    def _read_position(self) -> dict:
        pos = {}
        for ax in self.axes:
            c = self._read_counts(ax)
            if c is not None:
                pos[ax] = self._to_units(ax, c)
        return pos

    def _send_move(self, req: MoveRequest) -> None:
        unknown = set(req.target) - set(self.axes)
        if unknown:
            raise ValueError(f'unknown axes {sorted(unknown)}')
        unphased = [ax for ax in req.target if ax in self._unphased]
        if unphased:
            raise NotCommutatedError(unphased)
        if req.speed is None:
            raise ValueError('speed is required')

        kw = req.kwds
        acc = kw.get('acceleration') or self.default_acceleration
        jerk = kw.get('jerk') or self.default_jerk
        mode = self._profile_mode(kw['profile']) if kw.get('profile') else self.default_profile

        moves = {}
        for ax, value in req.target.items():
            start = self._counts.get(ax)
            if start is None:
                start = self._read_counts(ax)
            if start is None:
                raise CommunicationError(f'no valid position for axis {ax}')
            moves[ax] = _AxisMove(start, self._to_counts(ax, value))
        scale = self._axis_scales(req, moves)

        try:
            for ax, mv in moves.items():
                cpu = self._cpu(ax)
                f = scale[ax]
                enc_acc = max(1, p.encode_acceleration(acc * f, cpu))
                enc_jerk = max(1, p.encode_jerk(jerk * f, cpu))
                profile = (mode, enc_acc, enc_acc, enc_jerk)
                cached = self._profile_cache.get(ax)
                needs_stop = mode == p.ProfileMode.S_CURVE or cached is None or cached[0] != mode
                if needs_stop and self._read_activity(ax) & _IN_MOTION:
                    # The IC rejects an S-curve or profile-mode Update in motion (status 12),
                    # and the rejection also poisons a later stop, so stop before buffering.
                    self._stop_axes([ax])
                    self._wait_stopped(ax, self.stop_timeout)
                if cached != profile:
                    self._profile_cache.pop(ax, None)
                    self.axis_write(ax, p.SET_PROFILE_MODE, mode)
                    self.axis_write(ax, p.SET_ACCELERATION, enc_acc)
                    self.axis_write(ax, p.SET_DECELERATION, enc_acc)
                    self.axis_write(ax, p.SET_JERK, enc_jerk)
                    self._profile_cache[ax] = profile
                speed = self._per_axis(req.speed, ax) * f
                self._buffer_target(ax, max(1, p.encode_velocity(abs(speed), cpu)), mv.target)
            for ax in moves:
                self.axis_write(ax, p.UPDATE)
        except Exception:
            # never leave an axis finishing a superseded trajectory unsupervised
            try:
                self._stop_axes(list(moves))
            except Exception:
                pass
            raise
        req._pmd_moves = moves

    def _buffer_target(self, axis, velocity, target):
        # a stop zeroes the velocity register, so it is sent with every move
        self.axis_write(axis, p.SET_VELOCITY, velocity)
        self.axis_write(axis, p.SET_POSITION, target)
        self.axis_write(axis, p.RESET_EVENT_STATUS, _PRE_MOVE_RESET_MASK)

    def _wait_stopped(self, axis, timeout):
        """Poll Activity Status until In-Motion clears; MagellanError after *timeout* seconds."""
        deadline = time.monotonic() + timeout
        while self._read_activity(axis) & _IN_MOTION:
            if time.monotonic() > deadline:
                raise MagellanError(f'axis {axis} still in motion {timeout} s after stop')

    def _axis_scales(self, req, moves) -> dict:
        """Per-axis profile scale: distance share for a scalar speed, else 1."""
        if isinstance(req.speed, dict) or len(moves) < 2:
            return {ax: 1.0 for ax in moves}
        dist = {ax: abs(self._to_units(ax, mv.target - mv.start)) for ax, mv in moves.items()}
        total = math.sqrt(sum(d * d for d in dist.values()))
        if total == 0:
            return {ax: 1.0 for ax in moves}
        return {ax: max(d / total, 1e-3) for ax, d in dist.items()}

    def _send_stop(self, reason: str) -> None:
        self._stop_axes(list(self.axes))

    def _stop_axes(self, axes):
        """SetStopMode(Smooth) + Update on each axis; raises the first error after trying all."""
        first = None
        for ax in axes:
            try:
                self.axis_write(ax, p.SET_STOP_MODE, p.StopMode.SMOOTH)
                self.axis_write(ax, p.UPDATE)
            except Exception as exc:
                logger.exception('stop failed on axis %s', ax)
                first = first or exc
        if first is not None:
            raise first

    def _check_move(self, req: MoveRequest):
        moves = getattr(req, '_pmd_moves', None)
        if not moves:
            return MoveState.FAILED, f'{req} has no record of being sent'
        in_motion = False
        for ax, mv in moves.items():
            act = self._read_activity(ax)
            if act & _IN_MOTION:
                mv.started = True
                in_motion = True
        if in_motion:
            return MoveState.MOVING, None
        if req.done():
            # stopped/interrupted move awaited by stop_before_move: motion has ceased
            return MoveState.DONE, None

        now = time.monotonic()
        waiting = []
        for ax, mv in moves.items():
            event = self.axis_read(ax, p.GET_EVENT_STATUS)
            pos = self._read_counts(ax)
            if pos is not None and abs(pos - mv.start) > MOTION_CONFIRM_COUNTS:
                mv.started = True
            faults = [name for bit, name in _HARD_FAULTS.items() if event & (1 << bit)]
            limits = [name for bit, name in ((EV.POSITIVE_LIMIT, 'positive'), (EV.NEGATIVE_LIMIT, 'negative'))
                      if event & (1 << bit)]
            here = 'unknown' if pos is None else self._to_units(ax, pos)
            target = self._to_units(ax, mv.target)
            if limits:
                return MoveState.FAILED, (f'LimitError: axis {ax} hit the {" and ".join(limits)} limit at '
                                          f'{here} (target {target})')
            if faults:
                return MoveState.FAILED, f'axis {ax} faulted ({", ".join(faults)}) at {here} (target {target})'
            arrived = pos is not None and abs(pos - mv.target) <= self._arrival_counts[ax]
            if arrived and event & (1 << EV.MOTION_COMPLETE):
                continue
            if mv.settle_since is None:
                mv.settle_since = now
            if now - mv.settle_since < self.settle_timeout:
                waiting.append(ax)
                continue
            why = 'stopped short' if event & (1 << EV.MOTION_COMPLETE) else 'stopped without Motion Complete'
            never = '' if mv.started else '; the trajectory never started'
            return MoveState.FAILED, f'axis {ax} {why} at {here} (target {target}){never}'
        if waiting:
            return MoveState.MOVING, None
        return MoveState.DONE, None

    # ---- PMD-specific public API ----

    def set_enabled(self, enabled: bool, axes: list | None = None, reason: str = ''):
        """Enable (closed-loop servo, 0x37) or disable (idle, 0x01) motor drive; returns a future.

        Disabling removes motor output: Z sags ~15 mm. Enabling holds the current position,
        clears latched events, and is refused for unphased axes (NotCommutatedError).
        """
        axes = list(self.axes) if axes is None else list(axes)
        return self._submit(self._set_enabled, bool(enabled), axes, reason)

    def _set_enabled(self, enabled, axes, reason):
        unknown = set(axes) - set(self.axes)
        if unknown:
            raise ValueError(f'unknown axes {sorted(unknown)}')
        if reason:
            logger.info('%s axes %s: %s', 'enabling' if enabled else 'disabling', axes, reason)
        if not enabled:
            for ax in axes:
                self.axis_write(ax, p.SET_OPERATING_MODE, OM.IDLE)
            return
        self._refresh_phasing(axes)
        unphased = [ax for ax in axes if ax in self._unphased]
        if unphased:
            raise NotCommutatedError(unphased)
        for ax in axes:
            pos = self._read_counts(ax)
            if pos is None:
                raise CommunicationError(f'no valid position for axis {ax}')
            self.axis_write(ax, p.SET_POSITION, pos)
            self.axis_write(ax, p.CLEAR_POSITION_ERROR)
            self.axis_write(ax, p.UPDATE)
            self.axis_write(ax, p.RESET_EVENT_STATUS, 0)
            self.axis_write(ax, p.SET_OPERATING_MODE, OM.CLOSED_LOOP)
        self._invalidate_profile(axes)

    def commutate(self, axes: list | None = None, drive_levels=(2048, 4096, 8192)):
        """Phase-initialize unphased axes, one at a time; returns a future.

        MOVES EACH AXIS up to ~20.6 mm in an unpredictable direction and cannot be interrupted
        once started; ensure that much clearance both ways. Removing motor output first lets a
        vertical axis sag (Z ~15 mm). Already-phased axes are skipped. Escalates through
        *drive_levels* (SetMotorCommand, 1..32767) until Phasing Initialized is set with no
        Commutation Error. Interrupts any active move. On success the axis servos where it
        came to rest, with position zeroed there (not homed).

        The future's result is ``{axis: drive level used, or None if skipped}``; it fails with
        CommutationError (cause) naming the axis once the levels are exhausted.
        """
        axes = list(self.axes) if axes is None else list(axes)
        return self._submit(self._commutate, axes, tuple(drive_levels))

    def _commutate(self, axes, drive_levels):
        self._check_axes(axes)
        self._interrupt_motion('commutation')
        try:
            return {ax: commutation.commutate_axis(self, ax, drive_levels) for ax in axes}
        finally:
            self._publish_position(self._read_position())

    def home(self, axes: list | None = None):
        """Home axes on the centre vane, one at a time; returns a future.

        MOVES EACH AXIS over up to its full travel. Axes must be phased and enabled. Always
        finishes approaching the vane from the negative side, then sets position 0 there.
        Interrupts any active move. The future's result is ``{axis: vane position in the
        previous frame}``; it fails (cause NotCommutatedError, LimitError or MagellanError)
        if an axis cannot be homed.
        """
        axes = list(self.axes) if axes is None else list(axes)
        return self._submit(self._home, axes)

    def _home(self, axes):
        self._check_axes(axes)
        self._interrupt_motion('homing')
        try:
            return {ax: commutation.home_axis(self, ax) for ax in axes}
        finally:
            self._publish_position(self._read_position())

    def _check_axes(self, axes):
        unknown = set(axes) - set(self.axes)
        if unknown:
            raise ValueError(f'unknown axes {sorted(unknown)}')

    def _publish_position(self, pos=None):
        """Update the cached position (and fire the position callback) from *pos* or ``_counts``."""
        if pos is None:
            pos = {ax: self._to_units(ax, c) for ax, c in self._counts.items()}
        super()._publish_position(pos)

    def is_enabled(self, timeout: float = 5.0) -> dict:
        """Axis -> True if the active operating mode is full closed-loop servo. Blocks."""
        return self._submit(self._is_enabled).wait(timeout)

    def _is_enabled(self):
        return {ax: (self.axis_read(ax, p.GET_ACTIVE_OPERATING_MODE) & OM.CLOSED_LOOP) == OM.CLOSED_LOOP
                for ax in self.axes}

    def get_limits(self, timeout: float = 5.0) -> dict:
        """Limit switch states, ``{'x': {'neg': bool, 'pos': bool}, ...}``, freshly read. Blocks."""
        return self._submit(self._get_limits).wait(timeout)

    def _get_limits(self):
        for ax in self.axes:
            self._read_activity(ax)
        return {ax: dict(v) for ax, v in self._limits.items()}

    def __repr__(self):
        return f'<MagellanPMD {self.port or self._open_port or "?"} axes={self.axes}>'
