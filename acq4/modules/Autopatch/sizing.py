"""Sizing helpers shared by the Autopatch window's panels: floors measured in
rows of a widget's own text, and a label that wraps without growing without
bound."""
from __future__ import annotations

from acq4.util import Qt


def rowsHigh(widget, rows: int) -> int:
    """The height `rows` rows of `widget`'s own text occupy, chrome included.

    A floor stated in rows rather than in pixels, because how tall a row is
    depends on the font the rig is running and a number that reads as three
    lines here is two and a bit somewhere else. Approximate by nature -- this
    measures a minimum nobody is meant to work at for long, not a working size.

    An item view is asked what one of its own rows measures -- delegate, icon
    sizes and all -- but never below a row of its text: it answers -1 while it
    is empty, which is exactly the case at construction time before the first
    cell is queued, and a tree of parameter widgets answers a pixel or two,
    which is a measurement of its own layout rather than of anything readable.
    """
    metrics = widget.fontMetrics()
    # The larger of the two font measurements, because which one a widget lays
    # its rows out on differs: a text edit spaces lines by lineSpacing, while an
    # item view's row is as tall as the glyphs themselves -- and a font whose
    # leading is negative makes those two disagree by a pixel in either
    # direction. A floor that is a pixel generous still fits; one a pixel short
    # crops the last row.
    perRow = max(metrics.height(), metrics.lineSpacing())
    sizeHintForRow = getattr(widget, "sizeHintForRow", None)
    if sizeHintForRow is not None:
        perRow = max(perRow, sizeHintForRow(0))
    frameWidth = getattr(widget, "frameWidth", None)
    return rows * perRow + 2 * (frameWidth() if frameWidth is not None else 0)


def floorAtRows(widget, rows: int) -> None:
    """Let `widget` be squeezed down to `rows` rows of its own text.

    For the scrolling views -- lists, logs, trees -- whose own idea of a
    minimum is QAbstractScrollArea's guess at the smallest viewport still worth
    scrolling, some seventy pixels regardless of what is in it. Inside a panel
    that is itself inside one of this window's scrolling areas, every one of
    those guesses is height the panel insists on before it will shrink, and the
    area starts scrolling the panel bodily -- buttons and all -- rather than
    shortening the lists in it. A few rows and then scroll within itself is
    what the operator asked for and what these views are for.

    An explicit minimum rather than an overridden minimumSizeHint(): the
    layout takes whichever of the two is set explicitly, so this works on the
    stock widgets without a subclass each.
    """
    widget.setMinimumHeight(rowsHigh(widget, rows))


class CompactLabel(Qt.QLabel):
    """A word-wrapping label that takes a few rows and no more, and that never
    trades width for height.

    Word wrap is what stops a long message demanding a panel as wide as the
    message, which in a window of scrolling areas means everything beside it
    behind a horizontal scrollbar. What a wrapping QLabel normally asks in
    exchange is height-for-width: tell me my width and I will tell you my
    height, and the narrower you make me the taller I get. Two things go wrong
    with that inside an area an operator squeezes.

    The loop is the obvious one -- squeezing an area narrower makes the label,
    and so the panel, taller. The quieter one is that Qt has no notion of a
    *minimum* height-for-width across a widget boundary: QWidgetItem answers
    minimumHeightForWidth() with plain heightForWidth(), so one label deep
    inside a panel is enough to make that whole panel's minimum height equal
    its preferred height, and a QScrollArea sizes its content to exactly that.
    An area holding such a panel cannot compact it at all -- squeezing the
    handle only scrolls it -- which is the failure this window is full of
    scrolling viewports to avoid.

    So this label wraps but does not negotiate: it asks for at most `maxRows`
    rows whatever width it is given, and beyond that the message is clipped
    rather than paid for out of the lists and the log around it. Nothing is
    lost by the clipping -- the whole message is in the tooltip, and everything
    written into one of these labels is in the log as well.
    """

    def __init__(self, text: str = "", maxRows: int = 3):
        super().__init__(text)
        self._maxRows = maxRows
        self.setWordWrap(True)
        # setWordWrap turns height-for-width on in the size policy; see the
        # class docstring for why this label wants the wrapping without it.
        policy = self.sizePolicy()
        policy.setHeightForWidth(False)
        self.setSizePolicy(policy)
        self.setToolTip(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        # Nothing the cap clips is lost, only moved somewhere it costs no
        # height. The tooltip is set even for a message that fits: which
        # messages fit depends on how the operator has the window divided at
        # the time, and this label is in no position to know.
        self.setToolTip(text)

    def hasHeightForWidth(self) -> bool:
        return False

    def sizeHint(self):
        hint = super().sizeHint()
        return Qt.QSize(hint.width(), min(hint.height(), rowsHigh(self, self._maxRows)))

    def minimumSizeHint(self):
        # One row, and no width at all: a message about what is happening is
        # the last thing in a squeezed panel that should be deciding how small
        # that panel is allowed to be.
        return Qt.QSize(0, rowsHigh(self, 1))
