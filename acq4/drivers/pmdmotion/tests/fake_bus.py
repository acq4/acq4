"""Simulated PMD Magellan multi-drop RS-485 bus for testing drivers without hardware.

``FakeMagellanBus`` is a pyserial-like object: inject ``bus.open_serial`` (or the
bus itself) where a driver would construct ``serial.Serial``. Each write is one
command packet; only the addressed ``FakeNode`` answers, and only the first
packet of a concatenated write is seen. State advances on ``bus.clock`` (real
time by default; pass a ``ManualClock`` for deterministic tests).

Positions are encoder counts. Internally each node tracks a physical position
(limits and the centre vane are fixed in that frame) plus an encoder offset
changed by Reset and SetActualPosition.
"""

import collections
import math
import threading
import time

from acq4.drivers.pmdmotion import protocol as p

try:
    from serial import PortNotOpenError
except ImportError:  # pragma: no cover
    class PortNotOpenError(OSError):
        pass

OM = p.OperatingMode
EV = p.EventStatus
SPURIOUS_POSITION = 2 ** 28
MAX_STEP_S = 1e-3

Command = collections.namedtuple('Command', 'time node opcode name args axis')
Command.__doc__ = """One packet received by an addressed node (logged even if the node did not answer)."""


class ManualClock:
    """Deterministic clock; time moves only via ``advance`` / ``set`` (or bus timeouts)."""

    def __init__(self, start=0.0):
        self._t = float(start)

    def __call__(self):
        return self._t

    def advance(self, dt):
        self._t += float(dt)

    def set(self, t):
        self._t = float(t)


class _Fault:
    def __init__(self, kind, count, opcode, execute=True):
        self.kind = kind
        self.count = count
        self.opcode = opcode
        self.execute = execute


def _base_name(name):
    return name[3:] if name.startswith(('Set', 'Get')) else name


def _fit(width, value):
    value = int(value)
    if width == 'u16':
        return value & 0xFFFF
    if width == 'u32':
        return value & 0xFFFFFFFF
    if width == 'i16':
        value &= 0xFFFF
        return value - 0x10000 if value & 0x8000 else value
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _signed32(value):
    return _fit('i32', value)


DEFAULT_REGISTERS = {
    ('PhaseCounts',): 19844,
    ('PhasePrescale',): p.PhasePrescale.DIV_256,
    ('PhaseInitializeTime',): 15000,
    ('PhaseInitializeMode',): p.PhaseInitializeMode.ALGORITHMIC,
    ('PhaseCorrectionMode',): p.PhaseCorrectionMode.DISABLED,
    ('CommutationMode',): p.CommutationMode.SINUSOIDAL,
    ('CurrentControlMode',): p.CurrentControlMode.FOC,
    ('MotorType',): p.MotorType.BRUSHLESS_DC_3PHASE,
    ('MotorLimit',): 32767,
    ('PositionErrorLimit',): 100000,
    ('SignalSense',): 0x0030,
    ('EncoderSource',): 0,
    ('PhaseAngle',): 676,
    ('PhaseOffset',): 0xFFFF,
    ('MotionCompleteMode',): 0,
    ('SettleWindow',): 20,
    ('UpdateMask',): p.UpdateMask.TRAJECTORY | p.UpdateMask.POSITION_LOOP | p.UpdateMask.CURRENT_LOOP,
    ('SampleTime',): 51,
    ('Version',): 0x00110402,
    ('AnalogCalibration', 0): -115,
    ('AnalogCalibration', 1): -83,
    ('AnalogCalibration', 2): -77,
}

FACTORY_EVENT_ACTIONS = {
    p.EventActionEvent.POSITIVE_LIMIT: p.EventAction.ABRUPT_STOP,
    p.EventActionEvent.NEGATIVE_LIMIT: p.EventAction.ABRUPT_STOP,
    p.EventActionEvent.MOTION_ERROR: p.EventAction.DISABLE_MOTOR_OUTPUT_AND_HIGHER,
    p.EventActionEvent.CURRENT_FOLDBACK: p.EventAction.DISABLE_MOTOR_OUTPUT_AND_HIGHER,
}

# Registers cleared by Reset (NVRAM-backed configuration survives).
_RESET_REGISTERS = ('Position', 'Velocity', 'Acceleration', 'Deceleration', 'Jerk',
                    'ProfileMode', 'StopMode', 'MotorCommand', 'StartVelocity')


