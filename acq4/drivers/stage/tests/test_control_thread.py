import threading
import time

import pytest

from acq4.drivers.stage import (
    MoveCancelled,
    MoveInterrupted,
    MoveRequest,
    MoveState,
    MoveStopped,
    RequestError,
    RequestFailed,
    RequestFuture,
    StageDriver,
)


class FakeBackend:
    """In-memory stage backend: axes move linearly toward target at *speed* units/s.

    A stop decelerates for ``stop_settle`` seconds before motion ceases. Records every call
    in ``calls`` and fails it if ``fail_hooks`` names it.
    """

    def __init__(self, axes=('x', 'y', 'z'), stop_settle=0.0, stop_before_move=False):
        self.axes = tuple(axes)
        self.stop_before_move = stop_before_move
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

    def moving(self):
        return any(self.pos[ax] != self.target[ax] for ax in self.pos) or self.stop_until is not None

    def _guard(self, name):
        if not self.in_hook.acquire(blocking=False):
            self.reentrant = True
            raise RuntimeError("reentrant backend call")
        try:
            self._advance()
            self._hook(name)
        finally:
            self.in_hook.release()

    def open(self):
        self._guard('open')

    def close(self):
        self._guard('close')

    def read_position(self):
        self._guard('read_position')
        return dict(self.pos)

    def start_move(self, target, speed, **kwds):
        self._guard('start_move')
        self.moving_when_sent.append(self.moving())
        self.speed = speed
        self.target.update(target)
        self.stop_until = None
        return dict(target)

    def stop(self, reason):
        self._guard('stop')
        if self.stop_settle > 0:
            self.stop_until = time.monotonic() + self.stop_settle
        else:
            self.target = dict(self.pos)

    def check_move(self, target):
        self._guard('check_move')
        if self.moving():
            return MoveState.MOVING, None
        if all(abs(self.pos[ax] - v) < 1e-9 for ax, v in target.items()):
            return MoveState.DONE, None
        return MoveState.FAILED, f"stopped short at {self.pos}"

    def is_moving(self, target):
        self._guard('is_moving')
        return self.moving()

    def final_position(self, target):
        self._guard('final_position')
        return dict(self.pos)

    def poll_extra(self):
        self._guard('poll_extra')


def FakeStage(poll_interval=0.005, stop_timeout=5.0, position_change_threshold=None, **backend_kwds):
    """StageDriver over a new FakeBackend, which is ``driver.b``."""
    b = FakeBackend(**backend_kwds)
    d = StageDriver(b, poll_interval=poll_interval, stop_timeout=stop_timeout,
                    position_change_threshold=position_change_threshold)
    d.b = b
    return d


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
        assert not d.b.reentrant
        assert all(t is d._ctrl.thread for t in d.b.ctrl_threads)


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
    n = d.b.calls.count('read_position')
    for _ in range(100):
        d.get_position()
    assert d.b.calls.count('read_position') - n < 5  # get_position does no I/O
    assert 'poll_extra' in d.b.calls


def test_position_callback_threshold():
    d = FakeStage(position_change_threshold=1.0)
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


def test_rezero_in_call_published_by_next_poll():
    d = FakeStage(position_change_threshold=1.0)
    seen = []
    d.set_position_callback(seen.append)
    d.connect()
    try:
        assert wait_for(lambda: len(seen) >= 1)
        d.b.pos['x'] = d.b.target['x'] = 50.0

        def rezero():  # like homing: shifts the position frame without publishing
            d.b.pos['x'] = d.b.target['x'] = 0.0

        assert wait_for(lambda: seen[-1]['x'] == 50.0)
        d._run(rezero).wait()
        assert wait_for(lambda: seen[-1]['x'] == 0.0)
        assert d.get_position()['x'] == 0.0
    finally:
        d.close()


def test_position_callback_per_axis_threshold():
    d = FakeStage(position_change_threshold={'x': 100.0, 'y': 0.5})
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
    deadline = time.monotonic() + 1.0
    while len(seen) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(seen) >= 3


def test_move_completes(stage):
    d = stage()
    done = []
    req = d.move_to({'x': 1.0, 'y': -1.0, 'z': None}, speed=40, reason='test', acceleration=7)
    req.add_callback(done.append)
    assert req.target == {'x': 1.0, 'y': -1.0}
    assert req.kwds == {'acceleration': 7}
    assert req.wait(timeout=2) is None
    assert req.status == 'done'
    assert done == [req]
    assert wait_for(lambda: d.get_position()['x'] == 1.0)
    late = []
    req.add_callback(late.append)
    assert late == [req]  # fires immediately once done


