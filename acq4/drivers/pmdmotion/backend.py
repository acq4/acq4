"""MagellanBackend: StageBackend for a multi-drop RS-485 bus of PMD Magellan single-axis controllers."""
from __future__ import annotations

import logging
import math
import time

from acq4.drivers.stage import MoveCancelled, MoveState
from . import commutation
from . import protocol as p
from .serial_ports import ensure_rs485_4w, resolve_port
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
_PRE_MOVE_RESET_MASK = p.reset_event_mask(EV.MOTION_COMPLETE, EV.POSITIVE_LIMIT, EV.NEGATIVE_LIMIT,
                                          EV.INSTRUCTION_ERROR)

# Defaults (encoder counts) for distance options left as None.
# Above the Magellan IC's own 20-count settle window.
DEFAULT_ARRIVAL_WINDOW_COUNTS = 1000
# GetActualPosition sometimes returns 2**28 shortly after an IC Reset.
DEFAULT_POSITION_LIMIT_COUNTS = 2 ** 27
# Movement that proves a trajectory ran; holding dither is a few counts.
DEFAULT_MOTION_THRESHOLD_COUNTS = 100
# At rest = moved less than this within a hold time: after phase init, and at the home flag.
DEFAULT_SETTLE_THRESHOLD_COUNTS = 100
DEFAULT_HOME_SETTLE_THRESHOLD_COUNTS = 10

_PROFILE_MODES = {'scurve': p.ProfileMode.S_CURVE, 's-curve': p.ProfileMode.S_CURVE,
                  'trapezoidal': p.ProfileMode.TRAPEZOIDAL}


def profile_mode(profile) -> int:
    """ProfileMode for *profile*: 'scurve', 'trapezoidal' (any case) or a ProfileMode value."""
    if isinstance(profile, int):
        return profile
    try:
        return _PROFILE_MODES[profile.lower()]
    except KeyError:
        raise ValueError(f'unknown profile {profile!r}; use "scurve" or "trapezoidal"') from None


_qapp = None   # QApplication made by qt_confirm_commutation when none existed


def qt_confirm_commutation(axes, text) -> bool:
    """Ask in a modal Qt warning dialog (OK/Cancel, default Cancel); True if OK.

    Runs the dialog on the GUI thread, blocking the calling thread; creates a
    QApplication if none exists.
    """
    global _qapp
    from acq4.util import Qt
    if Qt.QApplication.instance() is None:
        _qapp = Qt.QApplication([])

    def ask():
        box = Qt.QMessageBox()
        box.setWindowTitle('Commutate stage axes')
        box.setIcon(Qt.QMessageBox.Warning)
        box.setText(text)
        box.setStandardButtons(Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel)
        box.setDefaultButton(Qt.QMessageBox.Cancel)
        return box.exec_() == Qt.QMessageBox.Ok

    from acq4.util.task import run_in_gui_thread
    return run_in_gui_thread(ask)


class _AxisMove:
    __slots__ = ('start', 'target', 'started', 'settle_since')

    def __init__(self, start, target):
        self.start = start
        self.target = target
        self.started = False
        self.settle_since = None


class _MoveHandle:
    """Per-axis progress of one commanded move: axis -> _AxisMove."""
    __slots__ = ('axes',)

    def __init__(self, axes: dict):
        self.axes = axes


