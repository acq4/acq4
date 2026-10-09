"""The commanded target on :class:`~acq4.devices.Stage.Stage.Stage`.

Headless against :class:`MockStage`; no hardware and no real Manager.
:meth:`Stage.targetPosition` is where the active motion task was commanded to go while one
is in progress, and the current position whenever none is.

``sigTargetChanged`` is connected with an explicit ``DirectConnection`` throughout: target
changes originate on the mock's hardware thread, and queued delivery would race the event
loop.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from unittest.mock import patch

from acq4.devices.MockStage import MockStage
from acq4.panic import GlobalHalt, GlobalHaltException
from acq4.util import Qt
from acq4.util.task import Stopped

UM = 1e-6
MM = 1e-3

#: Move speed, m/s: slow enough that a move is still in flight while a test inspects it.
CRAWL = 500 * UM

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
        dev = MockStage(dm, {'driver': 'MockStage', 'nAxes': 3}, 'TargetStage')
    # MockStage.__init__ primes its monitor thread with a zero-distance _move(); retire it.
    dev._lastMove.wait(timeout=TIMEOUT)
    yield dev
    dev.quit()


class TargetSpy:
    """Records every ``sigTargetChanged`` emission, synchronously on the emitting thread."""

    def __init__(self, dev):
        self.dev = dev
        self.targets = []
        dev.sigTargetChanged.connect(self._changed, type=Qt.Qt.DirectConnection)

    def _changed(self, dev, target):
        assert dev is self.dev
        self.targets.append(np.array(target))

    def disconnect(self):
        self.dev.sigTargetChanged.disconnect(self._changed)


def waitFor(predicate, what, timeout=TIMEOUT):
    """Block until *predicate* is true, or fail the test saying what was waited for."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail(f"timed out waiting for {what}")


def freezeHardware(stage):
    """Stop the mock's motion without completing its move, and return where it stopped.

    After this the stage reports no further positions.
    """
    stage.stageThread.stop()
    return np.array(stage.getPosition(), dtype=float)


# --------------------------------------------------------------------------- idle


class TestIdle:
    def test_a_stage_that_has_never_moved_targets_its_own_position(self, stage):
        np.testing.assert_allclose(stage.targetPosition(), stage.getPosition(), atol=1e-12)

    def test_there_is_no_no_target_state(self, stage):
        assert stage.targetPosition() is not None
        assert stage.globalTargetPosition() is not None

    def test_the_target_is_a_copy_the_caller_may_accumulate_into(self, stage):
        target = stage.targetPosition()
        target[0] += 1 * MM
        np.testing.assert_allclose(stage.targetPosition()[0], 0, atol=1e-12)

    def test_an_idle_position_update_moves_the_target_with_it(self, stage):
        spy = TargetSpy(stage)
        stage.posChanged([1 * MM, 2 * MM, 3 * MM])
        np.testing.assert_allclose(stage.targetPosition(), [1 * MM, 2 * MM, 3 * MM], atol=1e-12)
        assert len(spy.targets) == 1

    def test_an_idle_update_to_the_same_position_announces_nothing(self, stage):
        stage.posChanged([1 * MM, 0, 0])
        spy = TargetSpy(stage)
        stage.posChanged([1 * MM, 0, 0])
        assert spy.targets == [], "an unchanged target was re-announced"

    def test_motion_the_stage_did_not_command_drags_the_target_along(self, stage):
        # Straight at the mock hardware, past move() and setVelocity(), so no motion task
        # exists -- what a manual controller looks like from here.
        stage.stageThread.setVelocity(np.array([200 * UM, 0, 0]))
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the jog to travel")
        stage.stageThread.stop()
        assert not stage.isMoving()
        np.testing.assert_allclose(stage.targetPosition(), stage.getPosition(), atol=1e-12)


# --------------------------------------------------------------------------- commanded


