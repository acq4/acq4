"""Panic Lock integration — the §13 "Integration" section of ``Panic Lock Spec.md``.

Third sibling to ``test_panic_lock.py`` (``GlobalHalt`` in isolation) and
``test_panic_lock_guards.py`` (the §6.1 table and the §6.3 contract). Those two
stop at the boundary of a single device call. This file asks the next question:
what happens to the *automation* that was mid-flight when the rig was halted?

Two things have to hold for any of it to work, and they are tested first:

1. §5.2 requires a stage's abort callback to fail an in-flight ``MoveFuture``
   with ``GlobalHaltException`` -- not merely to stop the motor. Because
   ``GlobalHaltException`` is not a ``Stopped`` (§7), that is what makes a halt
   propagate *past* every handler written for routine cancellation (§7.1).
2. ``MovePathFuture`` must not rewrap that exception. A ``RuntimeError`` reading
   "Path step 2/3 failed" is indistinguishable from a hardware fault.

Everything below then rides on those two: a ``CleanState`` panicked mid-move, a
``SequentialGroup`` panicked between plan steps, and the reported incident --
panic during a move to the clean bath.

No hardware. The stages are ``MockStage`` and a ``DoverStage`` over a stand-in
motionsynergy client, both driving the real ``Stage``/``MoveFuture`` code.
"""

from __future__ import annotations

import logging
import time
from unittest import mock

import numpy as np
import pytest

from acq4.devices.DoverStage.doverstage import DoverStage
from acq4.devices.MockStage import MockStage
from acq4.devices.PatchPipette.states.clean import CleanState
from acq4.motion.plan import AtomicMove, SequentialGroup
from acq4.motion.planner import _execute_plan
from acq4.panic import GlobalHalt, GlobalHaltException
from acq4.util import Qt
from acq4.util.task import Stopped

# Only ever gates a pass, never manufactures one.
TIMEOUT = 10.0

# Slow enough that a move stays in flight while the test panics it.
CRAWL = 50e-6


