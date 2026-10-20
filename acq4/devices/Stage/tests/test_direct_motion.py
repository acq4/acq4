"""The direct-motion controller on :class:`~acq4.devices.Stage.direct_motion`.

Headless against :class:`MockStage`; no hardware and no real Manager. A burst of stepped
requests is one gesture, a continuous request is a jog held until the input ends it, at
most one of either is ever outstanding, and a programmatic move owns the stage.

Requests are fire-and-forget: ``waitUntilIdle()`` is the only synchronisation used here,
and returns once the control thread has decided about everything posted before it.
"""

from __future__ import annotations

import functools
import time

import numpy as np
import pytest
from unittest.mock import patch

from acq4.devices.MockStage import MockStage
from acq4.devices.Stage.Stage import Stage, VelocityFuture
from acq4.panic import GlobalHalt
from acq4.util.task import Stopped

UM = 1e-6
MM = 1e-3

#: Step speed, m/s: slow enough that a move is still in flight while the rest of a burst
#: is issued.
CRAWL = 50 * UM

#: Jog speed, m/s per axis: under a micrometre of travel between control-thread decisions.
JOG = 20 * UM

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


@pytest.fixture
def stage(dm):
    with patch("acq4.Manager.Manager.single") as single:
        single.return_value = dm
        dev = MockStage(dm, {'driver': 'MockStage', 'nAxes': 3}, 'DirectStage')
    # MockStage.__init__ primes its monitor thread with a zero-distance _move(); retire it.
    dev._lastMove.wait(timeout=TIMEOUT)
    yield dev
    dev.quit()


class MoveSpy:
    """Records the target of every move the stage is asked to make from now on."""

    def __init__(self, stage):
        self.targets = []
        self._real = stage.move
        stage.move = self._record

    def _record(self, position, **kwds):
        self.targets.append(np.asarray(position, dtype=float))
        return self._real(position, **kwds)


class VelocitySpy:
    """Records the velocity of every jog the stage is asked to run from now on."""

    def __init__(self, stage):
        self.velocities = []
        self._real = stage.setVelocity
        stage.setVelocity = self._record

    def _record(self, vel, **kwds):
        self.velocities.append(np.asarray(vel, dtype=float))
        return self._real(vel, **kwds)


def settled(controller):
    """Block until the controller has decided about everything asked of it so far."""
    assert controller.waitUntilIdle(TIMEOUT), "the direct motion thread never came back"


def arrived(stage, x):
    """Whether *stage* is at rest at *x* on axis 0."""
    return not stage.isMoving() and abs(stage.getPosition()[0] - x) < 1e-7


def waitFor(predicate, what, timeout=TIMEOUT):
    """Block until *predicate* is true, or fail the test saying what was waited for."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail(f"timed out waiting for {what}")


# --------------------------------------------------------------------------- the object


class TestTheController:
    def test_it_is_built_once_on_first_use(self, stage):
        assert stage.directMotion is stage.directMotion
        assert stage.directMotion.stage is stage

    def test_wait_and_collapse_is_the_default(self, stage):
        assert stage.retargetInterval == np.inf

    def test_its_thread_runs_until_the_stage_quits(self, stage):
        controller = stage.directMotion
        assert controller._thread.is_alive()
        stage.quit()
        assert not controller._thread.is_alive()

    def test_a_request_after_shutdown_is_ignored(self, stage):
        controller = stage.directMotion
        stage.quit()
        spy = MoveSpy(stage)
        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)
        assert spy.targets == []

    def test_shutdown_ends_a_jog(self, stage):
        controller = stage.directMotion
        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        jog = controller._inFlight
        waitFor(lambda: stage.getPosition()[0] > 5 * UM, "the stage to travel")

        controller.shutdown()

        assert jog.is_done
        assert not stage.isMoving()


# --------------------------------------------------------------------------- ownership


class TestOwnership:
    """The controller tells its own motion from everyone else's by identity."""

    def test_an_issued_move_is_the_stages_active_task(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 5 * MM, speed=CRAWL)
        settled(controller)
        fut = stage._activeTask
        try:
            assert fut is not None and not fut.is_done
            assert fut is controller._inFlight
        finally:
            fut.stop()

    def test_a_programmatic_move_is_not_the_controllers(self, stage):
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        try:
            assert fut is stage._activeTask
            assert fut is not stage.directMotion._inFlight
        finally:
            fut.stop()

    def test_a_path_is_not_the_controllers(self, stage):
        path = [{'position': [200 * UM, 0, 0], 'speed': CRAWL}]
        pathFut = stage.movePath(path, name='one-leg path')
        try:
            assert pathFut is not stage.directMotion._inFlight
        finally:
            pathFut.stop()


