"""Image rendering and encoding for the Stream Dock surface.

A Stream Dock key or knob strip is a small display, and the protocol's ``setImage`` takes
a base64 PNG data URI, so everything a control is asked to show ends up here: a colour
becomes a solid fill (:func:`renderSolidImage`), every label becomes drawn text
(:func:`renderTextImage`, laid out by :func:`fitText`), and all of it is encoded by
:func:`imageToDataUri`.

This is the natural home for these because a display is a Stream Dock idiosyncrasy: an
X-Keys key has one blue and one red LED and no pixels at all, so nothing generic has any
use for them.

Everything here works on ``QImage``, which -- unlike ``QPixmap`` -- may be created and
painted on any thread, so rendering and encoding can run on the surface's sender thread
and never block the GUI. A ``QApplication`` must nonetheless exist before any ``QImage``
is constructed.
"""

from __future__ import annotations

import base64
import collections
import re

import numpy as np
import pyqtgraph as pg

from acq4.util import Qt

#: Key image size on the Stream Dock panels we support.
KEY_SIZE = (72, 72)

#: Knob touch-strip size.
DIAL_SIZE = (200, 100)


def toQImage(image) -> Qt.QImage:
    """Coerce *image* to a ``QImage``.

    Parameters
    ----------
    image : QImage | ndarray | str
        A ``QImage`` is returned unchanged. An ndarray is interpreted as ``(row, col)`` or
        ``(row, col, channel)``. A string is a filesystem path.

    Returns
    -------
    QImage
    """
    if isinstance(image, Qt.QImage):
        return image
    if isinstance(image, np.ndarray):
        return pg.makeQImage(image, transpose=False)
    if isinstance(image, str):
        img = Qt.QImage(image)
        if img.isNull():
            raise ValueError(f"Could not load image file {image!r}")
        return img
    raise TypeError(f"Cannot interpret {type(image).__name__} as an image")


def renderSolidImage(color, size) -> Qt.QImage:
    """Return a ``QImage`` of *size* ``(width, height)`` filled with *color*.

    *color* is anything :func:`pyqtgraph.mkColor` accepts: a ``QColor``, a colour name, a
    ``'#rrggbb'`` string, an ``(r, g, b[, a])`` tuple, or a single grey level.
    """
    width, height = size
    img = Qt.QImage(int(width), int(height), Qt.QImage.Format_ARGB32)
    img.fill(pg.mkColor(color))
    return img


#: Smallest point size worth drawing. Text that will not fit even when broken up is drawn
#: at this size and clipped by the painter, because a font small enough to fit it would be
#: too small to read anyway: on a 72px key, 6pt is a 10px line and 4pt is a 6px one.
MIN_POINT_SIZE = 6

#: Largest point size this module ever considers, whatever it is asked for.
MAX_POINT_SIZE = 64

#: Standard label line height, as a fraction of the display's height.
#:
#: This is the size every label is drawn at unless it genuinely will not fit. It is a
#: fraction of the display rather than a number of points because a point size is
#: DPI-dependent: the same string fitted 49pt on one rig and 42pt on another, so a point
#: size pinned here would draw a different-sized label on every rig. A fraction of the key,
#: converted to points against the font metrics actually in force by
#: :func:`standardPointSize`, draws the same-sized label on all of them.
#:
#: 0.3 puts three standard lines on a 72px key with a little room to spare, and works out
#: at 13pt at 96 dpi -- which is the size the two-line knob position readout already
#: chose for itself, and the size the rig owner asked every other label to match.
STANDARD_LINE_FRACTION = 0.3

#: How a label is laid out: centred, broken at word boundaries only.
TEXT_FLAGS = Qt.Qt.AlignCenter | Qt.Qt.TextWordWrap

#: The same, but allowed to break inside a word. Used only where word boundaries cannot
#: help, because a single long word has none.
WRAP_ANYWHERE_FLAGS = TEXT_FLAGS | Qt.Qt.TextWrapAnywhere

#: Zero-width space, offered to word wrapping as a break it may use. It has no width and
#: no glyph, so it changes where a label breaks and nothing about how it looks.
ZERO_WIDTH_SPACE = '\u200b'

#: Seams inside a run of word characters where a break reads naturally: the camelCase seam
#: in ``aboveTarget`` and the letter-to-digit seam in ``objective2``.
_WORD_SEAM = re.compile(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=\d)')

#: What :func:`fitText` settled on: the point size to draw at, the text to draw (which may
#: carry :data:`ZERO_WIDTH_SPACE` break opportunities the caller did not write) and the
#: layout flags to draw it with.
TextFit = collections.namedtuple('TextFit', ['pointSize', 'text', 'flags'])

