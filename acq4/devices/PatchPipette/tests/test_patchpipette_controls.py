"""State-machine states bound to control-surface buttons.

Everything here runs headless against :class:`MockControlSurface`, :class:`MockStage` and
a real :class:`~acq4.devices.Pipette.Pipette`; no hardware and no real Manager are
involved. Control signals arrive over queued connections, so tests pump the Qt event loop
after injecting a press.

Most tests swap in :class:`RecordingStateManager` for the real state manager. A binding's
job is to hand a *state name* to the machine's own entry point, and the real states run
background jobs against a clamp, a pressure controller and a test pulse -- none of which
exist here, and all of which would make the assertions about which key is lit a race. The
stub answers :meth:`listStates` from the real registry and drives the real
:meth:`PatchPipette._setState`, so the names under test are the machine's own and the
change signal the indicator listens to is the real one. One test builds the device with
the genuine state manager, to say that the accepted names really are its registry.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from acq4.devices.ControlSurface import UnsupportedControlFeature
from acq4.devices.MockControlSurface import MockControl, MockControlSurface
from acq4.devices.MockStage import MockStage
from acq4.devices.PatchPipette import PatchPipette
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.devices.Pipette import Pipette
from acq4.panic import GlobalHalt
from acq4.util import Qt

#: A display key: images, text and any colour, like a Stream Dock key.
KEY = {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ['img', 0, 0]}
#: A lit-but-displayless key: one colour and no text, like an X-Keys key.
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


class RecordingStateManager:
    """Stands in for PatchPipetteStateManager: records requests and runs no jobs.

    Transitions are real as far as the device is concerned -- :meth:`PatchPipette._setState`
    is called, so ``sigStateChanged`` is emitted exactly as the genuine manager emits it --
    but no state class is instantiated and no background job is started.
    """

    def __init__(self, dev):
        self.dev = dev
        self.requests = []
        self.state = None
        self.refuse = None  # a state name to refuse, for the failure path

    def listStates(self):
        return list(PatchPipetteStateManager.stateHandlers.keys())

    def requestStateChange(self, state, **config):
        if state not in self.listStates():
            raise ValueError(f"Unknown patch pipette state {state!r}")
        if state == self.refuse:
            raise RuntimeError(f"refusing {state!r}")
        self.requests.append((state, config))
        old = None if self.state is None else self.state.stateName
        self.state = SimpleNamespace(stateName=state, config=config)
        self.dev._setState(state, old)
        return self.state

    def getState(self):
        return self.state

    def quit(self):
        pass


class BlindButtonSurface(MockControlSurface):
    """A mock with a pressable button that has no output at all."""

    def __init__(self, deviceManager, config: dict, name: str):
        MockControlSurface.__init__(self, deviceManager, config, name)
        self._addControlBlock(
            'button',
            {'input': {'press': True}, 'output': {}},
            keys=[('blind', 0, 0)],
            grid=False,
        )


class MockDM:
    """Just enough device manager for a PatchPipette, its pipette and one surface."""

    def __init__(self):
        self.globalHalt = GlobalHalt()
        self.devices = {}
        self.config = {}
        self.moves = []
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
    """A mock surface, manipulator and pipette, plus a factory for patch pipettes."""

    def __init__(self, surfaceClass=MockControlSurface):
        self.dm = MockDM()
        self.surface = surfaceClass(self.dm, {}, 'Dock')
        self.dm.devices['Dock'] = self.surface
        with patch("acq4.Manager.Manager.single", self.dm):
            self.stage = MockStage(
                self.dm, {'driver': 'MockStage', 'nAxes': 3, 'isManipulator': True}, 'Manip1'
            )
            self.dm.devices['Manip1'] = self.stage
            self.pipette = Pipette(
                self.dm,
                {'driver': 'Pipette', 'parentDevice': 'Manip1', 'pitch': 30.0, 'yaw': 0.0},
                'Pipette1',
            )
        self.dm.devices['Pipette1'] = self.pipette
        self.patchPipettes = []

    def makePatchPipette(self, stateManager=RecordingStateManager, **controls):
        config = {'driver': 'PatchPipette', 'pipetteDevice': 'Pipette1'}
        if controls:
            config['controls'] = controls

        class _PatchPipette(PatchPipette):
            defaultStateManagerClass = stateManager

        with patch("acq4.Manager.Manager.single", self.dm):
            dev = _PatchPipette(self.dm, config, f'PatchPipette{len(self.patchPipettes) + 1}')
        self.patchPipettes.append(dev)
        pump()
        return dev

    def control(self, *key, block='img'):
        return self.surface.getControl('button', 0, (block, *key))

    def press(self, *key, block='img'):
        self.surface.mockPress('button', (block, *key))
        pump()

    def writesFor(self, control, op='text'):
        return [w for w in self.surface.writesFor(control) if w['op'] == op]

    def quit(self):
        for dev in self.patchPipettes:
            dev.quit()
        self.pipette.quit()
        self.stage.quit()


@pytest.fixture
def rig(qapp):
    r = Rig()
    yield r
    r.quit()


# --------------------------------------------------------------------------- binding


class TestBinding:
    def test_no_controls_block_is_a_noop(self, rig):
        dev = rig.makePatchPipette()
        assert dev._boundControls == {}
        assert dev._stateControls == {}
        assert rig.control(0, 0).owner is None
        assert rig.surface.writes == []

        before = list(dev.stateManager().requests)
        rig.press(0, 0)
        assert dev.stateManager().requests == before

    def test_binding_acquires_the_control(self, rig):
        dev = rig.makePatchPipette(bath=KEY)
        assert rig.control(0, 0).owner is dev
        assert set(dev._boundControls) == {'bath'}

    def test_quit_releases_the_control(self, rig):
        dev = rig.makePatchPipette(bath=KEY)
        dev.quit()
        assert rig.control(0, 0).owner is None
        assert dev._boundControls == {}
        assert dev._stateControls == {}

    def test_released_control_can_be_claimed_again(self, rig):
        """Control.acquire is strictly once until released, so a leak would show here."""
        first = rig.makePatchPipette(bath=KEY)
        first.quit()
        second = rig.makePatchPipette(bath=KEY)
        assert rig.control(0, 0).owner is second

    def test_control_names_include_the_state_machine_registry(self, rig):
        # a superset, not an equality: every state is bindable, and so is each method-call
        # action the device offers alongside them
        dev = rig.makePatchPipette()
        assert set(PatchPipetteStateManager.stateHandlers) <= set(dev.controlNames())
        assert 'whole cell' in dev.controlNames()

    def test_control_names_come_from_the_real_state_manager(self, rig):
        """Built with the genuine manager, so the accepted set is really its registry."""
        dev = rig.makePatchPipette(stateManager=PatchPipetteStateManager)
        assert set(PatchPipetteStateManager.listStates()) <= set(dev.controlNames())

    def test_new_pipette_is_bindable_alongside_the_states(self, rig):
        dev = rig.makePatchPipette()
        assert 'newPipette' in dev.controlNames()

    def test_unknown_name_raises_naming_the_accepted_set(self, rig):
        with pytest.raises(ValueError) as exc:
            rig.makePatchPipette(wholeCell=KEY)
        message = str(exc.value)
        assert "unknown control name 'wholeCell'" in message
        for name in ('bath', 'seal', 'whole cell', 'break in', 'out'):
            assert name in message

    def test_missing_key_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="needs a 'key'"):
            rig.makePatchPipette(bath={'device': 'Dock', 'type': 'button', 'page': 0})

    def test_missing_device_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="needs a 'device' key"):
            rig.makePatchPipette(bath={'type': 'button', 'page': 0, 'key': ['img', 0, 0]})

    def test_a_control_that_cannot_be_pressed_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="no press input"):
            rig.makePatchPipette(bath=FADER)

    def test_two_entries_on_one_key_is_a_config_error(self, rig):
        from acq4.devices.ControlSurface import ControlInUse

        with pytest.raises(ControlInUse):
            rig.makePatchPipette(bath=KEY, seal=dict(KEY))

    def test_a_controls_block_that_is_not_a_dict_is_a_config_error(self, rig):
        dev = rig.makePatchPipette()
        with pytest.raises(TypeError, match="must be a dict"):
            dev._setupControls({'controls': ['bath']})


# -------------------------------------------------------------------------- dispatch


class TestDispatch:
    STATES = ('out', 'bath', 'seal', 'break in', 'whole cell', 'clean')

    def bindAll(self, rig):
        # the mock's display block is 2x3, so six states fill it exactly
        controls = {name: keyAt(*divmod(i, 3)) for i, name in enumerate(self.STATES)}
        return rig.makePatchPipette(**controls)

    def test_every_state_name_requests_that_state(self, rig):
        dev = self.bindAll(rig)
        manager = dev.stateManager()
        manager.requests.clear()

        for i, name in enumerate(self.STATES):
            rig.press(*divmod(i, 3))

        assert [r[0] for r in manager.requests] == list(self.STATES)

    def test_a_press_goes_through_setState(self, rig):
        """setState() is the panic-locked entry point and it also activates the pipette."""
        dev = rig.makePatchPipette(bath=KEY)
        dev.setActive(False)
        rig.press(0, 0)
        assert dev.stateManager().getState().stateName == 'bath'
        assert dev.active is True

    def test_set_active_false_is_honoured(self, rig):
        dev = rig.makePatchPipette(bath={**KEY, 'setActive': False})
        dev.setActive(False)
        rig.press(0, 0)
        assert dev.stateManager().getState().stateName == 'bath'
        assert dev.active is False

    def test_a_refused_state_request_is_logged_rather_than_raised(self, rig):
        dev = rig.makePatchPipette(bath=KEY)
        dev.stateManager().refuse = 'bath'
        dev.logger = MagicMock()
        rig.press(0, 0)
        assert dev.logger.exception.called

    def test_press_on_an_unbound_key_of_the_same_surface_does_nothing(self, rig):
        dev = rig.makePatchPipette(bath=KEY)
        manager = dev.stateManager()
        manager.requests.clear()
        rig.press(1, 2)
        assert manager.requests == []


# ------------------------------------------------------------------- state indication


class TestStateIndication:
    def test_keys_are_labelled_with_their_state_name(self, rig):
        rig.makePatchPipette(out=keyAt(0, 0), bath=keyAt(0, 1))
        assert rig.writesFor(rig.control(0, 0))[0]['text'] == 'out'
        assert rig.writesFor(rig.control(0, 1))[0]['text'] == 'bath'

    def test_the_first_paint_shows_the_state_the_device_starts_in(self, rig):
        """__init__ sets 'out' before the controls exist, so the paint has to be explicit."""
        dev = rig.makePatchPipette(out=keyAt(0, 0), bath=keyAt(0, 1))
        assert dev.stateManager().getState().stateName == 'out'
        assert rig.writesFor(rig.control(0, 0))[-1]['background'] == dev.activeStateColor
        assert rig.writesFor(rig.control(0, 1))[-1]['background'] is None

    def test_the_active_state_key_is_highlighted_after_a_transition(self, rig):
        dev = rig.makePatchPipette(out=keyAt(0, 0), bath=keyAt(0, 1))
        rig.surface.clearWrites()
        rig.press(0, 1)

        assert rig.writesFor(rig.control(0, 1))[-1]['background'] == dev.activeStateColor
        assert rig.writesFor(rig.control(0, 0))[-1]['background'] is None

    def test_a_transition_nobody_bound_unhighlights_everything(self, rig):
        dev = rig.makePatchPipette(out=keyAt(0, 0), bath=keyAt(0, 1))
        rig.surface.clearWrites()
        dev.setState('seal')
        pump()

        for key in ((0, 0), (0, 1)):
            assert rig.writesFor(rig.control(*key))[-1]['background'] is None

    def test_a_colour_only_key_indicates_with_its_colour(self, rig):
        """An X-Keys-shaped key: no text, but lit while its state is active."""
        dev = rig.makePatchPipette(bath=LIT_KEY)
        assert rig.writesFor(rig.control(0, 0, block='lit'), op='text') == []
        colors = rig.writesFor(rig.control(0, 0, block='lit'), op='color')
        assert colors, "the key was never coloured"
        assert colors[-1]['color'].name() == '#000000'  # not the active state

        rig.press(0, 0, block='lit')
        colors = rig.writesFor(rig.control(0, 0, block='lit'), op='color')
        assert colors[-1]['color'].green() == 0  # a blue+red LED pair can show it
        assert colors[-1]['color'].name() != '#000000'
        assert dev.stateManager().getState().stateName == 'bath'

    def test_a_key_with_no_output_indicates_nothing_but_still_requests(self, qapp):
        rig = Rig(BlindButtonSurface)
        try:
            dev = rig.makePatchPipette(
                bath={'device': 'Dock', 'type': 'button', 'page': 0, 'key': ['blind', 0, 0]}
            )
            assert dev._stateControls[rig.control(0, 0, block='blind')]['indicator'] is None
            assert rig.surface.writes == []

            rig.press(0, 0, block='blind')
            assert dev.stateManager().getState().stateName == 'bath'
        finally:
            rig.quit()

    def test_the_unpaintable_key_is_reported_once(self, rig):
        dev = rig.makePatchPipette()
        dev.logger = MagicMock()
        control = rig.control(0, 0)
        blind = SimpleNamespace()  # no setText, no setColor, no setBacklight
        assert dev._resolveStateIndicator('bath', 'bath', blind, control.capabilities()) is None
        assert dev.logger.warning.call_count == 1


# --------------------------------------------------------------------------- labelling


class TestLabel:
    """The ``label`` option, spelled as Microscope spells it for its lift/dip keys."""

    def test_the_default_label_is_the_state_name(self, rig):
        dev = rig.makePatchPipette(**{'cell detect': KEY})
        assert dev._stateControls[rig.control(0, 0)]['label'] == 'cell detect'
        assert rig.writesFor(rig.control(0, 0))[0]['text'] == 'cell detect'

    def test_a_custom_label_is_what_the_key_says(self, rig):
        dev = rig.makePatchPipette(**{'cell detect': {**KEY, 'label': 'cell det'}})
        assert dev._stateControls[rig.control(0, 0)]['label'] == 'cell det'
        assert rig.writesFor(rig.control(0, 0))[0]['text'] == 'cell det'

    def test_a_label_does_not_change_the_state_requested(self, rig):
        dev = rig.makePatchPipette(**{'cell detect': {**KEY, 'label': 'cell det'}})
        dev.stateManager().requests.clear()
        rig.press(0, 0)
        assert [r[0] for r in dev.stateManager().requests] == ['cell detect']

    def test_a_label_works_alongside_set_active(self, rig):
        dev = rig.makePatchPipette(bath={**KEY, 'setActive': False, 'label': 'BATH'})
        dev.setActive(False)
        rig.press(0, 0)
        assert dev.stateManager().getState().stateName == 'bath'
        assert dev.active is False
        assert rig.writesFor(rig.control(0, 0))[0]['text'] == 'BATH'

    def test_a_custom_label_survives_the_highlight_repaint(self, rig):
        """The highlight changes the background behind the label, never the label."""
        dev = rig.makePatchPipette(out=keyAt(0, 0), bath={**keyAt(0, 1), 'label': 'BATH'})
        rig.surface.clearWrites()
        rig.press(0, 1)

        write = rig.writesFor(rig.control(0, 1))[-1]
        assert write['text'] == 'BATH'
        assert write['background'] == dev.activeStateColor
        # ...and again when the highlight moves away
        rig.press(0, 0)
        write = rig.writesFor(rig.control(0, 1))[-1]
        assert write['text'] == 'BATH'
        assert write['background'] is None

    def test_a_custom_label_survives_an_out_of_band_repaint(self, rig):
        dev = rig.makePatchPipette(bath={**KEY, 'label': 'BATH'})
        rig.surface.clearWrites()
        dev._paintStateControls()
        assert rig.writesFor(rig.control(0, 0))[-1]['text'] == 'BATH'

    @pytest.mark.parametrize('label', ['', '   ', None])
    def test_an_empty_label_is_a_config_error(self, rig, label):
        """Refused, not obeyed: a blank key is what the option exists to prevent."""
        with pytest.raises(ValueError, match="empty 'label'"):
            rig.makePatchPipette(bath={**KEY, 'label': label})

    def test_a_colour_only_key_with_a_label_degrades_the_same_way(self, rig):
        """Same single bind-time resolution: no second painting path for a label."""
        dev = rig.makePatchPipette(bath={**LIT_KEY, 'label': 'BATH'})
        control = rig.control(0, 0, block='lit')
        assert dev._stateControls[control]['label'] == 'BATH'
        assert rig.writesFor(control, op='text') == []
        assert rig.writesFor(control, op='color'), "the key was never coloured"

        rig.press(0, 0, block='lit')
        assert dev.stateManager().getState().stateName == 'bath'

    def test_a_key_with_no_output_and_a_label_still_requests(self, qapp):
        rig = Rig(BlindButtonSurface)
        try:
            dev = rig.makePatchPipette(
                bath={
                    'device': 'Dock',
                    'type': 'button',
                    'page': 0,
                    'key': ['blind', 0, 0],
                    'label': 'BATH',
                }
            )
            control = rig.control(0, 0, block='blind')
            assert dev._stateControls[control]['indicator'] is None
            assert dev._stateControls[control]['label'] == 'BATH'
            assert rig.surface.writes == []

            rig.press(0, 0, block='blind')
            assert dev.stateManager().getState().stateName == 'bath'
        finally:
            rig.quit()


# -------------------------------------------------------------------- new pipette


NEW_PIPETTE = 'newPipette'


class TestNewPipetteButton:
    """The one bindable action that is a method call rather than a state request.

    :meth:`PatchPipette.newPipette` resets tip state, calibration and the patch record and
    then runs a calibration search against an imaging device, which this rig has none of.
    So these tests stand in for the call itself and assert what the binding is responsible
    for: that a press reaches it, that the key says what it does, and that a key which
    cannot be labelled is a startup failure rather than a blank button on a panel.
    """

    def test_binding_acquires_the_control(self, rig):
        dev = rig.makePatchPipette(**{NEW_PIPETTE: KEY})
        assert rig.control(0, 0).owner is dev
        assert set(dev._boundControls) == {NEW_PIPETTE}
        # a method call, not a state, so it takes no part in the state highlight
        assert dev._stateControls == {}

    def test_a_press_calls_new_pipette(self, rig):
        dev = rig.makePatchPipette(**{NEW_PIPETTE: KEY})
        with patch.object(type(dev), 'newPipette', autospec=True) as newPipette:
            rig.press(0, 0)
        assert newPipette.call_count == 1

    def test_a_press_on_a_state_key_does_not_call_new_pipette(self, rig):
        dev = rig.makePatchPipette(bath=keyAt(0, 0), **{NEW_PIPETTE: keyAt(0, 1)})
        dev.stateManager().requests.clear()
        with patch.object(type(dev), 'newPipette', autospec=True) as newPipette:
            rig.press(0, 0)
        assert newPipette.call_count == 0
        assert [r[0] for r in dev.stateManager().requests] == ['bath']

    def test_a_failing_new_pipette_is_logged_and_not_raised(self, rig):
        """Same policy as a state button: a press has no caller to raise at."""
        dev = rig.makePatchPipette(**{NEW_PIPETTE: KEY})
        boom = RuntimeError('no imaging device')
        with patch.object(type(dev), 'newPipette', autospec=True, side_effect=boom):
            with patch.object(dev, 'logger') as logger:
                rig.press(0, 0)
        assert logger.exception.call_count == 1

    def test_quit_releases_the_control(self, rig):
        dev = rig.makePatchPipette(**{NEW_PIPETTE: KEY})
        dev.quit()
        assert rig.control(0, 0).owner is None
        assert dev._boundControls == {}

    def test_the_default_label_is_the_name_it_is_declared_under(self, rig):
        rig.makePatchPipette(**{NEW_PIPETTE: KEY})
        assert rig.writesFor(rig.control(0, 0))[0]['text'] == NEW_PIPETTE

    def test_a_custom_label_is_what_the_key_says(self, rig):
        rig.makePatchPipette(**{NEW_PIPETTE: {**KEY, 'label': 'new pip'}})
        assert rig.writesFor(rig.control(0, 0))[0]['text'] == 'new pip'

    def test_an_empty_label_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="empty 'label'"):
            rig.makePatchPipette(**{NEW_PIPETTE: {**KEY, 'label': '  '}})

    def test_a_control_that_cannot_be_pressed_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match='no press input'):
            rig.makePatchPipette(**{NEW_PIPETTE: FADER})

    def test_a_key_that_cannot_be_labelled_is_a_startup_failure(self, rig):
        """A key that resets the patch record must never come up blank and unexplained."""
        boom = UnsupportedControlFeature('display is wedged')
        with patch.object(MockControl, 'setText', side_effect=boom):
            with pytest.raises(UnsupportedControlFeature):
                rig.makePatchPipette(**{NEW_PIPETTE: KEY})

    def test_a_colour_only_key_is_bound_without_a_label(self, rig):
        """No text output to fail at, so the key binds and the press still works."""
        dev = rig.makePatchPipette(**{NEW_PIPETTE: LIT_KEY})
        control = rig.control(0, 0, block='lit')
        assert rig.writesFor(control, op='text') == []
        with patch.object(type(dev), 'newPipette', autospec=True) as newPipette:
            rig.press(0, 0, block='lit')
        assert newPipette.call_count == 1


# ----------------------------------------------------------------------- docstring


def test_the_docstring_example_parses_as_rig_config(tmp_path):
    """pyqtgraph.configfile evals every value, so an example can be wrong in the docs.

    State names contain spaces, and a config *key* is taken literally -- quotes included --
    so ``break in:`` has to be written bare. Bare-key inline dict *values*
    (``{device: 'Dock'}``) raise ParseError, so those have to stay quoted.
    """
    import re
    import textwrap

    from pyqtgraph import configfile

    examples = re.findall(
        r'Example configuration::\n\n(.*?)(?:\n\n|\Z)', PatchPipette.__doc__, re.S
    )
    assert examples, "the PatchPipette docstring lost its example configuration"
    known = set(PatchPipetteStateManager.stateHandlers)
    for i, example in enumerate(examples):
        path = tmp_path / f'devices{i}.cfg'
        path.write_text(textwrap.dedent(example), newline='\n')
        config = configfile.readConfigFile(str(path))
        controls = list(config.values())[0]['controls']
        assert controls
        labelled = 0
        for name, spec in controls.items():
            assert isinstance(spec, dict), f"{name!r} did not parse as a dict"
            assert 'device' in spec and 'key' in spec
            assert name == name.strip("'\""), f"config key {name!r} kept its quotes"
            assert name in known, f"{name!r} is not a state this device can be set to"
            if 'label' in spec:
                labelled += 1
                assert isinstance(spec['label'], str), f"{name!r} label is not a string"
                assert spec['label'].strip(), f"{name!r} has an empty label"
        assert labelled, "the example no longer shows the 'label' option"
