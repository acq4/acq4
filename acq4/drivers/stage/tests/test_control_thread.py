import threading
import time

import pytest

from acq4.drivers.stage import (
    MoveCancelled,
    MoveInterrupted,
    MoveState,
    MoveStopped,
    RequestError,
    RequestFailed,
    StageDriver,
)


class FakeStage(StageDriver):
    """In-memory stage: axes move linearly toward target at *speed* units/s.

    A stop decelerates for ``stop_settle`` seconds before motion ceases.
    """

    poll_interval = 0.005

    def __init__(self, axes=('x', 'y', 'z'), stop_settle=0.0):
        super().__init__()
        self.pos = {ax: 0.0 for ax in axes}
        self.target = dict(self.pos)
        self.speed = 0.0
        self.t_last = time.monotonic()
        self.stop_settle = stop_settle
        self.stop_until = None
        self.calls = []
        self.fail_hooks = {}
        self.in_hook = threading.Lock()
        self.reentrant = False
        self.ctrl_threads = set()
        self.moving_when_sent = []

    def _hook(self, name):
        self.calls.append(name)
        self.ctrl_threads.add(threading.current_thread())
        exc = self.fail_hooks.get(name)
        if exc is not None:
            raise exc

    def _advance(self):
        now = time.monotonic()
        dt = now - self.t_last
        self.t_last = now
        if self.stop_until is not None:
            if now >= self.stop_until:
                self.stop_until = None
                self.target = dict(self.pos)
            # keep drifting during settle
        for ax, tgt in self.target.items():
            d = tgt - self.pos[ax]
            step = self.speed * dt
            self.pos[ax] = tgt if abs(d) <= step else self.pos[ax] + step * (1 if d > 0 else -1)

    def is_moving(self):
        return any(self.pos[ax] != self.target[ax] for ax in self.pos) or self.stop_until is not None

    def _guard(self, name):
        if not self.in_hook.acquire(blocking=False):
            self.reentrant = True
            raise RuntimeError("reentrant hook call")
        try:
            self._advance()
            self._hook(name)
        finally:
            self.in_hook.release()

    def _read_position(self):
        self._guard('_read_position')
        return dict(self.pos)

    def _send_move(self, req):
        self._guard('_send_move')
        self.moving_when_sent.append(self.is_moving())
        self.speed = req.speed
        self.target.update(req.target)
        self.stop_until = None

    def _send_stop(self, reason):
        self._guard('_send_stop')
        if self.stop_settle > 0:
            self.stop_until = time.monotonic() + self.stop_settle
        else:
            self.target = dict(self.pos)

    def _check_move(self, req):
        self._guard('_check_move')
        if self.is_moving():
            return MoveState.MOVING, None
        if all(abs(self.pos[ax] - v) < 1e-9 for ax, v in req.target.items()):
            return MoveState.DONE, None
        return MoveState.FAILED, f"stopped short at {self.pos}"

    def _poll_extra(self):
        self._guard('_poll_extra')


@pytest.fixture
def stage():
    drivers = []

    def make(**kwds):
        d = FakeStage(**kwds)
        d.connect()
        drivers.append(d)
        return d

    yield make
    for d in drivers:
        d.close()
        assert not d._ctrl.thread.is_alive()
        assert not d.reentrant
        assert all(t is d._ctrl.thread for t in d.ctrl_threads)


def wait_for(cond, timeout=2.0):
    t = time.monotonic() + timeout
    while time.monotonic() < t:
        if cond():
            return True
        time.sleep(0.002)
    return False


def test_position_cached(stage):
    d = stage()
    assert wait_for(lambda: d.get_position() is not None)
    assert d.get_position() == {'x': 0.0, 'y': 0.0, 'z': 0.0}
    n = d.calls.count('_read_position')
    for _ in range(100):
        d.get_position()
    assert d.calls.count('_read_position') - n < 5  # get_position does no I/O
    assert '_poll_extra' in d.calls


def test_position_callback_threshold():
    d = FakeStage()
    d.position_change_threshold = 1.0
    seen = []
    d.set_position_callback(seen.append)
    d.connect()
    try:
        assert wait_for(lambda: len(seen) >= 1)
        time.sleep(0.05)
        assert len(seen) == 1  # stationary: fired once only
        d.move_to({'x': 5.0}, speed=50).wait()
        time.sleep(0.02)
        xs = [p['x'] for p in seen]
        assert abs(xs[-1] - 5.0) <= 1.0  # final sub-threshold step not reported
        assert all(b - a > 1.0 for a, b in zip(xs, xs[1:]))
        assert len(seen) <= 6
    finally:
        d.close()