class TestCommandedMove:
    def test_the_target_is_held_while_the_move_runs(self, stage):
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        np.testing.assert_allclose(stage.targetPosition(), [5 * MM, 0, 0], atol=1e-12)

        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        assert stage.getPosition()[0] < 5 * MM, "the move finished before it was inspected"
        np.testing.assert_allclose(stage.targetPosition(), [5 * MM, 0, 0], atol=1e-12)

        fut.stop()

    def test_commanding_a_move_announces_the_target_once(self, stage):
        spy = TargetSpy(stage)
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        assert len(spy.targets) == 1
        np.testing.assert_allclose(spy.targets[0], [5 * MM, 0, 0], atol=1e-12)
        fut.stop()

    def test_a_partial_move_commands_the_axes_it_leaves_alone_where_they_are(self, stage):
        stage.posChanged([1 * MM, 2 * MM, 3 * MM])
        fut = stage.move([None, None, 4 * MM], speed=CRAWL)
        np.testing.assert_allclose(stage.targetPosition(), [1 * MM, 2 * MM, 4 * MM], atol=1e-9)
        fut.stop()

    def test_a_refused_move_leaves_the_target_alone(self, stage):
        stage.setLimits(x=(-1 * MM, 1 * MM))
        stage.posChanged([0, 0, 0])
        spy = TargetSpy(stage)
        with pytest.raises(ValueError):
            stage.move([50 * MM, 0, 0], speed=CRAWL)
        np.testing.assert_allclose(stage.targetPosition(), [0, 0, 0], atol=1e-12)
        assert spy.targets == []

    def test_a_move_refused_by_the_panic_lock_leaves_the_target_alone(self, stage, dm):
        dm.globalHalt.halt("target must not move while halted")
        spy = TargetSpy(stage)
        with pytest.raises(GlobalHaltException):
            stage.move([5 * MM, 0, 0], speed=CRAWL)
        np.testing.assert_allclose(stage.targetPosition(), [0, 0, 0], atol=1e-12)
        assert spy.targets == []

    def test_a_second_move_takes_the_target_from_the_first(self, stage):
        first = stage.move([5 * MM, 0, 0], speed=CRAWL)
        second = stage.move([0, 5 * MM, 0], speed=CRAWL)
        np.testing.assert_allclose(stage.targetPosition(), [0, 5 * MM, 0], atol=1e-12)

        # The superseded move no longer owns the target; identity decides that, not
        # coordinates.
        with pytest.raises(Exception):
            first.wait(timeout=TIMEOUT)
        np.testing.assert_allclose(stage.targetPosition(), [0, 5 * MM, 0], atol=1e-12)
        second.stop()


# --------------------------------------------------------------------------- arrival


class TestArrival:
    def test_arriving_leaves_the_target_where_the_stage_stopped(self, stage):
        fut = stage.move([100 * UM, 0, 0], speed=CRAWL)
        fut.wait(timeout=TIMEOUT)
        np.testing.assert_allclose(stage.targetPosition(), stage.getPosition(), atol=1e-12)
        np.testing.assert_allclose(stage.targetPosition(), [100 * UM, 0, 0], atol=1e-9)

    def test_a_successful_completion_collapses_the_target_onto_the_position(self, stage):
        """The stage is frozen short of its target and the move then completes, as a
        driver reporting arrival within its own tolerance would leave it."""
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        stopped = freezeHardware(stage)
        spy = TargetSpy(stage)

        fut.resolve(None)

        assert stopped[0] < 1 * MM, "the stage was not still short of its target"
        np.testing.assert_allclose(stage.targetPosition(), stopped, atol=1e-12)
        assert len(spy.targets) == 1
        np.testing.assert_allclose(spy.targets[0], stopped, atol=1e-12)

    def test_an_idle_update_after_a_move_keeps_the_target_on_the_position(self, stage):
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        stopped = freezeHardware(stage)
        fut.resolve(None)

        stage.posChanged(stopped + 1 * UM)
        np.testing.assert_allclose(stage.targetPosition(), stopped + 1 * UM, atol=1e-12)


# --------------------------------------------------------------------------- stopping


