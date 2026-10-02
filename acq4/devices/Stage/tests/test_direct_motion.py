"""The direct-motion controller on :class:`~acq4.devices.Stage.Stage.Stage`.

Headless against :class:`MockStage`; no hardware and no real Manager. The subject is
:class:`~acq4.devices.Stage.direct_motion.DirectMotionController`: a burst of stepped
requests is one gesture, at most one direct move is ever outstanding, and a programmatic
move owns the stage.

Three conventions:

- Requests are fire-and-forget, so every test posts its requests and then calls
  ``waitUntilIdle()``. That is the only synchronisation these tests use: it returns once
  the control thread has decided about everything posted before it, which is exactly when
  the assertions below become meaningful. Nothing here sleeps or retries except where it
  is waiting for the stage to travel.
- The desired target is never published, so an assertion about what the stage is doing
  reads ``Stage.targetPosition()`` and an assertion about the gesture reads the
  controller's own state -- only ever after ``waitUntilIdle()``, when the thread that
  owns that state is parked on its queue.
- Collapsing is counted, not inferred. ``MoveSpy`` records every target the stage is
  handed, because a queueing implementation would also arrive in the right place.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from unittest.mock import patch

from acq4.devices.MockStage import MockStage
from acq4.panic import GlobalHalt
from acq4.util.task import Stopped

UM = 1e-6
MM = 1e-3

#: Slow enough that a few micrometres of travel is still comfortably in flight while a
#: test issues the rest of its burst.
CRAWL = 50 * UM

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
    # MockStage.__init__ primes its monitor thread with a zero-distance _move(); retire
    # it so that no test mistakes it for the move it just asked for.
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


def settled(controller):
    """Block until the controller has decided about everything asked of it so far."""
    assert controller.waitUntilIdle(TIMEOUT), "the direct motion thread never came back"


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
        assert stage.canRetargetInFlight is False

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


# --------------------------------------------------------------------------- ownership


class TestOwnership:
    """The controller tells its own motion from everyone else's by identity.

    The gate asks whether the stage's active task is the move this controller issued,
    so a move nobody can mistake for it -- a programmatic one, a path -- reads as
    somebody else holding the stage.
    """

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

        waitFor(lambda: not stage.isMoving(), "the stage to arrive")
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
        """The desired target is internal and is not published."""
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
    def test_every_request_is_issued_at_once(self, stage):
        stage.canRetargetInFlight = True
        controller = stage.directMotion
        spy = MoveSpy(stage)
        for _ in range(3):
            controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)

        assert len(spy.targets) == 3
        np.testing.assert_allclose(
            [t[0] for t in spy.targets], [5 * UM, 10 * UM, 15 * UM], atol=1e-12
        )

    def test_nothing_is_left_pending(self, stage):
        stage.canRetargetInFlight = True
        controller = stage.directMotion
        for _ in range(3):
            controller.requestDelta(0, 5 * UM, speed=CRAWL)
        settled(controller)

        assert controller._desired is None
        np.testing.assert_allclose(stage.targetPosition(), [15 * UM, 0, 0], atol=1e-12)

    def test_a_request_too_small_to_be_worth_it_is_held(self, stage):
        """Re-aiming costs a supersession, so a sliver of a correction waits instead.

        The second delta is a thousandth of what the first move has left to run, which
        is well under :data:`RETARGET_DIVERGENCE_FRACTION`, so the stage is left running
        the move it has and the collapse issues the rest.
        """
        stage.canRetargetInFlight = True
        controller = stage.directMotion
        spy = MoveSpy(stage)
        controller.requestDelta(0, 1 * MM, speed=CRAWL)
        controller.requestDelta(0, 1 * UM, speed=CRAWL)
        settled(controller)

        assert len(spy.targets) == 1
        np.testing.assert_allclose(controller._desired, [1 * MM + 1 * UM, 0, 0], atol=1e-12)
        stage._activeTask.stop()


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

        # move() supersedes the direct move inside the call, so the completion that
        # drops the gesture is already queued by the time this returns.
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
        """Silent on the control surface: no exception, no dialog, and the thread lives."""
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