# --------------------------------------------------------------------------- stepped


class TestWaitAndCollapse:
    def test_a_burst_of_detents_becomes_two_moves_not_five(self, stage):
        controller = stage.directMotion
        spy = MoveSpy(stage)
        for _ in range(5):
            controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)

        assert len(spy.targets) == 1, "the burst queued instead of collapsing"
        np.testing.assert_allclose(spy.targets[0], [5 * UM, 0, 0], atol=1e-12)

        waitFor(lambda: len(spy.targets) > 1, "the collapsed remainder to be issued")
        np.testing.assert_allclose(spy.targets[1], [25 * UM, 0, 0], atol=1e-9)

        waitFor(lambda: arrived(stage, 25 * UM), "the stage to arrive")
        assert len(spy.targets) == 2
        np.testing.assert_allclose(stage.getPosition(), [25 * UM, 0, 0], atol=1e-7)

    def test_no_detent_is_lost(self, stage):
        controller = stage.directMotion
        for _ in range(4):
            controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)
        waitFor(
            lambda: not stage.isMoving() and controller._desired is None,
            "the gesture to finish",
        )
        np.testing.assert_allclose(stage.getPosition(), [20 * UM, 0, 0], atol=1e-7)

    def test_the_gesture_survives_a_move_boundary(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        controller.requestDelta(0, 20 * UM, speed=CRAWL)
        settled(controller)

        assert controller._desired is not None, "the second request was thrown away"
        waitFor(
            lambda: abs(stage.targetPosition()[0] - 25 * UM) < 1e-9,
            "the accumulated target to be issued once the first move landed",
        )
        waitFor(lambda: not stage.isMoving(), "the stage to arrive")
        np.testing.assert_allclose(stage.getPosition(), [25 * UM, 0, 0], atol=1e-7)

    def test_the_stage_shows_the_move_in_flight_not_the_gesture(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        controller.requestDelta(0, 495 * UM, speed=CRAWL)
        settled(controller)

        np.testing.assert_allclose(stage.targetPosition(), [5 * UM, 0, 0], atol=1e-12)
        np.testing.assert_allclose(controller._desired, [500 * UM, 0, 0], atol=1e-12)

    def test_a_delta_counts_from_the_gesture_not_from_the_stage(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)
        np.testing.assert_allclose(controller._desired, [10 * UM, 0, 0], atol=1e-12)

    def test_a_stopped_move_ends_the_gesture(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 500 * UM, speed=CRAWL)
        controller.requestDelta(0, 400 * UM, speed=CRAWL)
        settled(controller)
        fut = stage._activeTask

        fut.stop()
        settled(controller)

        assert controller._desired is None, "a stop must stop"
        with pytest.raises(Stopped):
            fut.wait(timeout=TIMEOUT)
        assert not stage.isMoving()


class TestRetargetInFlight:
    """A stage with a finite :attr:`Stage.retargetInterval` is re-aimed mid-move, paced."""

    INTERVAL = 0.2

    def test_the_first_detent_is_issued_at_once_and_the_rest_held(self, stage):
        stage.retargetInterval = self.INTERVAL
        controller = stage.directMotion
        spy = MoveSpy(stage)
        for _ in range(3):
            controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)

        assert len(spy.targets) == 1
        np.testing.assert_allclose(spy.targets[0], [5 * UM, 0, 0], atol=1e-12)
        np.testing.assert_allclose(controller._desired, [15 * UM, 0, 0], atol=1e-12)
        stage._activeTask.stop()

    def test_the_held_detents_re_aim_the_move_after_the_interval(self, stage):
        stage.retargetInterval = self.INTERVAL
        controller = stage.directMotion
        spy = MoveSpy(stage)
        start = time.monotonic()
        for _ in range(3):
            controller.requestDelta(0, 20 * UM, speed=CRAWL)  # first move outlasts INTERVAL
        waitFor(lambda: len(spy.targets) == 2, "the held detents to be issued")

        assert time.monotonic() - start >= self.INTERVAL * 0.9
        np.testing.assert_allclose(spy.targets[1], [60 * UM, 0, 0], atol=1e-12)
        assert controller._desired is None
        waitFor(lambda: arrived(stage, 60 * UM), "the stage to arrive")
        assert len(spy.targets) == 2

    def test_the_last_detents_of_a_burst_are_not_lost(self, stage):
        stage.retargetInterval = self.INTERVAL
        controller = stage.directMotion
        spy = MoveSpy(stage)
        for _ in range(10):
            controller.requestDelta(0, 5 * UM, speed=CRAWL)
            time.sleep(0.03)
        waitFor(lambda: arrived(stage, 50 * UM), "the gesture to finish")

        assert len(spy.targets) < 10, "the burst was not paced"
        np.testing.assert_allclose(stage.getPosition(), [50 * UM, 0, 0], atol=1e-7)

    def test_detents_that_cancel_out_issue_nothing(self, stage):
        stage.retargetInterval = self.INTERVAL
        controller = stage.directMotion
        spy = MoveSpy(stage)
        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        for d in (5, 5, -5, -5):
            controller.requestDelta(0, d * UM, speed=CRAWL)
        time.sleep(self.INTERVAL * 1.5)
        settled(controller)

        assert len(spy.targets) == 1
        assert controller._desired is None

    def test_a_held_target_is_issued_when_the_move_lands_first(self, stage):
        stage.retargetInterval = 60.0
        controller = stage.directMotion
        spy = MoveSpy(stage)
        controller.requestDelta(0, 5 * UM, speed='fast')
        controller.requestDelta(0, 5 * UM, speed='fast')
        waitFor(lambda: len(spy.targets) == 2, "the held target to be issued on arrival")
        np.testing.assert_allclose(spy.targets[1], [10 * UM, 0, 0], atol=1e-12)
        waitFor(lambda: not stage.isMoving(), "the stage to arrive")


# --------------------------------------------------------------------------- the gate


class TestProgrammaticMoveOwnsTheStage:
    def test_a_request_during_a_programmatic_move_is_a_no_op(self, stage):
        programmatic = stage.move([500 * UM, 0, 0], speed=CRAWL)
        controller = stage.directMotion
        spy = MoveSpy(stage)

        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)

        assert spy.targets == [], "a knob turn reached the stage during a programmatic move"
        assert controller._desired is None
        assert stage._activeTask is programmatic
        np.testing.assert_allclose(stage.targetPosition(), [500 * UM, 0, 0], atol=1e-12)
        programmatic.stop()

    def test_a_request_during_a_path_is_a_no_op(self, stage):
        path = [
            {'position': [200 * UM, 0, 0], 'speed': CRAWL},
            {'position': [200 * UM, 200 * UM, 0], 'speed': CRAWL},
        ]
        pathFut = stage.movePath(path, name='two-leg path')
        controller = stage.directMotion
        spy = MoveSpy(stage)
        try:
            controller.requestDelta(2, 5 * UM, speed=CRAWL)
            settled(controller)
            assert spy.targets == []
            assert controller._desired is None
            np.testing.assert_allclose(
                stage.targetPosition(), [200 * UM, 200 * UM, 0], atol=1e-12
            )
        finally:
            pathFut.stop()

    def test_the_gate_lifts_when_the_programmatic_move_ends(self, stage):
        stage.move([25 * UM, 0, 0], speed='fast').wait(timeout=TIMEOUT)
        controller = stage.directMotion

        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)

        assert controller._inFlight is stage._activeTask
        np.testing.assert_allclose(stage.targetPosition(), [30 * UM, 0, 0], atol=1e-7)
        stage._activeTask.stop()

    def test_a_programmatic_move_drops_the_gesture(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        controller.requestDelta(0, 895 * UM, speed=CRAWL)
        settled(controller)
        direct = stage._activeTask
        assert controller._desired is not None

        # move() supersedes inside the call, so the completion is queued before it returns.
        programmatic = stage.move([100 * UM, 0, 0], speed='fast')
        settled(controller)

        assert controller._desired is None, "the gesture fought the programmatic move"
        with pytest.raises(Exception):
            direct.wait(timeout=TIMEOUT)

        spy = MoveSpy(stage)
        programmatic.wait(timeout=TIMEOUT)
        settled(controller)
        assert spy.targets == [], "the dropped gesture was issued after the move"
        np.testing.assert_allclose(stage.getPosition(), [100 * UM, 0, 0], atol=1e-7)


# --------------------------------------------------------------------------- refusal


class TestRefusedFromBelow:
    def test_a_request_past_a_limit_leaves_nothing_pending(self, stage):
        stage.setLimits(x=(-1 * MM, 1 * MM))
        controller = stage.directMotion

        controller.requestDelta(0, 50 * MM, speed=CRAWL)
        settled(controller)

        assert controller._desired is None
        assert not stage.isMoving()
        np.testing.assert_allclose(stage.targetPosition(), stage.getPosition(), atol=1e-12)

    def test_a_request_refused_by_the_panic_lock_leaves_nothing_pending(self, stage, dm):
        dm.globalHalt.halt("nothing moves while halted")
        controller = stage.directMotion

        controller.requestDelta(0, 5 * MM, speed=CRAWL)
        settled(controller)

        assert controller._desired is None
        assert not stage.isMoving()
        np.testing.assert_allclose(stage.getPosition(), [0, 0, 0], atol=1e-12)

    def test_a_refusal_does_not_reach_the_caller(self, stage, dm):
        dm.globalHalt.halt("nothing moves while halted")
        controller = stage.directMotion
        controller.requestDelta(0, 5 * UM, speed=CRAWL)  # must not raise
        settled(controller)
        assert controller._thread.is_alive()

    def test_a_gesture_that_walks_past_a_limit_is_dropped_at_the_collapse(self, stage):
        stage.setLimits(x=(-1 * MM, 50 * UM))
        controller = stage.directMotion
        controller.requestDelta(0, 25 * UM, speed=CRAWL)
        controller.requestDelta(0, 475 * UM, speed=CRAWL)
        settled(controller)

        waitFor(
            lambda: controller._desired is None and not stage.isMoving(),
            "the collapse to be refused",
        )
        np.testing.assert_allclose(stage.getPosition(), [25 * UM, 0, 0], atol=1e-7)
        np.testing.assert_allclose(stage.targetPosition(), stage.getPosition(), atol=1e-12)


# --------------------------------------------------------------------------- axis names


class TestAxisNaming:
    def test_a_delta_may_name_its_axis(self, stage):
        controller = stage.directMotion
        controller.requestDelta('z', 5 * UM, speed=CRAWL)
        settled(controller)
        np.testing.assert_allclose(stage.targetPosition(), [0, 0, 5 * UM], atol=1e-12)
        stage._activeTask.stop()

    def test_an_unknown_axis_name_is_an_error_at_the_call_site(self, stage):
        with pytest.raises(ValueError):
            stage.directMotion.requestDelta('w', 5 * UM, speed=CRAWL)


# -------------------------------------------------------------------------- continuous


class TestContinuousMotion:
    """A velocity request is a jog on the stage, held until the input ends it."""

    def test_a_velocity_becomes_a_jog(self, stage):
        controller = stage.directMotion
        controller.requestVelocity([JOG, 0, 0])
        settled(controller)

        jog = stage._activeTask
        assert isinstance(jog, VelocityFuture)
        assert jog is controller._inFlight
        assert controller._desiredVelocity is None, "the issued velocity stayed pending"
        np.testing.assert_allclose(jog.velocity, [JOG, 0, 0], atol=1e-12)
        waitFor(lambda: stage.getPosition()[0] > 5 * UM, "the stage to travel")
        jog.stop()

    def test_a_zero_ends_the_jog(self, stage):
        controller = stage.directMotion
        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        jog = controller._inFlight
        waitFor(lambda: stage.getPosition()[0] > 5 * UM, "the stage to travel")

        controller.requestVelocity([0, 0, 0])
        settled(controller)

        assert jog.is_done
        assert controller._inFlight is None
        assert controller._desiredVelocity is None
        assert not stage.isMoving()
        stopped = stage.getPosition()
        time.sleep(0.05)
        np.testing.assert_allclose(stage.getPosition(), stopped, atol=1e-12)

    def test_an_all_none_velocity_ends_the_jog(self, stage):
        controller = stage.directMotion
        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        jog = controller._inFlight

        controller.requestVelocity([None, None, None])
        settled(controller)

        assert jog.is_done
        assert not stage.isMoving()

    def test_the_same_velocity_twice_does_not_recommand_the_stage(self, stage):
        controller = stage.directMotion
        spy = VelocitySpy(stage)
        for _ in range(3):
            controller.requestVelocity([JOG, 0, 0])
        settled(controller)

        assert len(spy.velocities) == 1, "a repeated reading restarted the jog"
        assert controller._desiredVelocity is None
        controller.requestVelocity([0, 0, 0])
        settled(controller)

    def test_a_new_velocity_re_aims_the_jog(self, stage):
        controller = stage.directMotion
        spy = VelocitySpy(stage)
        for v in (JOG, 2 * JOG, -JOG):
            controller.requestVelocity([v, 0, 0])
        settled(controller)

        assert len(spy.velocities) == 3
        jog = controller._inFlight
        assert jog is stage._activeTask and not jog.is_done
        np.testing.assert_allclose(jog.velocity, [-JOG, 0, 0], atol=1e-12)
        assert controller._desiredVelocity is None
        jog.stop()

    def test_a_velocity_refused_by_the_panic_lock_leaves_nothing_pending(self, stage, dm):
        dm.globalHalt.halt("nothing moves while halted")
        controller = stage.directMotion

        controller.requestVelocity([JOG, 0, 0])  # must not raise
        settled(controller)

        assert controller._desiredVelocity is None
        assert controller._inFlight is None
        assert not stage.isMoving()
        assert controller._thread.is_alive()

    def test_a_velocity_after_shutdown_is_ignored(self, stage):
        controller = stage.directMotion
        stage.quit()
        spy = VelocitySpy(stage)
        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        assert spy.velocities == []


# ------------------------------------------------------------------- the gate on a jog


class TestTheGateOnAVelocity:
    """A programmatic task owns the stage, and a velocity asked for meanwhile is lost."""

    def test_a_velocity_during_a_programmatic_move_is_a_no_op(self, stage):
        programmatic = stage.move([500 * UM, 0, 0], speed=CRAWL)
        controller = stage.directMotion
        spy = VelocitySpy(stage)

        controller.requestVelocity([0, 0, JOG])
        settled(controller)

        assert spy.velocities == [], "a jog reached the stage during a programmatic move"
        assert stage._activeTask is programmatic
        assert controller._inFlight is None
        assert controller._desiredVelocity is None, "the velocity was kept for later"
        programmatic.stop()

    def test_a_velocity_refused_during_a_move_does_not_start_when_it_ends(self, stage):
        programmatic = stage.move([500 * UM, 0, 0], speed=CRAWL)
        controller = stage.directMotion
        controller.requestVelocity([0, 0, JOG])
        settled(controller)

        programmatic.stop()
        waitFor(lambda: not stage.isMoving(), "the move to end")
        settled(controller)

        assert controller._inFlight is None
        assert controller._desiredVelocity is None
        assert not stage.isMoving()

    def test_a_programmatic_move_taking_the_stage_ends_the_jog(self, stage):
        controller = stage.directMotion
        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        jog = controller._inFlight

        programmatic = stage.move([0, 500 * UM, 0], speed=CRAWL)
        settled(controller)

        assert jog.is_done
        assert stage._activeTask is programmatic
        assert controller._inFlight is None
        assert controller._desiredVelocity is None
        programmatic.stop()


# ------------------------------------------------------------------ one kind at a time


class TestSwitchingKinds:
    """A request of either kind ends what the other has in progress."""

    def test_a_velocity_takes_over_from_a_stepped_gesture(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 500 * UM, speed=CRAWL)
        controller.requestDelta(0, 400 * UM, speed=CRAWL)
        settled(controller)
        move = controller._inFlight
        assert controller._desired is not None, "the stepped gesture never got going"

        controller.requestVelocity([0, 0, JOG])
        settled(controller)

        assert controller._desired is None, "the stepped gesture outlived the velocity"
        assert controller._desiredVelocity is None
        jog = controller._inFlight
        assert isinstance(jog, VelocityFuture)
        assert stage._activeTask is jog
        waitFor(lambda: move.is_done, "the stepped move to end")
        jog.stop()

    def test_a_delta_takes_over_from_a_jog(self, stage):
        controller = stage.directMotion
        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        jog = controller._inFlight
        waitFor(lambda: stage.getPosition()[0] > 5 * UM, "the stage to travel")
        here = stage.getPosition()[0]

        controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)

        assert jog.is_done
        assert controller._desiredVelocity is None
        move = controller._inFlight
        assert move is stage._activeTask
        assert not isinstance(move, VelocityFuture)
        # The step counts from where the jog stopped, not from its end-of-travel target.
        assert stage.targetPosition()[0] == pytest.approx(here + 5 * UM, abs=10 * UM)
        move.stop()

    def test_a_release_during_a_stepped_gesture_leaves_it_alone(self, stage):
        controller = stage.directMotion
        controller.requestDelta(0, 500 * UM, speed=CRAWL)
        controller.requestDelta(0, 400 * UM, speed=CRAWL)
        settled(controller)

        controller.requestVelocity([0, 0, 0])
        settled(controller)

        assert controller._desired is not None, "a stick at rest ended the stepped gesture"
        assert stage._activeTask is controller._inFlight
        stage._activeTask.stop()


