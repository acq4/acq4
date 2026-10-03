"""Constant-velocity motion: :meth:`Stage.setVelocity` and the futures behind it.

Headless against :class:`MockStage`; no hardware and no real Manager. MockStage's thread
holds a velocity, so it stands in for a device with a velocity command of its own; the
``targeted`` fixture puts the base class's ``_setVelocity`` back, the distant-target path
used by every stage without one.

Velocities are in m/s along each axis throughout, as :meth:`Stage.setVelocity` takes them.
"""
from __future__ import annotations

import time
import types

import numpy as np
import pytest
from unittest.mock import patch

from acq4.devices.MockStage import MockStage
from acq4.devices.Stage.Stage import Stage, TargetedVelocityFuture, VelocityFuture
from acq4.panic import GlobalHalt
from acq4.util.task import Stopped

UM = 1e-6
MM = 1e-3
TIMEOUT = 5.0


class MockDM:
    """Just enough device manager to construct a :class:`MockStage`."""

    def __init__(self):
        self.globalHalt = GlobalHalt()

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return None

    def readConfigFile(self, fn):
        return {}


@pytest.fixture
def dm(qtbot):
    (qtbot,)  # qtbot only guarantees a QApplication exists
    return MockDM()


def makeStage(dm, **config):
    conf = {'driver': 'MockStage', 'nAxes': 3}
    conf.update(config)
    with patch("acq4.Manager.Manager.single") as single:
        single.return_value = dm
        dev = MockStage(dm, conf, 'VelStage')
    # MockStage.__init__ primes its monitor thread with a zero-distance _move(); retire
    # it so that no test mistakes it for motion it asked for.
    dev._lastMove.wait(timeout=TIMEOUT)
    return dev


@pytest.fixture
def native(dm):
    dev = makeStage(dm)
    yield dev
    dev.quit()


@pytest.fixture
def targeted(dm):
    dev = makeStage(dm)
    # Put the base class's implementation back: this device now has no velocity command
    # of its own and jogs by moving to the end of its travel.
    dev._setVelocity = types.MethodType(Stage._setVelocity, dev)
    yield dev
    dev.quit()


def waitFor(predicate, what, timeout=TIMEOUT):
    """Block until *predicate* is true, or fail the test saying what was waited for."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail(f"timed out waiting for {what}")


# --------------------------------------------------------------- where a velocity aims


class TestTheTarget:
    """A velocity becomes a point to aim at and a speed to get there."""

    def test_an_unlimited_axis_travels_the_jog_distance(self, native):
        native.maxJogDistance = 2 * MM
        target, _ = native._velocityTarget([0, 0, 100 * UM])
        assert np.allclose(target, [0, 0, 2 * MM])

    def test_the_speed_is_the_magnitude_of_the_velocity(self, native):
        _, speed = native._velocityTarget([0, 30 * UM, 40 * UM])
        assert speed == pytest.approx(50 * UM)

    def test_the_nearest_limit_wins(self, native):
        native._limits = [(-1 * MM, 1 * MM), (-10 * MM, 10 * MM), (None, None)]
        target, _ = native._velocityTarget([100 * UM, 100 * UM, 0])
        assert np.allclose(target, [1 * MM, 1 * MM, 0])

    def test_a_limit_already_reached_leaves_nowhere_to_go(self, native):
        native._limits = [(None, 0.0), (None, None), (None, None)]
        target, _ = native._velocityTarget([100 * UM, 0, 0])
        assert np.allclose(target, native.getPosition())

    def test_a_negative_scale_walks_the_device_coordinate_backwards(self, dm):
        """On a negative-scale axis, positive global travel drives the device coordinate down."""
        dev = makeStage(dm, scale=[1, 1, -1])
        try:
            dev.maxJogDistance = 2 * MM
            target, speed = dev._velocityTarget([0, 0, 100 * UM])
            assert np.allclose(target, [0, 0, -2 * MM])
            assert speed == pytest.approx(100 * UM)
        finally:
            dev.quit()

    def test_an_unscaled_axis_is_refused(self, dm):
        dev = makeStage(dm, scale=[1, 1, 0])
        try:
            with pytest.raises(ValueError):
                dev._velocityTarget([0, 0, 100 * UM])
        finally:
            dev.quit()


# --------------------------------------------------------------------- the task itself


class TestTheTask:
    """A jog is the stage's active motion task, and says where it is headed."""

    def test_a_velocity_is_the_stages_active_task(self, native):
        fut = native.setVelocity([0, 0, 100 * UM])
        assert isinstance(fut, VelocityFuture)
        assert native._activeTask is fut
        assert native.isMoving()
        waitFor(lambda: native.getPosition()[2] > 10 * UM, "the stage to travel")
        fut.stop()

    def test_the_target_is_the_end_of_travel(self, native):
        native._limits = [(None, None), (None, None), (-5 * MM, 5 * MM)]
        fut = native.setVelocity([0, 0, 100 * UM])
        assert native.targetPosition()[2] == pytest.approx(5 * MM)
        fut.stop()

    def test_the_target_returns_when_the_jog_ends(self, native):
        fut = native.setVelocity([0, 0, 100 * UM])
        fut.stop()
        waitFor(lambda: fut.is_done, "the jog to end")
        assert np.allclose(native.targetPosition(), native.getPosition())

    def test_a_missing_axis_stays_put(self, native):
        fut = native.setVelocity([None, None, 100 * UM])
        assert np.allclose(fut.velocity, [0, 0, 100 * UM])
        fut.stop()

    def test_it_declines_to_predict_a_duration(self, native):
        fut = native.setVelocity([0, 0, 100 * UM])
        assert fut.expectedDuration() is None
        assert fut.moveTimeout() is None
        fut.stop()


