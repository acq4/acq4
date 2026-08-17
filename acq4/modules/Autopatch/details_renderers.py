"""Builders for Area 5's detail pane: one per ActionLogEntry.set_details() kind,
turning an action's retained plain-data payload into a widget to mount."""
from __future__ import annotations

from acq4.util import Qt

from .error_display import ErrorBlock


def captioned(widget, lines) -> Qt.QWidget:
    """`widget` under a caption of `lines`, or `widget` itself if there are none.

    Returning the bare widget for an empty caption keeps the pane's widget tree
    as shallow as the payload warrants, rather than wrapping everything in a
    layout that holds an empty label.
    """
    if not lines:
        return widget
    caption = Qt.QLabel("\n".join(str(line) for line in lines))
    caption.setWordWrap(True)
    # Selectable so a directory name or a measured value can be copied out.
    caption.setTextInteractionFlags(Qt.Qt.TextSelectableByMouse)
    wrapper = Qt.QWidget()
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(caption)
    layout.addWidget(widget)
    wrapper.setLayout(layout)
    return wrapper


def buildText(payload) -> Qt.QWidget:
    """Plain lines, read-only and selectable so values can be copied out."""
    view = Qt.QPlainTextEdit("\n".join(str(line) for line in payload.get("lines", ())))
    view.setReadOnly(True)
    return view


def buildError(payload) -> Qt.QWidget:
    """One failed action's traceback. Takes strings, never an exception -- see
    ErrorBlock's own docstring for why."""
    return ErrorBlock(
        payload["exc_type"],
        payload["exc_message"],
        payload["traceback_text"],
        payload.get("cell_repr"),
    )


# kind -> builder, keyed by the string an action passes to set_details(). A
# builder takes only the payload and returns a widget: it never sees a Cell, an
# ActionLogEntry, or the panel, so nothing it builds can retain any of them.
BUILDERS = {
    "text": buildText,
    "error": buildError,
}


def buildDetailsWidget(kind: str, payload) -> Qt.QWidget:
    """The widget for one retained payload.

    An unregistered kind renders as text rather than raising. A payload crosses
    a thread boundary out of protocol code, and a protocol author's typo must
    leave the pane usable instead of taking it down.
    """
    builder = BUILDERS.get(kind)
    if builder is None:
        return buildText(
            {"lines": [f"unrecognized details kind {kind!r}", repr(payload)]}
        )
    return builder(payload)
