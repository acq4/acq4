"""Gamepad jogging from the ``joystick:`` config block on :class:`~acq4.devices.Stage.Stage.Stage`.

Headless against :class:`MockStage` and a :class:`FakeJoystick` that offers the same
``sigStateChanged``/``state()`` surface as :class:`~acq4.devices.Joystick.Joystick`; no
pygame, no gamepad, no real Manager.

Shaping (deadzone, curve, sticks, modifiers) is tested through
``Stage._joystickVelocity()``, which returns m/s per axis without touching a thread. The
rate policy is tested through ``PostSpy``; readings held back by the post interval arrive
on a Qt timer, so those tests pump the event loop.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from unittest.mock import patch

from acq4.devices.MockStage import MockStage
from acq4.devices.Stage.Stage import VelocityFuture
from acq4.panic import GlobalHalt
from acq4.util import Qt

UM = 1e-6
MM = 1e-3

#: Full-scale jog speed, m/s: under a micrometre of travel between control-thread decisions.
SPEED = 20 * UM

TIMEOUT = 5.0


class FakeJoystick(Qt.QObject):
    """A :class:`~acq4.devices.Joystick.Joystick` stand-in with no pygame behind it.

    Axes read in [-1, 1] and buttons are booleans, as pygame reports them; deflecting or
    pressing emits ``sigStateChanged(self, event)``.
    """

    sigStateChanged = Qt.Signal(object, object)  # self, change

    def __init__(self, name='Gamepad', nAxes=4, nButtons=6):
        Qt.QObject.__init__(self)
        self._name = name
        self._axes = [0.0] * nAxes
        self._buttons = [False] * nButtons

    def name(self):
        return self._name

    def state(self):
        return {'axes': list(self._axes), 'buttons': list(self._buttons)}

    def deflect(self, values):
        """Set several axes from a {index: deflection} dict and emit one event for the last."""
        for index, value in values.items():
            self._axes[index] = float(value)
        last = list(values)[-1]
        self.sigStateChanged.emit(self, {'axis': last, 'value': self._axes[last]})

    def press(self, button, held=True):
        self._buttons[button] = bool(held)
        self.sigStateChanged.emit(self, {'button': button, 'value': bool(held)})

    def heartbeat(self):
        """Re-assert that this gamepad is still attached, as its polling thread does."""
        self.sigStateChanged.emit(self, {'heartbeat': True})

    def remove(self):
        """Unplug this gamepad: every axis and button reads at rest, and it says so."""
        self._axes = [0.0] * len(self._axes)
        self._buttons = [False] * len(self._buttons)
        self.sigStateChanged.emit(self, {'removed': True})


class MockDM:
    """Just enough device manager for a MockStage plus its joysticks."""

    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.devices = {}

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices.get(name, None)

    def readConfigFile(self, fn):
        return {}


@pytest.fixture
def dm(qtbot):
    (qtbot,)  # qtbot only guarantees a QApplication exists
    dm = MockDM()
    dm.devices['Gamepad'] = FakeJoystick('Gamepad')
    dm.devices['Gamepad2'] = FakeJoystick('Gamepad2')
    return dm


def makeStage(dm, joystick, **config):
    conf = {'driver': 'MockStage', 'nAxes': 3, 'joystick': joystick}
    conf.update(config)
    with patch("acq4.Manager.Manager.single") as single:
        single.return_value = dm
        dev = MockStage(dm, conf, 'JoyStage')
    # MockStage.__init__ primes its monitor thread with a zero-distance _move(); retire it.
    dev._lastMove.wait(timeout=TIMEOUT)
    return dev


@pytest.fixture
def stages(dm):
    """Builds stages on demand and quits every one of them at the end of the test."""
    built = []

    def build(joystick, **config):
        dev = makeStage(dm, joystick, **config)
        built.append(dev)
        return dev

    yield build
    for dev in built:
        dev.quit()


class PostSpy:
    """Stands in for the direct-motion controller, recording what is posted to it."""

    def __init__(self, stage):
        self.posted = []
        self.timeouts = []
        stage.directMotion.requestVelocity = self._record

    def _record(self, vel, timeout=None):
        self.posted.append(np.asarray(vel, dtype=float))
        self.timeouts.append(timeout)


def pump(iterations=5):
    for _ in range(iterations):
        Qt.QApplication.processEvents()


def pumpUntil(predicate, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        Qt.QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


def waitFor(predicate, what, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail(f"timed out waiting for {what}")


def settled(controller):
    assert controller.waitUntilIdle(TIMEOUT), "the direct motion thread never came back"


# One axis per stick, linear, no deadzone: deflection maps straight onto velocity.
PLAIN = {'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0, 'curve': 'linear'}}


# ----------------------------------------------------------------------------- the block


class TestTheBlock:
    def test_an_axis_may_be_named_or_numbered(self, stages, dm):
        byName = stages({'x': {'axis': ['Gamepad', 0], 'speed': SPEED}})
        byIndex = stages({0: {'axis': ['Gamepad', 0], 'speed': SPEED}})
        assert byName._jsGroups[0][0]['axis'] == 0
        assert byIndex._jsGroups[0][0]['axis'] == 0

    def test_no_block_binds_nothing(self, dm, stages):
        stage = stages({})
        assert stage._jsGroups == []
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 1.0})
        assert spy.posted == []

    def test_a_missing_joystick_drops_its_axis(self, stages):
        stage = stages({
            'x': {'axis': ['Nonesuch', 0], 'speed': SPEED},
            'y': {'axis': ['Gamepad', 1], 'speed': SPEED},
        })
        bound = [b['axis'] for group in stage._jsGroups for b in group]
        assert bound == [1]

    def test_an_unknown_stage_axis_is_refused(self, stages):
        with pytest.raises(ValueError, match="not an axis of this stage"):
            stages({'w': {'axis': ['Gamepad', 0], 'speed': SPEED}})

    def test_a_zero_speed_is_refused(self, stages):
        with pytest.raises(ValueError, match="'speed' of 0"):
            stages({'x': {'axis': ['Gamepad', 0], 'speed': 0}})

    def test_a_deadzone_of_one_is_refused(self, stages):
        with pytest.raises(ValueError, match="'deadzone'"):
            stages({'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 1.0}})

    def test_an_unknown_curve_is_refused(self, stages):
        with pytest.raises(ValueError, match="unknown 'curve'"):
            stages({'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'curve': 'sigmoid'}})

    def test_a_stick_whose_axes_disagree_is_refused(self, stages):
        with pytest.raises(ValueError, match="must agree"):
            stages({
                'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'stick': 'left', 'deadzone': 0.1},
                'y': {'axis': ['Gamepad', 1], 'speed': SPEED, 'stick': 'left', 'deadzone': 0.2},
            })

    def test_events_from_an_unbound_axis_are_ignored(self, dm, stages):
        stage = stages(PLAIN)
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({3: 1.0})
        assert spy.posted == []

    def test_events_from_an_unbound_joystick_are_ignored(self, dm, stages):
        stage = stages(PLAIN)
        spy = PostSpy(stage)
        dm.devices['Gamepad2'].deflect({0: 1.0})
        assert spy.posted == []

    def test_an_axis_the_gamepad_does_not_have_reads_zero(self, dm, stages):
        stage = stages({'x': {'axis': ['Gamepad', 11], 'speed': SPEED}})
        assert not np.any(stage._joystickVelocity())

    def test_a_joystick_with_no_state_yet_reads_zero(self, dm, stages):
        """Joystick.state() has nothing to copy until its first pygame event."""
        stage = stages(PLAIN)
        dm.devices['Gamepad'].state = lambda: None.copy()
        assert not np.any(stage._joystickVelocity())


# -------------------------------------------------------------------------------- shaping


class TestDeadzone:
    """Sticks rest a little off centre and drift; below the deadzone that reads as stopped."""

    @pytest.fixture
    def stage(self, stages):
        return stages({
            'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0.2, 'curve': 'linear'},
        })

    @pytest.mark.parametrize('deflection', [0.0, 0.05, 0.19, 0.2, -0.2, -0.05])
    def test_inside_it_the_axis_is_exactly_zero(self, dm, stage, deflection):
        dm.devices['Gamepad']._axes[0] = deflection
        assert stage._joystickVelocity()[0] == 0.0

    def test_just_outside_it_the_axis_barely_moves(self, dm, stage):
        dm.devices['Gamepad']._axes[0] = 0.21
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED * 0.01 / 0.8)

    def test_full_deflection_still_gives_the_configured_speed(self, dm, stage):
        dm.devices['Gamepad']._axes[0] = 1.0
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED)
        dm.devices['Gamepad']._axes[0] = -1.0
        assert stage._joystickVelocity()[0] == pytest.approx(-SPEED)


class TestResponseCurve:
    """The deflection left above the deadzone is rescaled to [0, 1] and raised to a power."""

    @pytest.mark.parametrize(
        'curve, deflection, fraction',
        [
            ('linear', 0.25, 0.25),
            ('linear', 0.5, 0.5),
            ('quadratic', 0.25, 0.0625),
            ('quadratic', 0.5, 0.25),
            ('cubic', 0.5, 0.125),
            ('cubic', 0.8, 0.512),
        ],
    )
    def test_it_scales_the_deflection(self, dm, stages, curve, deflection, fraction):
        stage = stages({
            'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0, 'curve': curve},
        })
        dm.devices['Gamepad']._axes[0] = deflection
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED * fraction)

    @pytest.mark.parametrize('curve', ['linear', 'quadratic', 'cubic'])
    def test_every_curve_reaches_full_speed(self, dm, stages, curve):
        stage = stages({
            'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0.3, 'curve': curve},
        })
        dm.devices['Gamepad']._axes[0] = 1.0
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED)

    def test_quadratic_is_the_default(self, dm, stages):
        stage = stages({'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0}})
        dm.devices['Gamepad']._axes[0] = 0.5
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED * 0.25)

    def test_a_negative_speed_inverts_the_stick(self, dm, stages):
        stage = stages({
            'x': {'axis': ['Gamepad', 0], 'speed': -SPEED, 'deadzone': 0, 'curve': 'linear'},
        })
        dm.devices['Gamepad']._axes[0] = 0.5
        assert stage._joystickVelocity()[0] == pytest.approx(-SPEED * 0.5)


class TestStickPairs:
    """Two axes of one stick are shaped as a vector, so a diagonal keeps its direction."""

    #: Deliberately not 45 degrees: on the diagonal, per-axis and paired shaping agree.
    DIAGONAL = {0: 0.8, 1: 0.4}

    PAIRED = {
        'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0.1, 'stick': 'left'},
        'y': {'axis': ['Gamepad', 1], 'speed': SPEED, 'deadzone': 0.1, 'stick': 'left'},
    }
    SEPARATE = {
        'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0.1},
        'y': {'axis': ['Gamepad', 1], 'speed': SPEED, 'deadzone': 0.1},
    }

    def test_a_stick_is_one_group(self, stages):
        stage = stages(self.PAIRED)
        assert len(stage._jsGroups) == 1
        assert sorted(b['axis'] for b in stage._jsGroups[0]) == [0, 1]

    def test_unlabelled_axes_are_separate_groups(self, stages):
        stage = stages(self.SEPARATE)
        assert sorted(len(g) for g in stage._jsGroups) == [1, 1]

    def test_a_pair_keeps_the_direction_of_the_deflection(self, dm, stages):
        stage = stages(self.PAIRED)
        dm.devices['Gamepad']._axes[0] = self.DIAGONAL[0]
        dm.devices['Gamepad']._axes[1] = self.DIAGONAL[1]
        vel = stage._joystickVelocity()
        assert vel[1] / vel[0] == pytest.approx(self.DIAGONAL[1] / self.DIAGONAL[0])

    def test_shaping_axes_independently_bends_it(self, dm, stages):
        stage = stages(self.SEPARATE)
        dm.devices['Gamepad']._axes[0] = self.DIAGONAL[0]
        dm.devices['Gamepad']._axes[1] = self.DIAGONAL[1]
        vel = stage._joystickVelocity()
        assert vel[1] / vel[0] != pytest.approx(self.DIAGONAL[1] / self.DIAGONAL[0])

    def test_the_curve_applies_to_the_magnitude(self, dm, stages):
        stage = stages(self.PAIRED)
        dm.devices['Gamepad']._axes[0] = 0.6
        dm.devices['Gamepad']._axes[1] = 0.8  # magnitude exactly 1
        vel = stage._joystickVelocity()
        assert np.linalg.norm(vel[:2]) == pytest.approx(SPEED)

    def test_a_deflection_past_one_is_clipped_without_turning(self, dm, stages):
        """A square-gated stick reads sqrt(2) on the diagonal."""
        stage = stages(self.PAIRED)
        dm.devices['Gamepad']._axes[0] = 1.0
        dm.devices['Gamepad']._axes[1] = 1.0
        vel = stage._joystickVelocity()
        assert np.linalg.norm(vel[:2]) == pytest.approx(SPEED)
        assert vel[1] == pytest.approx(vel[0])

    def test_the_deadzone_applies_to_the_magnitude(self, dm, stages):
        """Neither axis is past the deadzone on its own, but the stick is."""
        stage = stages(self.PAIRED)
        dm.devices['Gamepad']._axes[0] = 0.09
        dm.devices['Gamepad']._axes[1] = 0.09
        assert np.any(stage._joystickVelocity())

    def test_axes_of_one_stick_may_have_different_speeds(self, dm, stages):
        stage = stages({
            'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0, 'stick': 'left',
                  'curve': 'linear'},
            'y': {'axis': ['Gamepad', 1], 'speed': 2 * SPEED, 'deadzone': 0, 'stick': 'left',
                  'curve': 'linear'},
        })
        dm.devices['Gamepad']._axes[0] = 0.6
        dm.devices['Gamepad']._axes[1] = 0.8
        vel = stage._joystickVelocity()
        assert vel[0] == pytest.approx(SPEED * 0.6)
        assert vel[1] == pytest.approx(2 * SPEED * 0.8)


class TestModifiers:
    @pytest.fixture
    def stage(self, stages):
        return stages({
            'x': {
                'axis': ['Gamepad', 0],
                'speed': SPEED,
                'deadzone': 0,
                'curve': 'linear',
                'modifiers': [['Gamepad', 2, 10.0], ['Gamepad2', 3, 0.1]],
            },
        })

    def test_a_held_button_multiplies_the_speed(self, dm, stage):
        dm.devices['Gamepad']._axes[0] = 0.5
        dm.devices['Gamepad']._buttons[2] = True
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED * 5.0)

    def test_modifiers_on_two_joysticks_multiply_together(self, dm, stage):
        dm.devices['Gamepad']._axes[0] = 0.5
        dm.devices['Gamepad']._buttons[2] = True
        dm.devices['Gamepad2']._buttons[3] = True
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED * 0.5)

    def test_releasing_it_restores_the_speed(self, dm, stage):
        dm.devices['Gamepad']._axes[0] = 0.5
        dm.devices['Gamepad']._buttons[2] = True
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED * 5.0)
        dm.devices['Gamepad']._buttons[2] = False
        assert stage._joystickVelocity()[0] == pytest.approx(SPEED * 0.5)

    def test_a_modifier_cannot_start_a_jog_on_its_own(self, dm, stage):
        spy = PostSpy(stage)
        dm.devices['Gamepad'].press(2)
        assert spy.posted == []

    def test_a_modifier_pressed_mid_gesture_is_posted(self, dm, stage):
        stage.joystickPostInterval = 0
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.5})
        dm.devices['Gamepad'].press(2)
        assert len(spy.posted) == 2
        assert spy.posted[1][0] == pytest.approx(SPEED * 5.0)


# ---------------------------------------------------------------------------- rate policy


class TestRatePolicy:
    """At most one post per interval, nothing for a reading that has barely moved, and no
    wait at all for the one that ends the jog."""

    @pytest.fixture
    def stage(self, stages):
        return stages(PLAIN)

    def test_an_unchanged_reading_is_dropped(self, dm, stage):
        stage.joystickPostInterval = 0
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.5})
        dm.devices['Gamepad'].deflect({0: 0.5})
        assert len(spy.posted) == 1

    def test_a_reading_that_has_barely_moved_is_dropped(self, dm, stage):
        stage.joystickPostInterval = 0
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.5})
        dm.devices['Gamepad'].deflect({0: 0.5005})
        assert len(spy.posted) == 1
        assert stage._jsPending is None

    def test_small_changes_accumulate_until_they_count(self, dm, stage):
        stage.joystickPostInterval = 0
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.5})
        for step in range(1, 9):
            dm.devices['Gamepad'].deflect({0: 0.5 + 0.002 * step})
        assert len(spy.posted) == 2
        assert spy.posted[1][0] == pytest.approx(SPEED * 0.512)

    def test_the_first_reading_of_a_gesture_is_never_dropped(self, dm, stage):
        """The threshold is a fraction of full scale; near centre the whole velocity is less."""
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.001})
        assert len(spy.posted) == 1
        assert spy.posted[0][0] == pytest.approx(SPEED * 0.001)

    def test_a_second_reading_inside_the_interval_waits(self, dm, stage):
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.3})
        dm.devices['Gamepad'].deflect({0: 0.9})
        assert len(spy.posted) == 1
        assert stage._jsPostTimer.isActive()

    def test_the_reading_it_waited_for_is_posted_by_timer(self, dm, stage):
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.3})
        dm.devices['Gamepad'].deflect({0: 0.9})
        assert pumpUntil(lambda: len(spy.posted) == 2), "the held reading was never posted"
        assert spy.posted[1][0] == pytest.approx(SPEED * 0.9)

    def test_a_burst_is_thinned_to_the_interval(self, dm, stage):
        spy = PostSpy(stage)
        start = time.time()
        for step in range(20):  # 50 Hz of stick, as the pygame thread delivers it
            dm.devices['Gamepad'].deflect({0: 0.05 * (step + 1)})
            time.sleep(0.02)
            pump(1)
        elapsed = time.time() - start
        allowed = elapsed / stage.joystickPostInterval + 2
        assert 1 <= len(spy.posted) <= allowed, f"{len(spy.posted)} posts in {elapsed:.2f}s"
        assert len(spy.posted) < 20, "every reading was posted"

    def test_the_last_reading_of_a_burst_is_not_the_one_that_was_dropped(self, dm, stage):
        spy = PostSpy(stage)
        for step in range(5):
            dm.devices['Gamepad'].deflect({0: 0.1 * (step + 1)})
        assert pumpUntil(lambda: spy.posted[-1][0] == pytest.approx(SPEED * 0.5))

    def test_centring_the_stick_never_waits(self, dm, stage):
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.9})
        dm.devices['Gamepad'].deflect({0: 0.0})
        assert len(spy.posted) == 2
        assert not np.any(spy.posted[1])
        assert not stage._jsPostTimer.isActive()

    def test_centring_cancels_a_reading_that_was_waiting(self, dm, stage):
        spy = PostSpy(stage)
        dm.devices['Gamepad'].deflect({0: 0.3})
        dm.devices['Gamepad'].deflect({0: 0.9})
        assert stage._jsPending is not None
        dm.devices['Gamepad'].deflect({0: 0.0})
        assert stage._jsPending is None
        pump()
        assert len(spy.posted) == 2
        assert not np.any(spy.posted[1])


# -------------------------------------------------------------------------------- routing


class TestRouting:
    """The stick asks the direct-motion controller, and gets its gate and its dedupe."""

    @pytest.fixture
    def stage(self, stages):
        dev = stages(PLAIN)
        dev.joystickPostInterval = 0
        return dev

    def test_a_deflection_becomes_the_controllers_jog(self, dm, stage):
        controller = stage.directMotion
        dm.devices['Gamepad'].deflect({0: 1.0})
        settled(controller)
        task = stage._activeTask
        assert isinstance(task, VelocityFuture) and not task.is_done
        assert task is controller._inFlight
        assert task.velocity[0] == pytest.approx(SPEED)

    def test_centring_the_stick_ends_the_jog(self, dm, stage):
        controller = stage.directMotion
        dm.devices['Gamepad'].deflect({0: 1.0})
        settled(controller)
        jog = controller._inFlight
        waitFor(lambda: stage.getPosition()[0] > 0.5 * UM, "the stage to travel")

        dm.devices['Gamepad'].deflect({0: 0.0})
        settled(controller)

        assert jog.is_done
        assert not stage.isMoving()
        assert controller._inFlight is None

    def test_a_stick_inside_its_deadzone_ends_the_jog(self, dm, stages):
        stage = stages({
            'x': {'axis': ['Gamepad', 0], 'speed': SPEED, 'deadzone': 0.2, 'curve': 'linear'},
        })
        stage.joystickPostInterval = 0
        controller = stage.directMotion
        dm.devices['Gamepad'].deflect({0: 1.0})
        settled(controller)
        assert stage.isMoving()

        dm.devices['Gamepad'].deflect({0: 0.15})  # released, but resting off centre
        settled(controller)
        assert not stage.isMoving()

    def test_re_aiming_replaces_the_jog_rather_than_stacking(self, dm, stage):
        controller = stage.directMotion
        dm.devices['Gamepad'].deflect({0: 0.4})
        settled(controller)
        first = controller._inFlight
        dm.devices['Gamepad'].deflect({0: 1.0})
        settled(controller)

        second = controller._inFlight
        assert second is not first
        assert first.is_done
        assert second is stage._activeTask
        assert second.velocity[0] == pytest.approx(SPEED)

    def test_a_programmatic_move_keeps_the_stage(self, dm, stage):
        fut = stage.move([1 * MM, 0, 0], speed=SPEED)
        try:
            dm.devices['Gamepad'].deflect({0: 1.0})
            settled(stage.directMotion)
            assert stage._activeTask is fut
            assert stage.directMotion._inFlight is None
        finally:
            fut.stop()


# ------------------------------------------------------------------------------ liveness


class TestLiveness:
    """A jog runs only while the gamepad driving it keeps confirming that it is there.

    A stick held at full deflection rests against its gate and produces no events, so
    continued travel is no evidence that anyone is still holding it. The gamepad's own
    polling confirms the jog instead. Unplugging the gamepad stops the confirmations;
    so does a wedged main thread, because they are carried by a queued connection.
    """

    #: Short enough to keep these tests quick, long enough not to race the control thread.
    LIVENESS = 0.15

    @pytest.fixture
    def stage(self, stages):
        dev = stages(PLAIN, joystickLivenessTimeout=self.LIVENESS)
        dev.joystickPostInterval = 0
        return dev

    def test_a_jog_ends_when_nothing_confirms_it_any_more(self, dm, stage):
        controller = stage.directMotion
        dm.devices['Gamepad'].deflect({0: 1.0})
        settled(controller)
        jog = controller._inFlight
        assert jog is not None and not jog.is_done

        # The gamepad is unplugged, or the main thread wedges: no reading ever again.
        waitFor(lambda: jog.is_done, "the unconfirmed jog to end")
        waitFor(lambda: not stage.isMoving(), "the stage to stop")
        stopped = stage.getPosition()
        time.sleep(0.05)
        np.testing.assert_allclose(stage.getPosition(), stopped, atol=1e-12)

    def test_unplugging_the_gamepad_ends_the_jog_at_once(self, dm, stage):
        controller = stage.directMotion
        pad = dm.devices['Gamepad']
        pad.deflect({0: 1.0})
        settled(controller)
        jog = controller._inFlight
        waitFor(lambda: stage.getPosition()[0] > 0.5 * UM, "the stage to travel")

        pad.remove()
        settled(controller)

        assert jog.is_done, "the jog outlived the gamepad driving it"
        assert not stage.isMoving()
        assert controller._inFlight is None

    def test_a_stick_held_at_full_deflection_keeps_its_jog(self, dm, stage):
        controller = stage.directMotion
        pad = dm.devices['Gamepad']
        pad.deflect({0: 1.0})
        settled(controller)
        jog = controller._inFlight

        deadline = time.time() + 5 * self.LIVENESS
        while time.time() < deadline:
            pad.heartbeat()
            time.sleep(0.01)

        assert not jog.is_done, "a stick the operator is still holding lost its jog"

    def test_a_reading_the_rate_policy_drops_still_confirms_the_jog(self, dm, stage):
        controller = stage.directMotion
        pad = dm.devices['Gamepad']
        pad.deflect({0: 1.0})
        settled(controller)
        jog = controller._inFlight

        deadline = time.time() + 5 * self.LIVENESS
        while time.time() < deadline:
            pad.deflect({0: 1.0})  # identical, so dropped before it reaches the controller
            time.sleep(0.01)

        assert not jog.is_done, "the jog starved on readings its own rate policy dropped"

    def test_a_gamepad_this_stage_is_not_bound_to_does_not_confirm_it(self, dm, stage):
        controller = stage.directMotion
        dm.devices['Gamepad'].deflect({0: 1.0})
        settled(controller)
        jog = controller._inFlight

        deadline = time.time() + 5 * self.LIVENESS
        while time.time() < deadline and not jog.is_done:
            dm.devices['Gamepad2'].heartbeat()
            time.sleep(0.01)

        assert jog.is_done, "a gamepad this stage does not read kept the jog alive"

    def test_a_request_that_asks_for_no_deadline_gets_none(self, dm, stages):
        """The deadline belongs to the gamepad path, not to every continuous request."""
        stage = stages(PLAIN)
        controller = stage.directMotion
        controller.requestVelocity([SPEED, 0, 0])
        settled(controller)
        jog = controller._inFlight

        time.sleep(2 * stage.joystickLivenessTimeout)

        assert not jog.is_done, "a jog with no deadline was cut off anyway"
        jog.stop()
