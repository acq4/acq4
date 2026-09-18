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
        """Stands in for ``UMP.get_device()``; records what it was asked to do."""

        def __init__(self):
            self.calls = []

        def goto_pos(self, dest, speed, **kwds):
            self.calls.append((list(dest), speed, kwds))
            return object()

    class _FakeDev:
        def __init__(self, startPos, scale):
            self._pos = list(startPos)
            self._scale = scale
            self.dev = _FakeDriver()
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

    # d retracts first, so leg one moves d alone and keeps xyz where they were.
    assert first_dest == pytest.approx(start[:3] + [0.0])
    assert first_speed == pytest.approx(13.45e-6 / fut.minimumMoveTime * 1e6)

    # Leg two travels several mm in xyz and is long enough to run at full speed.
    assert second_dest == pytest.approx(target)
    assert second_speed == pytest.approx(5e-3 * 1e6)
