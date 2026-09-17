"""DoverStage's axis-enable toggles, declared in the base ``controls:`` config block.

Runs headless against :class:`MockControlSurface` and a stand-in for the motionsynergy
``smartstage`` object; no DLLs and no hardware.

Both spellings are exercised: one toggle per axis (``enableX``/``enableY``/``enableZ``) and
``enableXY``, the single key covering x and y, whose whole point is that x and y cannot end
up disagreeing through it.

Two surfaces are in play, because how a toggle indicates its state depends entirely on
what its control can show: the stock mock, whose display keys take text and whose lit keys
stand in for an X-Keys key (one blue and one red LED, so no green at all), and
:class:`AnyColorSurface`, whose lit keys take any colour and so exercise the colour-only
path that a two-LED key cannot reach.
"""

from __future__ import annotations

import numpy as np
import pytest
from unittest import mock

from acq4.devices.DoverStage.doverstage import DoverStage
from acq4.devices.MockControlSurface import MockControlSurface
from acq4.panic import GlobalHalt
from acq4.util import Qt

IMG_KEYS = [('img', 0, 0), ('img', 0, 1), ('img', 0, 2)]
LIT_KEY = ('lit', 0, 0)
XY_KEY, Z_KEY = IMG_KEYS[0], IMG_KEYS[2]

#: Every (x, y) state a toggle can be pressed from, and the matched state a press must
#: land on: disabled only from both-enabled, enabled from everything else -- including the
#: two mismatches, which a press resolves rather than carries forward.
XY_PRESS_RULE = [
    ((True, True), False),
    ((True, False), True),
    ((False, True), True),
    ((False, False), True),
]


def pump(iterations=5):
    for _ in range(iterations):
        Qt.QApplication.processEvents()


class AnyColorSurface(MockControlSurface):
    """A surface whose lit keys take any colour, as a full-colour LED keypad would.

    The stock lit block stands in for a key lit by one blue and one red LED and refuses
    any colour with green in it -- which both axis-enable colours have -- so it is no
    place to watch the colour-only indicator actually paint.
    """

    LIT_BUTTON_CAPS = {'input': {'press': True}, 'output': {'color': True}}


class FakeSmartStage:
    """The motionsynergy 'smartstage' surface DoverStage uses. Records commands."""

    def __init__(self):
        self.default_acceleration = None
        self.control_thread = type('ct', (), {'poll_interval': 0.1})()
        self._pos = np.zeros(3)
        self._enabled = [False, False, False]
        self.enabledCallback = None
        #: every per-axis enable/disable asked of this driver, as ``(op, axis)``. The real
        #: driver checks each axis before acting, so the interesting thing about a press is
        #: not how many commands it sends but that they all say the same thing.
        self.commands = []

    def enable(self):
        self._enabled = [True, True, True]

    def comeUpWith(self, enabled):
        """Start from *enabled* and do not enable everything on connect.

        The stage keeps its enabled state across restarts, so DoverStage can meet axes
        that already disagree; the real ``enable()`` is what hides that in every other
        test here.
        """
        self._enabled = list(enabled)
        self.enable = lambda: None

    def pos(self, refresh=False):
        return self._pos.copy()

    def set_callback(self, cb):
        pass

    def is_enabled(self, refresh=False):
        return tuple(self._enabled)

    def set_enabled_callback(self, cb):
        self.enabledCallback = cb

    def enable_axis(self, axis):
        self.commands.append(('enable', axis))
        self._enabled[axis] = True
        self._report()

    def disable_axis(self, axis):
        self.commands.append(('disable', axis))
        self._enabled[axis] = False
        self._report()

    def setEnabled(self, enabled):
        """Change the state behind acq4's back, as the MotionSynergy tray menu does."""
        self._enabled = list(enabled)
        self._report()

    def _report(self):
        """Stand in for the control thread noticing the state change and calling back."""
        if self.enabledCallback is not None:
            self.enabledCallback(tuple(self._enabled))


class FakeDM:
    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.devices = {}

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def readConfigFile(self, fn):
        return {}


