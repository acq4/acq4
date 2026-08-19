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
    # The axes override is what makes a 3D stack navigable at all: without it
    # pg.ImageView guesses, and a small last dimension is read as color rather
    # than the first dimension as time, leaving no frame axis for
    # setCurrentIndex to move along. xvals then labels those frames by index,
    # since the payload carries no real z coordinates.
    axesDict = None
    if stack.ndim == 3:
        axesDict = {"t": 0, "x": 1, "y": 2}
        nFrames = stack.shape[0]
        xvals = np.arange(nFrames, dtype=float)
    else:
        xvals = None
    view.setImage(stack, autoRange=True, autoLevels=True, xvals=xvals, axes=axesDict)
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
        f"{len(traces)} sweeps"
        f" — saved to {payload.get('sequence_dir') or 'nowhere'}"
    ]
    decimation = payload.get("decimation", 1)
    if decimation > 1:
        # Never silent: the pane says what it is not showing, and the
        # undecimated data is in the saved sequence directory named above.
        lines.append(f"plotted decimated {decimation}x; full data on disk")
    return captioned(plot, lines)


def _fitToData(plot, *_) -> None:
    """Let one of MultiPatch's PlotWidgets range over whatever it is showing.

    Every analysis mode picks its own Y range as it is selected, and most of
    those are fixed: steady-state resistance opens on 1 MΩ to 10 GΩ, capacitance
    on 0 to 100 pF. A live plot wants that -- a scale that holds still while
    numbers stream in is what makes a drifting seal legible. A finished attempt
    is the opposite case: the whole history is already in hand, and an operator
    reading it should not have to fit the axes by hand to find the curve.

    enableAutoRange rather than a one-shot fit, because pyqtgraph turns
    auto-range off as soon as a range is set by hand. The fit therefore lasts
    exactly until the operator zooms or pans, and then gets out of the way.

    Takes the plot first and ignores the rest so this can serve as
    sigModeChanged's slot, which emits the plot and its new mode.
    """
    plot.plot.enableAutoRange(x=True, y=True)


def buildTestPulseHistory(payload) -> Qt.QWidget:
    """One FSM action's steady-state resistance plot beside the pipette states it
    walked.

    Reuses MultiPatch's PlotWidget rather than reimplementing the plot. The
    mode combo stays visible, unlike the live plot's: because the whole
    analysis array is retained, re-reading the same attempt through
    capacitance or holding current costs nothing. setFrozen drops the two modes
    that would need the recording itself.
    """
    # Imported here, not at module scope: pipetteControl pulls in PatchPipette
    # and the rest of the MultiPatch module's device imports, and this module is
    # imported by cell_panel at Autopatch startup.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    plot = PlotWidget(mode="ss resistance")
    plot.setFrozen(True)
    plot.newTestPulse(None, payload["history"])
    _fitToData(plot)
    # Selecting a mode re-imposes that mode's own Y range and re-plots a
    # different field, so the fit has to be redone for the field now on screen.
    # sigModeChanged is emitted after both, once there is something to fit to.
    plot.sigModeChanged.connect(_fitToData)

    transitions = Qt.QListWidget()
    rows = list(payload.get("transitions", ()))
    firstTime = rows[0][0] if rows else 0.0
    for when, state in rows:
        # Elapsed rather than absolute: an epoch timestamp says nothing, and how
        # long the FSM sat in each state is what reading a failed patch needs.
        transitions.addItem(f"{when - firstTime:8.2f}s  {state}")

    split = Qt.QWidget()
    splitLayout = Qt.QHBoxLayout()
    splitLayout.setContentsMargins(0, 0, 0, 0)
    splitLayout.addWidget(plot, 2)
    splitLayout.addWidget(transitions, 1)
    split.setLayout(splitLayout)

    reached = payload.get("reached")
    caption = [
        f"entered at {payload.get('entry_state')!r}, "
        + (f"reached {reached!r}" if reached else "no terminal state reached")
    ]
    logFile = payload.get("log_file")
    if logFile:
        caption.append(f"events logged to {logFile}")
    return captioned(split, caption)


# kind -> builder, keyed by the string an action passes to set_details(). A
# builder takes only the payload and returns a widget: it never sees a Cell, an
# ActionLogEntry, or the panel, so nothing it builds can retain any of them.
BUILDERS = {
    "text": buildText,
    "error": buildError,
    "image_stack": buildImageStack,
    "task_results": buildTaskResults,
    "test_pulse_history": buildTestPulseHistory,
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