def test_position_callback_per_axis_threshold():
    d = FakeStage()
    d.position_change_threshold = {'x': 100.0, 'y': 0.5}
    seen = []
    d.set_position_callback(seen.append)
    d.connect()
    try:
        assert wait_for(lambda: len(seen) >= 1)
        d.move_to({'x': 3.0}, speed=100).wait()
        time.sleep(0.02)
        assert len(seen) == 1  # x moves below its threshold
        d.move_to({'y': 3.0}, speed=100).wait()
        time.sleep(0.02)
        assert len(seen) > 1
    finally:
        d.close()


def test_position_callback_every_poll(stage):
    d = stage()
    seen = []
    d.set_position_callback(seen.append)
    time.sleep(0.05)
    assert len(seen) >= 3


def test_move_completes(stage):
    d = stage()
    done = []
    req = d.move_to({'x': 1.0, 'y': -1.0, 'z': None}, speed=40, reason='test', acceleration=7)
    req.set_callback(done.append)
    assert req.target == {'x': 1.0, 'y': -1.0}
    assert req.kwds == {'acceleration': 7}
    assert req.wait(timeout=2) is None
    assert req.status == 'done'
    assert done == [req]
    assert wait_for(lambda: d.get_position()['x'] == 1.0)
    late = []
    req.set_callback(late.append)
    assert late == [req]  # fires immediately once done


def test_move_failure_reason(stage):
    d = stage()
    req = d.move_to({'x': 5.0}, speed=50)
    # make the device stop short via direct state manipulation from the control thread
    d._submit(lambda: d.target.update(x=0.5)).wait()
    with pytest.raises(RequestFailed, match="stopped short"):
        req.wait()
    assert req.status == 'failed'


@pytest.mark.parametrize('stop_before_move', [False, True])
def test_interrupt(stage, stop_before_move):
    d = stage(stop_settle=0.05 if stop_before_move else 0.0)
    d.stop_before_move = stop_before_move
    first = d.move_to({'x': 100.0}, speed=10)
    assert wait_for(lambda: first.status == 'moving')
    second = d.move_to({'x': -0.1}, speed=50)
    with pytest.raises(MoveInterrupted):
        first.wait()
    assert first.status == 'interrupted'
    assert not isinstance(first.error, RequestFailed)
    second.wait(timeout=3)
    assert second.status == 'done'
    if stop_before_move:
        assert d.calls.count('_send_stop') == 1
        assert d.moving_when_sent == [False, False]  # motion ceased before the new move
    else:
        assert '_send_stop' not in d.calls
        assert d.moving_when_sent == [False, True]


def test_interrupt_pending_after_stop(stage):
    # with stop_before_move, a third move replaces the one waiting for motion to cease
    d = stage(stop_settle=0.1)
    d.stop_before_move = True
    a = d.move_to({'x': 100.0}, speed=10)
    b = d.move_to({'x': 1.0}, speed=50)
    c = d.move_to({'x': 2.0}, speed=50)
    c.wait(timeout=3)
    assert (a.status, b.status, c.status) == ('interrupted', 'interrupted', 'done')
    assert d.calls.count('_send_move') == 2


def test_stop_before_move_timeout(stage):
    d = stage(stop_settle=10.0)
    d.stop_before_move = True
    d.stop_timeout = 0.05
    d.move_to({'x': 100.0}, speed=10)
    b = d.move_to({'x': 1.0}, speed=50)
    with pytest.raises(RequestFailed, match="did not stop"):
        b.wait()


def test_stop(stage):
    d = stage()
    req = d.move_to({'x': 100.0}, speed=10)
    assert wait_for(lambda: req.status == 'moving')
    s = d.stop(reason='because')
    s.wait()
    assert s.status == 'done'
    with pytest.raises(MoveStopped, match='because'):
        req.wait()
    assert req.status == 'stopped'
    # stop with nothing active still sends stop
    d.stop().wait()
    assert d.calls.count('_send_stop') == 2


def test_cancel_active(stage):
    d = stage()
    req = d.move_to({'x': 100.0}, speed=10)
    assert wait_for(lambda: req.status == 'moving')
    req.cancel().wait()
    with pytest.raises(MoveCancelled):
        req.wait()
    assert isinstance(req.error, MoveStopped)
    assert d.calls.count('_send_stop') == 1


