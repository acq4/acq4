"""Dial-driven axis movement on the base :class:`~acq4.devices.Stage.Stage.Stage`.

Headless against :class:`MockControlSurface` and :class:`MockStage`; no hardware and no
real Manager. Control signals and ``sigPositionChanged`` arrive over queued connections,
so tests pump the Qt event loop after injecting activity.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
import pytest
from unittest.mock import patch

from acq4.devices.MockControlSurface import MockControlSurface
from acq4.devices.MockStage import MockStage
from acq4.panic import GlobalHalt
from acq4.util import Qt

UM = 1e-6

#: A Dover's axis scale: device units are millimetres, with x and z wired the other way up
#: from the global frame.
DOVER_SCALE = (-1e-3, 1e-3, -1e-3)

JOG = {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': 'jog', 'step': 5 * UM}
FADER = {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': 'fader', 'step': 5 * UM}
BUTTON = {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ('img', 0, 0)}


def pump(iterations=5):
    """Deliver queued Qt events so that control and position signals arrive."""
    for _ in range(iterations):
        Qt.QApplication.processEvents()


def pumpUntil(predicate, timeout=5.0):
    """Pump the event loop until *predicate* is true or *timeout* elapses."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        Qt.QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


class TextDialSurface(MockControlSurface):
    """A mock whose relative dial draws text natively, like a Stream Dock knob strip."""

    RELATIVE_DIAL_CAPS = {
        'input': {'press': True, 'mode': 'relative', 'resolution': 1},
        'output': {'image': (200, 100), 'text': True, 'color': False},
    }


class TwoDialSurface(MockControlSurface):
    """A mock with a second relative dial, so two axes can be bound at once."""

    def __init__(self, deviceManager, config: dict, name: str):
        MockControlSurface.__init__(self, deviceManager, config, name)
        self._addControlBlock('dial', self.RELATIVE_DIAL_CAPS, keys=['jog2'], grid=False)


class BlindDialSurface(MockControlSurface):
    """A mock whose relative dial has no output at all, like an X-Keys jog wheel."""

    RELATIVE_DIAL_CAPS = {
        'input': {'press': True, 'mode': 'relative', 'resolution': 1},
        'output': {},
    }


class MockDM:
    """Just enough device manager for a MockStage plus one control surface."""

    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.devices = {}

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def readConfigFile(self, fn):
        return {}


class Rig:
    """A mock surface plus a factory for stages bound to it."""

    def __init__(self, surfaceClass=MockControlSurface):
        self.dm = MockDM()
        self.surface = surfaceClass(self.dm, {}, 'Dock')
        self.dm.devices['Dock'] = self.surface
        self.stages = []

    def makeStage(self, *, scale=None, **controls):
        config = {'driver': 'MockStage', 'nAxes': 3}
        if scale is not None:
            config['scale'] = scale
        if controls:
            config['controls'] = controls
        with patch("acq4.Manager.Manager.single", self.dm):
            stage = MockStage(self.dm, config, f'MockStage{len(self.stages)}')
        self.stages.append(stage)
        pump()
        return stage

    def quit(self):
        for stage in self.stages:
            stage.quit()

    def dial(self, key='jog'):
        return self.surface.getControl('dial', 0, key)

    def turn(self, delta, key='jog'):
        """Turn the relative dial by *delta* detents, and block until it has been decided.

        The detent crosses a queued connection and then the direct-motion thread, so both
        are drained here.
        """
        self.surface.mockMove('dial', key, delta)
        pump()
        for stage in self.stages:
            controller = stage._directMotion
            if controller is not None:
                assert controller.waitUntilIdle(), "the direct motion thread never came back"
        pump()


@pytest.fixture
def rig(qapp):
    r = Rig()
    yield r
    r.quit()


@pytest.fixture
def textRig(qapp):
    r = Rig(TextDialSurface)
    yield r
    r.quit()


def paintLabel(rig, stage, key='jog'):
    """Repaint the dials and return the two lines of *key*'s label as a list."""
    stage._paintAxisControls()
    control = rig.dial(key)
    texts = [w['text'] for w in rig.surface.writesFor(control) if w['op'] == 'text']
    assert texts, "the dial was never painted"
    return texts[-1].split('\n')


def settle(stage):
    """Wait for the stage to stop moving and for its position to be reported."""
    assert pumpUntil(lambda: not stage.isMoving()), "the stage never stopped moving"
    pump(10)


# --------------------------------------------------------------------------- binding