#: A candidate layout and how tall it came out, which is what says whether the fit was
#: limited by width or by height.
_Fitted = collections.namedtuple('_Fitted', ['pointSize', 'height', 'text', 'flags'])


def textRect(size) -> Qt.QRect:
    """Return the rectangle a label occupies on an image of *size* ``(width, height)``.

    Inset by two pixels, so that text does not run into the edge of a key.
    """
    width, height = int(size[0]), int(size[1])
    return Qt.QRect(2, 2, max(1, width - 4), max(1, height - 4))


def standardPointSize(size) -> int:
    """Return the point size of one standard line of text on a display of *size*.

    The standard is defined in pixels -- :data:`STANDARD_LINE_FRACTION` of the display's
    height -- and turned into a point size here by measuring the font that will actually be
    used, so that the label occupies the same fraction of the key at any screen DPI. The
    72px key that gives 13pt at 96 dpi gives 10pt at 120 dpi, and both draw a 21-pixel line.

    The whole range is measured rather than stopping at the first size that is too tall,
    because font metrics are not guaranteed to grow smoothly with point size.

    Parameters
    ----------
    size : tuple
        ``(width, height)`` of the display in pixels.

    Returns
    -------
    int
        Never below :data:`MIN_POINT_SIZE`, however small the display.
    """
    target = STANDARD_LINE_FRACTION * int(size[1])
    font = Qt.QFont()
    best = MIN_POINT_SIZE
    for pointSize in range(MIN_POINT_SIZE, MAX_POINT_SIZE + 1):
        font.setPointSize(pointSize)
        if Qt.QFontMetrics(font).lineSpacing() <= target:
            best = pointSize
    return best


def fitText(text, size, maxPointSize=None) -> TextFit:
    """Choose how to lay *text* out on an image of *size* ``(width, height)``.

    Every label starts at the standard size for this display (:func:`standardPointSize`)
    and is shrunk from there only if it does not fit, so that callers do not have to
    measure anything and so that a one-glyph label and a three-word one come out the same
    size. Starting instead from the largest size a key can hold drew ``X`` at 42pt beside
    ``clean`` at 22pt purely because ``X`` is short, and that is the inconsistency the
    standard size exists to remove.

    Shrinking alone is not enough. Word wrapping cannot break ``aboveTarget``, so that
    label is fitted on width with everything on one line, and width runs out before height
    does: it drops a couple of points below the standard for no reason but the lack of a
    space, with a third of the key blank. So when the chosen layout leaves room for another
    line -- the signature of a fit that ran out of width rather than height -- two more
    layouts are measured and the largest of the three wins:

    1. the text as given, broken at word boundaries;
    2. the same with a zero-width break offered at each camelCase or letter-to-digit seam,
       so that ``aboveTarget`` may break as ``above`` / ``Target``;
    3. the text as given, broken wherever it has to be.

    Ties go to the earliest, so a break the reader would have chosen is preferred to one in
    the middle of a word -- and since no candidate may exceed the standard size, a label
    that already fits at the standard is left exactly as it was given. At the standard size
    that is every label acq4's own consumers paint except ``aboveTarget``, which breaks at
    its camelCase seam; breaking mid-word is a last resort that nothing reaches.

    Parameters
    ----------
    text : str
        Text to lay out. Newlines are honoured.
    size : tuple
        ``(width, height)`` of the image in pixels.
    maxPointSize : int, optional
        Largest font size to consider. Defaults to the standard size for *size*. Pass a
        larger one only where a bigger glyph is genuinely wanted: a label drawn above the
        standard is a label out of step with the rest of the panel.

    Returns
    -------
    TextFit
        ``(pointSize, text, flags)``, ready for ``QPainter.drawText``.
    """
    text = '' if text is None else str(text)
    rect = textRect(size)
    maxPointSize = standardPointSize(size) if maxPointSize is None else maxPointSize

    best = _fit(text, TEXT_FLAGS, rect, maxPointSize)
    if best is None or _roomForAnotherLine(best, rect):
        seamed = _WORD_SEAM.sub(ZERO_WIDTH_SPACE, text)
        candidates = [] if seamed == text else [_fit(seamed, TEXT_FLAGS, rect, maxPointSize)]
        candidates.append(_fit(text, WRAP_ANYWHERE_FLAGS, rect, maxPointSize))
        for candidate in candidates:
            if candidate is None:
                continue
            if best is None or candidate.pointSize > best.pointSize:
                best = candidate
    if best is None:
        # longer than the key can hold at any size worth reading: break it as hard as
        # possible, draw it at the floor and let the painter clip what is left over
        return TextFit(MIN_POINT_SIZE, text, WRAP_ANYWHERE_FLAGS)
    return TextFit(best.pointSize, best.text, best.flags)


