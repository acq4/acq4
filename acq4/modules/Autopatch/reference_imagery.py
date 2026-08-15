"""ReferenceImagery: the pinned-frames workflow that opens a slice -- clear the
previous slice's frames, then ask the operator to pin a fresh set."""
from __future__ import annotations

import functools

from acq4.util import Qt

PIN_FRAMES_INSTRUCTION = (
    "Pin reference frames of this slice in the Camera module."
)

_CLEAR_PROMPT = (
    "Clear the pinned frames from the previous slice?\n\n"
    "They are imagery of tissue that is no longer under the objective, and "
    "regions for this slice will be drawn over them."
)


def _askToClear(text: str, parent=None) -> bool:
    """Default prompt: an Ok/Cancel dialog asking to clear the pinned frames.

    Its title and two-paragraph body are specific to a slice starting, not a
    copy of ImagingCtrl's own Clear button confirmation -- only the button set
    (Ok/Cancel) matches. `parent` places the dialog over the calling window
    instead of centring it on the primary screen with no owner.
    """
    answer = Qt.QMessageBox.question(
        parent, "Clear pinned frames?", text,
        Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel,
    )
    return answer == Qt.QMessageBox.Ok


class ReferenceImagery(Qt.QObject):
    """Sequences the Camera module's pinned frames into the start of a slice.

    A QObject, unlike the plain PinnedFrameMirror/CameraMirror classes beside
    it, because something listens to it: Area 3's band re-renders whenever the
    pinned set changes.

    The wait for a fresh set is advisory. Nothing here disables a control or
    blocks a run -- the band says what to do and the operator decides.
    """

    # The instruction this component wants shown, or "". Carries the text so a
    # listener need not call back to ask.
    sigInstructionChanged = Qt.Signal(str)

    def __init__(self, imagingCtrlGetter, prompt=None, parent=None):
        super().__init__()
        self._getter = imagingCtrlGetter
        # Owner window for the default clear-prompt dialog, so it stays over
        # the calling window on a multi-monitor rig instead of centring on
        # the primary screen with no taskbar entry of its own. Unused when a
        # caller supplies its own `prompt`.
        self._parent = parent
        if prompt is not None:
            self._prompt = prompt
        else:
            # functools.partial closing over the `parent` argument, not
            # `self._parent`: a lambda reading self._parent would close over
            # self, making a QObject that references itself -- a cycle
            # reclaimable only by the cyclic collector, exactly the shape
            # AutopatchWindow.teardown() exists to avoid for everything else
            # it owns.
            self._prompt = functools.partial(_askToClear, parent=parent)
        self._source = None
        self._instruction = ""
        # No slice yet, and the instruction is about a slice that has none of
        # its own imagery -- not about the window having just opened.
        self._sliceActive = False

    def beginSlice(self) -> None:
        """New slice's entry point: bind, offer to clear, then recompute.

        Whatever the getter raises propagates rather than being caught here.
        A Camera module closed after startup is an error rather than a state
        to degrade into. `_sliceActive` is only set once `rebind()` has
        returned successfully, so a raised getter leaves this component as if
        no slice had begun rather than stuck active with no source.

        A getter answering None outright (rather than raising) is not that
        case, though, and is not a slice to skip either: a headless window or
        a camera the Camera module has no interface for are both ordinary --
        see _imagingCtrl's own docstring -- so the offer to clear is simply
        skipped rather than raised through, exactly as _refresh() already
        treats a None source as "nothing to show" rather than an error.
        """
        self.rebind()
        self._sliceActive = True
        self._refresh()
        # Bound to a local before the prompt: the prompt is modal and re-enters
        # the Qt event loop, and release() (teardown, dispatched from inside
        # that loop) sets self._source to None. Reading self._source again
        # after the prompt would risk calling clearPinnedFrames() on None.
        source = self._source
        if source is not None and source.pinnedFrames and self._prompt(_CLEAR_PROMPT):
            # Emits sigPinnedFramesChanged, so the recompute below is
            # belt-and-braces rather than the only path.
            source.clearPinnedFrames()
        self._refresh()

    def rebind(self) -> None:
        """Re-resolve the imaging control and move the subscription to it.

        Re-resolved per slice because the operator may have changed the
        selected camera since the last one.

        Tolerant of the getter answering None: a headless window and a
        camera the Camera module has no interface for are both ordinary
        (see _imagingCtrl's own docstring), and there is nothing to
        subscribe to in either case -- exactly the state _refresh() and
        _disconnect() already treat a None source as, not an error.
        """
        self._disconnect()
        self._source = self._getter()
        if self._source is not None:
            self._source.sigPinnedFramesChanged.connect(self._refresh)
        self._refresh()

    def instruction(self) -> str:
        """The guidance this component wants shown, or ""."""
        return self._instruction

    def release(self) -> None:
        """Stop listening. Teardown's call.

        Tolerant of a source Qt has already destroyed, exactly as
        PinnedFrameMirror.unbind() is: Qt.disconnect swallows a dead
        connection's RuntimeError, but the signal is read off the source
        before it can be handed over, and that read raises through a wrapper
        whose C++ object is gone. A raise here would abandon the rest of
        AutopatchWindow.teardown().
        """
        self._sliceActive = False
        self._disconnect()
        self._refresh()

    def _disconnect(self) -> None:
        source, self._source = self._source, None
        if source is not None:
            try:
                Qt.disconnect(source.sigPinnedFramesChanged, self._refresh)
            except RuntimeError:
                pass

    def _refresh(self) -> None:
        """Recompute the instruction from current state, announcing a change.

        A pure function of state rather than of the event that got us here, so
        pinning the first frame and unpinning the last both fall out without
        either being handled: the band shows the instruction exactly while a
        slice has no reference imagery.
        """
        text = ""
        if self._sliceActive and self._source is not None:
            if not self._source.pinnedFrames:
                text = PIN_FRAMES_INSTRUCTION
        if text != self._instruction:
            self._instruction = text
            self.sigInstructionChanged.emit(text)