class TestBinding:
    def test_no_controls_block_is_a_noop(self, rig):
        stage = rig.makeStage()
        assert stage._boundControls == {}
        assert stage._axisControls == {}
        assert rig.dial().owner is None
        assert rig.surface.writes == []

        startPos = stage.getPosition()
        rig.turn(5)
        settle(stage)
        np.testing.assert_allclose(stage.getPosition(), startPos, atol=1e-9)

    def test_binding_acquires_the_control(self, rig):
        stage = rig.makeStage(x=JOG)
        assert rig.dial().owner is stage
        assert set(stage._boundControls) == {'x'}
        assert set(stage._axisControls) == {0}

    def test_quit_releases_the_control(self, rig):
        stage = rig.makeStage(x=JOG)
        stage.quit()
        assert rig.dial().owner is None
        assert stage._boundControls == {}

    def test_absolute_dial_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="relative dials only"):
            rig.makeStage(x=FADER)

    def test_a_failed_binding_leaves_no_control_claimed(self, rig):
        """A stage whose control binding raises releases every control it acquired."""
        with pytest.raises(ValueError, match="relative dials only"):
            rig.makeStage(x=JOG, y=FADER)
        assert rig.dial().owner is None
        assert rig.dial('fader').owner is None

    def test_button_on_an_axis_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="not a dial"):
            rig.makeStage(x=BUTTON)

    def test_unknown_control_name_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="unknown control name"):
            rig.makeStage(enableX=JOG)

    def test_missing_step_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="needs a 'step'"):
            rig.makeStage(x={'device': 'Dock', 'type': 'dial', 'page': 0, 'key': 'jog'})

    def test_control_names_are_the_axis_names(self, rig):
        stage = rig.makeStage()
        assert stage.controlNames() == ['x', 'y', 'z']


# ---------------------------------------------------------------------------- movement


class TestMovement:
    def test_relative_dial_moves_the_target_by_delta_times_step(self, rig):
        stage = rig.makeStage(x=JOG)
        rig.turn(3)
        np.testing.assert_allclose(stage.targetPosition(), [15 * UM, 0, 0], atol=1e-12)
        settle(stage)
        np.testing.assert_allclose(stage.getPosition(), [15 * UM, 0, 0], atol=1e-7)

    def test_negative_delta_moves_the_other_way(self, rig):
        stage = rig.makeStage(x=JOG)
        rig.turn(-2)
        np.testing.assert_allclose(stage.targetPosition(), [-10 * UM, 0, 0], atol=1e-12)

    def test_one_dial_per_axis(self, qapp):
        rig = Rig(TwoDialSurface)
        try:
            stage = rig.makeStage(
                x=JOG,
                z={'device': 'Dock', 'type': 'dial', 'page': 0, 'key': 'jog2', 'step': UM},
            )
            np.testing.assert_allclose(stage._axisControls[2]['step'], UM)
            rig.turn(4, key='jog2')
            np.testing.assert_allclose(stage.targetPosition(), [0, 0, 4 * UM], atol=1e-12)
        finally:
            rig.quit()

    def test_successive_detents_accumulate_from_the_reached_position(self, rig):
        stage = rig.makeStage(x=JOG)
        rig.turn(3)
        settle(stage)
        rig.turn(3)
        np.testing.assert_allclose(stage.targetPosition(), [30 * UM, 0, 0], atol=1e-7)

    def test_detents_landing_during_our_own_move_collapse_into_one_more(self, rig):
        """The speed is slow enough that the first move is still running when the second
        burst of detents lands."""
        stage = rig.makeStage(
            x={
                'device': 'Dock',
                'type': 'dial',
                'page': 0,
                'key': 'jog',
                'step': 5 * UM,
                'speed': 20e-6,
            }
        )
        rig.turn(3)
        assert stage.isMoving()
        rig.turn(3)
        np.testing.assert_allclose(stage.targetPosition(), [15 * UM, 0, 0], atol=1e-12)
        np.testing.assert_allclose(stage.directMotion._desired, [30 * UM, 0, 0], atol=1e-12)

        assert pumpUntil(lambda: abs(stage.targetPosition()[0] - 30 * UM) < 1e-9), (
            "the accumulated gesture was never issued"
        )
        settle(stage)
        np.testing.assert_allclose(stage.getPosition(), [30 * UM, 0, 0], atol=1e-7)