def _fit(text, flags, rect: Qt.QRect, maxPointSize):
    """Largest point size in ``[MIN_POINT_SIZE, maxPointSize]`` at which *text* fits *rect*.

    Returns a :data:`_Fitted`, or None if the text fits at none of those sizes. The search
    is linear from the top: font metrics are not guaranteed to grow smoothly with point
    size, so this is exact where a bisection would only be close, and it is cheap at these
    sizes.
    """
    font = Qt.QFont()
    for pointSize in range(min(int(maxPointSize), MAX_POINT_SIZE), MIN_POINT_SIZE - 1, -1):
        font.setPointSize(pointSize)
        bounds = Qt.QFontMetrics(font).boundingRect(rect, flags, text)
        if bounds.width() <= rect.width() and bounds.height() <= rect.height():
            return _Fitted(pointSize, bounds.height(), text, flags)
    return None


def _roomForAnotherLine(fitted, rect: Qt.QRect) -> bool:
    """Whether one more line of *fitted*'s font would still fit *rect*.

    True means the fit was limited by width rather than by height, and so that breaking the
    text differently may buy a larger font.
    """
    font = Qt.QFont()
    font.setPointSize(fitted.pointSize)
    return fitted.height + Qt.QFontMetrics(font).lineSpacing() <= rect.height()


def renderTextImage(text, size, color=None, background=None, maxPointSize=None) -> Qt.QImage:
    """Render *text* into a ``QImage`` of *size* ``(width, height)``.

    Every label a Stream Dock key shows comes through here, coloured or not, so that a key
    looks the same highlighted as unhighlighted. :func:`fitText` decides the point size --
    the standard one, unless the text will not fit at it -- and the line breaks.

    Parameters
    ----------
    text : str
        Text to draw. Newlines are honoured.
    size : tuple
        ``(width, height)`` in pixels.
    color : optional
        Text colour; default white.
    background : optional
        Background colour; default opaque black.
    maxPointSize : int, optional
        Largest font size to consider; see :func:`fitText`. Defaults to the standard size,
        which is what every consumer in acq4 uses.
    """
    width, height = int(size[0]), int(size[1])
    img = Qt.QImage(width, height, Qt.QImage.Format_ARGB32)
    img.fill(pg.mkColor('k' if background is None else background))

    text = '' if text is None else str(text)
    if text == '':
        return img

    fit = fitText(text, size, maxPointSize=maxPointSize)
    # the font fitText measured, which is the application's rather than QPainter's notion
    # of a default: the two agree, and measuring one while drawing the other would not
    font = Qt.QFont()
    font.setPointSize(fit.pointSize)

    painter = Qt.QPainter(img)
    try:
        painter.setRenderHint(Qt.QPainter.TextAntialiasing)
        painter.setPen(pg.mkColor('w' if color is None else color))
        painter.setFont(font)
        painter.drawText(textRect(size), fit.flags, fit.text)
    finally:
        painter.end()
    return img


def scaleToFit(image: Qt.QImage, size) -> Qt.QImage:
    """Return *image* scaled to *size* ``(width, height)``, or unchanged if it already is.

    The aspect ratio is ignored: a key image is square and a knob strip is not, and a
    letterboxed image on a 200x100 strip wastes most of it.
    """
    width, height = int(size[0]), int(size[1])
    if image.width() == width and image.height() == height:
        return image
    return image.scaled(width, height, Qt.Qt.IgnoreAspectRatio, Qt.Qt.SmoothTransformation)


def imageToDataUri(image: Qt.QImage, size=None) -> str:
    """Encode *image* as a base64 PNG data URI, scaled to *size* if given.

    Parameters
    ----------
    image : QImage
        The image to encode.
    size : tuple, optional
        ``(width, height)`` to scale to first.

    Returns
    -------
    str
        e.g. ``'data:image/png;base64,iVBORw0KGgo...'``
    """
    if size is not None:
        image = scaleToFit(image, size)
    buf = Qt.QBuffer()
    buf.open(Qt.QIODevice.WriteOnly)
    try:
        if not image.save(buf, 'PNG'):
            raise ValueError(f"Could not encode a {image.width()}x{image.height()} image as PNG")
        payload = base64.b64encode(bytes(buf.data())).decode('ascii')
    finally:
        buf.close()
    return f'data:image/png;base64,{payload}'
