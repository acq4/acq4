"""Typography for Stream Dock keys: what :func:`fitText` chooses, and what gets drawn.

Every label on a bound key has to be legible, and a key has 72x72 pixels to say it in --
but legible is not the same as large. Fitting each label to the biggest font it happened to
fit in drew ``X`` at 42pt beside ``clean`` at 22pt and ``above tgt`` at 19pt, which on a
real panel reads as a different typeface per key. So these tests pin the opposite property:
one standard size for every label a consumer paints, shrinking below it only for text that
genuinely will not fit, and never below the floor.

The point sizes here are what the standard works out to with the default UI font at 96 dpi.
The standard itself is a fraction of the display's height (``STANDARD_LINE_FRACTION``) so
that it survives a change of DPI; the point sizes it lands on do not, and a different font
or DPI makes these the record of what to re-measure.
"""

from __future__ import annotations

import pyqtgraph as pg
import pytest

from acq4.devices.StreamDock import render
from acq4.util import Qt

KEY = render.KEY_SIZE
DIAL = render.DIAL_SIZE

#: The standard size on each display acq4 paints, with the default UI font at 96 dpi. A
#: knob strip is taller than a key, so the same fraction of it is a larger font.
STANDARD = {KEY: 13, DIAL: 19}

#: Every label acq4's own consumers paint: a stage axis enable and readout, a microscope
#: lift/dip, a pipette or patch pipette state, and the configured ``label`` overrides the
#: rig uses for them. All of them must come out at the standard size.
CONSUMER_LABELS = [
    'X',
    'XY',
    'XY!',
    'Z',
    'Lift',
    'Dip',
    'Lift\n(unset)',
    'home',
    'clean',
    'approach',
    'above tgt',
    'aboveTarget',
    'x\n40.762 mm',
    'home with nucleus',
    'cell detect',
    'out',
    'Seal',
    'idle',
    'Break In',
    'whole cell',
]


def ink(image: Qt.QImage, background='k') -> set:
    """Return the pixels of *image* that are not *background*: the drawn text itself."""
    rgb = pg.mkColor(background).rgb()
    return {
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) != rgb
    }


def extent(image: Qt.QImage, background='k') -> tuple:
    """Return the ``(width, height)`` of *image*'s drawn text, or ``(0, 0)`` if there is none."""
    pixels = ink(image, background)
    if not pixels:
        return (0, 0)
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def lineSpacing(pointSize: int) -> int:
    """Return the line height of the default font at *pointSize*, in pixels."""
    font = Qt.QFont()
    font.setPointSize(pointSize)
    return Qt.QFontMetrics(font).lineSpacing()


class TestTheStandardSize:
    """The standard is a fraction of the display, measured against the live font."""

    @pytest.mark.parametrize('size', list(STANDARD))
    def test_it_is_the_size_measured_at_96_dpi(self, qapp, size):
        assert render.standardPointSize(size) == STANDARD[size]

    @pytest.mark.parametrize('size', list(STANDARD))
    def test_one_line_is_the_documented_fraction_of_the_display(self, qapp, size):
        # the definition: a line of standard text is STANDARD_LINE_FRACTION of the height,
        # and is the largest point size that still is -- which is what makes the same
        # fraction of the key come out at any DPI, where a pinned point size would not
        target = render.STANDARD_LINE_FRACTION * size[1]
        standard = render.standardPointSize(size)
        assert lineSpacing(standard) <= target
        assert lineSpacing(standard + 1) > target

    def test_three_standard_lines_fit_a_key_and_a_fourth_does_not(self, qapp):
        # what the fraction buys: a key holds a three-line label at the standard size, so
        # 'home with nucleus' needs no shrinking
        rect = render.textRect(KEY)
        assert 3 * lineSpacing(STANDARD[KEY]) <= rect.height()
        assert 4 * lineSpacing(STANDARD[KEY]) > rect.height()

    def test_a_taller_display_gets_a_larger_standard(self, qapp):
        # the knob strip is 100px tall against a key's 72, and the same fraction of it is a
        # bigger font -- not the same number of points on a bigger screen
        assert render.standardPointSize(DIAL) > render.standardPointSize(KEY)

    def test_a_display_too_small_for_the_standard_gets_the_floor(self, qapp):
        assert render.standardPointSize((8, 8)) == render.MIN_POINT_SIZE


class TestOneSizeForEveryLabel:
    """The point of the standard: what a label says must not change how big it is."""

    @pytest.mark.parametrize('label', CONSUMER_LABELS)
    @pytest.mark.parametrize('size', list(STANDARD))
    def test_every_label_a_consumer_paints_is_at_the_standard(self, qapp, size, label):
        assert render.fitText(label, size).pointSize == STANDARD[size]

    def test_the_shortest_and_longest_labels_agree(self, qapp):
        # 'X' used to be 42pt and 'home with nucleus' 13pt on the same panel
        sizes = {render.fitText(label, KEY).pointSize for label in CONSUMER_LABELS}
        assert sizes == {STANDARD[KEY]}

    def test_a_short_label_no_longer_fills_the_key(self, qapp):
        # 'X' was drawn 56px tall on a 72px key; at the standard it is a line of text
        assert extent(render.renderTextImage('X', KEY))[1] <= lineSpacing(STANDARD[KEY])

    def test_one_line_labels_are_drawn_the_same_height(self, qapp):
        heights = {extent(render.renderTextImage(label, KEY))[1] for label in ('Lift', 'home')}
        assert len(heights) == 1

    @pytest.mark.parametrize('label', CONSUMER_LABELS)
    def test_no_label_a_consumer_paints_is_broken_mid_word(self, qapp, label):
        # breaking inside a word is a last resort, and at the standard size nothing acq4
        # paints reaches it: 'home' and 'approach' used to be split as 'hom e' / 'appro ach'
        assert render.fitText(label, KEY).flags == render.TEXT_FLAGS

    @pytest.mark.parametrize('label', CONSUMER_LABELS)
    def test_the_text_is_drawn_as_given_apart_from_one_camel_case_seam(self, qapp, label):
        fit = render.fitText(label, KEY)
        if label == 'aboveTarget':
            # no space to wrap at and too wide for one line, so it is offered its seam
            assert fit.text == 'above' + render.ZERO_WIDTH_SPACE + 'Target'
        else:
            assert fit.text == label


