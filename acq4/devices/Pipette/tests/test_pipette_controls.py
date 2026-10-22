"""Named pipette moves bound to control-surface buttons.

Everything here runs headless against :class:`MockControlSurface` and :class:`MockStage`;
no hardware and no real Manager are involved. Control signals arrive over queued
connections, so tests pump the Qt event loop after injecting a press.

The dispatch tests watch :meth:`Pipette.moveTo` rather than the motion planner, because
most of the computed destinations (``search``, ``park``, ``aboveTarget``) need a
microscope, a camera and a detected sample surface to resolve a coordinate at all, and
what a binding is responsible for is choosing the right *name*. One test then follows
``home`` all the way to the planner, which is where the Panic Lock guard lives, so the
dispatch is known to reach the guarded path rather than some private shortcut.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from acq4.devices.MockControlSurface import MockControlSurface
from acq4.devices.MockStage import MockStage
from acq4.devices.Pipette import Pipette
from acq4.panic import GlobalHalt
from acq4.util import Qt

#: A display key: images, text and any colour, like a Stream Dock key.
KEY = {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ['img', 0, 0]}
#: A lit-but-displayless key: one colour, no text, like an X-Keys key.
LIT_KEY = {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ['lit', 0, 0]}
#: An absolute dial with no press input at all.
FADER = {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': 'fader'}


def pump(iterations=5):
    """Deliver queued Qt events so that control signals arrive."""
    for _ in range(iterations):
        Qt.QApplication.processEvents()


def keyAt(*key):
    """A display-key address at grid position *key*."""
    return {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ['img', *key]}


class MockDM:
    """Just enough device manager for a Pipette, a manipulator and one control surface.

    Config files are kept in memory so that a stored stage home position survives being
    written and read back, which is what ``goHome`` needs to reach the planner at all.
    """

    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.devices = {}
        self.config = {}
        self.moves = []  # names of the motion plans asked for
        self._files = {}

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def readConfigFile(self, fn):
        return self._files.get(fn, {})

    def writeConfigFile(self, data, fn):
        self._files[fn] = dict(data)

    def move(self, *specs, name: str = ""):
        self.moves.append(name)
        return MagicMock()


class Rig:
    """A mock surface and manipulator, plus a factory for pipettes bound to them."""

    def __init__(self, surfaceClass=MockControlSurface):
        self.dm = MockDM()
        self.surface = surfaceClass(self.dm, {}, 'Dock')
        self.dm.devices['Dock'] = self.surface
        with patch("acq4.Manager.Manager.single", self.dm):
            self.stage = MockStage(
                self.dm, {'driver': 'MockStage', 'nAxes': 3, 'isManipulator': True}, 'Manip1'
            )
        self.dm.devices['Manip1'] = self.stage
        self.pipettes = []

    def makePipette(self, **controls):
        config = {'driver': 'Pipette', 'parentDevice': 'Manip1', 'pitch': 30.0, 'yaw': 0.0}
        if controls:
            config['controls'] = controls
        with patch("acq4.Manager.Manager.single", self.dm):
            pip = Pipette(self.dm, config, f'Pipette{len(self.pipettes) + 1}')
        self.pipettes.append(pip)
        pump()
        return pip

    def control(self, *key):
        return self.surface.getControl('button', 0, ('img', *key))

    def litControl(self, *key):
        return self.surface.getControl('button', 0, ('lit', *key))

    def press(self, *key, block='img'):
        self.surface.mockPress('button', (block, *key))
        pump()

    def textsFor(self, control):
        return [w['text'] for w in self.surface.writesFor(control) if w['op'] == 'text']

    def quit(self):
        for pip in self.pipettes:
            pip.quit()
        self.stage.quit()


@pytest.fixture
def rig(qapp):
    r = Rig()
    yield r
    r.quit()


def recordMoves(pip):
    """Replace moveTo() with a recorder, returning the list it appends to."""
    calls = []
    pip.moveTo = lambda position, speed, **kwds: calls.append((position, speed, kwds))
    return calls


# --------------------------------------------------------------------------- binding


class TestBinding:
    def test_no_controls_block_is_a_noop(self, rig):
        pip = rig.makePipette()
        assert pip._boundControls == {}
        assert pip._moveControls == {}
        assert rig.control(0, 0).owner is None
        assert rig.surface.writes == []

        calls = recordMoves(pip)
        rig.press(0, 0)
        assert calls == []

    def test_binding_acquires_and_labels_the_control(self, rig):
        pip = rig.makePipette(home=KEY)
        assert rig.control(0, 0).owner is pip
        assert set(pip._boundControls) == {'home'}
        assert rig.textsFor(rig.control(0, 0)) == ['home']

    def test_quit_releases_the_control(self, rig):
        pip = rig.makePipette(home=KEY)
        pip.quit()
        assert rig.control(0, 0).owner is None
        assert pip._boundControls == {}
        assert pip._moveControls == {}

    def test_released_control_can_be_claimed_again(self, rig):
        """Control.acquire is strictly once until released, so a leak would show here."""
        first = rig.makePipette(home=KEY)
        first.quit()
        second = rig.makePipette(home=KEY)
        assert rig.control(0, 0).owner is second

    def test_control_names_are_the_computed_moves(self, rig):
        pip = rig.makePipette()
        assert pip.controlNames() == [
            'home',
            'search',
            'approach',
            'target',
            'aboveTarget',
            'park',
        ]

    def test_unknown_name_raises_naming_the_accepted_set(self, rig):
        with pytest.raises(ValueError) as exc:
            rig.makePipette(retract=KEY)
        message = str(exc.value)
        assert "unknown control name 'retract'" in message
        for name in ('home', 'search', 'approach', 'target', 'aboveTarget', 'park'):
            assert name in message
        assert "'position'" in message

    def test_missing_key_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="needs a 'key'"):
            rig.makePipette(home={'device': 'Dock', 'type': 'button', 'page': 0})

    def test_missing_device_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="needs a 'device' key"):
            rig.makePipette(home={'type': 'button', 'page': 0, 'key': ['img', 0, 0]})

    def test_a_control_that_cannot_be_pressed_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="no press input"):
            rig.makePipette(home=FADER)

    def test_two_entries_on_one_key_is_a_config_error(self, rig):
        from acq4.devices.ControlSurface import ControlInUse

        with pytest.raises(ControlInUse):
            rig.makePipette(home=KEY, park=dict(KEY))


    def test_a_controls_block_that_is_not_a_dict_is_a_config_error(self, rig):
        with pytest.raises(TypeError, match="must be a dict"):
            with patch("acq4.Manager.Manager.single", rig.dm):
                Pipette(
                    rig.dm,
                    {
                        'driver': 'Pipette',
                        'parentDevice': 'Manip1',
                        'pitch': 30.0,
                        'yaw': 0.0,
                        'controls': ['home'],
                    },
                    'PipetteBad',
                )


# -------------------------------------------------------------------------- dispatch


class TestDispatch:
    def test_every_computed_name_dispatches_to_that_move(self, rig):
        names = ('home', 'search', 'approach', 'target', 'aboveTarget', 'park')
        # the mock's display block is 2x3, so the six names fill it exactly
        controls = {name: keyAt(*divmod(i, 3)) for i, name in enumerate(names)}
        pip = rig.makePipette(**controls)
        calls = recordMoves(pip)

        for i, name in enumerate(names):
            rig.press(*divmod(i, 3))

        assert [c[0] for c in calls] == list(names)
        assert {c[1] for c in calls} == {'fast'}

    def test_speed_is_read_from_the_entry(self, rig):
        pip = rig.makePipette(target={**KEY, 'speed': 'slow'})
        calls = recordMoves(pip)
        rig.press(0, 0)
        assert calls == [('target', 'slow', {})]

    def test_a_position_option_binds_an_arbitrary_label(self, rig):
        """A stored position or a site role is reachable under a label of its own."""
        pip = rig.makePipette(cleanPot={**KEY, 'position': 'clean'})
        calls = recordMoves(pip)
        rig.press(0, 0)
        assert calls == [('clean', 'fast', {})]

    def test_the_label_is_what_the_key_says(self, rig):
        rig.makePipette(cleanPot={**KEY, 'position': 'clean'})
        assert rig.textsFor(rig.control(0, 0)) == ['cleanPot']


# --------------------------------------------------------------------------- labelling


class TestLabel:
    """The ``label`` option, spelled as Microscope spells it for its lift/dip keys."""

    def test_the_default_label_is_the_binding_name(self, rig):
        pip = rig.makePipette(aboveTarget=KEY)
        assert pip._moveControls[rig.control(0, 0)]['label'] == 'aboveTarget'
        assert rig.textsFor(rig.control(0, 0)) == ['aboveTarget']

    def test_a_custom_label_is_what_the_key_says(self, rig):
        """The motivating case: 'aboveTarget' is unreadable on a 72x72 key."""
        pip = rig.makePipette(aboveTarget={**KEY, 'label': 'above tgt'})
        assert pip._moveControls[rig.control(0, 0)]['label'] == 'above tgt'
        assert rig.textsFor(rig.control(0, 0)) == ['above tgt']

    def test_a_label_does_not_change_where_the_press_goes(self, rig):
        pip = rig.makePipette(aboveTarget={**KEY, 'label': 'above tgt'})
        calls = recordMoves(pip)
        rig.press(0, 0)
        assert calls == [('aboveTarget', 'fast', {})]

    def test_a_label_works_alongside_position_and_speed(self, rig):
        pip = rig.makePipette(
            cleanPot={**KEY, 'position': 'clean', 'speed': 'slow', 'label': 'clean'}
        )
        calls = recordMoves(pip)
        rig.press(0, 0)
        assert calls == [('clean', 'slow', {})]
        assert rig.textsFor(rig.control(0, 0)) == ['clean']

    @pytest.mark.parametrize('label', ['', '   ', None])
    def test_an_empty_label_is_a_config_error(self, rig, label):
        """Refused, not obeyed: a blank key is what the option exists to prevent."""
        with pytest.raises(ValueError, match="empty 'label'"):
            rig.makePipette(aboveTarget={**KEY, 'label': label})

    def test_a_non_string_label_is_drawn_as_its_text(self, rig):
        """configfile evals a value, so an unquoted label arrives as a number."""
        rig.makePipette(target={**KEY, 'label': 40})
        assert rig.textsFor(rig.control(0, 0)) == ['40']

    def test_home_press_reaches_the_motion_planner(self, rig):
        """The real path, not a recorder: moveTo -> goHome -> dm.move.

        dm.move() is the panic-locked entry point (the planner checks globalHalt before
        it reserves anything), so this is what says the binding uses the guarded path.
        """
        rig.stage.setHomePosition()
        rig.makePipette(home=KEY)
        rig.press(0, 0)
        assert rig.dm.moves == ['move Pipette1 to home']

    def test_a_failed_move_is_logged_rather_than_raised(self, rig):
        pip = rig.makePipette(nowhere={**KEY, 'position': 'nowhere'})
        pip.logger = MagicMock()
        rig.press(0, 0)  # 'nowhere' is not a stored position; moveTo raises
        assert pip.logger.exception.called

    def test_press_on_an_unbound_key_of_the_same_surface_does_nothing(self, rig):
        pip = rig.makePipette(home=KEY)
        calls = recordMoves(pip)
        rig.press(1, 2)
        assert calls == []


# ------------------------------------------------------------------------ appearance


class TestAppearance:
    def test_a_key_without_text_output_is_not_labelled(self, rig):
        """An X-Keys-hosted binding: the move still runs, and one line says why."""
        pip = rig.makePipette(home=LIT_KEY)
        pip.logger = MagicMock()
        control = rig.litControl(0, 0)
        pip._labelMoveControl('home', 'home', control, control.capabilities())
        assert pip.logger.warning.called

        texts = [w for w in rig.surface.writesFor(control) if w['op'] == 'text']
        assert texts == []

        calls = recordMoves(pip)
        rig.press(0, 0, block='lit')
        assert calls == [('home', 'fast', {})]

    def test_a_custom_label_on_a_textless_key_degrades_the_same_way(self, rig):
        """Same single bind-time resolution: no second painting path for a label."""
        pip = rig.makePipette(aboveTarget={**LIT_KEY, 'label': 'above tgt'})
        assert pip._moveControls[rig.litControl(0, 0)]['label'] == 'above tgt'
        assert [w for w in rig.surface.writesFor(rig.litControl(0, 0)) if w['op'] == 'text'] == []

        calls = recordMoves(pip)
        rig.press(0, 0, block='lit')
        assert calls == [('aboveTarget', 'fast', {})]

    def test_the_warning_names_the_label_that_was_not_drawn(self, rig):
        pip = rig.makePipette()
        pip.logger = MagicMock()
        control = rig.litControl(0, 0)
        assert (
            pip._labelMoveControl('aboveTarget', 'above tgt', control, control.capabilities())
            is False
        )
        assert pip.logger.warning.call_count == 1
        message = pip.logger.warning.call_args[0][0]
        assert 'above tgt' in message and 'aboveTarget' in message


# ----------------------------------------------------------------------- docstring


def test_the_docstring_example_parses_as_rig_config(tmp_path):
    """pyqtgraph.configfile evals every value, so an example can be wrong in the docs.

    Bare-key inline dicts (``{device: 'Dock'}``) raise ParseError, and a quoted config
    *key* keeps its quotes, so both mistakes have to stay out of the docstring.
    """
    import re
    import textwrap

    from pyqtgraph import configfile

    examples = re.findall(r'Example configuration::\n\n(.*?)(?:\n\n|\Z)', Pipette.__doc__, re.S)
    assert examples, "the Pipette docstring lost its example configuration"
    for i, example in enumerate(examples):
        path = tmp_path / f'devices{i}.cfg'
        path.write_text(textwrap.dedent(example), newline='\n')
        config = configfile.readConfigFile(str(path))
        controls = list(config.values())[0]['controls']
        labelled = 0
        for name, spec in controls.items():
            assert isinstance(spec, dict), f"{name!r} did not parse as a dict"
            assert 'device' in spec and 'key' in spec
            assert name == name.strip("'\""), f"config key {name!r} kept its quotes"
            if 'label' in spec:
                labelled += 1
                assert isinstance(spec['label'], str), f"{name!r} label is not a string"
                assert spec['label'].strip(), f"{name!r} has an empty label"
        assert labelled, "the example no longer shows the 'label' option"