class TestAxisScale:
    """``step`` is a length in metres, whatever units the device itself counts in.

    ``move()`` and ``getPosition()`` are in device coordinates, so a dial binding divides
    ``step`` by the axis scale. These tests use :data:`DOVER_SCALE`; ``globalPosition()``
    is the independent witness and must move ``+step`` per positive detent on every axis.
    """

    def test_detent_moves_the_metric_distance_on_a_positive_scaled_axis(self, rig):
        stage = rig.makeStage(scale=DOVER_SCALE, y=JOG)
        rig.turn(1)
        # 5 um of travel is 5e-3 device units on a millimetre stage, not 5e-6 of them
        np.testing.assert_allclose(stage.targetPosition(), [0, 5e-3, 0], atol=1e-12)
        settle(stage)
        np.testing.assert_allclose(stage.globalPosition(), [0, 5 * UM, 0], atol=1e-9)

    def test_detent_moves_the_metric_distance_on_a_negative_scaled_axis(self, rig):
        stage = rig.makeStage(scale=DOVER_SCALE, x=JOG)
        rig.turn(1)
        # the device coordinate goes *down* on an inverted axis; the operator's does not
        np.testing.assert_allclose(stage.targetPosition(), [-5e-3, 0, 0], atol=1e-12)
        settle(stage)
        np.testing.assert_allclose(stage.globalPosition(), [5 * UM, 0, 0], atol=1e-9)

    def test_positive_detent_always_raises_the_global_coordinate(self, qapp):
        for axis, name in ((0, 'x'), (1, 'y'), (2, 'z')):
            rig = Rig()
            try:
                stage = rig.makeStage(scale=DOVER_SCALE, **{name: JOG})
                start = stage.globalPosition()
                rig.turn(2)
                settle(stage)
                moved = stage.globalPosition() - start
                expected = np.zeros(3)
                expected[axis] = 2 * 5 * UM
                np.testing.assert_allclose(moved, expected, atol=1e-9)
                assert moved[axis] > 0, f"a positive detent lowered global {name}"
            finally:
                rig.quit()

    def test_negative_detent_lowers_the_global_coordinate_on_an_inverted_axis(self, rig):
        stage = rig.makeStage(scale=DOVER_SCALE, z=JOG)
        start = stage.globalPosition()
        rig.turn(-3)
        settle(stage)
        np.testing.assert_allclose(stage.globalPosition() - start, [0, 0, -15 * UM], atol=1e-9)

    def test_zero_axis_scale_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="configured 'scale' for that axis is 0"):
            rig.makeStage(scale=(0, 1e-3, 1e-3), x=JOG)


class TestReseeding:
    """Where a detent counts from: the dial keeps no target of its own, so the direct-motion
    controller counts from the gesture in progress or else from :meth:`Stage.targetPosition`.
    """

    def test_external_move_reseeds_the_target(self, rig):
        stage = rig.makeStage(x=JOG)
        rig.turn(1)
        settle(stage)

        # somebody else drives the stage
        stage.move([100 * UM, 0, 0], speed='fast').wait(timeout=5)
        pump(10)

        rig.turn(1)
        np.testing.assert_allclose(stage.targetPosition(), [105 * UM, 0, 0], atol=1e-6)

    def test_a_detent_during_a_programmatic_move_does_nothing(self, rig):
        stage = rig.makeStage(x=JOG)
        external = stage.move([500 * UM, 0, 0], speed=50e-6)
        assert pumpUntil(lambda: stage.getPosition()[0] > 20 * UM, timeout=5)
        assert stage.isMoving()

        rig.turn(1)

        assert stage._activeTask is external
        np.testing.assert_allclose(stage.targetPosition(), [500 * UM, 0, 0], atol=1e-12)
        assert stage.directMotion._desired is None
        external.stop()

    def test_our_own_move_is_not_treated_as_external(self, rig):
        stage = rig.makeStage(
            x={
                'device': 'Dock',
                'type': 'dial',
                'page': 0,
                'key': 'jog',
                'step': 5 * UM,
                'speed': 20e-6,
            }
        )
        rig.turn(3)
        assert stage.isMoving()
        # updates during the dial's own move are progress toward its target, not somebody
        # else driving the stage
        pump(5)
        np.testing.assert_allclose(stage.targetPosition(), [15 * UM, 0, 0], atol=1e-12)


# --------------------------------------------------------------------------- appearance