class MagellanBackend:
    """StageBackend for one RS-485 bus of single-axis Magellan ICs, addressed by node ID.

    Every method does serial I/O (or reads state written by methods that do) and must be
    called only from the owning driver's control thread; not thread-safe. Positions,
    speeds, accelerations and jerks are in driver units (``counts_per_unit`` counts each),
    or raw encoder counts when ``counts_per_unit`` is None.

    ``start_move(target, speed, acceleration=None, jerk=None, profile=None)``: a scalar
    *speed* (units/s) is the vector speed of a straight-line move, with each axis's speed,
    acceleration and jerk scaled by its share of the distance; a dict gives independent
    per-axis speeds. *acceleration* (units/s^2) and *jerk* (units/s^3) default to the
    constructor values; *profile* is 'scurve' or 'trapezoidal'. A trapezoidal move retargets
    an axis in motion directly; the IC rejects that for S-curve (or a profile change), so
    the axis is first stopped, blocking until it halts (~0.1-0.3 s).

    A move, enable or homing of an unphased (uncommutated) axis raises NotCommutatedError.
    An axis counts as unphased if Phasing Initialized is clear or its last commutation failed.

    Parameters
    ----------
    axes : dict
        Axis name -> node ID.
    port : str | None
        Serial port. Required unless *port_search* is given.
    port_search : str | None
        Used when *port* is None. ``'VID:PID'`` (hex) or a description substring; :meth:`open`
        uses the single matching port and raises CommunicationError for zero or several.
    counts_per_unit : float | dict | None
        Encoder counts per driver unit. A per-axis dict must have equal values
        (NotImplementedError otherwise).
    acceleration, jerk : float
        Required. Default move profile, units/s^2 and units/s^3.
    profile : str
        Default profile, 'trapezoidal' or 'scurve'.
    homing_speed, homing_acceleration, homing_jerk : float
        Required. S-curve profile for homing moves.
    home_offset : float
        Required. Distance backed off past the home flag before the final approach.
    home_sweep : float
        Required. Longest homing sweep (at least the axis travel).
    set_rs485_4w : bool
        If True, :meth:`open` sets the port to RS-485-4W mode (may prompt for elevation).
    auto_commutate : bool
        Default for ``commutate(confirm=None)``: True commutates without asking.
    confirm_commutation : callable | None
        ``confirm_commutation(axes, text) -> bool``, called on the control thread when
        :meth:`commutate` asks. None = :func:`qt_confirm_commutation`.
    arrival_window : float | dict | None
        Distance from target within which a stopped axis counts as arrived; None = 1000 counts.
    position_limit : float | dict | None
        Position reads with larger magnitude are discarded; None = 2**27 counts.
    motion_threshold : float | dict | None
        Distance from the start position that proves a trajectory ran; None = 100 counts.
    settle_threshold : float | dict | None
        An axis coasting after phase initialization is at rest once it moves less than
        this in 0.2 s; None = 100 counts.
    home_settle_threshold : float | dict | None
        As *settle_threshold*, at the home flag before zeroing (0.15 s); None = 10 counts.
    serial_factory : callable
        Called like ``serial.Serial(port, baudrate=..., timeout=..., write_timeout=...)``.
    timeout : float
        Per-read serial timeout, seconds.
    retries : int
        Extra attempts after a timeout, corrupt response or bad-checksum status.
    settle_timeout : float
        Seconds after motion stops to wait for Motion Complete and arrival before failing.
    stop_timeout : float
        Seconds to wait for an axis to halt after a stop issued inside a move or homing.
    resync_delay : float
        Seconds to wait for a late response before flushing input on a retry.
    """

    stop_before_move = False

    def __init__(self, axes: dict, port: str | None = None, port_search: str | None = None,
                 baudrate: int = 57600, counts_per_unit=None, *, acceleration, jerk, homing_speed,
                 homing_acceleration, homing_jerk, home_offset, home_sweep, profile: str = 'trapezoidal',
                 set_rs485_4w: bool = False, auto_commutate: bool = False, confirm_commutation=None,
                 arrival_window=None,
                 position_limit=None, motion_threshold=None, settle_threshold=None,
                 home_settle_threshold=None, serial_factory=None, timeout: float = 0.1, retries: int = 3,
                 settle_timeout: float = 0.5, stop_timeout: float = 5.0, resync_delay: float = 0.02):
        if not axes:
            raise ValueError('at least one axis is required')
        self.nodes = dict(axes)
        self.axes = tuple(axes)
        if bool(port) == bool(port_search):
            raise ValueError('exactly one of port or port_search is required')
        self.port = port
        self.port_search = port_search
        self.baudrate = baudrate
        if isinstance(counts_per_unit, dict):
            values = {counts_per_unit[ax] for ax in self.axes}
            if len(values) != 1:
                raise NotImplementedError(
                    f'counts_per_unit must be the same for every axis, got {counts_per_unit}')
            counts_per_unit = values.pop()
        self.counts_per_unit = counts_per_unit
        self.timeout = timeout
        self.retries = retries
        self.settle_timeout = settle_timeout
        self.stop_timeout = stop_timeout
        self.resync_delay = resync_delay
        self.set_rs485_4w = set_rs485_4w
        self.auto_commutate = auto_commutate
        self.confirm_commutation = confirm_commutation
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        self._serial_factory = serial_factory
        self._serial = None
        self._open_port = None      # port opened by open(): *port*, or the discovered one

        self.default_acceleration = acceleration
        self.default_jerk = jerk
        self.default_profile = profile_mode(profile)
        self.homing_speed = homing_speed
        self.homing_acceleration = homing_acceleration
        self.homing_jerk = homing_jerk
        self.home_offset = home_offset
        self.home_sweep = home_sweep
        # axis -> threshold in counts
        self._arrival_counts = self._counts_option(arrival_window, DEFAULT_ARRIVAL_WINDOW_COUNTS)
        self._position_limit_counts = self._counts_option(position_limit, DEFAULT_POSITION_LIMIT_COUNTS)
        self._motion_counts = self._counts_option(motion_threshold, DEFAULT_MOTION_THRESHOLD_COUNTS)
        self._settle_counts = self._counts_option(settle_threshold, DEFAULT_SETTLE_THRESHOLD_COUNTS)
        self._home_settle_counts = self._counts_option(home_settle_threshold,
                                                       DEFAULT_HOME_SETTLE_THRESHOLD_COUNTS)

        self._static = {}           # (node, opcode) -> encoded no-argument packet
        self._counts = {}           # axis -> last accepted position, counts
        self._bad_reads = {ax: 0 for ax in self.axes}
        self._unphased: set = set()
        self._failed_commutation: set = set()   # last commutation failed: unphased even if Phasing Initialized is set
        self._profile_cache = {}    # axis -> (mode, acc, dec, jerk) last sent

    # ---- units ----

    @staticmethod
    def _per_axis(value, axis):
        return value[axis] if isinstance(value, dict) else value

    def _counts_option(self, value, default_counts) -> dict:
        """Axis -> abs(*value*) (driver units; scalar or per-axis dict) in counts; None = *default_counts*."""
        return {ax: default_counts if value is None else abs(self._per_axis(value, ax)) * self._cpu(ax)
                for ax in self.axes}

    def _cpu(self, axis):
        return 1 if self.counts_per_unit is None else self.counts_per_unit

    def _to_units(self, axis, counts):
        return counts if self.counts_per_unit is None else counts / self._cpu(axis)

    def _to_counts(self, axis, value):
        return int(round(value * self._cpu(axis)))

    # ---- connection ----

    def open(self) -> None:
        """Find and open the port, check every node and read phasing.

        Never commutates. Raises CommunicationError if the port cannot be found or opened
        (e.g. held by another program) or a node does not respond.
        """
        port = resolve_port(self.port, self.port_search)
        if self.set_rs485_4w:
            ensure_rs485_4w(port)
        self._open_port = port
        try:
            ser = self._serial_factory(port, baudrate=self.baudrate, timeout=self.timeout,
                                       write_timeout=self.timeout)
        except Exception as exc:
            raise CommunicationError(
                f'cannot open serial port {port}: {exc}. Only one process can own the port; another '
                f'program (e.g. MotionSynergy) may be holding it.') from exc
        self._serial = ser
        ser.reset_input_buffer()
        self._static = {(node, op): p.encode(node, op)
                        for node in self.nodes.values()
                        for op in (p.GET_ACTUAL_POSITION, p.GET_ACTIVITY_STATUS,
                                   p.GET_EVENT_STATUS, p.UPDATE, p.GET_ACTIVE_OPERATING_MODE)}
        self.refresh_phasing()
        if self._unphased:
            logger.info('axes %s are not commutated', ', '.join(ax for ax in self.axes if ax in self._unphased))

    def close(self) -> None:
        ser, self._serial = self._serial, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                logger.exception('error closing serial port')

    # ---- transport ----

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
        _, values = self.transact(self.nodes[axis], opcode, *args)
        if not values:
            return None
        return values[0] if len(values) == 1 else values

    def axis_write(self, axis: str, opcode: int, *args) -> None:
        """Send a command with no response data to *axis*."""
        self.transact(self.nodes[axis], opcode, *args)

    # ---- state helpers ----

    def _read_activity(self, axis) -> int:
        return self.axis_read(axis, p.GET_ACTIVITY_STATUS)

    def refresh_phasing(self, axes=None) -> dict:
        """Read Activity Status of *axes* (default all); update the unphased set; return axis -> phased.

        Axes whose last commutation failed count as unphased even if Phasing Initialized is set.
        """
        out = {}
        for ax in (self.axes if axes is None else axes):
            out[ax] = bool(self._read_activity(ax) & _PHASED) and ax not in self._failed_commutation
        for ax, ok in out.items():
            if ok:
                self._unphased.discard(ax)
            else:
                self._unphased.add(ax)
        return out

    def _invalidate_profile(self, axes=None):
        """Force the next move to resend profile mode, acceleration, deceleration and jerk."""
        for ax in (list(self._profile_cache) if axes is None else axes):
            self._profile_cache.pop(ax, None)

    def _read_counts(self, axis):
        """Read GetActualPosition; return counts, or None if the read is implausible."""
        raw = self.axis_read(axis, p.GET_ACTUAL_POSITION)
        if raw is None:
            raise CommunicationError(f'GetActualPosition on axis {axis} returned no value')
        if abs(raw) > self._position_limit_counts[axis]:
            self._bad_reads[axis] += 1
            if self._bad_reads[axis] == 1:
                logger.warning('discarding implausible position %d counts on axis %s', raw, axis)
            return None
        self._bad_reads[axis] = 0
        self._counts[axis] = raw
        return raw

    def _check_axes(self, axes):
        unknown = set(axes) - set(self.axes)
        if unknown:
            raise ValueError(f'unknown axes {sorted(unknown)}')

    # ---- StageBackend ----

    def read_position(self) -> dict:
        """Read every axis; CommunicationError if any axis has no valid read."""
        pos = {}
        for ax in self.axes:
            c = self._read_counts(ax)
            if c is None:
                raise CommunicationError(f'no valid position for axis {ax}')
            pos[ax] = self._to_units(ax, c)
        return pos

    def poll_extra(self) -> None:
        pass

    def start_move(self, target: dict, speed, acceleration=None, jerk=None, profile=None) -> _MoveHandle:
        self._check_axes(target)
        unphased = [ax for ax in target if ax in self._unphased]
        if unphased:
            raise NotCommutatedError(unphased)
        if speed is None:
            raise ValueError('speed is required')

        acc = acceleration or self.default_acceleration
        jerk = jerk or self.default_jerk
        mode = profile_mode(profile) if profile else self.default_profile

        moves = {}
        for ax, value in target.items():
            start = self._counts.get(ax)
            if start is None:
                start = self._read_counts(ax)
            if start is None:
                raise CommunicationError(f'no valid position for axis {ax}')
            moves[ax] = _AxisMove(start, self._to_counts(ax, value))
        scale = self._axis_scales(speed, moves)

        try:
            for ax, mv in moves.items():
                cpu = self._cpu(ax)
                f = scale[ax]
                enc_acc = max(1, p.encode_acceleration(acc * f, cpu))
                enc_jerk = max(1, p.encode_jerk(jerk * f, cpu))
                axis_profile = (mode, enc_acc, enc_acc, enc_jerk)
                cached = self._profile_cache.get(ax)
                needs_stop = mode == p.ProfileMode.S_CURVE or cached is None or cached[0] != mode
                if needs_stop and self._read_activity(ax) & _IN_MOTION:
                    # The Magellan IC rejects an S-curve or profile-mode Update in motion (status 12),
                    # and the rejection also poisons a later stop, so stop before buffering.
                    self._stop_axes([ax])
                    self._wait_stopped(ax, self.stop_timeout)
                if cached != axis_profile:
                    self._profile_cache.pop(ax, None)
                    self._write_profile(ax, axis_profile)
                    self._profile_cache[ax] = axis_profile
                axis_speed = self._per_axis(speed, ax) * f
                self._buffer_target(ax, max(1, p.encode_velocity(abs(axis_speed), cpu)), mv.target)
            for ax in moves:
                self.axis_write(ax, p.UPDATE)
        except Exception:
            # never leave an axis finishing a superseded trajectory unsupervised
            try:
                self._stop_axes(list(moves))
            except Exception:
                pass
            raise
        return _MoveHandle(moves)

    def _write_profile(self, axis, profile):
        """Write encoded ``(mode, acceleration, deceleration, jerk)``; does not touch the cache."""
        mode, acc, dec, jerk = profile
        self.axis_write(axis, p.SET_PROFILE_MODE, mode)
        self.axis_write(axis, p.SET_ACCELERATION, acc)
        self.axis_write(axis, p.SET_DECELERATION, dec)
        self.axis_write(axis, p.SET_JERK, jerk)

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

    def _axis_scales(self, speed, moves) -> dict:
        """Per-axis profile scale: distance share for a scalar speed, else 1."""
        if isinstance(speed, dict) or len(moves) < 2:
            return {ax: 1.0 for ax in moves}
        dist = {ax: abs(self._to_units(ax, mv.target - mv.start)) for ax, mv in moves.items()}
        total = math.sqrt(sum(d * d for d in dist.values()))
        if total == 0:
            return {ax: 1.0 for ax in moves}
        return {ax: max(d / total, 1e-3) for ax, d in dist.items()}

    def stop(self, reason: str) -> None:
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

    def _poll_in_motion(self, handle: _MoveHandle) -> bool:
        """Read Activity Status of every axis of *handle*; True if any is in motion."""
        in_motion = False
        for mv_axis, mv in handle.axes.items():
            if self._read_activity(mv_axis) & _IN_MOTION:
                mv.started = True
                in_motion = True
        return in_motion

    def is_moving(self, handle: _MoveHandle) -> bool:
        return self._poll_in_motion(handle)

    def check_move(self, handle: _MoveHandle):
        if self._poll_in_motion(handle):
            return MoveState.MOVING, None

        now = time.monotonic()
        waiting = []
        for ax, mv in handle.axes.items():
            event = self.axis_read(ax, p.GET_EVENT_STATUS)
            pos = self._read_counts(ax)
            if pos is not None and abs(pos - mv.start) > self._motion_counts[ax]:
                mv.started = True
            faults = [name for bit, name in p.HARD_FAULT_EVENTS.items() if event & (1 << bit)]
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

    def final_position(self, handle: _MoveHandle) -> dict:
        # Read every axis: check_move read only the moved ones, the poll cache can be
        # stale, and this position also relocates every device attached to the stage.
        return self.read_position()

    # ---- device operations ----

    def set_enabled(self, enabled: bool, axes=None, reason: str = '') -> None:
        """Enable (closed-loop servo, 0x37) or disable (idle, 0x01) motor drive of *axes* (default all).

        Enabling holds the current position, clears latched events, and raises
        NotCommutatedError for unphased axes.
        """
        axes = list(self.axes) if axes is None else list(axes)
        self._check_axes(axes)
        if reason:
            logger.info('%s axes %s: %s', 'enabling' if enabled else 'disabling', axes, reason)
        if not enabled:
            for ax in axes:
                self.axis_write(ax, p.SET_OPERATING_MODE, OM.IDLE)
            return
        self.refresh_phasing(axes)
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

    def is_enabled(self) -> dict:
        """Axis -> True if the active operating mode is full closed-loop servo."""
        return {ax: (self.axis_read(ax, p.GET_ACTIVE_OPERATING_MODE) & OM.CLOSED_LOOP) == OM.CLOSED_LOOP
                for ax in self.axes}

    def get_limits(self) -> dict:
        """Limit switch states, ``{'x': {'neg': bool, 'pos': bool}, ...}``."""
        out = {}
        for ax in self.axes:
            act = self._read_activity(ax)
            out[ax] = {'neg': bool(act & (1 << AS.IN_NEGATIVE_LIMIT)),
                       'pos': bool(act & (1 << AS.IN_POSITIVE_LIMIT))}
        return out

    def commutate(self, axes=None, drive_levels=(2048, 4096, 8192), confirm: bool | None = None) -> dict:
        """Phase-initialize the unphased axes among *axes* (default all), one at a time.

        If no requested axis is unphased, returns at once without asking. Otherwise, if
        *confirm* (None = ``not auto_commutate``), asks ``confirm_commutation`` first and
        raises MoveCancelled if declined. Commutation MOVES EACH AXIS a large, unpredictable
        distance and escalates through *drive_levels* (SetMotorCommand, 1..32767) until
        Phasing Initialized is set with no Commutation Error. A commutated axis servos where
        it came to rest, position zeroed there (not homed).

        Returns ``{axis: drive level used, or None if already phased}``. Raises
        CommutationError (or the I/O error) on failure.
        """
        axes = list(self.axes) if axes is None else list(axes)
        self._check_axes(axes)
        phased = self.refresh_phasing(axes)
        unphased = [ax for ax in axes if not phased[ax]]
        if not unphased:
            return {ax: None for ax in axes}
        ask = not self.auto_commutate if confirm is None else confirm
        if ask:
            confirm_fn = self.confirm_commutation or qt_confirm_commutation
            if not confirm_fn(unphased, self.commutation_warning(unphased)):
                raise MoveCancelled('declined by user')
        return {ax: commutation.commutate_axis(self, ax, drive_levels) for ax in axes}

    def commutation_warning(self, axes) -> str:
        """Confirmation text for commutating *axes*."""
        return (
            f'Commutate axes {", ".join(axes)} of the PMD Magellan stage on '
            f'{self._open_port or self.port or "an unknown port"}?\n\n'
            f'These axes are not commutated and cannot move until they are. Commutation may move '
            f'each axis a large, unpredictable distance, and CANNOT BE INTERRUPTED once started. '
            f'Vertical axes may drop when their motor output is removed. Check that every axis has '
            f'clearance before continuing.'
        )

    def home(self, axes=None) -> dict:
        """Home *axes* (default all) on the centre vane, one at a time.

        MOVES EACH AXIS over up to its full travel. Axes must be phased and enabled. Always
        finishes approaching the vane from the negative side, then sets position 0 there.
        Returns ``{axis: vane position in the previous frame}``; raises NotCommutatedError,
        LimitError or MagellanError if an axis cannot be homed.
        """
        axes = list(self.axes) if axes is None else list(axes)
        self._check_axes(axes)
        return {ax: commutation.home_axis(self, ax) for ax in axes}

    def __repr__(self):
        return f'<MagellanBackend {self._open_port or self.port or "?"} axes={self.nodes}>'