def test_cancel_not_active(stage):
    d = stage()
    # block the control thread so the move is still queued when cancelled
    gate = threading.Event()
    blocker = d._submit(gate.wait, 2)
    req = d.move_to({'x': 1.0}, speed=10)
    c = req.cancel()
    assert c.done() and req.done()  # resolved immediately, in this thread
    assert req.status == 'cancelled'
    gate.set()
    blocker.wait()
    d._submit(lambda: None).wait()
    assert '_send_move' not in d.calls
    assert '_send_stop' not in d.calls

    # cancelling a finished move changes nothing
    done = d.move_to({'x': 0.5}, speed=100)
    done.wait()
    done.cancel().wait()
    assert done.status == 'done'
    assert '_send_stop' not in d.calls


def test_submit(stage):
    d = stage()
    fut = d._submit(lambda a, b=0: (threading.current_thread(), a + b), 2, b=3)
    th, val = fut.wait()
    assert th is d._ctrl.thread and val == 5

    def boom():
        raise ValueError("bad")
    f = d._submit(boom)
    with pytest.raises(RequestFailed) as ei:
        f.wait()
    assert isinstance(ei.value.__cause__, ValueError)
    assert f.status == 'failed'
    with pytest.raises(TypeError):
        f.cancel()
    assert d._ctrl.thread.is_alive()


def test_send_move_exception_fails_request(stage):
    d = stage()
    d.fail_hooks['_send_move'] = OSError("port gone")
    req = d.move_to({'x': 1.0}, speed=10)
    with pytest.raises(RequestFailed) as ei:
        req.wait()
    assert isinstance(ei.value.__cause__, OSError)
    del d.fail_hooks['_send_move']
    d.move_to({'x': 1.0}, speed=100).wait()


def test_send_stop_exception_fails_stop(stage):
    d = stage()
    d.fail_hooks['_send_stop'] = OSError("nope")
    with pytest.raises(RequestFailed):
        d.stop().wait()


def test_check_move_exception_fails_move(stage):
    d = stage()
    d.fail_hooks['_check_move'] = OSError("read failed")
    req = d.move_to({'x': 100.0}, speed=10)
    with pytest.raises(RequestFailed, match="read failed"):
        req.wait()
    assert d._ctrl.thread.is_alive()


def test_poll_exceptions_logged(stage, caplog):
    d = stage()
    d.fail_hooks['_read_position'] = OSError("glitch")
    d.fail_hooks['_poll_extra'] = OSError("extra glitch")
    time.sleep(0.05)
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert 1 <= len(errors) <= 2  # repeats suppressed
    d.fail_hooks.clear()
    req = d.move_to({'x': 1.0}, speed=100)
    req.wait()
    assert wait_for(lambda: d.get_position()['x'] == 1.0)


def test_callback_exception_does_not_kill_thread(stage):
    d = stage()
    d.set_position_callback(lambda pos: 1 / 0)
    req = d.move_to({'x': 1.0}, speed=100)
    req.set_callback(lambda r: 1 / 0)
    req.wait()
    assert d._ctrl.thread.is_alive()


def test_close():
    d = FakeStage()
    gate = threading.Event()
    d.connect()
    blocker = d._submit(gate.wait, 2)
    move = d.move_to({'x': 100.0}, speed=1)
    queued = d._submit(lambda: 1)
    threading.Timer(0.05, gate.set).start()
    t = time.monotonic()
    d.close()
    assert time.monotonic() - t < 1
    assert not d._ctrl.thread.is_alive()
    blocker.wait()
    assert queued.wait() == 1  # requests queued before close still run
    with pytest.raises(RequestFailed, match="closed"):
        move.wait()
    late = d.move_to({'x': 1.0}, speed=1)
    with pytest.raises(RequestFailed, match="not connected"):
        late.wait(timeout=0)
    d.close()  # idempotent
    # reconnect works
    d.connect()
    d.move_to({'x': 1.0}, speed=100).wait()
    d.close()


def test_not_connected():
    d = FakeStage()
    with pytest.raises(RequestError):
        d.move_to({'x': 1.0}, speed=1).wait(timeout=0)
    assert d.get_position() is None


def test_wait_timeout(stage):
    d = stage()
    req = d.move_to({'x': 100.0}, speed=1)
    with pytest.raises(TimeoutError):
        req.wait(timeout=0.01)
    req.cancel()