@pytest.fixture
def rig(qapp):
    dm = FakeDM()
    surface = MockControlSurface(dm, {}, 'Dock')
    dm.devices['Dock'] = surface
    dm.devices['Color'] = AnyColorSurface(dm, {}, 'Color')
    driver = FakeSmartStage()
    devices = []

    def makeStage(**controls):
        config = {'driver': 'DoverStage', 'dllPath': 'unused-in-tests'}
        if controls:
            config['controls'] = controls
        with mock.patch(
            'acq4.devices.DoverStage.doverstage.get_client',
            return_value={'smartstage': driver},
        ):
            with mock.patch('acq4.Manager.Manager.single', dm):
                dev = DoverStage(dm, config, 'DoverStage')
        devices.append(dev)
        pump()
        return dev

    yield dm, surface, driver, makeStage
    for dev in devices:
        dev.quit()


def labelsFor(surface, control):
    """Return the ``(text, background)`` pairs *control* was asked to show, in order.

    The mock's display keys take text with a background colour, which is the shape the
    axis-enable indicator wants: the axis letter and its state arrive in one write, so
    they cannot disagree on the panel.
    """
    return [(w['text'], w['background']) for w in surface.writesFor(control) if w['op'] == 'text']


def colorsFor(surface, control):
    """Return the colours *control* was asked to show, in order."""
    return [w['color'] for w in surface.writesFor(control) if w['op'] == 'color']


def enableConf(key, device='Dock', type='button'):
    return {'device': device, 'type': type, 'page': 0, 'key': key}


