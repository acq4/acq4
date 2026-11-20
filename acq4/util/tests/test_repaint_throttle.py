import logging
import time

import numpy as np

from acq4.util.repaint_throttle import RepaintThrottle


class _Recorder:
    def __init__(self, fail=False):
        self.calls = []
        self.times = []
        self.fail = fail

    def __call__(self, *args):
        self.calls.append(args)
        self.times.append(time.perf_counter())
        if self.fail:
            raise RuntimeError("repaint failure")


def test_burst_paints_once_with_newest_args(qtbot):
    rec = _Recorder()
    throttle = RepaintThrottle(rec)
    for i in range(1000):
        throttle.submit(i, 'x')
    assert rec.calls == []  # never synchronous
    qtbot.waitUntil(lambda: len(rec.calls) > 0, timeout=1000)
    qtbot.wait(150)
    assert rec.calls == [(999, 'x')]
    assert not throttle.isPending()


def test_paint_rate_is_bounded_and_newest_is_painted(qtbot):
    rec = _Recorder()
    throttle = RepaintThrottle(rec, maxRate=20.0)
    n = 0
    start = time.perf_counter()
    while time.perf_counter() - start < 0.6:
        throttle.submit(n)
        n += 1
        qtbot.wait(2)
    elapsed = time.perf_counter() - start
    qtbot.wait(150)

    assert n > 50
    assert 3 <= len(rec.calls) <= elapsed * 20 + 2
    assert np.diff(rec.times).min() >= 0.045
    assert rec.calls[-1] == (n - 1,)
    values = [c[0] for c in rec.calls]
    assert values == sorted(values)


def test_first_submission_after_idle_paints_promptly(qtbot):
    rec = _Recorder()
    throttle = RepaintThrottle(rec, maxRate=1.0)
    throttle.submit(1)
    qtbot.waitUntil(lambda: len(rec.calls) > 0, timeout=200)
    assert rec.calls == [(1,)]


def test_cancel_drops_pending_repaint(qtbot):
    rec = _Recorder()
    throttle = RepaintThrottle(rec)
    throttle.submit(1)
    assert throttle.isPending()
    throttle.cancel()
    assert not throttle.isPending()
    qtbot.wait(150)
    assert rec.calls == []


def test_cancel_drops_trailing_repaint(qtbot):
    rec = _Recorder()
    throttle = RepaintThrottle(rec)
    throttle.submit(1)
    qtbot.waitUntil(lambda: len(rec.calls) > 0, timeout=1000)
    throttle.submit(2)  # within the interval: scheduled for later
    assert throttle.isPending()
    throttle.cancel()
    qtbot.wait(150)
    assert rec.calls == [(1,)]

    throttle.submit(3)
    qtbot.waitUntil(lambda: len(rec.calls) == 2, timeout=1000)
    assert rec.calls[-1] == (3,)


def test_failure_logged_once_until_cancel(qtbot, caplog):
    rec = _Recorder(fail=True)
    throttle = RepaintThrottle(rec, maxRate=100.0)

    def failures():
        return [r for r in caplog.records if 'Error in repaint' in r.getMessage()]

    with caplog.at_level(logging.ERROR, logger='acq4'):
        for i in range(3):
            throttle.submit(i)
            qtbot.waitUntil(lambda: len(rec.calls) == i + 1, timeout=1000)
        assert len(failures()) == 1

        throttle.cancel()
        throttle.submit(3)
        qtbot.waitUntil(lambda: len(rec.calls) == 4, timeout=1000)
        assert len(failures()) == 2
