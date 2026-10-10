"""MagellanBackend's bus traffic for a fixed scenario must match the recorded trace in magellan_trace.json.

The scenario runs synchronously on a ManualClock (no control thread), calling the backend
in the order the control thread would: connect, a move, an S-curve retarget, a stop,
disable/enable, commutation of one axis, homing.
"""
import json
import os

from acq4.drivers.pmdmotion import backend as backend_module
from acq4.drivers.pmdmotion import commutation
from acq4.drivers.pmdmotion.backend import MagellanBackend
from acq4.drivers.pmdmotion.tests.fake_bus import FakeMagellanBus, ManualClock
from acq4.drivers.pmdmotion.tests.sim import FakeTime
from acq4.drivers.stage import MoveState

TRACE_FILE = os.path.join(os.path.dirname(__file__), 'magellan_trace.json')
AXES = {'x': 1, 'y': 2, 'z': 3}
OPTS = dict(port='COMTEST', counts_per_unit=200_000, timeout=0.02, resync_delay=0.001,
            acceleration=400, jerk=50_000, homing_speed=50.0, homing_acceleration=2000.0,
            homing_jerk=1e6, home_offset=10, home_sweep=102)
POLL = 0.025


class Adapter:
    """Drives a MagellanBackend the way StageControlThread does."""

    def __init__(self, bus, clock):
        self.b = MagellanBackend(dict(AXES), serial_factory=bus.open_serial, **OPTS)
        self.clock = clock

    def open(self):
        self.b.open()

    def start_move(self, target, speed, **kw):
        return self.b.start_move(target, speed, **kw)

    def poll(self, handle=None):
        self.clock.advance(POLL)
        self.b.read_position()
        self.b.poll_extra()
        if handle is not None:
            state, _ = self.b.check_move(handle)
            if state is MoveState.DONE:
                self.b.final_position(handle)
            return state
        return None

    def stop(self):
        self.b.stop('test')

    def commutate(self):
        return self.b.commutate(None, (2048, 4096, 8192), confirm=False)

    def home(self, axes):
        return self.b.home(axes)

    def set_enabled(self, enabled, axes):
        self.b.set_enabled(enabled, axes, '')

    def is_enabled(self):
        return self.b.is_enabled()

    def get_limits(self):
        return self.b.get_limits()


def scenario(a, bus):
    marks = {}

    def mark(name):
        marks[name] = len(bus.log)

    def run_to_done(h, limit=2000):
        for _ in range(limit):
            if a.poll(h) is not MoveState.MOVING:
                return
        raise RuntimeError('move did not finish')

    mark('connect')
    a.open()
    mark('move')
    h = a.start_move({'x': 1.0, 'y': -0.5}, 20)
    run_to_done(h)
    mark('interrupt')
    h = a.start_move({'x': 3.0}, 2, profile='scurve')
    for _ in range(5):
        a.poll(h)
    h = a.start_move({'x': 0.25}, 20, profile='scurve')
    run_to_done(h)
    mark('stop')
    h = a.start_move({'x': 10.0}, 2)
    for _ in range(5):
        a.poll(h)
    a.stop()
    for _ in range(200):
        a.poll()
        if not bus[1].in_motion:
            break
    a.poll()
    mark('enable')
    a.set_enabled(False, ['y'])
    a.is_enabled()
    a.set_enabled(True, ['y'])
    a.get_limits()
    mark('commutate')
    assert a.commutate() == {'x': None, 'y': None, 'z': 2048}
    mark('home')
    a.home(['x'])
    mark('end')
    return marks


def test_trace_matches_recording(monkeypatch):
    clock = ManualClock()
    fake_time = FakeTime(clock)
    monkeypatch.setattr(backend_module, 'time', fake_time)
    monkeypatch.setattr(commutation, 'time', fake_time)
    nodes = {1: dict(position=-200_000, vane_position=400_000, vane_hysteresis=12_000),
             2: dict(position=-200_000),
             3: dict(phased=False, operating_mode=0, registers={('PhaseInitializeTime',): 100})}
    bus = FakeMagellanBus(nodes=nodes, clock=clock, transaction_time=0.001)

    marks = scenario(Adapter(bus, clock), bus)

    with open(TRACE_FILE) as fh:
        expected = json.load(fh)
    got = [[c.node, c.name, list(c.args) if c.args is not None else None] for c in bus.log]
    names = list(expected['marks'])
    for name, nxt in zip(names, names[1:]):   # per section first, for a readable failure
        want = expected['commands'][expected['marks'][name]:expected['marks'][nxt]]
        assert got[marks[name]:marks[nxt]] == want, name
    assert marks == expected['marks']
    assert got == expected['commands']