class TestAppearance:
    def test_dial_shows_axis_name_and_position(self, textRig):
        stage = textRig.makeStage(x=JOG)
        textRig.turn(2)
        settle(stage)
        stage._paintAxisControls()

        texts = [w['text'] for w in textRig.surface.writesFor(textRig.dial()) if w['op'] == 'text']
        assert texts, "the dial was never painted"
        assert texts[-1].startswith('x\n')
        assert texts[-1].split('\n')[1].endswith(' mm')

    def test_dial_label_is_a_real_length_on_a_scaled_stage(self, qapp):
        """The stage is driven straight to a device coordinate rather than by turning the
        dial, so this checks the label alone."""
        rig = Rig(TextDialSurface)
        try:
            stage = rig.makeStage(scale=DOVER_SCALE, x=JOG)
            stage.move([-10e-3, 0, 0], speed='fast').wait(timeout=5)
            pump(10)
            stage._paintAxisControls()

            texts = [w['text'] for w in rig.surface.writesFor(rig.dial()) if w['op'] == 'text']
            assert texts, "the dial was never painted"
            name, shown = texts[-1].split('\n')
            assert name == 'x'
            np.testing.assert_allclose(pg.siEval(shown), 10 * UM, rtol=1e-3)
            np.testing.assert_allclose(pg.siEval(shown), stage.globalPosition()[0], rtol=1e-3)
        finally:
            rig.quit()

    @pytest.mark.parametrize(
        "devicePos,expected",
        [
            (-40.762, '40.762 mm'),  # a Dover parked near the far end of its travel
            (-0.0008, '0.001 mm'),  # sub-micrometre: still three decimals, not '800 nm'
            (-1200.0, '1200.000 mm'),  # over a metre of travel: still millimetres
            (25.4, '-25.400 mm'),  # an inverted axis the other side of its origin
            (0.0, '0.000 mm'),  # not '-0.000 mm', though this axis' scale is negative
        ],
    )
    def test_dial_label_is_millimetres_to_three_places(self, qapp, devicePos, expected):
        """The exact string is asserted: a change of unit, of precision or of the space
        before the suffix is a failure. The position is patched in rather than driven to,
        but the axis scale is still the configured one."""
        rig = Rig(TextDialSurface)
        try:
            stage = rig.makeStage(scale=DOVER_SCALE, x=JOG)
            with patch.object(stage, 'getPosition', return_value=[devicePos, 0, 0]):
                assert paintLabel(rig, stage) == ['x', expected]
        finally:
            rig.quit()

    def test_negative_position_is_painted_with_its_sign(self, qapp):
        rig = Rig(TextDialSurface)
        try:
            stage = rig.makeStage(scale=DOVER_SCALE, x=JOG)
            rig.turn(-1)
            settle(stage)
            assert stage.globalPosition()[0] < 0
            assert paintLabel(rig, stage) == ['x', '-0.005 mm']
        finally:
            rig.quit()

    def test_positive_detent_raises_the_number_on_every_axis(self, qapp):
        for name in ('x', 'y', 'z'):
            rig = Rig(TextDialSurface)
            try:
                stage = rig.makeStage(scale=DOVER_SCALE, **{name: JOG})
                before = float(paintLabel(rig, stage)[1].split()[0])
                rig.turn(20)  # 100 um, two orders of magnitude above the last digit
                settle(stage)
                after = float(paintLabel(rig, stage)[1].split()[0])
                assert after > before, f"a positive detent lowered the {name} label"
            finally:
                rig.quit()

    def test_painting_is_throttled(self, textRig):
        stage = textRig.makeStage(x=JOG)
        pump(5)
        stage.axisControlPaintInterval = 10.0
        stage._axisControlLastPaint = 0.0
        stage._scheduleAxisControlPaint()  # one paint, then the interval closes the door
        textRig.surface.clearWrites()

        for i in range(10):
            stage.posChanged([i * UM, 0, 0])
            pump(2)

        texts = [w for w in textRig.surface.writes if w['op'] == 'text']
        assert len(texts) == 0, f"{len(texts)} repaints inside one throttle interval"

    def test_dial_without_output_is_not_painted(self, qapp):
        # an X-Keys-hosted binding: the axis still moves
        rig = Rig(BlindDialSurface)
        try:
            stage = rig.makeStage(x=JOG)
            assert stage._axisControls[0]['paintable'] is False
            rig.turn(2)
            np.testing.assert_allclose(stage.targetPosition(), [10 * UM, 0, 0], atol=1e-12)
            assert rig.surface.writes == []
        finally:
            rig.quit()


class TestPressHook:
    def test_press_calls_the_hook_and_does_not_move(self, rig):
        stage = rig.makeStage(x=JOG)
        seen = []
        stage.axisDialPressed = seen.append
        before = stage.getPosition()

        rig.surface.mockPress('dial', 'jog')
        pump()

        assert seen == [0]
        assert not stage.isMoving()
        np.testing.assert_allclose(stage.getPosition(), before, atol=1e-12)

    def test_default_hook_does_nothing(self, rig):
        stage = rig.makeStage(x=JOG)
        assert stage.axisDialPressed(0) is None