class TestTextThatWillNotFit:
    """Below the standard is where the shrink loop and the break rules still live."""

    def test_a_camel_case_word_breaks_at_the_camel_seam_before_anywhere_else(self, qapp):
        fit = render.fitText('aboveTarget', KEY)
        assert fit.pointSize == STANDARD[KEY]
        assert fit.text == 'above' + render.ZERO_WIDTH_SPACE + 'Target'
        assert fit.flags == render.TEXT_FLAGS  # a real break, not a break anywhere

    def test_a_word_with_no_seam_that_does_not_fit_is_broken_anywhere(self, qapp):
        # not a label acq4 paints, but the last resort has to still work
        fit = render.fitText('concentration', KEY)
        assert fit.flags == render.WRAP_ANYWHERE_FLAGS
        assert fit.pointSize == STANDARD[KEY]

    def test_text_far_too_long_shrinks_below_the_standard(self, qapp):
        fit = render.fitText('m' * 40, KEY)
        assert fit.pointSize < STANDARD[KEY]
        assert fit.pointSize >= render.MIN_POINT_SIZE

    def test_a_label_longer_than_the_key_is_drawn_at_the_floor_not_below_it(self, qapp):
        fit = render.fitText('m' * 200, KEY)
        assert fit.pointSize == render.MIN_POINT_SIZE
        assert fit.flags == render.WRAP_ANYWHERE_FLAGS

    @pytest.mark.parametrize(
        'label',
        ['X', 'aboveTarget', 'extracellularRecording', 'm' * 40, 'objective2', 'a b c d e f g'],
    )
    def test_nothing_is_ever_fitted_below_the_floor(self, qapp, label):
        for size in (KEY, DIAL):
            assert render.fitText(label, size).pointSize >= render.MIN_POINT_SIZE

    @pytest.mark.parametrize('label', CONSUMER_LABELS)
    def test_no_label_a_consumer_paints_is_ever_below_the_standard(self, qapp, label):
        for size in (KEY, DIAL):
            assert render.fitText(label, size).pointSize == STANDARD[size]


class TestOverridingTheStandard:
    """A caller may ask for a bigger glyph; nothing in acq4 does."""

    def test_an_explicit_maximum_is_honoured(self, qapp):
        assert render.fitText('X', KEY, maxPointSize=30).pointSize == 30

    def test_an_explicit_maximum_is_still_capped(self, qapp):
        assert render.fitText('X', (400, 400), maxPointSize=500).pointSize == render.MAX_POINT_SIZE

    def test_an_override_does_not_rescue_text_that_does_not_fit(self, qapp):
        assert render.fitText('m' * 200, KEY, maxPointSize=64).pointSize == render.MIN_POINT_SIZE


class TestDrawing:
    def test_empty_text_is_just_the_background(self, qapp):
        img = render.renderTextImage('', KEY, background='r')
        assert (img.width(), img.height()) == KEY
        assert ink(img, 'r') == set()

    def test_the_colours_asked_for_are_the_ones_drawn(self, qapp):
        img = render.renderTextImage('Seal', KEY, color='r', background='b')
        assert img.pixel(0, 0) == pg.mkColor('b').rgb()
        drawn = ink(img, 'b')
        assert drawn  # something was actually drawn
        assert pg.mkColor('r').rgb() in {img.pixel(x, y) for x, y in drawn}

    def test_the_text_is_the_same_shape_whatever_it_is_coloured(self, qapp):
        # this is the whole point of drawing every label rather than only the coloured
        # ones: a key must not change the size or shape of its label when it lights up
        plain = render.renderTextImage('aboveTarget', KEY)
        coloured = render.renderTextImage('aboveTarget', KEY, color='k', background='y')
        assert ink(plain, 'k') == ink(coloured, 'y')

    def test_a_label_is_rendered_at_the_size_it_was_fitted_at(self, qapp):
        # drawing must use the font that was measured, or the fit means nothing
        fit = render.fitText('Lift', KEY)
        font = Qt.QFont()
        font.setPointSize(fit.pointSize)
        bounds = Qt.QFontMetrics(font).boundingRect(render.textRect(KEY), fit.flags, fit.text)
        drawn = extent(render.renderTextImage('Lift', KEY))
        assert drawn[0] <= bounds.width() and drawn[1] <= bounds.height()
        assert drawn[1] >= 0.5 * bounds.height()

    def test_a_label_is_drawn_at_the_standard_unless_told_otherwise(self, qapp):
        standard = extent(render.renderTextImage('Lift', KEY))
        bigger = extent(render.renderTextImage('Lift', KEY, maxPointSize=30))
        assert bigger[1] > standard[1]
