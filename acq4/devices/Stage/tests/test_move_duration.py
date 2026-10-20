"""How long a move should take: ``Stage.acceleration`` and ``MoveFuture.expectedDuration``.

``Stage.acceleration`` is SI, m/s^2, while drivers configure it in vendor units -- mm/s^2
for Dover, um/s^2 for Sensapex -- so each conversion is pinned against a worked example.
A move too short to reach its commanded speed follows a triangular profile: at 0.05 m/s
with 0.05 m/s^2, a 500 um step takes twenty times ``distance / speed``.
``wait(timeout=None)`` still means "wait forever"; the auto timeout is opt-in via
:meth:`MoveFuture.waitForMove`.

No hardware: the futures are built by running only the ``MoveFuture`` base initializer
over a stub device, the way ``tests/test_sensapex_move_speed.py`` does.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from acq4.devices.Stage.Stage import MoveFuture, Stage


class _StubStage:
    """Just enough of a Stage for a MoveFuture to measure a distance against.

    ``expectedMoveDuration`` and ``_interpretSpeed`` are the real class's.
    """

    fastSpeed = 1e-3
    slowSpeed = 10e-6

    def __init__(self, startPos, scale, acceleration=Stage.defaultAcceleration):
        self._pos = list(startPos)
        self._scale = scale
        self.acceleration = acceleration

    def name(self):
        return "StubStage"

    def getPosition(self):
        return list(self._pos)

    def getAxisScale(self):
        return np.array(self._scale, dtype=float)

    _interpretSpeed = Stage._interpretSpeed
    expectedMoveDuration = Stage.expectedMoveDuration


@pytest.fixture
def make_future(qapp):
    """Return a factory for bare MoveFutures over a stub stage."""

    def factory(startPos, targetPos, speed, scale=None, acceleration=0.05):
        if scale is None:
            scale = [1e-6] * len(startPos)
        dev = _StubStage(startPos, scale, acceleration=acceleration)
        fut = MoveFuture.__new__(MoveFuture)
        MoveFuture.__init__(fut, dev, pos=targetPos, speed=speed, name="test move")
        return fut

    return factory


# --------------------------------------------------------------- unit conversions


def test_base_stage_default_acceleration_is_the_documented_one():
    # expectedMoveDuration divides by it, so it may be neither zero nor None.
    assert Stage.defaultAcceleration > 0
    stub = _StubStage([0, 0, 0], [1e-6] * 3, acceleration=Stage.defaultAcceleration)
    assert stub.acceleration == Stage.defaultAcceleration


def test_dover_converts_millimetres_per_second_squared_to_si():
    from acq4.devices.DoverStage import DoverStage

    # DoverStage config key `defaultAcceleration` is mm/s^2.
    stub = DoverStage.__new__(DoverStage)
    stub.config = {"defaultAcceleration": 50}
    accel = DoverStage.acceleration.fget(stub)
    assert accel == pytest.approx(0.05)
    assert 0.01 < accel < 0.1  # a factor of 1000 either way is the failure mode


def test_dover_acceleration_defaults_without_a_config_key():
    from acq4.devices.DoverStage import DoverStage

    stub = DoverStage.__new__(DoverStage)
    stub.config = {}
    assert DoverStage.acceleration.fget(stub) == pytest.approx(
        DoverStage.DEFAULT_ACCELERATION_MM_S2 * 1e-3
    )


def test_sensapex_converts_micrometres_per_second_squared_to_si(monkeypatch):
    pytest.importorskip("sensapex")
    monkeypatch.setattr("acq4.getManager", lambda: type("_M", (), {"config": {}})())
    from acq4.devices.Sensapex import Sensapex

    # Sensapex config key `maxAcceleration` is um/s^2.
    stub = Sensapex.__new__(Sensapex)
    stub.config = {"maxAcceleration": 1000}
    assert Sensapex.acceleration.fget(stub) == pytest.approx(1e-3)


def test_sensapex_without_max_acceleration_falls_back_to_the_base_default(monkeypatch):
    pytest.importorskip("sensapex")
    monkeypatch.setattr("acq4.getManager", lambda: type("_M", (), {"config": {}})())
    from acq4.devices.Sensapex import Sensapex

    # No key and an explicit 0 both mean "leave the controller's own default", which this
    # class cannot read back.
    for config in ({}, {"maxAcceleration": 0}):
        stub = Sensapex.__new__(Sensapex)
        stub.config = config
        stub._acceleration = Stage.defaultAcceleration
        assert Sensapex.acceleration.fget(stub) == Stage.defaultAcceleration


def test_untouched_drivers_keep_the_base_default():
    # Only the drivers that program an acceleration override the property.
    from acq4.devices.MockStage import MockStage
    from acq4.devices.Scientifica.scientifica import Scientifica
    from acq4.devices.SutterMPC200.SutterMPC200 import SutterMPC200

    for cls in (MockStage, Scientifica, SutterMPC200):
        assert "acceleration" not in vars(cls)


# ------------------------------------------------------------------ the arithmetic


def test_long_move_is_cruise_time_plus_one_ramp():
    # 100 mm at 50 mm/s with a 50 mm/s^2 ramp: 2 s of cruise plus 1 s of ramp.
    stub = _StubStage([0, 0, 0], [1e-3] * 3, acceleration=0.05)
    assert stub.expectedMoveDuration(0.1, 0.05) == pytest.approx(0.1 / 0.05 + 0.05 / 0.05)


def test_short_move_never_reaches_the_commanded_speed():
    # 500 um at 50 mm/s would need 25 mm just to accelerate, so the profile is a triangle:
    # 2 * sqrt(d / a) = 0.2 s, against the 0.01 s distance/speed claims.
    stub = _StubStage([0, 0, 0], [1e-3] * 3, acceleration=0.05)
    predicted = stub.expectedMoveDuration(500e-6, 0.05)
    assert predicted == pytest.approx(2 * math.sqrt(500e-6 / 0.05))
    assert predicted == pytest.approx(0.2)
    assert predicted > 19 * (500e-6 / 0.05)  # the ramp is not a rounding error here


def test_the_two_branches_agree_at_the_boundary():
    # d = v^2 / a is where the triangle's peak touches the commanded speed.
    stub = _StubStage([0, 0, 0], [1e-3] * 3, acceleration=0.05)
    v, a = 0.05, 0.05
    d = v**2 / a
    assert stub.expectedMoveDuration(d * (1 - 1e-9), v) == pytest.approx(
        stub.expectedMoveDuration(d * (1 + 1e-9), v), rel=1e-6
    )


def test_ignoring_acceleration_is_only_safe_on_long_moves():
    stub = _StubStage([0, 0, 0], [1e-3] * 3, acceleration=0.05)
    for d in (1e-6, 1e-4, 1e-2, 1.0):
        assert stub.expectedMoveDuration(d, 0.05) >= d / 0.05
    assert stub.expectedMoveDuration(1.0, 0.05) / (1.0 / 0.05) < 1.1


@pytest.mark.parametrize("accel", [0, -0.05, None, float("nan")])
def test_an_acceleration_that_cannot_ramp_is_refused(accel):
    """A nonsense acceleration is a config mistake, not a degradation to absorb.

    Estimating distance / speed instead would err *fast* -- it is the duration of a move
    that never had to start or stop -- so every deadline built on it is shorter than the
    move it is watching. Refusing says so where someone can fix it.
    """
    stub = _StubStage([0, 0, 0], [1e-6] * 3, acceleration=accel)
    with pytest.raises(ValueError, match="acceleration"):
        stub.expectedMoveDuration(1e-3, 0.05)


def test_a_future_over_a_stage_that_cannot_ramp_declines_to_estimate(make_future):
    # expectedDuration answers None for anything it cannot trust, and moveTimeout turns
    # that into "no deadline" -- a long wait, not a short one.
    fut = make_future([0, 0, 0], [1000, 0, 0], speed=1e-3, acceleration=0)

    assert fut.expectedDuration() is None
    assert fut.moveTimeout() is None


def test_speed_strings_resolve_against_the_device():
    stub = _StubStage([0, 0, 0], [1e-3] * 3, acceleration=0.05)
    assert stub.expectedMoveDuration(1e-3, "slow") == pytest.approx(
        stub.expectedMoveDuration(1e-3, stub.slowSpeed)
    )
    assert stub.expectedMoveDuration(1e-3, "fast") == pytest.approx(
        stub.expectedMoveDuration(1e-3, stub.fastSpeed)
    )


def test_a_speed_that_cannot_move_anything_is_refused():
    stub = _StubStage([0, 0, 0], [1e-3] * 3, acceleration=0.05)
    for bad in (0, -1e-3, None, float("nan")):
        with pytest.raises(ValueError):
            stub.expectedMoveDuration(1e-3, bad)


# ------------------------------------------------------------ MoveFuture integration


def test_expected_duration_scales_device_units_into_metres(make_future):
    # The same 2 mm move on a um-reporting stage and a mm-reporting one.
    in_um = make_future([0, 0, 0], [2000, 0, 0], speed=1e-3, scale=[1e-6] * 3)
    in_mm = make_future([0, 0, 0], [2, 0, 0], speed=1e-3, scale=[1e-3] * 3)
    assert in_um.expectedDuration() == pytest.approx(in_mm.expectedDuration())
    assert in_um.expectedDuration() == pytest.approx(
        in_um.dev.expectedMoveDuration(2e-3, 1e-3)
    )


def test_a_pure_d_move_on_a_four_axis_stage_is_measured(make_future):
    """The d axis carries the whole distance, and scale must reach far enough to see it.

    A 10 mm retraction of d alone at 10 um/s takes 1000 s. Measured against a scale with
    an entry per axis -- which Stage refuses to load without -- that is what comes back;
    against a 3-entry scale the d column falls off the end and the move scores zero
    distance, so waitForMove() would raise Timeout ten seconds into a healthy retraction.
    """
    fut = make_future(
        [0, 0, 0, 10000], [0, 0, 0, 0], speed=10e-6, scale=[1e-6] * 4, acceleration=1.0
    )

    duration = fut.expectedDuration()

    # Ramp time at 1 m/s^2 is 10 us, far below the 1000 s cruise.
    assert duration == pytest.approx(1000.0, rel=1e-4)
    assert fut.moveTimeout() == pytest.approx(3 * duration, rel=1e-4)


def test_negative_scale_is_a_direction_not_a_shorter_move(make_future):
    # An axis pointing along a negative global direction has a negative scale.
    forward = make_future([0, 0, 0], [0, 0, 100], speed=1e-3, scale=[1e-6, 1e-6, 1e-6])
    reversed_ = make_future([0, 0, 0], [0, 0, 100], speed=1e-3, scale=[1e-6, 1e-6, -1e-6])
    assert forward.expectedDuration() == pytest.approx(reversed_.expectedDuration())
    assert forward.expectedDuration() > 0


def test_an_axis_with_no_target_contributes_no_distance(make_future):
    # A partial move (MicroManagerStage moves only z, or only xy) carries None for the
    # axes it leaves alone; those must not turn into a NaN duration.
    partial = make_future([0, 0, 0], [None, None, 100], speed=1e-3)
    whole = make_future([0, 0, 0], [0, 0, 100], speed=1e-3)
    assert partial.expectedDuration() == pytest.approx(whole.expectedDuration())


def test_an_unresolved_speed_string_does_not_reach_the_arithmetic(make_future):
    # ThorlabsMFC1 hands 'fast' straight through to its future.
    fut = make_future([0, 0, 0], [0, 0, 1000], speed="fast")
    assert fut.expectedDuration() == pytest.approx(
        fut.dev.expectedMoveDuration(1e-3, fut.dev.fastSpeed)
    )


def test_a_pathless_future_declines_to_answer(make_future):
    # MovePathFuture calls the base initializer with pos=None; numpy stores that as a 0-d
    # nan.
    fut = make_future([0, 0, 0], None, speed=1e-3)
    assert fut.expectedDuration() is None
    assert fut.moveTimeout() is None


def test_positions_overwritten_with_plain_lists_still_work(make_future):
    # MockMoveFuture and MFC1MoveFuture reassign startPos/targetPos to lists after the
    # base initializer has turned them into arrays.
    fut = make_future([0, 0, 0], [0, 0, 100], speed=1e-3)
    expected = fut.expectedDuration()
    fut.startPos = [0, 0, 0]
    fut.targetPos = [0, 0, 100]
    assert fut.expectedDuration() == pytest.approx(expected)


def test_a_driver_speed_code_declines_to_answer(make_future):
    # SutterMPC200 stores an MPC200 speed table index, which is a number in no units.
    fut = make_future([0, 0, 0], [0, 0, 1000], speed=12)
    assert fut.expectedDuration() is not None
    fut.speedIsSI = False
    assert fut.expectedDuration() is None


def test_mpc200_futures_declare_their_speed_is_not_si():
    from acq4.devices.SutterMPC200.SutterMPC200 import MPC200MoveFuture

    assert MPC200MoveFuture.speedIsSI is False
    assert MoveFuture.speedIsSI is True


# ----------------------------------------------------------------- timeout policy


def test_timeout_is_the_margin_over_the_estimate_once_the_move_is_long():
    # 1 s of estimate, 3x margin, floor of 10 -- the margin only shows above the floor.
    assert MoveFuture.timeoutFor(1.0) == pytest.approx(MoveFuture.timeoutFloor)
    assert MoveFuture.timeoutFor(100.0) == pytest.approx(300.0)
    assert MoveFuture.timeoutFor(MoveFuture.timeoutFloor) == pytest.approx(
        MoveFuture.timeoutMargin * MoveFuture.timeoutFloor
    )


def test_the_floor_carries_short_moves():
    assert MoveFuture.timeoutFor(1e-3) == pytest.approx(MoveFuture.timeoutFloor)
    assert MoveFuture.timeoutFor(0.0) == pytest.approx(MoveFuture.timeoutFloor)


def test_an_unknowable_duration_means_no_deadline():
    assert MoveFuture.timeoutFor(None) is None


def test_move_timeout_composes_the_two(make_future):
    fut = make_future([0, 0, 0], [0, 0, 100000], speed=1e-3, scale=[1e-6] * 3)
    assert fut.moveTimeout() == pytest.approx(
        MoveFuture.timeoutFor(fut.expectedDuration())
    )
    assert fut.moveTimeout() > MoveFuture.timeoutFloor  # 100 mm at 1 mm/s


# -------------------------------------------------------- wait() semantics unchanged


def test_wait_with_no_timeout_still_means_forever(make_future):
    fut = make_future([0, 0, 0], [0, 0, 100], speed=1e-3)
    with pytest.raises(fut.Timeout):
        fut.wait(timeout=0.05)
    assert not fut.is_done

    # wait(None) blocks, so only "did not return or raise immediately" can be asserted.
    import threading

    returned = threading.Event()

    def waiter():
        try:
            fut.wait()
        except BaseException:
            pass
        returned.set()

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    assert not returned.wait(0.3), "wait(None) must not time out on its own"
    fut.resolve(None)
    assert returned.wait(2)


def test_wait_for_move_applies_the_auto_timeout(make_future):
    # 100 um at 1 mm/s with the stub's 0.05 m/s^2 ramp is a tenth of a second, so the
    # floor applies.
    fut = make_future([0, 0, 0], [0, 0, 100], speed=1e-3)
    assert fut.moveTimeout() == pytest.approx(MoveFuture.timeoutFloor)

    seen = {}

    def fake_wait(timeout=None, **kwds):
        seen["timeout"] = timeout
        return "waited"

    fut.wait = fake_wait
    assert fut.waitForMove() == "waited"
    assert seen["timeout"] == pytest.approx(MoveFuture.timeoutFloor)


def test_wait_for_move_waits_forever_when_it_cannot_estimate(make_future):
    fut = make_future([0, 0, 0], [0, 0, 100], speed=1e-3)
    fut.speedIsSI = False

    seen = {}

    def fake_wait(timeout=None, **kwds):
        seen["timeout"] = timeout

    fut.wait = fake_wait
    fut.waitForMove()
    assert seen["timeout"] is None
