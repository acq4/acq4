"""Tests for X-Keys and the consumers ported onto the control-surface API.

Everything here is headless. X-Keys runs against a stand-in for the PIE driver object
(:class:`FakePieDevice`), injected through ``XKeys._openDevice``; every other consumer runs
against :class:`~acq4.devices.MockControlSurface.MockControlSurface`. Control signals are
delivered over a queued connection, so tests pump the Qt event loop with :func:`pump` after
injecting an event.

Output is each surface's own API, so a consumer is tested against both shapes where it
matters: an X-Keys key takes ``setBacklight(blue, red)`` and the mock's keys take
``setColor``, and every consumer here settles which it is using once, at bind time.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pyqtgraph as pg
import pytest

from acq4.Manager import getManager
from acq4.devices.ControlSurface import ControlInUse, UnsupportedControlFeature
from acq4.devices.LightSource import LightSource
from acq4.devices.MockControlSurface import MockControlSurface
from acq4.devices.XKeys import UnsupportedColor, XKeys, XKeysControl
from acq4.util import Qt

LIT_KEY = ('lit', 0, 0)


def pump(iterations=3):
    """Deliver queued Qt events so that control signals arrive."""
    for _ in range(iterations):
        Qt.QApplication.processEvents()


@pytest.fixture(scope='module')
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture(autouse=True)
def globalManager(monkeypatch):
    """Install a fake in the global Manager singleton slot for every test here.

    :func:`~acq4.devices.ControlSurface.acquireControlFromConfig` resolves a configured
    surface on the global Manager, so every consumer bound below needs one. The factories
    point its ``getDevice`` at the surface under test and hand the same object to the
    device as its own manager, which is what passing one explicitly used to do.
    """
    dm = MagicMock()
    monkeypatch.setattr('acq4.Manager.Manager.single', dm)
    return dm


@pytest.fixture
def surface(qapp):
    """A hardware-free surface whose lit buttons stand in for X-Keys keys."""
    return MockControlSurface(MagicMock(), {}, 'MockSurface')


# ------------------------------------------------------------------------------- X-Keys


class FakePieDevice:
    """Stand-in for ``acq4.drivers.xkeys.pie.XKeysDevice``.

    Records backlight writes so that a test can count how many driver calls a burst of
    per-control writes collapsed into.
    """

    def __init__(self, keyshape=(8, 10), jogShuttle=True):
        self.model = 'Fake X-Keys'
        self.keyshape = keyshape
        self.capabilities = {
            'rows': keyshape[0],
            'columns': keyshape[1],
            'joysticks': 0,
            'jog/shuttle': jogShuttle,
            'touchpad': False,
        }
        self.state = {'keys': np.zeros(keyshape, dtype=bool)}
        self.backlightState = np.zeros(keyshape + (2,), dtype='ubyte')
        self.callback = None
        self.intensity = None
        self.setBacklightsCalls = []
        self.closed = False

    def setCallback(self, cb):
        self.callback = cb

    def setIntensity(self, b1, b2):
        self.intensity = (b1, b2)

    def setBacklights(self, state, axis=None, reverse=None):
        self.setBacklightsCalls.append(np.array(state))
        self.backlightState = np.array(state)

    def setBacklightRows(self, bl1=None, bl2=None):
        self.backlightState[:] = 0

    def close(self):
        self.closed = True


class FakeXKeys(XKeys):
    """X-Keys wired to a :class:`FakePieDevice` instead of real hardware."""

    def _openDevice(self, config):
        return FakePieDevice(
            keyshape=tuple(config.get('keyshape', (8, 10))),
            jogShuttle=config.get('jogShuttle', True),
        )


def makeXKeys(qapp, name='XK', **config):
    return FakeXKeys(MagicMock(), dict(config), name)


@pytest.fixture
def xkeys(qapp):
    return makeXKeys(qapp)


class TestXKeysLayout:
    def test_one_button_per_key_in_one_grid(self, xkeys):
        grids = xkeys.controlGrids(page=0)
        assert [g.shape for g in grids] == [(8, 10)]
        assert grids[0][3, 7] is xkeys.getControl('button', 0, (3, 7))

    def test_button_capabilities(self, xkeys):
        caps = xkeys.getControl('button', 0, (0, 0)).capabilities()
        assert caps['input'] == {'press': True}
        # the backlight is the whole of a key's output, and 'output' is this device's own
        # vocabulary, so that is the only word in it
        assert caps['output'] == {'backlight': True}

    def test_a_dial_declares_and_offers_no_output(self, xkeys):
        jog = xkeys.getControl('dial', 0, 'jog')
        assert jog.capabilities()['output'] == {}
        with pytest.raises(UnsupportedControlFeature):
            jog.setBacklight(1, 1)
        with pytest.raises(UnsupportedControlFeature):
            jog.setColor('b')

    def test_keyshape_follows_the_driver(self, qapp):
        surface = makeXKeys(qapp, name='XK12', keyshape=(3, 4))
        assert [g.shape for g in surface.controlGrids(page=0)] == [(3, 4)]

    def test_configured_page_count_builds_controls_on_every_page(self, qapp):
        surface = makeXKeys(qapp, name='XK3', pages=3)
        assert surface.pageCount() == 3
        page0 = {(c.type, c.key) for c in surface.allControls(page=0)}
        assert len(page0) == 8 * 10 + 2  # every key, plus the jog wheel and shuttle ring
        for page in range(3):
            assert [g.shape for g in surface.controlGrids(page=page)] == [(8, 10)]
            assert {(c.type, c.key) for c in surface.allControls(page=page)} == page0
            assert all(c.page == page for c in surface.allControls(page=page))

    def test_one_page_by_default_and_pages_are_configurable(self, qapp, xkeys):
        assert xkeys.pageCount() == 1
        assert makeXKeys(qapp, name='XKpages', pages=3).pageCount() == 3

    def test_intensity_is_set_at_startup(self, xkeys):
        assert xkeys.dev.intensity == (255, 255)

    def test_jog_and_shuttle_exist_only_where_the_hardware_has_them(self, qapp):
        withThem = makeXKeys(qapp, name='XKjs')
        assert sorted(withThem.controls(page=0)['dial']) == ['jog', 'shuttle']
        without = makeXKeys(qapp, name='XKplain', jogShuttle=False)
        assert 'dial' not in without.controls(page=0)

    def test_jog_is_relative_and_reports_no_range(self, xkeys):
        caps = xkeys.getControl('dial', 0, 'jog').capabilities()['input']
        assert caps['mode'] == 'relative'
        assert not {'min', 'max', 'flat'} & set(caps)

    def test_shuttle_is_absolute_and_centred_on_zero(self, xkeys):
        caps = xkeys.getControl('dial', 0, 'shuttle').capabilities()['input']
        assert caps['mode'] == 'absolute'
        # the driver decodes one signed byte; a symmetric range puts rest at the centre
        assert (caps['min'], caps['max']) == (-127, 127)
        assert (caps['min'] + caps['max']) / 2 == 0
        assert caps['flat'] == 0

    def test_shuttle_deadzone_is_configurable(self, qapp):
        surface = makeXKeys(qapp, name='XKflat', shuttleDeadzone=2)
        assert surface.getControl('dial', 0, 'shuttle').capabilities()['input']['flat'] == 2


class TestXKeysEvents:
    def test_press_and_release_are_both_delivered(self, xkeys):
        control = xkeys.getControl('button', 0, (2, 3))
        events = []
        control.sigPressed.connect(lambda c: events.append('press'))
        control.sigReleased.connect(lambda c: events.append('release'))

        # the driver reports both transitions; the old callback layer dropped releases
        xkeys.dev.callback({'keys': [((2, 3), True), ((2, 3), False)]})
        pump()
        assert events == ['press', 'release']

    def test_only_the_addressed_control_hears_about_it(self, xkeys):
        other = MagicMock()
        xkeys.getControl('button', 0, (0, 0)).sigPressed.connect(other)
        xkeys.dev.callback({'keys': [((1, 1), True)]})
        pump()
        other.assert_not_called()

    def test_jog_reports_deltas(self, xkeys):
        moves = []
        xkeys.getControl('dial', 0, 'jog').sigMoved.connect(lambda c, v: moves.append(v))
        xkeys.dev.callback({'jog': 3})
        xkeys.dev.callback({'jog': -1})
        pump()
        assert moves == [3, -1]

    def test_shuttle_reports_absolute_positions(self, xkeys):
        moves = []
        xkeys.getControl('dial', 0, 'shuttle').sigMoved.connect(lambda c, v: moves.append(v))
        for value in (4, 7, 0):
            xkeys.dev.callback({'shuttle': value})
        pump()
        assert moves == [4, 7, 0]
        assert xkeys.getControl('dial', 0, 'shuttle').value() == 0

    def test_shuttle_deadzone_reads_as_centre(self, qapp):
        surface = makeXKeys(qapp, name='XKflat2', shuttleDeadzone=2)
        moves = []
        surface.getControl('dial', 0, 'shuttle').sigMoved.connect(lambda c, v: moves.append(v))
        surface.dev.callback({'shuttle': 1})
        surface.dev.callback({'shuttle': 5})
        pump()
        assert moves == [0, 5]

    def test_the_program_switch_is_ignored_rather_than_crashing(self, xkeys):
        xkeys.dev.callback({'button': True})
        pump()  # no control is declared for it, and no exception escapes

    def test_an_unknown_key_is_logged_not_raised(self, xkeys, caplog):
        with caplog.at_level('WARNING'):
            xkeys.dev.callback({'keys': [((99, 99), True)]})
            pump()
        assert 'unknown control' in caplog.text


class TestXKeysBacklights:
    @pytest.mark.parametrize(
        'color,expected',
        [
            ('k', (0, 0)),
            ('b', (1, 0)),
            ('r', (0, 1)),
            ('m', (1, 1)),
            # nothing special about the four primaries: any colour with no green in it is
            # showable, its blue and red components deciding which LED is lit
            ('#7f00c8', (1, 1)),
            ('#01000a', (1, 1)),
            ((0, 0, 3), (1, 0)),
            ((180, 0, 0), (0, 1)),
            ('#00000a', (1, 0)),
            (Qt.QColor(9, 0, 0, 128), (0, 1)),  # alpha is ignored
        ],
    )
    def test_setcolor_shows_any_colour_with_no_green_in_it(self, xkeys, color, expected):
        control = xkeys.getControl('button', 0, (3, 3))
        control.setColor(color)
        xkeys._flushBacklights()
        assert tuple(xkeys.dev.backlightState[3, 3]) == expected, color

    def test_setcolor_refuses_only_a_colour_with_green_in_it(self, xkeys):
        # two LEDs cannot make green; saying so beats a dark key or a substituted colour
        control = xkeys.getControl('button', 0, (4, 4))
        control.setColor('b')
        xkeys._flushBacklights()
        with pytest.raises(UnsupportedColor) as exc:
            control.setColor('g')
        xkeys._flushBacklights()
        assert tuple(xkeys.dev.backlightState[4, 4]) == (1, 0)  # still the last good one
        # a colour is cached as the LED pair it became, because the pair is the hardware
        # state; the refused request never reached the cache at all
        assert control.cachedAppearance() == ('backlight', {'blue': 1, 'red': 0})
        # a consumer catching the general case catches this too, and the refusal names the
        # control, carries the colour asked for, and states the rule it broke
        assert isinstance(exc.value, UnsupportedControlFeature)
        assert exc.value.control is control
        assert pg.mkColor(exc.value.color).green() == 255
        assert 'green' in str(exc.value)

    @pytest.mark.parametrize('color', ['g', 'w', '#010101', (0, 1, 0), 'y', 'c'])
    def test_green_in_any_amount_is_the_only_refusal(self, xkeys, color):
        # including white, which consumers used to spell "both LEDs on"
        control = xkeys.getControl('button', 0, (5, 5))
        with pytest.raises(UnsupportedColor):
            control.setColor(color)

    def test_the_rule_is_readable_without_a_device(self):
        # a consumer deciding what to ask for needs the rule, not a palette to look up
        assert XKeys.backlightForColor('m') == (1, 1)
        assert not hasattr(XKeys, 'BACKLIGHT_COLORS')

    def test_the_two_led_api_lives_on_this_surface_not_the_base_class(self, xkeys):
        from acq4.devices.ControlSurface import Control

        control = xkeys.getControl('button', 0, (0, 0))
        assert isinstance(control, XKeysControl)
        for name in ('setBacklight', 'setColor'):
            assert hasattr(control, name)
            assert not hasattr(Control, name)
        # and nothing pretends a key has pixels
        for name in ('setImage', 'setText', 'setAnimation'):
            assert not hasattr(control, name), name

    def test_writes_coalesce_into_one_driver_call(self, xkeys):
        # the driver needs ~60 ms per changed light, so a bank repaint must not become
        # one setBacklights() per control
        for control in xkeys.controlGrids(page=0)[0][:, 4:8].flat:
            control.setColor('b')
        assert xkeys.dev.setBacklightsCalls == []
        pump()
        assert len(xkeys.dev.setBacklightsCalls) == 1
        assert (xkeys.dev.backlightState[:, 4:8, 0] == 1).all()
        assert (xkeys.dev.backlightState[:, 4:8, 1] == 0).all()
        assert (xkeys.dev.backlightState[:, 0:4, 0] == 0).all()

    def test_the_last_write_to_a_control_wins(self, xkeys):
        control = xkeys.getControl('button', 0, (0, 0))
        control.setColor('r')
        control.setColor('b')
        pump()
        assert len(xkeys.dev.setBacklightsCalls) == 1
        assert tuple(xkeys.dev.backlightState[0, 0]) == (1, 0)

    def test_native_setbacklight_reaches_the_flash_state(self, xkeys):
        control = xkeys.getControl('button', 0, (0, 5))
        control.setBacklight(blue=0, red=2)
        pump()
        assert tuple(xkeys.dev.backlightState[0, 5]) == (0, 2)
        # cached like any other appearance, so a page repaint can replay it
        assert control.cachedAppearance() == ('backlight', {'blue': 0, 'red': 2})

    def test_native_setbacklight_leaves_a_none_channel_alone(self, xkeys):
        control = xkeys.getControl('button', 0, (0, 6))
        control.setBacklight(blue=1, red=1)
        pump()
        control.setBacklight(red=0)
        pump()
        assert tuple(xkeys.dev.backlightState[0, 6]) == (1, 0)

    def test_release_turns_a_key_off(self, xkeys):
        control = xkeys.acquireControl('button', 0, (2, 2), owner=object())
        control.setColor('m')
        pump()
        control.release()
        pump()
        assert tuple(xkeys.dev.backlightState[2, 2]) == (0, 0)

    def test_release_of_a_dial_is_quiet(self, xkeys):
        # a dial has no backlight, so _blank has nothing to do and must not raise
        control = xkeys.acquireControl('dial', 0, 'jog', owner=object())
        control.release()
        pump()
        assert control.owner is None
        assert xkeys.dev.setBacklightsCalls == []

    def test_a_page_switch_replays_and_blanks_through_the_led_pair(self, qapp):
        surface = makeXKeys(qapp, name='XKpaged', pages=2)
        onPage1 = surface.getControl('button', 1, (0, 0))
        onPage1.setBacklight(1, 2)
        pump()
        assert tuple(surface.dev.backlightState[0, 0]) == (0, 0)  # page 1 is not active

        surface.getControl('button', 0, (0, 1)).setColor('r')
        pump()
        surface.setCurrentPage(1)
        pump()
        assert tuple(surface.dev.backlightState[0, 0]) == (1, 2)  # replayed, flash intact
        assert tuple(surface.dev.backlightState[0, 1]) == (0, 0)  # blanked, not lingering

    def test_quit_blanks_and_closes(self, xkeys):
        xkeys.getControl('button', 0, (0, 0)).setColor('m')
        xkeys.quit()
        assert (xkeys.dev.backlightState == 0).all()
        assert xkeys.dev.closed


class TestXKeysIntensity:
    """Brightness is global to the keypad, and nothing per-key may move it."""

    def test_config_sets_both_banks(self, qapp):
        surface = makeXKeys(qapp, name='XKint', intensity=(40, 200))
        assert surface.dev.intensity == (40, 200)
        assert surface.getIntensity() == (40, 200)

    def test_default_is_full_brightness(self, xkeys):
        assert xkeys.getIntensity() == (255, 255)

    def test_every_level_of_each_bank_is_reachable(self, xkeys):
        # the 256 levels per channel are real; they are just not addressable per key
        for level in (0, 1, 127, 254, 255):
            xkeys.setIntensity(level, 255 - level)
            assert xkeys.dev.intensity == (level, 255 - level)
            assert xkeys.getIntensity() == (level, 255 - level)

    @pytest.mark.parametrize('args', [(-1, 0), (0, 256), (300, 300)])
    def test_a_level_outside_0_255_is_refused_without_writing(self, xkeys, args):
        with pytest.raises(ValueError):
            xkeys.setIntensity(*args)
        assert xkeys.getIntensity() == (255, 255)

    def test_painting_one_key_never_moves_the_brightness(self, xkeys):
        # the hardware has no per-key brightness, and faking one by moving the global
        # level would silently repaint every other key on the device
        xkeys.setIntensity(30, 90)
        xkeys.getControl('button', 0, (0, 0)).setColor('#400080')
        xkeys.getControl('button', 0, (0, 1)).setColor('#ff0000')
        pump()
        assert xkeys.dev.intensity == (30, 90)
        assert tuple(xkeys.dev.backlightState[0, 0]) == (1, 1)
        assert tuple(xkeys.dev.backlightState[0, 1]) == (0, 1)


# -------------------------------------------------------------------------- LightSource


class FakeLightSource(LightSource):
    """Concrete LightSource that only remembers what it was told."""

    def setSourceActive(self, name, active):
        self.sourceConfigs[name]['active'] = bool(active)
        self._updateXkeyLight(name)
        self.sigLightChanged.emit(self, name)


def makeLightSource(surface, sourceConf, name='LEDs'):
    dm = getManager()
    dm.getDevice.return_value = surface
    dev = FakeLightSource(dm, {}, name)
    dev.addSource('Blue', dict(sourceConf))
    return dev


class TestLightSourceControl:
    def test_canonical_config_claims_the_control(self, surface):
        dev = makeLightSource(surface, {'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}})
        control = surface.getControl('button', 0, LIT_KEY)
        assert control.owner is dev

    def test_deprecated_xkey_spelling_still_works(self, xkeys, caplog):
        with caplog.at_level('WARNING'):
            dev = makeLightSource(xkeys, {'xkey': ('XK', 7, 8)})
        assert 'deprecated' in caplog.text
        assert dev._sourceControls['Blue'] is xkeys.getControl('button', 0, (7, 8))

    def test_pressing_the_control_toggles_the_source(self, surface):
        dev = makeLightSource(surface, {'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}})
        assert dev.sourceActive('Blue') is False
        surface.mockPress(key=LIT_KEY)
        pump()
        assert dev.sourceActive('Blue') is True
        surface.mockPress(key=LIT_KEY)
        pump()
        assert dev.sourceActive('Blue') is False

    def test_indicator_lights_both_channels_deliberately(self, surface):
        """The old ``bl[row, col] = int(active)`` set *both* LEDs by accident, because the
        backlight array is (rows, cols, 2). The behaviour is kept, but stated -- as
        magenta, which is what both LEDs lit look like and is showable on a two-LED key."""
        dev = makeLightSource(surface, {'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}})
        control = surface.getControl('button', 0, LIT_KEY)
        surface.clearWrites()

        dev.setSourceActive('Blue', True)
        write = surface.writesFor(control)[-1]
        assert (write['op'], write['color']) == ('color', pg.mkColor('m'))

        dev.setSourceActive('Blue', False)
        write = surface.writesFor(control)[-1]
        assert (write['op'], write['color']) == ('color', pg.mkColor('k'))

    def test_the_indicator_goes_native_on_a_surface_with_a_backlight(self, xkeys):
        """Same indicator, the device's own API: on an X-Keys it is the LED pair."""
        dev = makeLightSource(xkeys, {'control': {'device': 'XK', 'key': [7, 8]}})
        dev.setSourceActive('Blue', True)
        pump()
        assert tuple(xkeys.dev.backlightState[7, 8]) == (1, 1)
        dev.setSourceActive('Blue', False)
        pump()
        assert tuple(xkeys.dev.backlightState[7, 8]) == (0, 0)

    def test_a_control_that_can_indicate_nothing_is_reported_once(self, surface, caplog):
        """Degrade loudly: the button still toggles the source, and says so at bind time
        rather than failing on every switch."""
        with caplog.at_level('WARNING'):
            dev = makeLightSource(
                surface, {'control': {'device': 'MockSurface', 'type': 'dial', 'key': 'fader'}}
            )
        assert 'will not indicate' in caplog.text
        assert dev._sourceIndicators == {}
        caplog.clear()
        with caplog.at_level('WARNING'):
            dev.setSourceActive('Blue', True)
            dev.setSourceActive('Blue', False)
        assert dev.sourceActive('Blue') is False
        assert caplog.text == ''

    def test_a_source_without_a_control_is_untouched(self, surface):
        dev = makeLightSource(surface, {})
        dev.setSourceActive('Blue', True)
        assert dev._sourceControls == {}
        assert surface.writes == []

    def test_two_sources_cannot_share_one_control(self, surface):
        """A control is claimed once, so the duplicate address fails at acquisition."""
        dev = makeLightSource(surface, {'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}})
        with pytest.raises(ControlInUse) as exc:
            dev.addSource('Green', {'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}})
        assert exc.value.owner is dev
        assert str(LIT_KEY) in str(exc.value)


# --------------------------------------------------------------------------- FilterWheel


def makeFilterWheel(surface, slots, name='FW'):
    from acq4.devices.FilterWheel.filterwheel import FilterWheel, FilterWheelFuture

    class FakeFilterWheel(FilterWheel):
        """Filter wheel whose position changes the instant it is asked to."""

        def __init__(self, dm, config, wheelName):
            self._pos = 0
            FilterWheel.__init__(self, dm, config, wheelName)

        def _setPosition(self, pos):
            self._pos = pos
            return FilterWheelFuture(self, pos)

        def _getPosition(self):
            return self._pos

        def isMoving(self):
            return False

        def _stop(self):
            pass

    dm = getManager()
    dm.getDevice.return_value = surface
    return FakeFilterWheel(dm, {'slots': slots, 'pollInterval': None, 'ports': []}, name)


class TestFilterWheelControl:
    SLOTS = {
        '0': 'empty',
        '1': {'name': 'cube', 'control': {'device': 'MockSurface', 'key': ['lit', 0, 1]}},
        '2': {'name': 'other', 'control': {'device': 'MockSurface', 'key': ['lit', 0, 2]}},
    }

    def test_only_dict_slots_bind_a_control(self, surface):
        wheel = makeFilterWheel(surface, self.SLOTS)
        assert sorted(wheel._slotIndicators) == [1, 2]

    def test_deprecated_hotkey_spelling_still_works(self, surface, caplog):
        slots = {'0': {'name': 'cube', 'hotkey': {'device': 'MockSurface', 'key': LIT_KEY}}}
        with caplog.at_level('WARNING'):
            wheel = makeFilterWheel(surface, slots)
        assert 'deprecated' in caplog.text
        assert wheel._slotIndicators[0] is surface.getControl('button', 0, LIT_KEY)

    def test_pressing_a_control_selects_its_slot(self, surface):
        wheel = makeFilterWheel(surface, self.SLOTS)
        surface.mockPress(key=('lit', 0, 2))
        pump()
        assert wheel.getPosition() == 2

    def test_only_the_active_slot_is_lit(self, surface):
        wheel = makeFilterWheel(surface, self.SLOTS)
        surface.clearWrites()
        wheel.setPosition(1)
        wheel.getPosition()  # polls, which is what notices the change

        def lit(key):
            writes = surface.writesFor(surface.getControl('button', 0, key))
            return writes[-1]['color']

        assert lit(('lit', 0, 1)) == pg.mkColor('m')
        assert lit(('lit', 0, 2)) == pg.mkColor('k')

    def test_the_indicator_goes_native_on_a_surface_with_a_backlight(self, xkeys):
        slots = {
            '0': {'name': 'cube', 'control': {'device': 'XK', 'key': [0, 0]}},
            '1': {'name': 'other', 'control': {'device': 'XK', 'key': [0, 1]}},
        }
        wheel = makeFilterWheel(xkeys, slots)
        wheel.setPosition(1)
        wheel.getPosition()
        pump()
        assert tuple(xkeys.dev.backlightState[0, 0]) == (0, 0)
        assert tuple(xkeys.dev.backlightState[0, 1]) == (1, 1)

    def test_a_control_that_can_indicate_nothing_is_reported_once(self, surface, caplog):
        slots = {
            '0': {
                'name': 'cube',
                'control': {'device': 'MockSurface', 'type': 'dial', 'key': 'fader'},
            }
        }
        with caplog.at_level('WARNING'):
            wheel = makeFilterWheel(surface, slots)
        assert 'will not indicate' in caplog.text
        assert wheel._slotLights == {}
        wheel.setPosition(0)
        wheel.getPosition()  # the wheel still moves; nothing raises


# -------------------------------------------------------------------- Camera / Microscope


class TestCameraPresetControl:
    def test_pressing_a_control_loads_the_preset(self, surface):
        from acq4.devices.MockCamera import MockCamera

        dm = getManager()
        dm.getDevice.return_value = surface
        conf = {
            'presets': {
                'binned': {
                    'params': {'binning': (2, 2)},
                    'control': {'device': 'MockSurface', 'key': list(LIT_KEY)},
                }
            }
        }
        cam = MockCamera(dm, conf, 'Cam')
        assert list(cam._presetControls.values()) == ['binned']

        surface.mockPress(key=LIT_KEY)
        pump()
        assert list(cam.getParam('binning')) == [2, 2]

    def test_a_preset_without_a_control_is_skipped(self, surface):
        from acq4.devices.MockCamera import MockCamera

        cam = MockCamera(MagicMock(), {'presets': {'plain': {'params': {}}}}, 'Cam2')
        assert cam._presetControls == {}


class TestMicroscopePresetControl:
    OBJECTIVES = {'0': {'4x': {'name': '4x', 'scale': 1.0, 'offset': (0, 0, 0)}}}

    def makeScope(self, surface, presets, name='Scope'):
        from acq4.devices.Microscope import Microscope

        self.target = MagicMock()
        dm = getManager()
        dm.getDevice.side_effect = lambda n: surface if n == 'MockSurface' else self.target
        return Microscope(dm, {'objectives': self.OBJECTIVES, 'presets': presets}, name)

    def test_the_device_claims_the_control_not_the_gui(self, surface):
        """Bound in ``__init__`` rather than ScopeGUI, so a preset key works with the
        device rack closed, and reopening it cannot double-claim."""
        scope = self.makeScope(
            surface,
            {'GFP': {'LEDs': 'blue', 'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}}},
        )
        assert surface.getControl('button', 0, LIT_KEY).owner is scope

    def test_pressing_a_control_loads_the_preset(self, surface):
        scope = self.makeScope(
            surface,
            {'GFP': {'LEDs': 'blue', 'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}}},
        )
        surface.mockPress(key=LIT_KEY)
        for _ in range(40):  # loadPreset runs detached, so give it a moment
            pump()
            if self.target.loadPreset.called:
                break
        self.target.loadPreset.assert_called_once_with('blue')
        assert scope.presets['GFP']['control']['device'] == 'MockSurface'

    def test_control_is_a_reserved_preset_key(self, surface):
        """``loadPreset`` must not try to treat 'control' (or 'hotkey') as a device."""
        from acq4.devices.Microscope.Microscope import RESERVED_PRESET_KEYS

        scope = self.makeScope(
            surface,
            {'GFP': {'LEDs': 'blue', 'control': {'device': 'MockSurface', 'key': list(LIT_KEY)}}},
        )
        scope.loadPreset('GFP')
        assert {'objective', 'control', 'hotkey'} <= RESERVED_PRESET_KEYS
        assert self.target.loadPreset.call_args_list == [(('blue',), {})]


# ---------------------------------------------------------------------------- MultiPatch


class FakePipetteDevice:
    def __init__(self):
        self.moving = False


class FakePipette:
    def __init__(self, name):
        self._name = name
        self.pipetteDevice = FakePipetteDevice()

    def name(self):
        return self._name


class FakePipetteControl:
    """The slice of ``PipetteControl`` that MultiPatch's control-surface code touches."""

    def __init__(self, name):
        self.pip = FakePipette(name)
        self.ui = _namespace(
            activeBtn=_checkableButton(),
            lockBtn=_checkableButton(),
            selectBtn=_checkableButton(),
            tipBtn=_checkableButton(),
            targetBtn=_checkableButton(),
        )

    def active(self):
        return self.ui.activeBtn.isChecked()

    def locked(self):
        return self.ui.lockBtn.isChecked()

    def selected(self):
        return self.ui.selectBtn.isChecked()


def _checkableButton():
    btn = Qt.QPushButton()
    btn.setCheckable(True)
    return btn


class _namespace:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


def makeMultiPatchWindow(qapp, surface=None, nPipettes=2, **conf):
    """Build a MultiPatchWindow with the real control-surface code and nothing else.

    The real ``__init__`` needs a Manager, PatchPipette devices and a full UI, none of
    which this exercises, so the surface wiring is driven directly.
    """
    from acq4.modules.MultiPatch.multipatch import DEFAULT_ACTION_KEYS, MultiPatchWindow

    class TestWindow(MultiPatchWindow):
        def __init__(self):
            Qt.QWidget.__init__(self)
            self.pipCtrls = [FakePipetteControl(f'Pipette{i + 1}') for i in range(nPipettes)]
            self.pips = [c.pip for c in self.pipCtrls]
            self.ui = _namespace(**{name: _checkableButton() for name in DEFAULT_ACTION_KEYS})
            self._surface = None
            self._surfacePage = 0
            self._actionControls = {}
            self._pipetteControls = {}
            self._backlights = {}
            self._pipetteGrid = None

    win = TestWindow()
    if surface is not None:
        win._setupControlSurface(dict(conf, device='Surface'))
    return win


@pytest.fixture
def bigSurface(qapp):
    """An X-Keys 80-shaped surface: the layout MultiPatch's default map was written for."""
    return makeXKeys(qapp, name='Surface', keyshape=(8, 10))


def backlightOf(surface, key):
    """Return *key*'s ``(blue, red)`` state on a :class:`FakeXKeys`, after a flush."""
    pump()
    return tuple(surface.dev.backlightState[key[0], key[1]])


def patchManager(monkeypatch, surface):
    manager = MagicMock()
    manager.getDevice.return_value = surface
    monkeypatch.setattr('acq4.modules.MultiPatch.multipatch.getManager', lambda: manager)


class TestMultiPatchControlSurface:
    def test_per_pipette_columns_are_claimed_from_the_grid(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface, nPipettes=3)
        grid = win._pipetteGrid
        assert grid.shape == (5, 3)  # 5 per-pipette rows, one column per pipette
        assert all(c.owner is win for c in grid.flat)
        # columns 0-3 hold the fixed buttons and are not part of the pipette block
        fullGrid = bigSurface.controlGrids(page=0)[0]
        assert fullGrid[0, 3].owner is not win
        assert fullGrid[0, 4] is grid[0, 0]

    def test_fixed_buttons_are_claimed_at_their_historical_positions(
        self, qapp, bigSurface, monkeypatch
    ):
        from acq4.modules.MultiPatch.multipatch import DEFAULT_ACTION_KEYS

        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface)
        byName = {name: control for control, name in win._actionControls.items()}
        assert set(byName) == set(DEFAULT_ACTION_KEYS)
        for name, key in DEFAULT_ACTION_KEYS.items():
            assert byName[name].key == key

    def test_actions_can_be_remapped_from_config(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface, actions={'sealBtn': (7, 9)})
        assert list(win._actionControls.values()) == ['sealBtn']
        assert list(win._actionControls)[0].key == (7, 9)

    def test_a_short_surface_is_skipped_not_fatal(self, qapp, monkeypatch, caplog):
        small = makeXKeys(qapp, name='Surface', keyshape=(3, 4))  # an XK-12
        patchManager(monkeypatch, small)
        with caplog.at_level('WARNING'):
            win = makeMultiPatchWindow(qapp, small, nPipettes=4)
        # 3 rows, and no spare columns past the 4 the fixed buttons occupy
        assert win._pipetteGrid.shape == (3, 0)
        assert win._actionControls  # the in-range fixed buttons still bound
        assert 'could not claim' in caplog.text

    def test_pressing_a_fixed_control_clicks_its_button(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface)
        bigSurface.dev.callback({'keys': [((1, 2), True)]})  # hideMarkersBtn
        pump()
        assert win.ui.hideMarkersBtn.isChecked()

    def test_a_release_does_not_click_anything(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface)
        bigSurface.dev.callback({'keys': [((1, 2), False)]})
        pump()
        assert not win.ui.hideMarkersBtn.isChecked()

    def test_pressing_a_pipette_control_clicks_that_pipettes_button(
        self, qapp, bigSurface, monkeypatch
    ):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface, nPipettes=3)
        bigSurface.dev.callback({'keys': [((2, 6), True)]})  # row 2 = select, col 6 = pipette 3
        pump()
        assert win.pipCtrls[2].ui.selectBtn.isChecked()
        assert not win.pipCtrls[0].ui.selectBtn.isChecked()

    def test_indicators_follow_button_state(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface)
        win.ui.recordBtn.setChecked(True)
        win.updateControlLights()
        assert backlightOf(bigSurface, (7, 2)) == (1, 1)  # recordBtn
        assert backlightOf(bigSurface, (0, 0)) == (0, 0)  # sealBtn is not a toggle

    def test_one_repaint_is_one_driver_call(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface, nPipettes=8)
        pump()
        bigSurface.dev.setBacklightsCalls.clear()
        for ctrl in win.pipCtrls:
            ctrl.ui.activeBtn.setChecked(True)
        win.updateControlLights()
        pump()
        assert len(bigSurface.dev.setBacklightsCalls) == 1

    def test_pipette_indicators_show_active_locked_selected_and_moving(
        self, qapp, bigSurface, monkeypatch
    ):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface, nPipettes=2)
        ctrl = win.pipCtrls[0]
        ctrl.ui.activeBtn.setChecked(True)
        ctrl.ui.lockBtn.setChecked(True)
        ctrl.pip.pipetteDevice.moving = True
        win.updateControlLights()

        assert backlightOf(bigSurface, (0, 4)) == (1, 2)  # active; moving flashes red
        assert backlightOf(bigSurface, (1, 4)) == (1, 0)  # locked, and so not selected
        assert backlightOf(bigSurface, (0, 5)) == (0, 0)  # pipette 2 is idle

    def test_release_lets_the_window_reopen(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface)
        win.releaseControls()
        assert all(c.owner is None for c in bigSurface.allControls(0))
        second = makeMultiPatchWindow(qapp, bigSurface)
        assert second._actionControls

    def test_non_surface_device_is_a_clear_error(self, qapp, monkeypatch):
        patchManager(monkeypatch, object())
        with pytest.raises(TypeError):
            makeMultiPatchWindow(qapp, surface=object())


class TestMultiPatchBacklightFallback:
    """The (blue, red) -> colour fallback used on a surface that takes a colour instead."""

    @pytest.mark.parametrize(
        'state,color',
        [((0, 0), 'k'), ((1, 0), 'b'), ((0, 1), 'r'), ((1, 1), 'm'), ((2, 2), 'm')],
    )
    def test_states_map_to_colours_that_map_back(self, state, color):
        from acq4.modules.MultiPatch.multipatch import BACKLIGHT_COLORS

        blue, red = state
        assert BACKLIGHT_COLORS[(bool(blue), bool(red))] == color
        # every fallback colour is one an X-Keys key can also show, so the indicator is
        # the same one either way rather than a different-looking substitute
        assert XKeys.backlightForColor(color) == (min(blue, 1), min(red, 1))

    def test_flash_goes_native_where_the_surface_offers_it(self, qapp, bigSurface, monkeypatch):
        patchManager(monkeypatch, bigSurface)
        win = makeMultiPatchWindow(qapp, bigSurface)
        control = next(iter(win._actionControls))
        win._setBacklight(control, 0, 2)
        pump()
        assert tuple(bigSurface.dev.backlightState[control.key]) == (0, 2)

    def test_the_colour_fallback_is_used_on_a_surface_without_a_backlight(self, qapp, surface):
        from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

        win = MultiPatchWindow.__new__(MultiPatchWindow)
        win._backlights = {}
        control = surface.getControl('button', 0, LIT_KEY)
        win._bindBacklight(control)
        win._setBacklight(control, 1, 2)  # flash collapses to "lit"
        assert surface.writesFor(control)[-1]['color'] == pg.mkColor('m')

    def test_a_control_that_can_show_nothing_is_reported_once(self, qapp, surface, caplog):
        from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

        win = MultiPatchWindow.__new__(MultiPatchWindow)
        win._backlights = {}
        control = surface.getControl('dial', 0, 'fader')
        with caplog.at_level('WARNING'):
            win._bindBacklight(control)
        assert 'cannot indicate state' in caplog.text
        caplog.clear()
        with caplog.at_level('WARNING'):
            win._setBacklight(control, 1, 1)  # a no-op, not a second complaint
        assert caplog.text == ''
        assert surface.writes == []