def waitUntil(predicate, message, timeout=TIMEOUT):
    """Block until *predicate* is true, or fail the test saying what never happened."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail(f"timed out waiting for {message}")


# ---------------------------------------------------------------------------
# Stand-ins
# ---------------------------------------------------------------------------


class _StandInDM:
    """The slice of the Manager a Stage touches, plus one shared GlobalHalt."""

    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.devices = {}

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def listInterfaces(self, typ):
        return []

    def readConfigFile(self, filename):
        return {}

    def writeConfigFile(self, data, filename):
        return None

    def appendConfigFile(self, data, filename):
        return None

    def configFileName(self, filename):
        return filename


@pytest.fixture
def dm(qtbot):
    """A stand-in device manager. qtbot only guarantees a QApplication exists."""
    (qtbot,)
    return _StandInDM()


@pytest.fixture
def stage(dm):
    with mock.patch("acq4.Manager.Manager.single") as single:
        single.return_value = dm
        dev = MockStage(dm, {"driver": "MockStage", "nAxes": 3}, "Stage")
    # MockStage.__init__ ends with a zero-distance _move() to prime the monitor
    # thread; retire it here so `_lastMove` is unambiguous and no test can
    # mistake that priming move for the one it just requested.
    dev._lastMove.wait(timeout=TIMEOUT)
    dm.devices["Stage"] = dev
    yield dev
    dev.quit()


def inFlight(future, what="a move to be in flight"):
    """Block until *future* (or the callable returning it) is running, then return it."""
    getter = future if callable(future) else (lambda: future)
    waitUntil(lambda: getter() is not None and not getter().is_done, what)
    return getter()


def inFlightStep(pathFut):
    """Block until a MovePathFuture has a step actually running, then return it.

    Deliberately not ``stage._lastMove``: the two are the same object only once
    ``_movePath`` has reached its wait loop, and a test that grabs the wrong one
    fails the wrong future.
    """
    return inFlight(lambda: pathFut._currentFuture, "a path step to be in flight")


# ---------------------------------------------------------------------------
# §5.2 / §7.1 -- what a panicked move reports to whoever is waiting on it
# ---------------------------------------------------------------------------


class TestPanickedMoveSurfacesTheHalt:
    """§5.2's second half: the abort callback fails the in-flight MoveFuture.

    Stopping the motor is not enough. If the future completes with a plain
    ``Stopped``, every ``except Stopped:`` site in the codebase reads the panic
    as an ordinary cancellation and carries on -- which is precisely the hazard
    §7 closes by refusing to make ``GlobalHaltException`` a ``Stopped``.
    """

    def test_a_plain_move_fails_with_globalhaltexception(self, stage, dm):
        fut = stage.move([5e-3, 0, 0], speed=CRAWL)
        assert not fut.is_done

        dm.globalHalt.halt("panic during a move")

        with pytest.raises(GlobalHaltException) as exc:
            fut.wait(timeout=TIMEOUT)
        assert "panic during a move" in str(exc.value)
        # ...and specifically not the ordinary stop path, nor a phantom driver
        # fault from the producer winning the completion race.
        assert not isinstance(exc.value, Stopped)
        assert type(exc.value) is GlobalHaltException

    def test_an_except_stopped_waiter_does_not_absorb_it(self, stage, dm):
        """§7.1 in the shape real calling code has: cancellation handling is bypassed."""
        fut = stage.move([5e-3, 0, 0], speed=CRAWL)
        dm.globalHalt.halt("panic past a cancellation handler")

        cancelled = False
        with pytest.raises(GlobalHaltException):
            try:
                fut.wait(timeout=TIMEOUT)
            except Stopped:
                cancelled = True  # not reached
        assert cancelled is False

    def test_the_driver_cannot_resolve_the_move_after_the_halt_failed_it(self, stage, dm):
        """The completion race, from the other side.

        ``MockStage``'s monitor thread is the future's producer and would resolve
        it on arrival. A halt at 1 nanometre from the target must still be a
        halt: ``_finish`` is first-completer-wins, and ``abortForHalt`` fails
        before it stops the hardware, so the producer's later ``resolve()`` (or
        its interrupt ``fail()``) is the harmless no-op it assumes it is.
        """
        fut = stage.move([5e-3, 0, 0], speed=CRAWL)
        dm.globalHalt.halt("panic, then let the driver try to finish")
        with pytest.raises(GlobalHaltException):
            fut.wait(timeout=TIMEOUT)

        # Whatever the monitor thread does from here cannot overwrite the outcome.
        stage._lastMove.mockFinish()
        stage._lastMove.mockInterrupt()
        with pytest.raises(GlobalHaltException):
            fut.wait(timeout=TIMEOUT)

    def test_a_path_step_surfaces_the_halt_unwrapped(self, stage, dm):
        """§7.1 through ``MovePathFuture``: the exception reaches the caller as itself.

        The path future is not ``_lastMove`` -- only single steps are -- so it
        inherits the failure through its running step. That inheritance is only
        worth anything if ``_movePath`` stops rewrapping it.
        """
        path = [
            {"position": [5e-3, 0, 0], "speed": CRAWL, "explanation": "first leg"},
            {"position": [5e-3, 5e-3, 0], "speed": CRAWL, "explanation": "second leg"},
        ]
        pathFut = stage.movePath(path, name="two-leg path")
        step = inFlightStep(pathFut)
        assert step is stage._lastMove

        dm.globalHalt.halt("panic during a path")

        with pytest.raises(GlobalHaltException) as exc:
            pathFut.wait(timeout=TIMEOUT)
        assert type(exc.value) is GlobalHaltException
        assert "Path step" not in str(exc.value), "the halt was rewrapped as a step failure"
        # The second leg was never commanded.
        assert stage.stageThread.target is None

    def test_a_genuine_step_failure_keeps_its_path_step_context(self, stage, dm):
        """The other half of the 6b ruling: only halts skip the wrapper.

        Without this, "let GlobalHaltException through" could have been
        implemented by dropping the wrapping altogether, and the diagnostic that
        says *which* leg of a path broke would be gone.
        """
        path = [
            {"position": [5e-3, 0, 0], "speed": CRAWL, "explanation": "first leg"},
            {"position": [5e-3, 5e-3, 0], "speed": CRAWL, "explanation": "second leg"},
        ]
        pathFut = stage.movePath(path, name="two-leg path")
        step = inFlightStep(pathFut)

        step.fail(RuntimeError("driver reported an alert"))

        with pytest.raises(RuntimeError) as exc:
            pathFut.wait(timeout=TIMEOUT)
        assert not isinstance(exc.value, GlobalHaltException)
        assert "Path step 1/2 failed" in str(exc.value)
        assert "driver reported an alert" in str(exc.value)


# ---------------------------------------------------------------------------
# §13 Integration -- a running CleanState panicked mid-move
# ---------------------------------------------------------------------------


class _RecordingPressure:
    def __init__(self):
        self.calls = []

    def setPressure(self, source=None, pressure=None):
        self.calls.append((source, pressure))

    @property
    def sources(self):
        return [source for source, _ in self.calls]


class _CleanPipette:
    """The slice of ``Pipette`` that ``CleanState.run()`` drives.

    Every named destination becomes a real ``Stage.move()`` on a real
    ``MockStage``, so the guard, the ``MoveFuture`` and the abort callback under
    test are the shipped ones; only the pipette's coordinate bookkeeping is
    faked.
    """

    #: Where each named destination lives, in stage coordinates.
    SITES = {
        "clean": [5e-3, 0, 0],
        "rinse": [0, 5e-3, 0],
        "home": [0, 0, 0],
    }

    def __init__(self, stage):
        self.stage = stage
        self.moveRequests = []
        self.lastMove = None

    def getSiteFor(self, role):
        return None  # no InteractionSite configured; CleanState falls back to moveTo()

    def moveTo(self, position, speed, **kwds):
        self.moveRequests.append(position)
        self.lastMove = self.stage.move(self.SITES[position], speed=CRAWL)
        return self.lastMove

    def goHome(self, **kwds):
        self.moveRequests.append("home")
        self.lastMove = self.stage.move(self.SITES["home"], speed=CRAWL)
        return self.lastMove


class _CleanDev(Qt.QObject):
    """The slice of ``PatchPipette`` that ``PatchPipetteState`` and ``CleanState`` use."""

    sigTargetChanged = Qt.Signal(object, object)
    sigActiveChanged = Qt.Signal(object, object)

    def __init__(self, pipette, pressure):
        Qt.QObject.__init__(self)
        self.active = True
        self.cell = None
        self.clampDevice = None  # no clamp: initializeClamp() returns immediately
        self.pressureDevice = pressure
        self.pipetteDevice = pipette
        self.sonicatorDevice = None
        self.logger = logging.getLogger(f"{__name__}._CleanDev")
        self._record = {"cleanCount": 0}
        self.tipCleanCalls = []
        self.newPatchAttempts = 0

    def name(self):
        return "CleanPipette"

    def pipetteRecord(self):
        return self._record

    def setTipClean(self, value):
        self.tipCleanCalls.append(value)

    def newPatchAttempt(self):
        self.newPatchAttempts += 1

    def finishPatchRecord(self):
        pass

    def newPipette(self):
        pass


class TestCleanStatePanic:
    """§13: a running ``CleanState`` panicked mid-move terminates, and does not
    advance to the rinse stage or to ``nextState``."""

    @staticmethod
    def _state(stage):
        pressure = _RecordingPressure()
        pipette = _CleanPipette(stage)
        dev = _CleanDev(pipette, pressure)
        state = CleanState(
            dev,
            {
                "cleanSequence": [(-35e3, 0.05), (100e3, 0.05)],
                "rinseSequence": [(-35e3, 0.05)],
                # Distinct from fallbackState, so "did not advance to nextState"
                # is an assertion and not a coincidence.
                "nextState": "seal",
                "fallbackState": "out",
            },
        )
        return state, dev, pipette, pressure

    def test_a_panic_mid_move_terminates_the_state(self, stage, dm):
        state, dev, pipette, pressure = self._state(stage)
        state.start()
        inFlight(lambda: pipette.lastMove)  # the move to the clean bath is under way
        assert pipette.moveRequests == ["clean"]

        dm.globalHalt.halt("panic during clean")

        # The state dies of the halt rather than finishing or being cancelled.
        with pytest.raises(GlobalHaltException):
            state.wait(timeout=TIMEOUT)

        # It never reached the rinse stage...
        assert pipette.moveRequests == ["clean"], "the rinse move was commanded anyway"
        assert "regulator" not in pressure.sources, "cleaning pressure was applied anyway"
        # ...and it never chose a next state, so the manager sees the fallback,
        # not the configured nextState.
        assert state._runChoseNextState is False
        assert state.nextState == {"state": "out"}
        assert dev.tipCleanCalls == []
        assert dev.newPatchAttempts == 0
        assert dev._record["cleanCount"] == 0

    def test_the_halted_state_cannot_move_on_the_way_out(self, stage, dm):
        """The latch outlives the state: cleanup gets no motion either (§8)."""
        state, dev, pipette, pressure = self._state(stage)
        state.start()
        inFlight(lambda: pipette.lastMove)
        dm.globalHalt.halt("panic during clean")
        with pytest.raises(GlobalHaltException):
            state.wait(timeout=TIMEOUT)

        state.cleanup().wait(timeout=TIMEOUT)  # CleanState._cleanup vents; that is Allowed
        assert pressure.calls[-1] == ("atmosphere", 0)
        with pytest.raises(GlobalHaltException):
            pipette.goHome()


# ---------------------------------------------------------------------------
# §13 Integration -- a panic between the steps of a SequentialGroup
# ---------------------------------------------------------------------------


class TestSequentialGroupPanic:
    """§13: a panic between plan steps prevents the next step from starting.

    ``_execute_plan`` is the real executor and ``SequentialGroup`` the real plan
    node; the only stand-in is the hook that decides *when* to panic, which has
    to be deterministic or the test would be asserting on a sleep.
    """

    def test_the_next_step_never_starts(self, stage, dm):
        plan = SequentialGroup(
            explanation="two-step plan",
            steps=[
                AtomicMove(stage, [50e-6, 0, 0], "fast", explanation="step one"),
                AtomicMove(stage, [100e-6, 0, 0], "fast", explanation="step two"),
            ],
        )

        realMove = stage.moveToGlobalNoPlanning
        realSetTarget = stage.stageThread.setTarget
        attempted = []
        commanded = []

        def recordingSetTarget(future, target, speed):
            commanded.append(np.asarray(target, dtype=float).copy())
            return realSetTarget(future, target, speed)

        def panicAfterTheFirstStep(pos, speed, **kwds):
            attempted.append(np.asarray(pos, dtype=float))
            fut = realMove(pos, speed, **kwds)
            fut.wait(timeout=TIMEOUT)
            if len(attempted) == 1:
                # Between steps: step one is complete, step two has not been asked for.
                dm.globalHalt.halt("panic between plan steps")
            return fut

        with mock.patch.object(stage.stageThread, "setTarget", side_effect=recordingSetTarget):
            with mock.patch.object(
                stage, "moveToGlobalNoPlanning", side_effect=panicAfterTheFirstStep
            ):
                with pytest.raises(GlobalHaltException):
                    _execute_plan(plan)

        # The executor did go on to step two -- the plan does not know it is
        # doomed -- but the step was refused above the driver.
        assert len(attempted) == 2
        assert len(commanded) == 1, "the second step reached the hardware"
        np.testing.assert_allclose(commanded[0][:3], [50e-6, 0, 0], atol=1e-9)
        np.testing.assert_allclose(stage.getPosition()[:3], [50e-6, 0, 0], atol=1e-6)


# ---------------------------------------------------------------------------
# §13 Integration -- the reported incident
# ---------------------------------------------------------------------------


class _RemoteValue:
    """A teleprox proxy attribute: read with ``._get_value()`` (``control_thread.py``)."""

    def __init__(self, value):
        self._value = value

    def _get_value(self):
        return self._value


class _FakeRequestFuture:
    """A SmartStageRequestFuture: completed by the driver, read via proxy attributes."""

    def __init__(self):
        self._callback = None
        self.error = _RemoteValue(None)
        self.exc_info = _RemoteValue(None)

    def set_callback(self, cb):
        self._callback = cb

    def fail(self, message):
        # What ``control_thread._handle_stop`` does: fail with a *string*, which is
        # why the Dover path alone cannot tell a halt from an alert (§12 item 5).
        self.error = _RemoteValue(message)
        if self._callback is not None:
            self._callback(self)


class _FakeSmartStage:
    """The motionsynergy 'smartstage' surface ``DoverStage`` uses. Records commands."""

    def __init__(self):
        self.default_acceleration = None
        self.enabled = False
        self.moves = []
        self.stopCount = 0
        self.control_thread = type("ct", (), {"poll_interval": 0.1})()
        self._pos = np.zeros(3)
        self._pending = None

    def enable(self):
        self.enabled = True

    def pos(self, refresh=False):
        return self._pos.copy()

    def set_callback(self, cb):
        self._posCallback = cb

    def move(self, pos, speed, name=None):
        self.moves.append((np.asarray(pos, dtype=float), name))
        self._pending = _FakeRequestFuture()
        return self._pending

    def stop(self):
        self.stopCount += 1
        if self._pending is not None:
            self._pending.fail("stop requested before move finished")
            self._pending = None


@pytest.fixture
def dover(dm):
    fake = _FakeSmartStage()
    with mock.patch(
        "acq4.devices.DoverStage.doverstage.get_client", return_value={"smartstage": fake}
    ):
        with mock.patch("acq4.Manager.Manager.single") as single:
            single.return_value = dm
            dev = DoverStage(dm, {"dllPath": "unused-in-tests"}, "DoverStage")
    dev.driver = fake
    dm.devices["DoverStage"] = dev
    yield dev
    dev.quit()


class TestMoveToCleanRegression:
    """§13: the reported incident -- panic during a move to the clean bath.

    A move to the clean bath is a multi-waypoint ``movePath``, so the incident
    exercises exactly the two things §13's other integration rows depend on: the
    in-flight step future must fail with the halt, and ``MovePathFuture`` must
    not disguise it. Both regressions are visible here: before 6a the caller got
    the driver's ``RuntimeError("stop requested before move finished")``, and
    before 6b that arrived wrapped as ``"Path step 1/2 failed: ..."``.
    """

    PATH = [
        {"position": [0, 0, 2e-3], "speed": "fast", "explanation": "retract"},
        {"position": [5e-3, 0, 2e-3], "speed": "fast", "explanation": "traverse to clean bath"},
        {"position": [5e-3, 0, 0], "speed": "fast", "explanation": "descend into clean bath"},
    ]

    def test_a_panic_mid_path_halts_the_stage_and_commands_no_further_motion(self, dover, dm):
        fake = dover.driver
        pathFut = dover.movePath(self.PATH, name="move to clean")
        waitUntil(lambda: len(fake.moves) == 1, "the first leg to be commanded")
        assert fake.stopCount == 0

        dm.globalHalt.halt("Operator pressed ESC during move to clean")

        # The waiter learns this was a halt, not a hardware alert and not a
        # routine cancellation.
        with pytest.raises(GlobalHaltException) as exc:
            pathFut.wait(timeout=TIMEOUT)
        assert type(exc.value) is GlobalHaltException
        assert not isinstance(exc.value, Stopped)
        assert "Path step" not in str(exc.value)

        # The stage was stopped, and nothing further was ever commanded.
        waitUntil(lambda: fake.stopCount >= 1, "the driver to be stopped")
        assert len(fake.moves) == 1, f"further motion commanded: {fake.moves}"

        # The latch holds: a retry cannot restart the path either.
        with pytest.raises(GlobalHaltException):
            dover.movePath(self.PATH, name="retry move to clean").wait(timeout=TIMEOUT)
        assert len(fake.moves) == 1

    def test_the_halt_wins_the_race_against_the_drivers_own_failure(self, dover, dm):
        """§12 item 5, contained.

        ``control_thread`` fails a stopped request with a bare string, so the
        Dover path itself cannot distinguish a deliberate halt from an alert --
        ``DoverMoveFuture._future_finished`` turns both into ``RuntimeError``.
        ``abortForHalt`` fails the future *before* stopping the hardware, so that
        RuntimeError arrives at an already-completed promise and is discarded.
        """
        fake = dover.driver
        fut = dover.move([5e-3, 0, 0], speed="fast")
        waitUntil(lambda: len(fake.moves) == 1, "the move to be commanded")

        dm.globalHalt.halt("panic against the driver")

        with pytest.raises(GlobalHaltException):
            fut.wait(timeout=TIMEOUT)
        assert fake.stopCount >= 1  # the driver really was stopped and did fail the request


# ---------------------------------------------------------------------------
# §6.3 -- the new abort callback must still be a legal halt-path action
# ---------------------------------------------------------------------------


def test_failing_the_move_does_not_make_the_abort_callback_raise(stage, dm):
    """§6.1 lists "Failing an in-flight MoveFuture" as Allowed, so the callback
    that does it must complete with the latch already set (§6.3)."""
    stage.move([5e-3, 0, 0], speed=CRAWL)
    dm.globalHalt.halt("contract check")
    # Invoked exactly as the fan-out invokes it: halted first, callback second.
    stage.abortForHalt()  # must not raise
    assert stage._lastMove.is_done


def test_the_abort_callback_leaves_an_already_completed_move_alone(stage, dm):
    """The other direction of the completion race: no failing a finished future.

    ``_finish`` is first-completer-wins, so a halt arriving after the move
    already arrived must not rewrite its result into a failure.
    """
    fut = stage.move([10e-6, 0, 0], speed="fast")
    assert fut.wait(timeout=TIMEOUT) is None

    dm.globalHalt.halt("nothing in flight")
    stage.abortForHalt()  # must not raise

    assert fut.wait(timeout=TIMEOUT) is None


def test_quit_unregisters_the_registered_callback(dm):
    with mock.patch("acq4.Manager.Manager.single") as single:
        single.return_value = dm
        dev = MockStage(dm, {"driver": "MockStage", "nAxes": 3}, "Transient")
    assert any(cb == dev.abortForHalt for _, cb in dm.globalHalt._abortCallbacks)
    dev.quit()
    assert not any(cb == dev.abortForHalt for _, cb in dm.globalHalt._abortCallbacks)