class FakeNode:
    """One simulated single-axis Magellan IC on the bus.

    Configuration attributes (all mutable at any time):

    - ``stroke``: ``(negative, positive)`` physical limit-switch positions; a limit
      is engaged at or beyond its position.
    - ``hard_stop_margin``: travel allowed past a limit before a mechanical stop.
    - ``vane_position``, ``vane_hysteresis``: AxisIn (Signal Status bit 6) reads 1
      above the vane; the switch points are ``vane +/- hysteresis/2``.
    - ``sag``: physical displacement applied whenever motor output is removed.
    - ``phase_init_ramps``: ``(ramp1, ramp2)`` counts travelled by a successful
      InitializePhase (segments 1 and 3).
    - ``commutation_min_drive``: lowest SetMotorCommand at which InitializePhase succeeds.
    - ``commutation_failure``: ``'error'`` (bit 0 and Commutation Error set) or
      ``'unphased'`` (bit 0 stays clear) for a failed init.
    - ``commutation_outcome``: optional ``f(drive_level) -> 'ok'|'error'|'unphased'``
      overriding the built-in rule (mode 3, drive >= ``commutation_min_drive``).
    - ``calibration_time``: seconds CalibrateAnalog takes to set DriveStatus bit 0.
    - ``reset_silence``: seconds the node ignores commands after Reset.
    - ``reset_clears_phasing``, ``reset_operating_mode``.
    - ``spurious_reads_after_reset``: GetActualPosition reads returning 2**28 after Reset.
    - ``motion_complete_relatch``: seconds after which a cleared Motion Complete
      re-latches while at rest (None disables).
    - ``holding_command``: GetActiveMotorCommand value while servoing.
    - ``responsive``: False makes the node ignore everything.

    Register values not modelled explicitly are kept in ``registers``, keyed by
    ``(name_without_Set/Get, *key_args)``, e.g. ``('PhaseCounts',)`` or
    ``('EventAction', 1)``.
    """

    def __init__(self, bus, node_id, *, position=0, phased=True,
                 operating_mode=OM.CLOSED_LOOP, stroke=(-5_000_000, 5_000_000),
                 hard_stop_margin=100_000, vane_position=0, vane_hysteresis=0, sag=0,
                 phase_init_ramps=(-1_000_000, 1_270_016), commutation_min_drive=2048,
                 commutation_failure='error', commutation_outcome=None,
                 calibration_time=0.1, reset_silence=0.2, reset_clears_phasing=True,
                 reset_operating_mode=OM.IDLE, spurious_reads_after_reset=0,
                 motion_complete_relatch=0.027, holding_command=0, registers=None):
        self.bus = bus
        self.node_id = node_id
        self.stroke = tuple(stroke)
        self.hard_stop_margin = hard_stop_margin
        self.vane_position = vane_position
        self.vane_hysteresis = vane_hysteresis
        self.sag = sag
        self.phase_init_ramps = tuple(phase_init_ramps)
        self.commutation_min_drive = commutation_min_drive
        self.commutation_failure = commutation_failure
        self.commutation_outcome = commutation_outcome
        self.calibration_time = calibration_time
        self.reset_silence = reset_silence
        self.reset_clears_phasing = reset_clears_phasing
        self.reset_operating_mode = reset_operating_mode
        self.spurious_reads_after_reset = spurious_reads_after_reset
        self.motion_complete_relatch = motion_complete_relatch
        self.holding_command = holding_command
        self.responsive = True

        self.registers = dict(DEFAULT_REGISTERS)
        for event, action in FACTORY_EVENT_ACTIONS.items():
            self.registers[('EventAction', event)] = action
        self.registers[('OperatingMode',)] = operating_mode
        if registers:
            self.registers.update(registers)

        self._t = bus.clock()
        self._phys = float(position)
        self._cmd = float(position)
        self._target = float(position)
        self._offset = 0.0
        self._vel = 0.0
        self._moving = False
        self._stopping = False
        self._active = {'Velocity': 0, 'Acceleration': 0, 'Deceleration': 0, 'Jerk': 0,
                        'ProfileMode': 0}
        self._active_mode = operating_mode
        self._phased = phased
        self._phase_init = None
        self._event = 1 << EV.MOTION_COMPLETE
        self._mc_cleared_at = None
        self._calibrated = True
        self._calib_done_at = None
        self._clear_error_pending = False
        self._silent_until = None
        self._spurious = 0
        self._faults = []
        self._axis_in = self._phys >= self.vane_position
        self._limits = self._limit_engaged()

    def __repr__(self):
        return f'<FakeNode {self.node_id} pos={self.actual_position} phased={self._phased}>'

    # ------------------------------------------------------------------
    # Inspection and test setup
    # ------------------------------------------------------------------

    @property
    def actual_position(self):
        """Encoder-frame actual position, in counts."""
        with self.bus.lock:
            self.advance()
            return int(round(self._phys + self._offset))

    @property
    def physical_position(self):
        """Position in the fixed frame of ``stroke`` and ``vane_position``."""
        with self.bus.lock:
            self.advance()
            return self._phys

    @property
    def commanded_position(self):
        with self.bus.lock:
            self.advance()
            return int(round(self._cmd + self._offset))

    @property
    def phased(self):
        with self.bus.lock:
            self.advance()
            return self._phased

    @property
    def in_motion(self):
        with self.bus.lock:
            self.advance()
            return self._moving or self._stopping

    @property
    def active_operating_mode(self):
        with self.bus.lock:
            self.advance()
            return self._active_mode

    @property
    def event_status(self):
        with self.bus.lock:
            self.advance()
            return self._event

    @property
    def activity_status(self):
        with self.bus.lock:
            self.advance()
            return self._activity_status()

    @property
    def signal_status(self):
        with self.bus.lock:
            self.advance()
            return self._signal_status()

    def set_physical_position(self, pos):
        """Place the axis at physical ``pos`` (stops any motion; commanded follows)."""
        with self.bus.lock:
            self.advance()
            self._phys = self._cmd = self._target = float(pos)
            self._vel = 0.0
            self._moving = self._stopping = False
            self._update_axis_in(force=True)
            self._limits = self._limit_engaged()

    def register(self, name, *keys):
        return self.registers.get((name,) + keys, 0)

    # ------------------------------------------------------------------
    # Fault injection
    # ------------------------------------------------------------------

    def drop_responses(self, count=1, opcode=None, execute=True):
        """Suppress the next ``count`` responses (to ``opcode`` only, if given).

        ``execute`` False also discards the command itself.
        """
        with self.bus.lock:
            self._faults.append(_Fault('drop', count, opcode, execute))

    def corrupt_checksum(self, count=1, opcode=None):
        """Send the next ``count`` responses with a wrong checksum byte."""
        with self.bus.lock:
            self._faults.append(_Fault('corrupt', count, opcode))

    def spurious_position(self, count=1):
        """Make the next ``count`` GetActualPosition reads return 2**28."""
        with self.bus.lock:
            self._spurious += count

    def inject_event(self, bits):
        """OR ``bits`` into Event Status without running any event action."""
        with self.bus.lock:
            self.advance()
            self._event |= bits

    def trigger_motion_error(self):
        """Latch Motion Error and run the Motion Error event action."""
        with self.bus.lock:
            self.advance()
            self._event |= 1 << EV.MOTION_ERROR
            self._apply_action(self.register('EventAction', p.EventActionEvent.MOTION_ERROR))

    def _take_fault(self, opcode):
        for fault in self._faults:
            if fault.opcode is None or fault.opcode == opcode:
                fault.count -= 1
                if fault.count <= 0:
                    self._faults.remove(fault)
                return fault
        return None

    # ------------------------------------------------------------------
    # Packet handling
    # ------------------------------------------------------------------

    def receive(self, opcode, axis, args, status=0):
        """Process one decoded packet; return the response bytes, or None for silence.

        A non-zero ``status`` (framing error found by the bus) is answered without
        executing anything.
        """
        now = self.bus.clock()
        self.advance(now)
        if not self.responsive:
            return None
        if self._silent_until is not None:
            if now < self._silent_until:
                return None
            self._silent_until = None

        fault = self._take_fault(opcode)
        if fault is not None and fault.kind == 'drop' and not fault.execute:
            return None

        values = []
        if status == 0:
            if axis != 0:
                status = p.STATUS_INVALID_AXIS
            else:
                status, values = self._execute(opcode, args)

        if status == 0:
            widths = p.response_widths(opcode) or ()
            data = p.pack_values(widths, [_fit(w, v) for w, v in zip(widths, values)])
        else:
            data = b''
        head = bytes((self.node_id & 0xFF, status & 0xFF))
        chk = p.checksum(head + data)

        if fault is not None and fault.kind == 'drop':
            return None
        if fault is not None and fault.kind == 'corrupt':
            chk ^= 0x5A
        return head + bytes((chk,)) + data

    def _execute(self, opcode, args):
        name = p.OPCODE_NAMES.get(opcode)
        if name is None:
            return p.STATUS_INVALID_INSTRUCTION, []
        handler = getattr(self, '_op_' + name, None)
        if handler is not None:
            result = handler(*args)
        elif name.startswith('Set'):
            result = self._generic_set(opcode, name, args)
        elif name.startswith('Get'):
            result = self._generic_get(opcode, name, args)
        else:
            return p.STATUS_INVALID_INSTRUCTION, []
        if result is None:
            return 0, []
        if isinstance(result, tuple):
            return result
        return 0, list(result) if isinstance(result, list) else [result]

    def _generic_set(self, opcode, name, args):
        getter = p.OPCODES.get('Get' + _base_name(name))
        nkeys = len(p.arg_widths(getter)) if getter is not None else 0
        value = args[nkeys:]
        self.registers[(_base_name(name),) + tuple(args[:nkeys])] = (
            value[0] if len(value) == 1 else tuple(value))

    def _generic_get(self, opcode, name, args):
        value = self.registers.get((_base_name(name),) + tuple(args), 0)
        return list(value) if isinstance(value, tuple) else value

    # --- profile and motion ---

    def _op_SetStopMode(self, mode):
        self.registers[('StopMode',)] = mode

    def _op_Update(self):
        return self._do_update()

    def _op_MultiUpdate(self, mask):
        if mask & 1:
            return self._do_update()

    def _op_GetPosition(self):
        return self.register('Position')

    def _op_ClearPositionError(self):
        self._clear_error_pending = True

    def _op_GetActualPosition(self):
        if self._spurious > 0:
            self._spurious -= 1
            return SPURIOUS_POSITION
        return _signed32(round(self._phys + self._offset))

    def _op_SetActualPosition(self, value):
        delta = value - (self._phys + self._offset)
        self._offset += delta
        self.registers[('Position',)] = _signed32(self.register('Position') + round(delta))

    def _op_AdjustActualPosition(self, delta):
        self._offset += delta
        self.registers[('Position',)] = _signed32(self.register('Position') + delta)

    def _op_GetCommandedPosition(self):
        return _signed32(round(self._cmd + self._offset))

    def _op_GetActualVelocity(self):
        return self._encoded_velocity()

    def _op_GetCommandedVelocity(self):
        return self._encoded_velocity()

    def _op_GetCommandedAcceleration(self):
        return 0

    def _op_GetPositionError(self):
        return 0

    def _op_GetTime(self):
        return int(self._t / p.SAMPLE_TIME_S)

    def _encoded_velocity(self):
        return _signed32(round(self._vel * p.SAMPLE_TIME_S * 2 ** 16))

    # --- status ---

    def _op_GetEventStatus(self):
        return self._event

    def _op_ResetEventStatus(self, mask):
        had_mc = self._event & (1 << EV.MOTION_COMPLETE)
        self._event &= mask
        if had_mc and not self._event & (1 << EV.MOTION_COMPLETE):
            self._mc_cleared_at = self._t

    def _op_GetActivityStatus(self):
        return self._activity_status()

    def _op_GetSignalStatus(self):
        return self._signal_status()

    def _op_GetDriveStatus(self):
        return (1 << p.DriveStatus.CALIBRATED) if self._calibrated else 0

    def _op_GetInstructionError(self):
        return 0

    def _op_ClearDriveFaultStatus(self):
        pass

    def _op_NoOperation(self):
        pass

    def _activity_status(self):
        s = 0
        if self._phased:
            s |= 1 << p.ActivityStatus.PHASING_INITIALIZED
        moving = self._moving or self._stopping
        vmax = abs(p.decode_velocity(self._active['Velocity']))
        if moving and vmax and abs(abs(self._vel) - vmax) <= 1e-6 * vmax:
            s |= 1 << p.ActivityStatus.AT_MAX_VELOCITY
        s |= (self._active['ProfileMode'] << p.ActivityStatus.PROFILE_MODE_SHIFT) \
            & p.ActivityStatus.PROFILE_MODE_MASK
        if not moving:
            s |= 1 << p.ActivityStatus.AXIS_SETTLED
        if self._active_mode & OM.POSITION_LOOP:
            s |= 1 << p.ActivityStatus.POSITION_LOOP_ENABLED
        if moving:
            s |= 1 << p.ActivityStatus.IN_MOTION
        neg, pos = self._limits
        if pos:
            s |= 1 << p.ActivityStatus.IN_POSITIVE_LIMIT
        if neg:
            s |= 1 << p.ActivityStatus.IN_NEGATIVE_LIMIT
        return s

    def _signal_status(self):
        sense = self.register('SignalSense')
        neg, pos = self._limits
        levels = {p.SignalStatus.POSITIVE_LIMIT: pos, p.SignalStatus.NEGATIVE_LIMIT: neg,
                  p.SignalStatus.AXIS_IN: self._axis_in}
        s = 0
        for bit, level in levels.items():
            if bool(level) != bool(sense & (1 << bit)):
                s |= 1 << bit
        return s

    # --- operating mode / motor ---

    def _op_SetOperatingMode(self, mode):
        self.registers[('OperatingMode',)] = mode
        self._set_active_mode(mode)

    def _op_GetActiveOperatingMode(self):
        return self._active_mode

    def _op_RestoreOperatingMode(self):
        self._set_active_mode(self.register('OperatingMode'))

    def _op_GetActiveMotorCommand(self):
        if not self._active_mode & OM.MOTOR_OUTPUT:
            return 0
        if self._active_mode & OM.POSITION_LOOP:
            return self.holding_command
        return self.register('MotorCommand')

    def _op_CalibrateAnalog(self, option):
        self._calibrated = False
        self._calib_done_at = self._t + self.calibration_time

    def _op_GetEventAction(self, event):
        return self.register('EventAction', event)

    # --- commutation ---

    def _op_InitializePhase(self):
        drive = self.register('MotorCommand')
        outcome = self._commutation_result(drive)
        r1, r2 = self.phase_init_ramps
        if outcome == 'error':
            ramps = (r1, r2 * 0.05)
        elif outcome == 'unphased':
            ramps = (r1 * 0.1, 0.0)
        else:
            ramps = (r1, r2)
        cycles = self.register('PhaseInitializeTime')
        self._phased = False
        self._moving = self._stopping = False
        self._vel = 0.0
        self._phase_init = {
            'start': self._t, 'duration': p.phase_init_duration(cycles),
            'origin': self._phys, 'ramps': ramps, 'outcome': outcome,
        }

    def _commutation_result(self, drive):
        if self.commutation_outcome is not None:
            return self.commutation_outcome(drive)
        mode = self._active_mode
        if not mode & OM.MOTOR_OUTPUT or mode & (OM.CURRENT_CONTROL | OM.POSITION_LOOP | OM.TRAJECTORY):
            return 'error'
        if drive < self.commutation_min_drive:
            return self.commutation_failure
        return 'ok'

    # --- misc ---

    def _op_Reset(self):
        self._silent_until = self._t + self.reset_silence
        # Position re-zeroes before motor output drops, so any sag reads as displacement.
        self._offset = -self._phys
        self.registers[('OperatingMode',)] = self.reset_operating_mode
        self._set_active_mode(self.reset_operating_mode)
        self._phase_init = None
        for name in _RESET_REGISTERS:
            self.registers[(name,)] = 0
        for bp in (0, 1):
            self.registers[('Breakpoint', bp)] = 0
            self.registers[('BreakpointValue', bp)] = 0
        for event, action in FACTORY_EVENT_ACTIONS.items():
            self.registers[('EventAction', event)] = action
        self._active = {k: 0 for k in self._active}
        self._cmd = self._target = self._phys
        self._vel = 0.0
        self._moving = self._stopping = False
        self._clear_error_pending = False
        if self.reset_clears_phasing:
            self._phased = False
        self._event = 0
        self._mc_cleared_at = self._t
        self._spurious = self.spurious_reads_after_reset

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def _do_update(self):
        regs = self.registers
        stop = regs.get(('StopMode',), 0)
        if (self._moving or self._stopping) and not stop and not self._clear_error_pending and (
                self._active['ProfileMode'] == p.ProfileMode.S_CURVE
                or regs.get(('ProfileMode',), 0) != self._active['ProfileMode']):
            # S-curve profiles cannot be changed in motion; trapezoidal can.
            return p.STATUS_INVALID_PARAMETER_CHANGE, []
        for key in ('Acceleration', 'Deceleration', 'Jerk', 'ProfileMode'):
            self._active[key] = regs.get((key,), 0)
        if self._clear_error_pending:
            self._clear_error_pending = False
            self._cmd = self._target = self._phys
            self._moving = self._stopping = False
            self._vel = 0.0
        if stop:
            regs[('StopMode',)] = p.StopMode.NO_STOP
            self._stop(abrupt=stop == p.StopMode.ABRUPT)
            return None

        dest = regs.get(('Position',), 0) - self._offset
        velocity = regs.get(('Velocity',), 0)
        neg, pos = self._limits
        if self._active['ProfileMode'] == p.ProfileMode.VELOCITY_CONTOURING:
            direction = (velocity > 0) - (velocity < 0)
        else:
            direction = (dest > self._cmd) - (dest < self._cmd)
        if (pos and direction > 0) or (neg and direction < 0):
            return p.STATUS_MOVE_INTO_LIMIT, []
        if self._event & (1 << EV.MOTION_ERROR):
            return p.STATUS_MOVE_WITH_MOTION_ERROR, []

        self._active['Velocity'] = velocity
        if not (self._active_mode & OM.TRAJECTORY and self._active_mode & OM.MOTOR_OUTPUT):
            self._target = self._cmd
            return None
        self._target = dest
        self._stopping = False
        if self._active['ProfileMode'] == p.ProfileMode.VELOCITY_CONTOURING:
            self._moving = velocity != 0 or self._vel != 0
        elif dest != self._cmd and velocity != 0 and self._active['Acceleration'] != 0:
            self._moving = True
        elif not self._moving:
            self._target = self._cmd
            self._event |= 1 << EV.MOTION_COMPLETE
        return None

    def _stop(self, abrupt):
        """Execute a stop: zero the velocity register, then halt now or decelerate."""
        self.registers[('Velocity',)] = 0
        self._active['Velocity'] = 0
        decel = self._active['Deceleration'] or self._active['Acceleration']
        if not (self._moving or self._stopping):
            self._target = self._cmd
            return
        if abrupt or decel == 0:
            self._finish_motion()
        else:
            self._moving = False
            self._stopping = True

    def _finish_motion(self):
        self._vel = 0.0
        self._moving = self._stopping = False
        self._target = self._cmd
        self._event |= 1 << EV.MOTION_COMPLETE

    def _set_active_mode(self, mode):
        old = self._active_mode
        self._active_mode = mode
        if old & OM.MOTOR_OUTPUT and not mode & OM.MOTOR_OUTPUT:
            self._lose_motor_output()
        if not mode & OM.TRAJECTORY:
            self._moving = self._stopping = False
            self._vel = 0.0
            self._target = self._cmd
        if mode & OM.POSITION_LOOP and not old & OM.POSITION_LOOP:
            self._cmd = self._phys
            self._target = self._phys

    def _lose_motor_output(self):
        self._phase_init = None
        self._moving = self._stopping = False
        self._vel = 0.0
        if self.sag:
            self._phys = self._clamp(self._phys + self.sag)
        self._cmd = self._target = self._phys
        self._update_axis_in()

    def _apply_action(self, action):
        traj = self._active_mode & OM.TRAJECTORY
        if action in (p.EventAction.ABRUPT_STOP, p.EventAction.ABRUPT_STOP_WITH_POSITION_ERROR_CLEAR):
            if traj:
                self._stop(abrupt=True)
        elif action == p.EventAction.SMOOTH_STOP:
            if traj:
                self._stop(abrupt=False)
        elif action == p.EventAction.DISABLE_POSITION_LOOP_AND_HIGHER:
            self._set_active_mode(self._active_mode & ~(OM.POSITION_LOOP | OM.TRAJECTORY))
        elif action == p.EventAction.DISABLE_CURRENT_LOOP_AND_HIGHER:
            self._set_active_mode(self._active_mode & ~(OM.CURRENT_CONTROL | OM.POSITION_LOOP
                                                        | OM.TRAJECTORY))
        elif action == p.EventAction.DISABLE_MOTOR_OUTPUT_AND_HIGHER:
            self._set_active_mode(self._active_mode & ~(OM.MOTOR_OUTPUT | OM.CURRENT_CONTROL
                                                        | OM.POSITION_LOOP | OM.TRAJECTORY))

    def _clamp(self, pos):
        lo = self.stroke[0] - self.hard_stop_margin
        hi = self.stroke[1] + self.hard_stop_margin
        return min(max(pos, lo), hi)

    def _limit_engaged(self):
        return (self._phys <= self.stroke[0], self._phys >= self.stroke[1])

    def _vane_edges(self):
        h = self.vane_hysteresis / 2.0
        return self.vane_position - h, self.vane_position + h

    def _update_axis_in(self, force=False):
        low, high = self._vane_edges()
        if force:
            self._axis_in = self._phys >= self.vane_position
        elif self._axis_in and self._phys < low:
            self._axis_in = False
        elif not self._axis_in and self._phys >= high:
            self._axis_in = True

    def _busy(self):
        if self._moving or self._stopping or self._phase_init is not None:
            return True
        return any((self.register('Breakpoint', bp) >> 8) & 0xFF for bp in (0, 1))

    def advance(self, now=None):
        """Bring the simulation up to ``now`` (default: the bus clock)."""
        if now is None:
            now = self.bus.clock()
        remaining = now - self._t
        if remaining <= 0:
            if self._busy():
                self._check_breakpoints(self._phys, self._axis_in)
            return
        if not self._busy():
            self._t = now
            self._timers()
            return
        while remaining > 1e-12:
            dt = min(MAX_STEP_S, remaining)
            self._t += dt
            remaining -= dt
            self._step(dt)
            if not self._busy():
                self._t = now
                self._timers()
                return

    def _step(self, dt):
        p0, axis_in0 = self._phys, self._axis_in
        if self._phase_init is not None:
            self._step_phase_init()
        elif self._active_mode & OM.TRAJECTORY and self._active_mode & OM.MOTOR_OUTPUT:
            self._step_trajectory(dt)
            if self._active_mode & OM.POSITION_LOOP:
                self._phys = self._clamp(self._cmd)
                if self._phys != self._cmd:
                    self._cmd = self._phys
        if not self._active_mode & OM.POSITION_LOOP:
            self._cmd = self._phys
        self._update_axis_in()
        self._check_limits()
        self._check_breakpoints(p0, axis_in0)
        self._timers()

    def _step_phase_init(self):
        pi = self._phase_init
        elapsed = self._t - pi['start']
        seg = pi['duration'] / p.PHASE_INIT_SEGMENTS
        r1, r2 = pi['ramps']
        disp = r1 * min(max(elapsed / seg, 0.0), 1.0) \
            + r2 * min(max((elapsed - 2 * seg) / seg, 0.0), 1.0)
        self._phys = self._clamp(pi['origin'] + disp)
        if elapsed >= pi['duration']:
            self._phase_init = None
            if pi['outcome'] in ('ok', 'error'):
                self._phased = True
            if pi['outcome'] == 'error':
                self._event |= 1 << EV.COMMUTATION_ERROR

    def _step_trajectory(self, dt):
        if not (self._moving or self._stopping):
            return
        acc = p.decode_acceleration(self._active['Acceleration'])
        dec = p.decode_acceleration(self._active['Deceleration']) or acc
        vmax = abs(p.decode_velocity(self._active['Velocity']))
        v = self._vel
        profile = self._active['ProfileMode']

        if self._stopping or (profile == p.ProfileMode.VELOCITY_CONTOURING and vmax == 0):
            dv = dec * dt
            if abs(v) <= dv or dec == 0:
                self._cmd += v * dt / 2
                self._finish_motion()
                return
            v -= math.copysign(dv, v)
            self._cmd += v * dt
            self._vel = v
            return

        if profile == p.ProfileMode.VELOCITY_CONTOURING:
            vt = p.decode_velocity(self._active['Velocity'])
            rate = acc if abs(vt) > abs(v) and vt * v >= 0 else dec
            dv = rate * dt
            v = vt if abs(vt - v) <= dv else v + math.copysign(dv, vt - v)
            self._vel = v
            self._cmd += v * dt
            return

        d = self._target - self._cmd
        direction = 1.0 if d > 0 else -1.0
        if abs(d) < 0.5 and abs(v) * dt < 1.0:
            self._cmd = self._target
            self._finish_motion()
            return
        if v * direction < 0:
            v += direction * dec * dt
        else:
            speed = min(vmax, abs(v) + acc * dt, math.sqrt(2 * dec * abs(d)) if dec else vmax)
            v = direction * speed
        step = v * dt
        if step * direction >= abs(d) and v * direction > 0:
            self._cmd = self._target
            self._finish_motion()
            return
        self._cmd += step
        self._vel = v

    def _check_limits(self):
        engaged = self._limit_engaged()
        events = ((0, EV.NEGATIVE_LIMIT, p.EventActionEvent.NEGATIVE_LIMIT),
                  (1, EV.POSITIVE_LIMIT, p.EventActionEvent.POSITIVE_LIMIT))
        prev = self._limits
        self._limits = engaged
        for idx, bit, event in events:
            if engaged[idx] and not prev[idx]:
                self._event |= 1 << bit
                self._apply_action(self.register('EventAction', event))

    def _breakpoint_condition(self, trigger, value):
        signed = _signed32(value)
        sel, sense = (value >> 16) & 0xFFFF, value & 0xFFFF
        if trigger == p.BreakpointTrigger.GE_COMMANDED_POSITION:
            return self._cmd + self._offset >= signed
        if trigger == p.BreakpointTrigger.LE_COMMANDED_POSITION:
            return self._cmd + self._offset <= signed
        if trigger == p.BreakpointTrigger.GE_ACTUAL_POSITION:
            return self._phys + self._offset >= signed
        if trigger == p.BreakpointTrigger.LE_ACTUAL_POSITION:
            return self._phys + self._offset <= signed
        registers = {
            p.BreakpointTrigger.EVENT_STATUS: self._event,
            p.BreakpointTrigger.ACTIVITY_STATUS: self._activity_status(),
            p.BreakpointTrigger.SIGNAL_STATUS: self._signal_status(),
        }
        if trigger in registers:
            return (registers[trigger] & sel) == (sense & sel)
        return False

    def _check_breakpoints(self, p0, axis_in0):
        for bp, bit in ((0, EV.BREAKPOINT1), (1, EV.BREAKPOINT2)):
            word = self.register('Breakpoint', bp)
            trigger = (word >> 8) & 0xFF
            if not trigger:
                continue
            value = self.register('BreakpointValue', bp)
            if not self._breakpoint_condition(trigger, value):
                continue
            self.registers[('Breakpoint', bp)] = word & 0x00FF
            self._event |= 1 << bit
            if (trigger == p.BreakpointTrigger.SIGNAL_STATUS
                    and (value >> 16) & (1 << p.SignalStatus.AXIS_IN)
                    and self._axis_in != axis_in0):
                # The IC stops within one servo cycle of the edge.
                low, high = self._vane_edges()
                edge = high if self._axis_in else low - 1e-3
                self._phys = edge
                if self._active_mode & OM.POSITION_LOOP:
                    self._cmd = edge
            action = (word >> 4) & 0x0F
            if action == p.BreakpointAction.UPDATE:
                self._do_update()
            else:
                self._apply_action(action)

    def _timers(self):
        if self._calib_done_at is not None and self._t >= self._calib_done_at:
            self._calibrated = True
            self._calib_done_at = None
        if (self.motion_complete_relatch is not None and self._mc_cleared_at is not None
                and not (self._moving or self._stopping)
                and self._t - self._mc_cleared_at >= self.motion_complete_relatch):
            self._event |= 1 << EV.MOTION_COMPLETE
            self._mc_cleared_at = None


