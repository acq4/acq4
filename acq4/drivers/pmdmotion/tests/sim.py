"""Helpers for calling MagellanBackend directly (no control thread) against the fake bus on a ManualClock."""
from acq4.drivers.pmdmotion.backend import MagellanBackend
from acq4.drivers.stage import MoveState

AXES = {'x': 1, 'y': 2, 'z': 3}
CPM = 200_000
POLL = 0.01
PROFILE = dict(acceleration=400, jerk=50_000, homing_speed=5, homing_acceleration=200,
               homing_jerk=25_000, home_offset=10, home_sweep=102)


def decline(axes, text):
    return False


class FakeTime:
    """Stand-in for the ``time`` module driven by a ManualClock: ``sleep`` advances it."""

    def __init__(self, clock):
        self.clock = clock

    def monotonic(self):
        return self.clock()

    def sleep(self, dt):
        self.clock.advance(dt)


def make_backend(bus, **kwds):
    opts = dict(port='COMTEST', counts_per_unit=CPM, serial_factory=bus.open_serial, timeout=0.02,
                resync_delay=0.001, confirm_commutation=decline, **PROFILE)
    opts.update(kwds)
    return MagellanBackend(dict(AXES), **opts)


def finish(b, clock, handle, polls=5000):
    """Poll *handle* as the control thread does until not MOVING; return (state, reason, final position)."""
    for _ in range(polls):
        clock.advance(POLL)
        b.read_position()
        state, reason = b.check_move(handle)
        if state is not MoveState.MOVING:
            return state, reason, b.final_position(handle) if state is MoveState.DONE else None
    raise AssertionError('move did not finish')


def move(b, clock, target, speed, **kwds):
    """Start a move and poll it to the end; returns as :func:`finish`."""
    return finish(b, clock, b.start_move(target, speed, **kwds))


def poll_until(b, clock, cond, polls=1000):
    """Advance *clock* a poll at a time, reading position, until ``cond()``; False if it never holds."""
    for _ in range(polls):
        if cond():
            return True
        clock.advance(POLL)
        b.read_position()
    return False