def test_move_failure_reason(stage):
    d = stage()
    req = d.move_to({'x': 5.0}, speed=50)
    # make the device stop short via direct state manipulation from the control thread
    d._run(lambda: d.b.target.update(x=0.5)).wait()
    with pytest.raises(RequestFailed, match="stopped short"):
        req.wait()
    assert req.status == 'failed'


@pytest.mark.parametrize('stop_before_move', [False, True])
def test_interrupt(stage, stop_before_move):
    d = stage(stop_settle=0.05 if stop_before_move else 0.0, stop_before_move=stop_before_move)
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
        assert d.b.calls.count('stop') == 1
        assert d.b.moving_when_sent == [False, False]  # motion ceased before the new move
        assert 'is_moving' in d.b.calls
    else:
        assert 'stop' not in d.b.calls
        assert d.b.moving_when_sent == [False, True]


def test_interrupt_pending_after_stop(stage):
    # with stop_before_move, a third move replaces the one waiting for motion to cease
    d = stage(stop_settle=0.1, stop_before_move=True)
    a = d.move_to({'x': 100.0}, speed=10)
    b = d.move_to({'x': 1.0}, speed=50)
    c = d.move_to({'x': 2.0}, speed=50)
    c.wait(timeout=3)
    assert (a.status, b.status, c.status) == ('interrupted', 'interrupted', 'done')
    assert d.b.calls.count('start_move') == 2


def test_stop_before_move_timeout(stage):
    d = stage(stop_settle=10.0, stop_before_move=True, stop_timeout=0.05)
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
    assert d.b.calls.count('stop') == 2


def test_cancel_active(stage):
    d = stage()
    req = d.move_to({'x': 100.0}, speed=10)
    assert wait_for(lambda: req.status == 'moving')
    req.cancel().wait()
    with pytest.raises(MoveCancelled):
        req.wait()
    assert type(req.error) is RequestError  # no underlying exception: describes how it ended
    assert d.b.calls.count('stop') == 1


def test_cancel_not_active(stage):
    d = stage()
    # block the control thread so the move is still queued when cancelled
    gate = threading.Event()
    blocker = d._run(gate.wait, 2)
    req = d.move_to({'x': 1.0}, speed=10)
    c = req.cancel()
    assert not req.done()  # resolved by the control thread when it reaches the move
    gate.set()
    blocker.wait()
    c.wait()
    assert req.status == 'cancelled'
    with pytest.raises(MoveCancelled):
        req.wait(timeout=0)
    assert 'start_move' not in d.b.calls
    assert 'stop' not in d.b.calls

    # cancelling a finished move changes nothing
    done = d.move_to({'x': 0.5}, speed=100)
    done.wait()
    done.cancel().wait()
    assert done.status == 'done'
    assert 'stop' not in d.b.calls


def test_cancel_queued_move_overtakes_it(stage):
    # cancelling a queued move must not let it interrupt the active move
    d = stage()
    active = d.move_to({'x': 100.0}, speed=10)
    assert wait_for(lambda: active.status == 'moving')
    gate = threading.Event()
    blocker = d._run(gate.wait, 2)
    queued = d.move_to({'x': -1.0}, speed=10)
    c = d.cancel_move(queued)
    gate.set()
    blocker.wait()
    c.wait()
    with pytest.raises(MoveCancelled):
        queued.wait()
    assert active.status == 'moving'
    assert d.b.calls.count('start_move') == 1
    assert 'stop' not in d.b.calls
    d.stop().wait()


def test_cancel_pending_move(stage):
    # stop_before_move: a move waiting for previous motion to cease is cancelled without hardware access
    d = stage(stop_settle=0.2, stop_before_move=True)
    a = d.move_to({'x': 100.0}, speed=10)
    b = d.move_to({'x': 1.0}, speed=50)
    assert wait_for(lambda: d._ctrl.pending_move is b)
    b.cancel().wait()
    assert b.status == 'cancelled' and a.status == 'interrupted'
    assert d.b.calls.count('start_move') == 1
    assert d.b.calls.count('stop') == 1  # from b interrupting a, not from the cancel