class FakeMagellanBus:
    """pyserial-like simulated multi-drop Magellan bus.

    Args:
        nodes: node IDs, or ``{node_id: FakeNode kwargs}``.
        clock: zero-argument callable returning seconds (default ``time.monotonic``).
            If it has ``advance(dt)``, read timeouts and ``transaction_time``
            advance it instead of sleeping.
        transaction_time: seconds added to a manual clock per write.
        **node_kwargs: defaults passed to every ``FakeNode``.

    Attributes:
        nodes: ``{node_id: FakeNode}``.
        log: list of ``Command`` received by existing nodes, in order.
        writes: every raw write, in order.
    """

    def __init__(self, nodes=(1, 2, 3), clock=None, transaction_time=0.0, **node_kwargs):
        self.lock = threading.RLock()
        self.clock = clock if clock is not None else time.monotonic
        self.transaction_time = transaction_time
        self._node_defaults = node_kwargs
        self.nodes = {}
        self.log = []
        self.writes = []
        self._out = bytearray()

        self.port = None
        self.baudrate = 57600
        self.timeout = 0.25
        self.write_timeout = None
        self.is_open = True

        if isinstance(nodes, dict):
            for node_id, kwargs in nodes.items():
                self.add_node(node_id, **(kwargs or {}))
        else:
            for node_id in nodes:
                self.add_node(node_id)

    def add_node(self, node_id, **kwargs):
        """Create (or replace) the node at ``node_id``; returns it."""
        with self.lock:
            node = FakeNode(self, node_id, **{**self._node_defaults, **kwargs})
            self.nodes[node_id] = node
            return node

    def __getitem__(self, node_id):
        return self.nodes[node_id]

    # --- command log ---

    def commands(self, node=None, name=None):
        """Return logged commands, filtered by node ID and/or opcode name (str or iterable)."""
        names = {name} if isinstance(name, str) else (set(name) if name else None)
        return [c for c in self.log
                if (node is None or c.node == node) and (names is None or c.name in names)]

    def command_names(self, node=None):
        return [c.name for c in self.commands(node)]

    def clear_log(self):
        with self.lock:
            self.log.clear()
            self.writes.clear()

    # --- serial-like interface ---

    def open_serial(self, port=None, baudrate=None, timeout=None, **kwargs):
        """Stand-in for ``serial.Serial(...)``: record settings, open, return the bus."""
        with self.lock:
            self.port = port
            if baudrate is not None:
                self.baudrate = baudrate
            if timeout is not None:
                self.timeout = timeout
            if 'write_timeout' in kwargs:
                self.write_timeout = kwargs['write_timeout']
            self.is_open = True
            self._out.clear()
            return self

    __call__ = open_serial

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def _check_open(self):
        if not self.is_open:
            raise PortNotOpenError()

    @property
    def in_waiting(self):
        self._check_open()
        return len(self._out)

    def reset_input_buffer(self):
        self._check_open()
        with self.lock:
            self._out.clear()

    def reset_output_buffer(self):
        self._check_open()

    def flush(self):
        self._check_open()

    def _wait(self, seconds):
        if not seconds:
            return
        advance = getattr(self.clock, 'advance', None)
        if advance is not None:
            advance(seconds)
        else:
            time.sleep(seconds)

    def read(self, size=1):
        """Return up to ``size`` buffered response bytes; waits ``timeout`` if short."""
        self._check_open()
        with self.lock:
            data = bytes(self._out[:size])
            del self._out[:size]
        if len(data) < size:
            self._wait(self.timeout)
        return data

    def write(self, data):
        """Deliver one command packet to the bus; returns the byte count."""
        self._check_open()
        data = bytes(data)
        with self.lock:
            self.writes.append(data)
            advance = getattr(self.clock, 'advance', None)
            if self.transaction_time and advance is not None:
                advance(self.transaction_time)
            response = self._dispatch(data)
            if response:
                self._out += response
        return len(data)

    def _dispatch(self, data):
        if len(data) < 4:
            return None
        node = self.nodes.get(data[0])
        if node is None:
            return None
        axis, opcode = data[2], data[3]
        widths = p.arg_widths(opcode)
        if widths is None:
            packet = data
            payload = data[4:]
            args = [int.from_bytes(payload[i:i + 2], 'big') for i in range(0, len(payload) - 1, 2)]
            name = f'0x{opcode:02X}'
        else:
            packet = data[:4 + p.width_bytes(widths)]
            args = None
            name = p.OPCODE_NAMES[opcode]

        status = 0
        if sum(packet) & 0xFF:
            status = p.STATUS_BAD_CHECKSUM
        elif widths is not None and len(packet) < 4 + p.width_bytes(widths):
            status = p.STATUS_WRONG_DATA_COUNT
        elif args is None:
            args = p.unpack_values(widths, packet[4:])
        self.log.append(Command(self.clock(), node.node_id, opcode, name,
                                tuple(args) if args is not None else None, axis))
        return node.receive(opcode, axis, args or [], status)
