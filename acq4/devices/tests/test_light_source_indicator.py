"""How a light source draws itself on a control surface.

Covers the wavelength-to-colour mapping, the indicator image itself, and which of the two
:meth:`~acq4.devices.LightSource.LightSource._bindIndicator` resolves for a control that
can show a picture, one that can only show a colour, and one that can show nothing.

Everything here is headless, against
:class:`~acq4.devices.MockControlSurface.MockControlSurface`; the X-Keys LED-pair path is
exercised against the device itself in ``test_control_surface_consumers.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pyqtgraph as pg
import pytest

from acq4.Manager import getManager
from acq4.devices.LightSource import (
    INFRARED_COLOR,
    ULTRAVIOLET_COLOR,
    UNKNOWN_WAVELENGTH_COLOR,
    LightSource,
    renderSourceIndicator,
    wavelengthToColor,
)
from acq4.devices.MockControlSurface import MockControlSurface
from acq4.util import Qt

IMG_KEY = ('img', 0, 0)
LIT_KEY = ('lit', 0, 0)
KEY_SIZE = (72, 72)
nm = 1e-9


def pump(iterations=3):
    """Deliver queued Qt events so that control signals arrive."""
    for _ in range(iterations):
        Qt.QApplication.processEvents()


@pytest.fixture(scope='module')
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture(autouse=True)
def globalManager(monkeypatch):
    """Install a fake in the global Manager singleton slot, which binding a control needs."""
    dm = MagicMock()
    monkeypatch.setattr('acq4.Manager.Manager.single', dm)
    return dm


@pytest.fixture
def surface(qapp):
    return MockControlSurface(MagicMock(), {}, 'MockSurface')


class FakeLightSource(LightSource):
    """Concrete LightSource that only remembers what it was told."""

    def setSourceActive(self, name, active):
        self.sourceConfigs[name]['active'] = bool(active)
        self._updateXkeyLight(name)
        self.sigLightChanged.emit(self, name)


def makeLightSource(surface, sourceConf, sourceName='Blue', name='LEDs'):
    dm = getManager()
    dm.getDevice.return_value = surface
    dev = FakeLightSource(dm, {}, name)
    dev.addSource(sourceName, dict(sourceConf))
    return dev


def controlConf(key, type='button'):
    return {'device': 'MockSurface', 'type': type, 'key': key}


# ------------------------------------------------------------------ wavelength -> colour


class TestWavelengthToColor:
    @pytest.mark.parametrize(
        'wavelength,dominant',
        [
            (400 * nm, 'blue'),
            (470 * nm, 'blue'),
            (532 * nm, 'green'),
            (589 * nm, 'red'),
            (650 * nm, 'red'),
        ],
    )
    def test_a_visible_wavelength_gets_its_spectral_colour(self, wavelength, dominant):
        color = wavelengthToColor(wavelength)
        channels = {'red': color.red(), 'green': color.green(), 'blue': color.blue()}
        assert channels[dominant] == max(channels.values())
        assert max(channels.values()) == 255, "the mapping is full intensity, not faded"

    def test_infrared_is_deep_red_rather_than_the_black_a_literal_mapping_gives(self):
        """The rig's IR source is 850 nm: outside the visible range, where a spectral
        mapping has no colour at all, and black on a key reads as a dead key."""
        color = wavelengthToColor(850 * nm)
        assert color.getRgb()[:3] == INFRARED_COLOR
        assert color != pg.mkColor('k')

    def test_ultraviolet_goes_the_way_the_spectrum_was_heading(self):
        assert wavelengthToColor(360 * nm).getRgb()[:3] == ULTRAVIOLET_COLOR

    @pytest.mark.parametrize('wavelength', [None, 0, -1, float('nan'), float('inf'), 'blue'])
    def test_no_usable_wavelength_is_neutral_white(self, wavelength):
        """A source with no wavelength configured -- a white LED, or an omission -- says
        nothing about its spectrum, so neither does its colour."""
        assert wavelengthToColor(wavelength).getRgb()[:3] == UNKNOWN_WAVELENGTH_COLOR


# ----------------------------------------------------------------- the indicator picture


class TestRenderSourceIndicator:
    def test_off_is_an_outlined_circle_and_on_is_a_filled_one(self, qapp):
        color = wavelengthToColor(470 * nm)
        off = renderSourceIndicator('Blue', color, filled=False, size=KEY_SIZE)
        on = renderSourceIndicator('Blue', color, filled=True, size=KEY_SIZE)
        assert (off.width(), off.height()) == KEY_SIZE
        # the middle of the circle is the only place the two can differ
        assert Qt.QColor(on.pixel(36, 24)) == color
        assert Qt.QColor(off.pixel(36, 24)) == pg.mkColor('k')
        assert off != on

    def test_the_outline_is_drawn_in_the_wavelength_colour(self, qapp):
        color = wavelengthToColor(470 * nm)
        off = renderSourceIndicator('Blue', color, filled=False, size=KEY_SIZE)
        rim = [Qt.QColor(off.pixel(x, 24)) for x in range(36)]
        assert color in rim

    def test_rendering_is_deterministic_so_a_test_can_predict_a_write(self, qapp):
        args = ('Blue', wavelengthToColor(470 * nm))
        assert renderSourceIndicator(*args, filled=True, size=KEY_SIZE) == (
            renderSourceIndicator(*args, filled=True, size=KEY_SIZE)
        )

    def test_an_unnamed_source_is_the_circle_alone(self, qapp):
        image = renderSourceIndicator(None, 'r', filled=True, size=KEY_SIZE)
        assert (image.width(), image.height()) == KEY_SIZE
        assert Qt.QColor(image.pixel(36, 36)) == pg.mkColor('r')


# ------------------------------------------------------------ what reaches which surface


class TestDisplayIndicator:
    def indicatorWrites(self, surface, control):
        return [w for w in surface.writesFor(control) if w['op'] == 'image']

    def test_a_display_key_shows_the_name_under_a_circle_it_opens_and_closes(self, surface):
        dev = makeLightSource(
            surface, {'wavelength': 470 * nm, 'control': controlConf(list(IMG_KEY))}
        )
        control = surface.getControl('button', 0, IMG_KEY)
        color = wavelengthToColor(470 * nm)

        # bound while the source is off: the open circle
        assert self.indicatorWrites(surface, control)[-1]['image'] == renderSourceIndicator(
            'Blue', color, filled=False, size=KEY_SIZE
        )

        dev.setSourceActive('Blue', True)
        assert self.indicatorWrites(surface, control)[-1]['image'] == renderSourceIndicator(
            'Blue', color, filled=True, size=KEY_SIZE
        )

        dev.setSourceActive('Blue', False)
        assert self.indicatorWrites(surface, control)[-1]['image'] == renderSourceIndicator(
            'Blue', color, filled=False, size=KEY_SIZE
        )

    def test_the_circle_takes_the_configured_wavelength_colour(self, surface):
        dev = makeLightSource(
            surface,
            {'wavelength': 850 * nm, 'control': controlConf(list(IMG_KEY))},
            sourceName='IR',
        )
        control = surface.getControl('button', 0, IMG_KEY)
        dev.setSourceActive('IR', True)
        assert self.indicatorWrites(surface, control)[-1]['image'] == renderSourceIndicator(
            'IR', pg.mkColor(INFRARED_COLOR), filled=True, size=KEY_SIZE
        )

    def test_a_source_with_no_wavelength_still_gets_an_indicator(self, surface):
        dev = makeLightSource(surface, {'control': controlConf(list(IMG_KEY))}, sourceName='White')
        control = surface.getControl('button', 0, IMG_KEY)
        dev.setSourceActive('White', True)
        assert self.indicatorWrites(surface, control)[-1]['image'] == renderSourceIndicator(
            'White', pg.mkColor(UNKNOWN_WAVELENGTH_COLOR), filled=True, size=KEY_SIZE
        )

    def test_pressing_the_key_toggles_the_source_and_closes_the_circle(self, surface):
        dev = makeLightSource(
            surface, {'wavelength': 470 * nm, 'control': controlConf(list(IMG_KEY))}
        )
        control = surface.getControl('button', 0, IMG_KEY)
        surface.mockPress(key=IMG_KEY)
        pump()
        assert dev.sourceActive('Blue') is True
        assert self.indicatorWrites(surface, control)[-1]['image'] == renderSourceIndicator(
            'Blue', wavelengthToColor(470 * nm), filled=True, size=KEY_SIZE
        )


class TestIndicatorDegradation:
    def test_a_colour_only_key_keeps_the_colour_path(self, surface):
        """Outlined versus filled means nothing on a key with no pixels, so a key that
        takes only a colour lights as it always has."""
        dev = makeLightSource(
            surface, {'wavelength': 470 * nm, 'control': controlConf(list(LIT_KEY))}
        )
        control = surface.getControl('button', 0, LIT_KEY)
        surface.clearWrites()

        dev.setSourceActive('Blue', True)
        write = surface.writesFor(control)[-1]
        assert (write['op'], write['color']) == ('color', pg.mkColor('m'))

        dev.setSourceActive('Blue', False)
        write = surface.writesFor(control)[-1]
        assert (write['op'], write['color']) == ('color', pg.mkColor('k'))
        assert not [w for w in surface.writesFor(control) if w['op'] == 'image']

    def test_a_control_with_no_output_at_all_is_reported_once(self, surface, caplog):
        with caplog.at_level('WARNING'):
            dev = makeLightSource(
                surface, {'wavelength': 470 * nm, 'control': controlConf('fader', type='dial')}
            )
        assert 'will not indicate' in caplog.text
        assert dev._sourceIndicators == {}

        caplog.clear()
        with caplog.at_level('WARNING'):
            dev.setSourceActive('Blue', True)
            dev.setSourceActive('Blue', False)
        assert surface.writes == []
        assert caplog.text == ''