def test_error_messages_include_reason(stage):
    d = stage()
    req = d.move_to({'x': 100.0}, speed=10, reason='jog x')
    assert 'jog x' in repr(req)
    with pytest.raises(TimeoutError, match='jog x'):
        req.wait(timeout=0.01)
    d.stop(reason='because').wait()
    with pytest.raises(MoveStopped, match=r"\(jog x\) stopped>: stopped: because") as ei:
        req.wait()
    # chained from the stored description, never a copy of it
    assert ei.value.__cause__ is req.error
    assert type(req.error) is RequestError and str(req.error) == 'stopped: because'

    def boom():
        raise ValueError("bad")
    f = d._run(boom, reason='calibrate')
    with pytest.raises(RequestFailed, match="'calibrate' failed>: ValueError: bad") as ei:
        f.wait()
    assert ei.value.__cause__ is f.error and isinstance(f.error, ValueError)
    with pytest.raises(RequestFailed) as again:
        f.wait()
    assert again.value is not ei.value and again.value.__cause__ is f.error


def test_run_interrupt(stage):
    d = stage()
    plain = d._run(lambda: 1)
    assert plain.wait() == 1 and 'stop' not in d.b.calls   # nothing to interrupt: no stop sent
    move = d.move_to({'x': 100.0}, speed=10)
    assert wait_for(lambda: move.status == 'moving' and d.get_position()['x'] > 0.05)
    seen = []
    fut = d._run(lambda: seen.append(move.status) or 2, interrupt=True, reason='homing')
    assert fut.wait() == 2
    assert seen == ['interrupted']   # ended before fn ran
    with pytest.raises(MoveInterrupted, match='interrupted by homing'):
        move.wait()
    assert d.b.calls.count('stop') == 1
    assert 0 < move.final_position['x'] < 100.0


def test_run_cancelled(stage):
    d = stage()

    def decline():
        raise MoveCancelled('declined by user')
    fut = d._run(decline, reason='commutate')
    with pytest.raises(MoveCancelled, match="'commutate' cancelled>: MoveCancelled: declined by user") as ei:
        fut.wait()
    assert fut.status == 'cancelled' and ei.value.__cause__ is fut.error


def test_run(stage):
    d = stage()
    fut = d._run(lambda a, b: (threading.current_thread(), a + b), 2, 3)
    th, val = fut.wait()
    assert th is d._ctrl.thread and val == 5

    def boom():
        raise ValueError("bad")
    f = d._run(boom)
    with pytest.raises(RequestFailed) as ei:
        f.wait()
    assert isinstance(ei.value.__cause__, ValueError)
    assert f.status == 'failed'
    assert not hasattr(f, 'cancel')
    assert d._ctrl.thread.is_alive()


def test_start_move_exception_fails_request(stage):
    d = stage()
    d.b.fail_hooks['start_move'] = OSError("port gone")
    req = d.move_to({'x': 1.0}, speed=10)
    with pytest.raises(RequestFailed) as ei:
        req.wait()
    assert isinstance(ei.value.__cause__, OSError)
    del d.b.fail_hooks['start_move']
    d.move_to({'x': 1.0}, speed=100).wait()


def test_stop_exception_fails_stop(stage):
    d = stage()
    d.b.fail_hooks['stop'] = OSError("nope")
    with pytest.raises(RequestFailed):
        d.stop().wait()


def test_check_move_exception_fails_move(stage):
    d = stage()
    d.b.fail_hooks['check_move'] = OSError("read failed")
    req = d.move_to({'x': 100.0}, speed=10)
    with pytest.raises(RequestFailed, match="read failed"):
        req.wait()
    assert d._ctrl.thread.is_alive()


def test_poll_exceptions_logged(stage, caplog):
    d = stage()
    d.b.fail_hooks['read_position'] = OSError("glitch")
    d.b.fail_hooks['poll_extra'] = OSError("extra glitch")
    time.sleep(0.05)
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert 1 <= len(errors) <= 2  # repeats suppressed
    d.b.fail_hooks.clear()
    req = d.move_to({'x': 1.0}, speed=100)
    req.wait()
    assert wait_for(lambda: d.get_position()['x'] == 1.0)


def test_callback_exception_does_not_kill_thread(stage):
    d = stage()
    d.set_position_callback(lambda pos: 1 / 0)
    req = d.move_to({'x': 1.0}, speed=100)
    req.add_callback(lambda r: 1 / 0)
    req.wait()
    assert d._ctrl.thread.is_alive()


