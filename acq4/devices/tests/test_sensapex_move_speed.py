"""Regression tests for the minimum-move-time speed limit on Sensapex moves.

A uMp move commanded to finish in a couple of milliseconds stops short of its target,
so `SensapexMoveFuture` slows short moves down until they are expected to take
`minimumMoveTime`. The limit compares a distance against a speed, and those two are in
different units -- positions in um, speeds in m/s -- so the distance has to be scaled
into metres first. Getting that conversion wrong is silent: the comparison simply never
fires and every move goes out at full speed.

The limit also has to be applied to each leg of a 4-axis move separately. `_4AxisMove`
splits a move into a d-axis leg and an xyz leg; a 13 um d-axis retraction needs slowing
down even when the xyz leg that follows it travels 14 mm.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def make_future(qapp, monkeypatch):
    """Return a factory for SensapexMoveFutures with no hardware behind them.

    The sensapex driver calls ``getManager()`` at import time, so a stub manager is
    patched in before importing the device module. Only the ``MoveFuture`` base
    initializer is run, skipping the hardware move request and monitor thread that
    ``SensapexMoveFuture.__init__`` would start.
    """

    pytest.importorskip("sensapex")

    class _StubManager:
        config = {}

    monkeypatch.setattr("acq4.getManager", lambda: _StubManager())

    from acq4.devices.Stage.Stage import MoveFuture
    from acq4.devices.Sensapex import SensapexMoveFuture

    class _FakeDriver:
        """Stands in for ``UMP.get_device()``; records what it was asked to do.

        ``pos`` is where the device claims to be *now*, which a test may move between
        legs to stand in for a device that has travelled since the move was requested.
        """

        def __init__(self, pos):
            self.calls = []
            self.pos = list(pos)

        def get_pos(self, timeout=None):
            return list(self.pos)

        def goto_pos(self, dest, speed, **kwds):
            self.calls.append((list(dest), speed, kwds))
            return object()

    class _FakeDev:
        retryThreshold = 0.1  # um, the driver default

        def __init__(self, startPos, scale):
            self._pos = list(startPos)
            self._scale = scale
            self.dev = _FakeDriver(startPos)
            self.nAxes = len(self._pos)

        def name(self):
            return "FakeSensapex"

        def getPosition(self):
            return list(self._pos)

        def getAxisScale(self):
            return np.array(self._scale, dtype=float)

    def factory(startPos, targetPos, speed, scale=None, linear=False):
        if scale is None:
            scale = [1e-6] * len(startPos)
        dev = _FakeDev(startPos, scale)
        fut = SensapexMoveFuture.__new__(SensapexMoveFuture)
        MoveFuture.__init__(fut, dev, pos=targetPos, speed=speed, name="test move")
        fut.max_attempts = 3
        fut._linear = linear
        fut._moveReq = None
        return fut

    return factory


def test_long_fast_move_keeps_requested_speed(make_future):
    # 10 mm at 5 mm/s takes 2 s all by itself; nothing to limit.
    fut = make_future([0, 0, 0], [10000, 0, 0], speed=5e-3)
    assert fut._legSpeed(fut.startPos, fut.targetPos) == pytest.approx(5e-3)


def test_short_fast_move_is_slowed_to_the_minimum_move_time(make_future):
    # The failing case from the field: a 13.45 um retraction commanded at 5 mm/s would
    # be over in 2.7 ms, and the axis never arrives.
    fut = make_future([0, 0, 0, 13.45], [0, 0, 0, 0.0], speed=5e-3)
    speed = fut._legSpeed(fut.startPos, fut.targetPos)
    assert speed == pytest.approx(13.45e-6 / fut.minimumMoveTime)
    # ... which is the whole point: the move now takes minimumMoveTime.
    assert 13.45e-6 / speed == pytest.approx(fut.minimumMoveTime)
    assert speed < 5e-3


def test_distance_is_scaled_by_device_units_not_compared_raw(make_future):
    # Same 2 mm move on two devices reporting different units. If the distance were
    # compared to the speed without scaling, the mm device (2.0) and the um device
    # (2000.0) would get different limits for the same physical move.
    in_um = make_future([0, 0, 0], [2000, 0, 0], speed=5e-3, scale=[1e-6] * 3)
    in_mm = make_future([0, 0, 0], [2, 0, 0], speed=5e-3, scale=[1e-3] * 3)
    assert in_um._legSpeed(in_um.startPos, in_um.targetPos) == pytest.approx(
        in_mm._legSpeed(in_mm.startPos, in_mm.targetPos)
    )
    # 2 mm at 5 mm/s already takes 0.4 s, so neither is limited.
    assert in_um._legSpeed(in_um.startPos, in_um.targetPos) == pytest.approx(5e-3)


def test_negative_scale_does_not_cancel_the_limit(make_future):
    # An axis pointing along a negative global direction has a negative scale; the
    # distance it travels is still positive.
    fut = make_future([0, 0, 0], [10, 0, 0], speed=5e-3, scale=[-1e-6, 1e-6, -1e-6])
    assert fut._legSpeed(fut.startPos, fut.targetPos) == pytest.approx(
        10e-6 / fut.minimumMoveTime
    )


def test_slow_moves_are_left_alone(make_future):
    # Below 10 um/s the uMp is not being rushed, and the stepwise path handles the
    # speeds it cannot command at all.
    fut = make_future([0, 0, 0, 13.45], [0, 0, 0, 0.0], speed=2e-6)
    assert fut._legSpeed(fut.startPos, fut.targetPos) == pytest.approx(2e-6)


def test_zero_length_move_keeps_requested_speed(make_future):
    fut = make_future([1, 2, 3], [1, 2, 3], speed=5e-3)
    assert fut._legSpeed(fut.startPos, fut.targetPos) == pytest.approx(5e-3)


def test_missing_scale_entries_fall_back_to_the_last_axis(make_future):
    # A 4-axis device configured with only xyz scales: the d axis must not blow up or
    # be treated as unscaled.
    fut = make_future([0, 0, 0, 13.45], [0, 0, 0, 0.0], speed=5e-3, scale=[1e-6] * 3)
    assert fut._legSpeed(fut.startPos, fut.targetPos) == pytest.approx(
        13.45e-6 / fut.minimumMoveTime
    )


def test_each_leg_of_a_four_axis_move_is_limited_on_its_own_length(make_future, monkeypatch):
    # The field failure: home is 14 mm away in xyz, but the d leg that goes first is
    # 13.45 um. The long leg must not lend its speed to the short one.
    start = [4487.4, 13192.0, 14103.7, 13.45]
    target = [355.7, 77.4, 11452.1, 0.0]
    fut = make_future(start, target, speed=5e-3, linear=True)
    monkeypatch.setattr(type(fut), "_waitFor", lambda self, req: True)
    monkeypatch.setattr(type(fut), "_completeFromMoveReq", lambda self: None)

    fut._4AxisMove()

    calls = fut.dev.dev.calls
    assert len(calls) == 2
    (first_dest, first_speed, _), (second_dest, second_speed, _) = calls

    # d retracts first, and that leg names d alone: xyz are NaN, so the driver leaves
    # them wherever the device has actually got to.
    assert first_dest[:3] == [pytest.approx(np.nan, nan_ok=True)] * 3
    assert first_dest[3] == pytest.approx(0.0)
    assert first_speed == pytest.approx(13.45e-6 / fut.minimumMoveTime * 1e6)

    # Leg two travels several mm in xyz and is long enough to run at full speed.
    assert second_dest[:3] == pytest.approx(target[:3])
    assert second_dest[3] != second_dest[3], "the xyz leg must not command d"
    assert second_speed == pytest.approx(5e-3 * 1e6)


def test_a_four_axis_move_that_leaves_d_alone_is_issued_as_one_request(make_future, monkeypatch):
    # Nothing for d to do, so there is no d leg at all.
    start = [100.0, 200.0, 300.0, 50.0]
    target = [100.0, 200.0, 900.0, 50.0]
    fut = make_future(start, target, speed=5e-3, linear=True)
    monkeypatch.setattr(type(fut), "_waitFor", lambda self, req: True)
    monkeypatch.setattr(type(fut), "_completeFromMoveReq", lambda self: None)

    fut._4AxisMove()

    calls = fut.dev.dev.calls
    assert len(calls) == 1
    assert calls[0][0][:3] == pytest.approx(target[:3])
    assert calls[0][0][3] != calls[0][0][3], "the xyz leg must not command d"
    # 600 um at 5 mm/s would be over in 0.12 s, so the single leg is slowed as usual.
    assert calls[0][1] == pytest.approx(600e-6 / fut.minimumMoveTime * 1e6)


def test_a_sub_threshold_d_change_does_not_earn_its_own_leg(make_future, monkeypatch):
    # 0.03 um of d is below the driver's retry threshold: it would be dropped from the
    # request anyway, so it must not split the move.
    start = [100.0, 200.0, 300.0, 50.0]
    target = [100.0, 200.0, 900.0, 49.97]
    fut = make_future(start, target, speed=5e-3, linear=True)
    monkeypatch.setattr(type(fut), "_waitFor", lambda self, req: True)
    monkeypatch.setattr(type(fut), "_completeFromMoveReq", lambda self: None)

    fut._4AxisMove()

    assert len(fut.dev.dev.calls) == 1


def test_a_leg_is_sized_from_where_the_device_is_not_where_it_was(make_future, monkeypatch):
    # startPos is a cached reading, tens of um stale on a moving device. A target that
    # lands near that stale reading is a long way from the device, and sizing the leg on
    # the stale distance commands the driver's 1 um/s floor for the whole real distance.
    fut = make_future([0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.05, 0.0], speed=5e-3)
    fut.dev.dev.pos = [0.0, 0.0, 50.0, 0.0]  # where it has actually got to
    monkeypatch.setattr(type(fut), "_waitFor", lambda self, req: True)
    monkeypatch.setattr(type(fut), "_completeFromMoveReq", lambda self: None)

    fut._4AxisMove()

    speed = fut.dev.dev.calls[0][1]
    assert speed == pytest.approx(49.95e-6 / fut.minimumMoveTime * 1e6)
    assert speed > 1.0, "the leg was sized from the stale start and floored"
