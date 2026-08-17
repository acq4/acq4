"""Builders for Area 5's detail pane: one per ActionLogEntry.set_details() kind,
turning an action's retained plain-data payload into a widget to mount."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg

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


def buildImageStack(payload) -> Qt.QWidget:
    """A z-stack in a pg.ImageView, opened at the frame the cell was found on.

    setImage jumps to frame 0, which for a cellfie is the top of the stack and
    shows nothing; center_index is the plane the cell actually sits on.
    """
    view = pg.ImageView()
    stack = np.asarray(payload["stack"])
    # Provide frame indices as xvals so setCurrentIndex works. Explicitly set
    # axes for 3D arrays so the first dimension (z-stack) is treated as time,
    # not as color (which would be the default guess for small last dimensions).
    axes_dict = None
    if stack.ndim == 3:
        axes_dict = {'t': 0, 'x': 1, 'y': 2}
        n_frames = stack.shape[0]
        xvals = np.arange(n_frames, dtype=float)
    else:
        xvals = None
    view.setImage(stack, autoRange=True, autoLevels=True, xvals=xvals, axes=axes_dict)
    centerIndex = payload.get("center_index")
    if centerIndex is not None:
        view.setCurrentIndex(centerIndex)
    title = payload.get("title") or ""
    return captioned(view, [title] if title else [])


def buildTaskResults(payload) -> Qt.QWidget:
    """One TaskRunner sequence's sweeps, coloured over sequence index so the
    order they ran in is readable at a glance."""
    plot = pg.PlotWidget()
    plot.setLabels(left=("primary", payload.get("units") or ""), bottom=("time", "s"))
    traces = list(payload.get("traces", ()))
    for index, (times, values) in enumerate(traces):
        plot.plot(
            np.asarray(times),
            np.asarray(values),
            pen=pg.intColor(index, hues=max(len(traces), 1)),
        )
    lines = [
        f"{payload.get('sweep_count', len(traces))} sweeps"
        f" — saved to {payload.get('sequence_dir') or 'nowhere'}"
    ]
    decimation = payload.get("decimation", 1)
    if decimation > 1:
        # Never silent: the pane says what it is not showing, and the
        # undecimated data is in the saved sequence directory named above.
        lines.append(f"plotted decimated {decimation}x; full data on disk")
    return captioned(plot, lines)


# kind -> builder, keyed by the string an action passes to set_details(). A
# builder takes only the payload and returns a widget: it never sees a Cell, an
# ActionLogEntry, or the panel, so nothing it builds can retain any of them.
BUILDERS = {
    "text": buildText,
    "error": buildError,
    "image_stack": buildImageStack,
    "task_results": buildTaskResults,
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