def test_close():
    d = FakeStage()
    gate = threading.Event()
    d.connect()
    blocker = d._run(gate.wait, 2)
    move = d.move_to({'x': 100.0}, speed=1)
    queued = d._run(lambda: 1)
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
    with pytest.raises(RuntimeError, match='closed'):
        d.connect()


def test_not_connected():
    d = FakeStage()
    with pytest.raises(RequestError, match='not connected'):
        d.move_to({'x': 1.0}, speed=1).wait(timeout=0)
    assert d.get_position() is None
    d.close()  # no-op before connect
    d.connect()
    with pytest.raises(RuntimeError, match='already connected'):
        d.connect()
    d.close()


def test_open_and_close_run_on_control_thread():
    d = FakeStage()
    d.connect()
    d.close()
    assert d.b.calls[0] == 'open' and d.b.calls[-1] == 'close'
    assert d.b.ctrl_threads == {d._ctrl.thread}


def test_open_failure_raises_from_connect():
    d = FakeStage()
    d.b.fail_hooks['open'] = OSError("no port")
    with pytest.raises(OSError, match="no port"):
        d.connect()
    assert d.b.calls == ['open', 'close']  # no poll before the link is open
    with pytest.raises(RequestFailed, match='not connected'):
        d.move_to({'x': 1.0}, speed=1).wait(timeout=0)


def test_requests_racing_close_are_all_resolved():
    d = FakeStage()
    d.connect()
    futs = []
    stop = threading.Event()

    def spam():
        while not stop.is_set():
            futs.append(d._run(lambda: None))
    threads = [threading.Thread(target=spam) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.02)
    d.close()
    time.sleep(0.01)
    stop.set()
    for t in threads:
        t.join()
    assert all(f.done() for f in futs)


def test_callback_registered_while_finishing_runs_once():
    for _ in range(200):
        fut = RequestFuture('call')
        calls = []
        t = threading.Thread(target=fut._finish, args=('done',))
        t.start()
        fut.add_callback(calls.append)
        t.join()
        assert calls == [fut]
        assert fut._callbacks == []


def test_add_callback_concurrent_with_finish_runs_each_once():
    import random
    import sys
    n_threads, per_thread = 4, 50
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # maximise thread interleaving
    try:
        for _ in range(100):
            fut = RequestFuture('call')
            ran = []
            start = threading.Barrier(n_threads + 1)

            def adder(k):
                start.wait()
                for j in range(per_thread):
                    fut.add_callback(lambda f, i=k * per_thread + j: ran.append(i))

            def finisher():
                start.wait()
                # finish after a random number of adds, so later adds race the drain
                n = random.randrange(n_threads * per_thread)
                while len(fut._callbacks) < n:
                    pass
                fut._finish('done')

            threads = [threading.Thread(target=adder, args=(k,)) for k in range(n_threads)]
            threads.append(threading.Thread(target=finisher))
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert sorted(ran) == list(range(n_threads * per_thread))
            assert fut._callbacks == []
    finally:
        sys.setswitchinterval(old_interval)


def test_wait_timeout(stage):
    d = stage()
    req = d.move_to({'x': 100.0}, speed=1)
    with pytest.raises(TimeoutError):
        req.wait(timeout=0.01)
    req.cancel()


# ---- request arguments ----

def test_improper_request_keys_fail_the_request(stage):
    d = stage()
    extra = d._enqueue(RequestFuture('stop', d, 'x'), reason='x', bogus=1)
    missing = d._enqueue(RequestFuture('stop', d, 'x'))
    move = d._enqueue(MoveRequest(d, {'x': 1.0}, 10), speed=5)
    for fut in (extra, missing, move):
        with pytest.raises(RequestFailed) as ei:
            fut.wait()
        assert isinstance(ei.value.__cause__, TypeError)
    assert move.final_position is None
    assert 'stop' not in d.b.calls and 'start_move' not in d.b.calls
    assert d._ctrl.thread.is_alive()
    d.move_to({'x': 1.0}, speed=100).wait()


# ---- timestamps ----

def test_start_and_finish_times(stage):
    d = stage()
    req = d.move_to({'x': 1.0}, speed=50)
    call = d._run(lambda: None)
    req.wait()
    call.wait()
    for fut in (req, call):
        assert fut.created_time <= fut.start_time <= fut.finish_time
    assert req.start_time <= call.start_time  # handled in submission order
    assert call.finish_time <= req.finish_time  # the move completes over several polls