class TestAxisEnableControls:
    def test_names_extend_the_base_axis_names(self, rig):
        _, _, _, makeStage = rig
        stage = makeStage()
        assert stage.controlNames() == [
            'x',
            'y',
            'z',
            'enableX',
            'enableY',
            'enableZ',
            'enableXY',
        ]

    def test_toggles_are_acquired_and_painted_for_the_initial_state(self, rig):
        dm, surface, driver, makeStage = rig
        stage = makeStage(enableX=enableConf(IMG_KEYS[0]))
        control = surface.getControl('button', 0, IMG_KEYS[0])
        assert control.owner is stage
        # DoverStage.__init__ enables every axis, so the toggle comes up green
        writes = labelsFor(surface, control)
        assert writes, "the toggle was never painted"
        assert writes[-1] == ('X', DoverStage.AXIS_ENABLED_COLOR)

    def test_the_label_is_the_axis_letter_and_needs_no_configuration(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage(
            enableX=enableConf(IMG_KEYS[0]),
            enableY=enableConf(IMG_KEYS[1]),
            enableZ=enableConf(IMG_KEYS[2]),
        )
        labels = [
            labelsFor(surface, surface.getControl('button', 0, key))[-1][0] for key in IMG_KEYS
        ]
        assert labels == ['X', 'Y', 'Z']

    def test_press_toggles_the_axis_and_repaints(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage(enableY=enableConf(IMG_KEYS[1]))
        control = surface.getControl('button', 0, IMG_KEYS[1])

        surface.mockPress('button', IMG_KEYS[1])
        pump()
        assert driver.is_enabled() == (True, False, True)
        assert labelsFor(surface, control)[-1] == ('Y', DoverStage.AXIS_DISABLED_COLOR)

        surface.mockPress('button', IMG_KEYS[1])
        pump()
        assert driver.is_enabled() == (True, True, True)
        assert labelsFor(surface, control)[-1] == ('Y', DoverStage.AXIS_ENABLED_COLOR)

    def test_driver_state_change_repaints_without_a_press(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage(enableZ=enableConf(IMG_KEYS[2]))
        control = surface.getControl('button', 0, IMG_KEYS[2])
        surface.clearWrites()

        # somebody disabled the axis outside acq4; the control thread reports it
        driver._enabled[2] = False
        driver._report()
        pump()

        assert labelsFor(surface, control)[-1] == ('Z', DoverStage.AXIS_DISABLED_COLOR)

    def test_quit_releases_the_toggle_and_unsubscribes(self, rig):
        dm, surface, driver, makeStage = rig
        stage = makeStage(enableX=enableConf(IMG_KEYS[0]))
        stage.quit()
        assert surface.getControl('button', 0, IMG_KEYS[0]).owner is None
        assert driver.enabledCallback is None

    def test_no_controls_block_does_not_subscribe(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage()
        assert driver.enabledCallback is None
        assert surface.writes == []


class TestAxisEnableDegradation:
    """What a toggle shows on a control that cannot show all of it, or any of it."""

    def test_a_control_that_cannot_draw_text_keeps_the_colour_and_loses_the_label(
        self, rig, caplog
    ):
        dm, surface, driver, makeStage = rig
        colorSurface = dm.devices['Color']
        with caplog.at_level('WARNING'):
            makeStage(enableX=enableConf(LIT_KEY, device='Color'))
        assert "cannot draw text" in caplog.text and "'X' label" in caplog.text

        control = colorSurface.getControl('button', 0, LIT_KEY)
        last = colorsFor(colorSurface, control)[-1]
        assert (last.red(), last.green(), last.blue()) == DoverStage.AXIS_ENABLED_COLOR

        colorSurface.mockPress('button', LIT_KEY)
        pump()
        assert driver.is_enabled() == (False, True, True)
        last = colorsFor(colorSurface, control)[-1]
        assert (last.red(), last.green(), last.blue()) == DoverStage.AXIS_DISABLED_COLOR

    def test_a_two_led_key_refuses_both_colours_and_indicates_nothing(self, rig, caplog):
        """Degrade loudly: both colours have green in them, which a blue and a red LED
        cannot make, so the key indicates nothing -- said once, at bind time, while the
        toggle keeps working."""
        dm, surface, driver, makeStage = rig
        with caplog.at_level('WARNING'):
            stage = makeStage(enableY=enableConf(LIT_KEY))
        assert 'will not indicate the state of axis' in caplog.text
        assert stage._axisEnablePainters == {}
        control = surface.getControl('button', 0, LIT_KEY)
        assert surface.writesFor(control) == []

        caplog.clear()
        with caplog.at_level('WARNING'):
            surface.mockPress('button', LIT_KEY)
            pump()
        assert driver.is_enabled() == (True, False, True)
        assert surface.writesFor(control) == []
        assert caplog.text == ''

    def test_a_control_with_no_output_at_all_indicates_nothing(self, rig, caplog):
        dm, surface, driver, makeStage = rig
        with caplog.at_level('WARNING'):
            stage = makeStage(enableZ=enableConf('fader', type='dial'))
        assert 'will not indicate the state of axis' in caplog.text
        assert stage._axisEnablePainters == {}

        caplog.clear()
        with caplog.at_level('WARNING'):
            driver._enabled[2] = False
            driver._report()
            pump()
        assert surface.writes == []
        assert caplog.text == ''


class TestXYEnableToggle:
    """``enableXY``: one key for x and y, which cannot leave them disagreeing.

    Presses are checked against :data:`XY_PRESS_RULE` from every starting state, mismatches
    included, because a mismatch is reachable without this key -- the stage comes up
    however it was left, and the MotionSynergy tray menu toggles each axis on its own.
    """

    def test_press_with_both_enabled_disables_both(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage(enableXY=enableConf(XY_KEY))
        control = surface.getControl('button', 0, XY_KEY)
        assert labelsFor(surface, control)[-1] == ('XY', DoverStage.AXIS_ENABLED_COLOR)

        surface.mockPress('button', XY_KEY)
        pump()
        assert driver.is_enabled() == (False, False, True)
        assert labelsFor(surface, control)[-1] == ('XY', DoverStage.AXIS_DISABLED_COLOR)

    def test_press_with_both_disabled_enables_both(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage(enableXY=enableConf(XY_KEY))
        control = surface.getControl('button', 0, XY_KEY)
        driver.setEnabled((False, False, True))
        pump()
        assert labelsFor(surface, control)[-1] == ('XY', DoverStage.AXIS_DISABLED_COLOR)

        surface.mockPress('button', XY_KEY)
        pump()
        assert driver.is_enabled() == (True, True, True)
        assert labelsFor(surface, control)[-1] == ('XY', DoverStage.AXIS_ENABLED_COLOR)

    def test_press_from_a_mismatch_lands_on_a_matched_state(self, rig):
        """The core requirement: a press out of x != y leaves x == y, and enabled."""
        dm, surface, driver, makeStage = rig
        makeStage(enableXY=enableConf(XY_KEY))
        control = surface.getControl('button', 0, XY_KEY)

        for mixed in ((True, False), (False, True)):
            driver.setEnabled(mixed + (True,))
            pump()
            assert labelsFor(surface, control)[-1] == ('XY!', DoverStage.AXIS_MIXED_COLOR)

            surface.mockPress('button', XY_KEY)
            pump()
            enabled = driver.is_enabled()
            assert enabled[0] == enabled[1], f"press from {mixed} left x and y disagreeing"
            assert enabled[:2] == (True, True)
            assert labelsFor(surface, control)[-1] == ('XY', DoverStage.AXIS_ENABLED_COLOR)

    def test_no_press_can_produce_a_mismatch(self, rig):
        """From every starting state, and pressed again from where that landed."""
        dm, surface, driver, makeStage = rig
        makeStage(enableXY=enableConf(XY_KEY))

        for start, target in XY_PRESS_RULE:
            driver.setEnabled(start + (True,))
            driver.commands.clear()
            pump()

            surface.mockPress('button', XY_KEY)
            pump()
            enabled = driver.is_enabled()
            assert enabled[0] == enabled[1], f"press from {start} left x and y disagreeing"
            assert enabled[:2] == (target, target), f"press from {start} did not follow the rule"
            # one decision applied to both axes, never a toggle per axis: the commands of a
            # single press all say the same thing, whatever state it started from
            assert {op for op, _ in driver.commands} == {'enable' if target else 'disable'}
            assert sorted(axis for _, axis in driver.commands) == [0, 1]

            surface.mockPress('button', XY_KEY)
            pump()
            enabled = driver.is_enabled()
            assert enabled[0] == enabled[1], f"second press from {start} broke the match"

    def test_a_mismatch_at_startup_is_shown_rather_than_assumed_away(self, rig):
        dm, surface, driver, makeStage = rig
        driver.comeUpWith((True, False, True))
        makeStage(enableXY=enableConf(XY_KEY))
        control = surface.getControl('button', 0, XY_KEY)
        assert labelsFor(surface, control)[-1] == ('XY!', DoverStage.AXIS_MIXED_COLOR)

    def test_the_mixed_indicator_is_distinct_from_both_settled_ones(self, rig):
        """A rig owner has to see that something is wrong, not read a confident green."""
        dm, surface, driver, makeStage = rig
        makeStage(enableXY=enableConf(XY_KEY))
        control = surface.getControl('button', 0, XY_KEY)

        shown = {}
        for state in ((True, True, True), (True, False, True), (False, False, True)):
            driver.setEnabled(state)
            pump()
            shown[state] = labelsFor(surface, control)[-1]

        assert len(set(shown.values())) == 3, f"two of these states look the same: {shown}"
        # distinct in the colour *and* in the glyphs, because red, green and amber are
        # three fields red-green colour blindness cannot be relied on to separate
        assert len({color for _, color in shown.values()}) == 3
        assert len({text for text, _ in shown.values()}) == 2
        assert shown[(True, False, True)] == ('XY!', DoverStage.AXIS_MIXED_COLOR)

    def test_a_driver_side_change_repaints_without_a_press(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage(enableXY=enableConf(XY_KEY))
        control = surface.getControl('button', 0, XY_KEY)
        surface.clearWrites()

        driver.setEnabled((True, False, True))  # somebody disabled y outside acq4
        pump()
        assert labelsFor(surface, control)[-1] == ('XY!', DoverStage.AXIS_MIXED_COLOR)

        driver.setEnabled((False, False, True))  # ... and then x as well
        pump()
        assert labelsFor(surface, control)[-1] == ('XY', DoverStage.AXIS_DISABLED_COLOR)

    def test_z_keeps_its_own_toggle_and_is_untouched_by_the_xy_key(self, rig):
        dm, surface, driver, makeStage = rig
        makeStage(enableXY=enableConf(XY_KEY), enableZ=enableConf(Z_KEY))
        zControl = surface.getControl('button', 0, Z_KEY)

        surface.mockPress('button', XY_KEY)
        pump()
        assert driver.is_enabled() == (False, False, True)
        assert labelsFor(surface, zControl)[-1] == ('Z', DoverStage.AXIS_ENABLED_COLOR)

        surface.mockPress('button', Z_KEY)
        pump()
        assert driver.is_enabled() == (False, False, False)
        assert labelsFor(surface, surface.getControl('button', 0, XY_KEY))[-1] == (
            'XY',
            DoverStage.AXIS_DISABLED_COLOR,
        )

    def test_quit_releases_the_toggle_and_unsubscribes(self, rig):
        dm, surface, driver, makeStage = rig
        stage = makeStage(enableXY=enableConf(XY_KEY))
        stage.quit()
        assert surface.getControl('button', 0, XY_KEY).owner is None
        assert driver.enabledCallback is None


class TestXYEnableCoexistence:
    """Two keys claiming the same axis is refused at startup, in either order.

    Press one and the other's indicator is stale, with nothing on the panel to say which
    key last won -- there is no reading of that worth shipping to a bench, so it is a
    configuration error rather than a race to watch for.
    """

    def test_enableXY_with_enableX_is_refused(self, rig):
        dm, surface, driver, makeStage = rig
        with pytest.raises(ValueError, match="already toggles"):
            makeStage(enableXY=enableConf(XY_KEY), enableX=enableConf(IMG_KEYS[1]))

    def test_enableX_with_enableXY_is_refused_too(self, rig):
        dm, surface, driver, makeStage = rig
        with pytest.raises(ValueError, match="already toggles"):
            makeStage(enableX=enableConf(IMG_KEYS[1]), enableXY=enableConf(XY_KEY))

    def test_enableXY_with_enableY_is_refused(self, rig):
        dm, surface, driver, makeStage = rig
        with pytest.raises(ValueError, match=r"axis 'y'"):
            makeStage(enableXY=enableConf(XY_KEY), enableY=enableConf(IMG_KEYS[1]))

    def test_the_error_names_both_keys_and_the_axes_they_share(self, rig):
        dm, surface, driver, makeStage = rig
        with pytest.raises(ValueError) as exc:
            makeStage(enableX=enableConf(IMG_KEYS[1]), enableXY=enableConf(XY_KEY))
        message = str(exc.value)
        assert "'enableX'" in message and "'enableXY'" in message
        assert "axes 'x' and 'y'" in message and "axis 'x' in common" in message

    def test_enableXY_and_enableZ_are_fine_together(self, rig):
        dm, surface, driver, makeStage = rig
        stage = makeStage(enableXY=enableConf(XY_KEY), enableZ=enableConf(Z_KEY))
        assert sorted(stage._axisEnableControls) == [(0, 1), (2,)]

    def test_the_per_axis_spelling_still_binds_all_three(self, rig):
        dm, surface, driver, makeStage = rig
        stage = makeStage(
            enableX=enableConf(IMG_KEYS[0]),
            enableY=enableConf(IMG_KEYS[1]),
            enableZ=enableConf(IMG_KEYS[2]),
        )
        assert sorted(stage._axisEnableControls) == [(0,), (1,), (2,)]


class TestXYEnableDegradation:
    """What the xy toggle shows on a control that cannot show all of it, or any of it."""

    def test_a_colour_only_control_keeps_all_three_colours_and_loses_the_label(self, rig, caplog):
        dm, surface, driver, makeStage = rig
        colorSurface = dm.devices['Color']
        with caplog.at_level('WARNING'):
            makeStage(enableXY=enableConf(LIT_KEY, device='Color'))
        assert "cannot draw text" in caplog.text and "axes 'x' and 'y'" in caplog.text

        control = colorSurface.getControl('button', 0, LIT_KEY)
        expected = [
            ((True, True, True), DoverStage.AXIS_ENABLED_COLOR),
            ((True, False, True), DoverStage.AXIS_MIXED_COLOR),
            ((False, False, True), DoverStage.AXIS_DISABLED_COLOR),
        ]
        for state, color in expected:
            driver.setEnabled(state)
            pump()
            last = colorsFor(colorSurface, control)[-1]
            assert (last.red(), last.green(), last.blue()) == color

        colorSurface.mockPress('button', LIT_KEY)
        pump()
        assert driver.is_enabled() == (True, True, True)

    def test_a_two_led_key_indicates_nothing_but_still_matches_the_axes(self, rig, caplog):
        """All three colours have green in them, so a blue and a red LED can show none of
        them: the key indicates nothing -- said once, at bind time -- and the toggle keeps
        working, mismatch recovery included."""
        dm, surface, driver, makeStage = rig
        with caplog.at_level('WARNING'):
            stage = makeStage(enableXY=enableConf(LIT_KEY))
        assert "will not indicate the state of axes 'x' and 'y'" in caplog.text
        assert stage._axisEnablePainters == {}
        control = surface.getControl('button', 0, LIT_KEY)
        assert surface.writesFor(control) == []

        driver.setEnabled((True, False, True))
        caplog.clear()
        with caplog.at_level('WARNING'):
            surface.mockPress('button', LIT_KEY)
            pump()
        assert driver.is_enabled() == (True, True, True)
        assert surface.writesFor(control) == []
        assert caplog.text == ''

    def test_a_control_with_no_output_at_all_indicates_nothing(self, rig, caplog):
        dm, surface, driver, makeStage = rig
        with caplog.at_level('WARNING'):
            stage = makeStage(enableXY=enableConf('fader', type='dial'))
        assert "will not indicate the state of axes 'x' and 'y'" in caplog.text
        assert stage._axisEnablePainters == {}

        caplog.clear()
        with caplog.at_level('WARNING'):
            driver.setEnabled((True, False, True))
            pump()
        assert surface.writes == []
        assert caplog.text == ''


# ----------------------------------------------------------------------- docstring


def test_the_docstring_examples_parse_as_rig_config(rig, tmp_path):
    """pyqtgraph.configfile evals every value, so an example can be wrong in the docs.

    A bare-key inline dict *value* (``{device: 'Dock'}``) raises ParseError, so those keys
    stay quoted; a config *key* is taken literally, quotes included, so ``enableXY:`` has
    to be written bare. Each example is also checked against what this device actually
    accepts, overlapping enable toggles included -- an example that would raise at startup
    is worse than no example.
    """
    import re
    import textwrap

    from pyqtgraph import configfile

    _, _, _, makeStage = rig
    known = set(makeStage().controlNames())

    examples = re.findall(
        r'[Ee]xample configuration[^:]*::\n\n(.*?)(?:\n\n|\Z)', DoverStage.__doc__, re.S
    )
    assert len(examples) == 2, "the DoverStage docstring lost an example configuration"
    for i, example in enumerate(examples):
        path = tmp_path / f'devices{i}.cfg'
        path.write_text(textwrap.dedent(example), newline='\n')
        config = configfile.readConfigFile(str(path))
        controls = list(config.values())[0]['controls']
        assert controls
        for name, spec in controls.items():
            assert isinstance(spec, dict), f"{name!r} did not parse as a dict"
            assert 'device' in spec and 'key' in spec
            assert name == name.strip('\'"'), f"config key {name!r} kept its quotes"
            assert name in known, f"{name!r} is not a control this device accepts"
        assert 'enableXY' not in controls or not {'enableX', 'enableY'} & set(
            controls
        ), f"example {i} binds enableXY alongside a per-axis toggle, which raises"