# ------------------------------------------------------------------- a stop that fails


def useBaseVelocityPath(stage):
    """Drive this stage's jogs through :class:`TargetedVelocityFuture`.

    :class:`MockStage` overrides ``_setVelocity`` to drive its simulator thread at a
    velocity directly, which never builds the future whose ``stop()`` reaches
    ``dev.stop()``. The base-class path is what every real device uses, and it is the
    one the stop ordering lives on.
    """
    stage._setVelocity = functools.partial(Stage._setVelocity, stage)


class StopThatFails:
    """Makes the device-level halt raise for its first *count* calls, as a comms glitch does."""

    def __init__(self, stage, count=1):
        self.calls = 0
        self.count = count
        self._stage = stage
        self._real = stage.stop
        stage.stop = self._stop

    def _stop(self, reason=None):
        self.calls += 1
        if self.calls <= self.count:
            raise IOError("the controller did not answer")
        return self._real(reason)

    def restore(self):
        self._stage.stop = self._real


@pytest.fixture
def failingStop():
    """Makes a stage's halt raise, and puts the real one back before the stage is quit."""
    patched = []

    def fail(stage, count=1):
        patched.append(StopThatFails(stage, count))
        return patched[-1]

    yield fail
    for spy in patched:
        spy.restore()


def stillTravelling(stage, samples=3, interval=0.05):
    """Whether *stage*'s reported position is still changing."""
    seen = [np.asarray(stage.getPosition(), dtype=float)]
    for _ in range(samples):
        time.sleep(interval)
        seen.append(np.asarray(stage.getPosition(), dtype=float))
    return any(not np.allclose(a, b, atol=1e-9) for a, b in zip(seen, seen[1:]))