def test_times_for_requests_that_never_start():
    d = FakeStage()
    rejected = d.move_to({'x': 1.0}, speed=1)
    assert rejected.start_time is None and rejected.finish_time >= rejected.created_time
    d.connect()
    try:
        gate = threading.Event()
        blocker = d._run(gate.wait, 2)
        queued = d.move_to({'x': 1.0}, speed=10)
        cancel = queued.cancel()
        gate.set()
        blocker.wait()
        cancel.wait()
        assert queued.status == 'cancelled'
        assert queued.start_time is None and queued.finish_time is not None
        assert cancel.start_time is not None
        assert d._ctrl.opened.start_time <= d._ctrl.opened.finish_time
    finally:
        d.close()


# ---- final position ----

def test_final_position_done_is_read_after_completion(stage):
    d = stage()
    req = d.move_to({'x': 1.0, 'y': -1.0}, speed=50)
    req.wait()
    assert req.final_position == {'x': 1.0, 'y': -1.0, 'z': 0.0}
    i = len(d.b.calls) - 1 - d.b.calls[::-1].index('check_move')
    assert 'final_position' in d.b.calls[i:]  # read after check_move reported DONE


def test_final_position_read_failure_falls_back(stage):
    d = stage()
    d.b.fail_hooks['final_position'] = OSError("read failed")
    req = d.move_to({'x': 1.0}, speed=50)
    req.wait()
    assert req.status == 'done'
    assert req.final_position is not None and set(req.final_position) == {'x', 'y', 'z'}


def _moving(d, req):
    assert wait_for(lambda: req.status == 'moving' and d.get_position()['x'] > 0.05)


def test_final_position_stopped(stage):
    d = stage()
    req = d.move_to({'x': 100.0}, speed=10)
    _moving(d, req)
    d.stop().wait()
    assert req.status == 'stopped'
    assert 0.05 < req.final_position['x'] < 100.0


def test_final_position_interrupted(stage):
    d = stage()
    first = d.move_to({'x': 100.0}, speed=10)
    _moving(d, first)
    second = d.move_to({'x': -0.1}, speed=50)
    second.wait()
    assert first.status == 'interrupted'
    assert 0.05 < first.final_position['x'] < 100.0
    assert second.final_position['x'] == -0.1


def test_final_position_cancelled(stage):
    d = stage()
    active = d.move_to({'x': 100.0}, speed=10)
    _moving(d, active)
    active.cancel().wait()
    assert active.status == 'cancelled'
    assert 0.05 < active.final_position['x'] < 100.0

    gate = threading.Event()
    blocker = d._run(gate.wait, 2)
    queued = d.move_to({'x': 1.0}, speed=10)
    c = queued.cancel()
    gate.set()
    blocker.wait()
    c.wait()
    assert queued.status == 'cancelled' and queued.final_position is None


def test_final_position_none_for_pending_move(stage):
    # stop_before_move: a move interrupted while waiting for motion to cease was never sent
    d = stage(stop_settle=0.1, stop_before_move=True)
    a = d.move_to({'x': 100.0}, speed=10)
    b = d.move_to({'x': 1.0}, speed=50)
    c = d.move_to({'x': 2.0}, speed=50)
    c.wait(timeout=3)
    assert b.status == 'interrupted' and b.final_position is None
    assert a.final_position is not None


# ---- quit / close ----

def test_quit_does_not_block():
    d = FakeStage()
    d.connect()
    gate = threading.Event()
    blocker = d._run(gate.wait, 2)
    t = time.monotonic()
    fut = d._ctrl.quit()
    assert time.monotonic() - t < 0.1
    assert not fut.done() and d._ctrl.thread.is_alive()
    gate.set()
    blocker.wait()
    assert fut.wait() is None and fut.status == 'done'
    d._ctrl.thread.join(2)
    assert not d._ctrl.thread.is_alive()
    assert d._ctrl.quit().status == 'failed'  # not running: rejected at once
    d.close()


def test_close_from_control_thread():
    d = FakeStage()
    d.connect()
    d._run(d.close).wait()  # queues the shutdown; must not wait on itself
    d._ctrl.thread.join(2)
    assert not d._ctrl.thread.is_alive()
    assert d._ctrl.state == 'closed'