# ------------------------------------------------------------------------ one at a time


class TestReplacement:
    """Every velocity is a new task; the one it replaces is retired, not stopped."""

    def test_a_new_velocity_is_a_new_task(self, native):
        first = native.setVelocity([0, 0, 100 * UM])
        second = native.setVelocity([0, 0, -100 * UM])
        assert second is not first
        assert native._activeTask is second
        waitFor(lambda: first.is_done, "the replaced jog to be retired")
        with pytest.raises(Stopped):
            first.wait(timeout=TIMEOUT)
        waitFor(lambda: native.getPosition()[2] < 0, "the stage to reverse")
        second.stop()

    def test_replacing_a_velocity_does_not_stop_the_device(self, native):
        native.setVelocity([0, 0, 100 * UM])
        with patch.object(native, 'stop', wraps=native.stop) as stop:
            fut = native.setVelocity([0, 0, -100 * UM])
            assert stop.call_count == 0
        fut.stop()


class TestEnding:
    """Asking for motion and ending it are different requests."""

    def test_a_zero_velocity_is_refused(self, native):
        """Zero is refused, not read as a stop: setVelocity asks for motion."""
        with pytest.raises(ValueError):
            native.setVelocity([0, 0, 0])
        assert not native.isMoving()

    def test_stopping_the_jog_stops_the_stage(self, native):
        fut = native.setVelocity([0, 0, 100 * UM])
        waitFor(lambda: native.getPosition()[2] > 10 * UM, "the stage to travel")
        fut.stop()
        waitFor(lambda: fut.is_done, "the jog to end")
        assert not native.isMoving()
        settled = native.getPosition()
        time.sleep(0.05)
        assert np.allclose(native.getPosition(), settled)

    def test_stopvelocity_ends_the_jog(self, native):
        fut = native.setVelocity([0, 0, 100 * UM])
        assert native.stopVelocity() is True
        waitFor(lambda: fut.is_done, "the jog to end")
        assert not native.isMoving()

    def test_stopvelocity_with_nothing_running_says_so(self, native):
        assert native.stopVelocity() is False
        assert not native.isMoving()

    def test_a_move_taking_the_stage_ends_the_jog(self, native):
        jog = native.setVelocity([0, 0, 100 * UM])
        move = native.move([0, 0, 1 * MM], speed=50 * UM)
        assert native._activeTask is move
        waitFor(lambda: jog.is_done, "the jog to end")
        with pytest.raises(Stopped):
            jog.wait(timeout=TIMEOUT)
        move.stop()

    def test_stopping_an_ended_jog_leaves_the_new_owner_alone(self, native):
        """stop() on a completed future touches nothing."""
        jog = native.setVelocity([0, 0, 100 * UM])
        move = native.move([0, 0, 1 * MM], speed=50 * UM)
        assert native.stopVelocity() is False
        jog.stop()
        assert not move.is_done
        assert native._activeTask is move
        move.stop()


# ----------------------------------------------------------------- without a velocity command


class TestTheTargetedPath:
    """A stage with no velocity command of its own jogs toward the end of its travel."""

    def test_it_moves_the_stage(self, targeted):
        targeted._limits = [(None, None), (None, None), (-5 * MM, 5 * MM)]
        fut = targeted.setVelocity([0, 0, 500 * UM])
        assert isinstance(fut, TargetedVelocityFuture)
        assert targeted._activeTask is fut
        waitFor(lambda: targeted.getPosition()[2] > 50 * UM, "the stage to travel")
        fut.stop()

    def test_a_replacement_turns_the_stage_around(self, targeted):
        targeted._limits = [(None, None), (None, None), (-5 * MM, 5 * MM)]
        first = targeted.setVelocity([0, 0, 500 * UM])
        waitFor(lambda: targeted.getPosition()[2] > 20 * UM, "the stage to travel")
        second = targeted.setVelocity([0, 0, -500 * UM])
        assert second is not first
        assert targeted.targetPosition()[2] == pytest.approx(-5 * MM)
        waitFor(lambda: targeted.getPosition()[2] < 0, "the stage to reverse")
        assert not second.is_done, "the replaced jog's leg ended the new one"
        second.stop()

    def test_it_ends_at_the_end_of_travel(self, targeted):
        targeted._limits = [(None, None), (None, None), (None, 200 * UM)]
        fut = targeted.setVelocity([0, 0, 2 * MM])
        waitFor(lambda: fut.is_done, "the jog to reach the end of travel")
        fut.wait(timeout=TIMEOUT)  # arrived: not stopped, not failed
        assert targeted.getPosition()[2] == pytest.approx(200 * UM, abs=UM)
        assert not targeted.isMoving()

    def test_pushing_into_a_limit_ends_quietly(self, targeted):
        targeted._limits = [(None, None), (None, None), (None, 0.0)]
        fut = targeted.setVelocity([0, 0, 100 * UM])
        assert fut.is_done
        fut.wait(timeout=TIMEOUT)