class TestAFailedHardwareStop:
    """A driver that refuses a stop must not leave the stage travelling unwatched.

    A jog is aimed at the end of travel, so nothing else ever ends it: if the controller
    forgets it before the stage has taken the stop, the one refusal is final and the
    stage keeps going with ACQ4 reporting it stopped.
    """

    def test_the_stage_stops_even_though_the_first_stop_raised(self, stage, failingStop):
        useBaseVelocityPath(stage)
        controller = stage.directMotion
        failures = failingStop(stage, count=1)

        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        waitFor(lambda: stage.getPosition()[0] > 2 * UM, "the jog to start travelling")

        controller.requestVelocity([0, 0, 0])
        settled(controller)

        waitFor(lambda: not stillTravelling(stage), "the stage to stop after the retry")
        assert failures.calls > 1, "the refused stop was never retried"

    def test_the_jog_is_not_forgotten_while_the_stop_keeps_failing(self, stage, failingStop):
        useBaseVelocityPath(stage)
        controller = stage.directMotion
        failingStop(stage, count=10_000)

        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        jog = controller._inFlight

        controller.requestVelocity([0, 0, 0])
        settled(controller)

        assert controller._inFlight is jog, (
            "the controller forgot a jog it had not managed to stop"
        )

    def test_it_gives_up_loudly_rather_than_retrying_for_ever(self, stage, failingStop):
        useBaseVelocityPath(stage)
        controller = stage.directMotion
        controller.stopRetryInterval = 0.0
        failures = failingStop(stage, count=10_000)
        errors = []
        stage.logger.error = lambda *args, **kwds: errors.append(args)

        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        controller.requestVelocity([0, 0, 0])

        waitFor(lambda: errors, "the controller to report that it could not stop the stage")
        assert failures.calls >= controller.stopRetryLimit
        waitFor(lambda: controller._inFlight is None, "the controller to give up")

    def test_a_new_velocity_supersedes_a_stop_that_was_still_failing(self, stage, failingStop):
        useBaseVelocityPath(stage)
        controller = stage.directMotion
        failingStop(stage, count=1)

        controller.requestVelocity([JOG, 0, 0])
        settled(controller)
        controller.requestVelocity([0, 0, 0])
        settled(controller)
        controller.requestVelocity([0, 0, JOG])
        settled(controller)

        jog = controller._inFlight
        assert isinstance(jog, VelocityFuture)
        assert stage._activeTask is jog and not jog.is_done
        np.testing.assert_allclose(jog.velocity, [0, 0, JOG], atol=1e-12)
        assert controller._stopRetryAt is None, "the new jog inherited the old stop retry"
        jog.stop()