class TestEndingWithoutArriving:
    """Every stop resets the target, without waiting for a position update.

    The hardware is frozen first in each case, so no position report is left to arrive.
    """

    def test_a_cooperative_stop_resets_the_target(self, stage):
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        stopped = freezeHardware(stage)
        spy = TargetSpy(stage)

        fut.stop()

        np.testing.assert_allclose(stage.targetPosition(), stopped, atol=1e-12)
        assert len(spy.targets) == 1
        with pytest.raises(Stopped):
            fut.wait(timeout=TIMEOUT)

    def test_an_abort_resets_the_target(self, stage):
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        stopped = freezeHardware(stage)

        stage.abort()

        np.testing.assert_allclose(stage.targetPosition(), stopped, atol=1e-12)
        with pytest.raises(RuntimeError):
            fut.wait(timeout=TIMEOUT)

    def test_a_driver_failure_resets_the_target(self, stage):
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        stopped = freezeHardware(stage)

        fut.fail(RuntimeError("the controller fell over"))

        np.testing.assert_allclose(stage.targetPosition(), stopped, atol=1e-12)

    def test_a_panic_lock_halt_resets_the_target(self, stage, dm):
        fut = stage.move([5 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the move to travel")
        stopped = freezeHardware(stage)

        dm.globalHalt.halt("panic mid-move")

        np.testing.assert_allclose(stage.targetPosition(), stopped, atol=1e-12)
        with pytest.raises(GlobalHaltException):
            fut.wait(timeout=TIMEOUT)

    def test_a_distant_target_does_not_outlive_the_move_that_set_it(self, stage):
        fut = stage.move([50 * MM, 0, 0], speed=CRAWL)
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the jog to travel")
        stopped = freezeHardware(stage)
        fut.stop()

        nextStep = stage.targetPosition()
        nextStep[0] += 5 * UM
        assert abs(nextStep[0] - stopped[0]) < 10 * UM


# --------------------------------------------------------------------------- paths


class TestPath:
    PATH = [
        {'position': [200 * UM, 0, 0], 'speed': CRAWL, 'explanation': 'first leg'},
        {'position': [200 * UM, 200 * UM, 0], 'speed': CRAWL, 'explanation': 'second leg'},
        {'position': [200 * UM, 200 * UM, 100 * UM], 'speed': CRAWL, 'explanation': 'third leg'},
    ]
    ENDPOINT = [200 * UM, 200 * UM, 100 * UM]

    def test_a_path_commands_its_endpoint_from_the_start(self, stage):
        pathFut = stage.movePath(self.PATH, name='three-leg path')
        try:
            np.testing.assert_allclose(stage.targetPosition(), self.ENDPOINT, atol=1e-12)
        finally:
            pathFut.stop()

    def test_a_path_is_one_move_with_one_target(self, stage):
        """No per-waypoint targets, and no collapse in the gaps between waypoints."""
        spy = TargetSpy(stage)
        pathFut = stage.movePath(self.PATH, name='three-leg path')
        try:
            waitFor(lambda: pathFut.currentStep >= 2, "the path to cross into its second leg")
            assert stage.isMoving()
            assert len(spy.targets) == 1, [list(t) for t in spy.targets]
            np.testing.assert_allclose(spy.targets[0], self.ENDPOINT, atol=1e-12)
            np.testing.assert_allclose(stage.targetPosition(), self.ENDPOINT, atol=1e-12)
        finally:
            pathFut.stop()

    def test_the_stage_counts_as_moving_for_the_whole_path(self, stage):
        pathFut = stage.movePath(self.PATH, name='three-leg path')
        seen = []
        while not pathFut.is_done:
            seen.append(stage.isMoving())
            time.sleep(0.005)
        pathFut.wait(timeout=TIMEOUT)
        assert seen and all(seen), "the stage reported itself idle mid-path"

    def test_the_path_is_the_active_task_and_the_step_is_the_driver_move(self, stage):
        """``_activeTask`` is what ``isMoving()`` and ``targetPosition()`` ask about;
        ``MockStage._lastMove`` is the driver's record of the hardware move in flight."""
        pathFut = stage.movePath(self.PATH, name='three-leg path')
        try:
            waitFor(lambda: pathFut._currentFuture is not None, "a step to start")
            assert stage._activeTask is pathFut
            assert stage._lastMove is pathFut._currentFuture
            assert stage._lastMove is not pathFut
        finally:
            pathFut.stop()

    def test_a_stopped_path_resets_the_target(self, stage):
        pathFut = stage.movePath(self.PATH, name='three-leg path')
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the path to travel")
        pathFut.stop()
        waitFor(lambda: pathFut.is_done, "the path to complete")

        # The stage stopped inside the first leg, 200 um short in y and 100 um in z.
        np.testing.assert_allclose(stage.targetPosition(), stage.getPosition(), atol=5 * UM)

    def test_a_halted_path_resets_the_target(self, stage, dm):
        pathFut = stage.movePath(self.PATH, name='three-leg path')
        waitFor(lambda: stage.getPosition()[0] > 20 * UM, "the path to travel")
        dm.globalHalt.halt("panic during a path")
        with pytest.raises(GlobalHaltException):
            pathFut.wait(timeout=TIMEOUT)

        np.testing.assert_allclose(stage.targetPosition(), stage.getPosition(), atol=5 * UM)

    def test_a_path_given_in_global_coordinates_still_commands_its_endpoint(self, stage):
        path = [
            {'globalPos': [100 * UM, 0, 0], 'speed': CRAWL},
            {'globalPos': [100 * UM, 100 * UM, 0], 'speed': CRAWL},
        ]
        expected = stage.mapGlobalToDevicePosition([100 * UM, 100 * UM, 0], stage.getPosition())
        pathFut = stage.movePath(path, name='global path')
        try:
            np.testing.assert_allclose(stage.targetPosition(), expected, atol=1e-12)
        finally:
            pathFut.stop()


# --------------------------------------------------------------------------- global


class TestGlobalTarget:
    def test_the_global_target_tracks_the_device_target(self, stage):
        fut = stage.move([1 * MM, 2 * MM, 3 * MM], speed=CRAWL)
        try:
            np.testing.assert_allclose(
                stage.globalTargetPosition(),
                stage.mapDeviceToGlobalPosition([1 * MM, 2 * MM, 3 * MM]),
                atol=1e-12,
            )
        finally:
            fut.stop()

    def test_an_idle_stage_targets_where_it_is(self, stage):
        stage.posChanged([1 * MM, 2 * MM, 3 * MM])
        np.testing.assert_allclose(
            stage.globalTargetPosition(), stage.globalPosition(), atol=1e-12
        )
