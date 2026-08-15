"""ReferenceImagery: the pinned-frames workflow that opens a slice -- clear the
previous slice's frames, then ask the operator to pin a fresh set."""
from __future__ import annotations

from acq4.util import Qt

PIN_FRAMES_INSTRUCTION = (
    "Pin reference frames of this slice in the Camera module."
)

_CLEAR_PROMPT = (
    "Clear the pinned frames from the previous slice?\n\n"
    "They are imagery of tissue that is no longer under the objective, and "
    "regions for this slice will be drawn over them."
)


def _askToClear(text: str) -> bool:
    """Default prompt: the same confirmation ImagingCtrl uses for its own
    Clear button, so clearing frames asks the same way wherever it starts."""
    answer = Qt.QMessageBox.question(
        None, "Clear pinned frames?", text,
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

    def __init__(self, imagingCtrlGetter, prompt=None):
        super().__init__()
        self._getter = imagingCtrlGetter
        self._prompt = prompt if prompt is not None else _askToClear
        self._source = None
        self._instruction = ""
        # No slice yet, and the instruction is about a slice that has none of
        # its own imagery -- not about the window having just opened.
        self._sliceActive = False

    def beginSlice(self) -> None:
        """New slice's entry point: bind, offer to clear, then recompute.

        Whatever the getter raises propagates. A Camera module closed after
        startup is an error rather than a state to degrade into, and the
        operator sees acq4's error dialog -- deliberately unlike the storage
        slot beside it in the band, which is caught and rendered as guidance
        because an unset storage directory is a thing not yet done.
        """
        self._sliceActive = True
        self.rebind()
        if self._source.pinnedFrames and self._prompt(_CLEAR_PROMPT):
            # Emits sigPinnedFramesChanged, so the recompute below is
            # belt-and-braces rather than the only path.
            self._source.clearPinnedFrames()
        self._refresh()

    def rebind(self) -> None:
        """Re-resolve the imaging control and move the subscription to it.

        Re-resolved per slice because the operator may have changed the
        selected camera since the last one.
        """
        self._disconnect()
        self._source = self._getter()
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
        self._disconnect()
        self._sliceActive = False

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
