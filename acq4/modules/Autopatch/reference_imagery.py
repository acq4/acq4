"""ReferenceImagery: the pinned-frames workflow that opens a slice -- archive the
previous slice's frames into its own data directory, clear them, then ask the
operator to pin a fresh set."""
from __future__ import annotations

import functools

import numpy as np
from MetaArray import MetaArray

from acq4.logging_config import get_logger
from acq4.util import Qt

logger = get_logger(__name__)

PIN_FRAMES_INSTRUCTION = (
    "Pin reference frames of this slice in the Camera module."
)

# The subdirectory an outgoing slice's frames are archived into, inside that
# slice's own data directory. A directory of MetaArrays rather than one
# container file: the Data Manager already reads and displays a `.ma`, so this
# costs no new file type and no new viewer, and one frame per file is also what
# lets a partly-written archive still be worth something.
PINNED_FRAMES_DIR = "pinned_frames"

# Axis names for an archived frame. X before Y because pyqtgraph indexes an
# ImageItem's array column-major unless told otherwise, and acq4 never tells it
# otherwise -- the same order Frame._metaArrayInfo names for a camera frame. A
# pinned frame is normally 2-D mono; a colour camera makes it 3-D.
_AXIS_NAMES = ("X", "Y", "Color")

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


def _frameArray(item) -> MetaArray:
    """One pinned frame as a MetaArray: its pixels, and the display state that
    makes them a reference frame rather than a picture.

    A pinned frame is a `pg.ImageItem` carrying four things beyond its array --
    the global transform that says where on the tissue it sits, the levels and
    the lookup table it was rendered with, and a deliberately very low z-value
    that keeps it under everything else in the view. Those four are exactly
    what PinnedFrameMirror copies across to rebuild an item in another view
    (see its `refresh`), so they are exactly what has to survive to disk for a
    frame to be put back on screen. Levels and a lookup table are both optional
    on the way in, and an absent one is recorded as absent rather than
    invented: an ImageItem given neither scales itself to its own contents, so
    inventing a pair here would be inventing a rendering nobody chose.

    The state rides in the MetaArray's own info rather than in the `info=`
    the Data Manager writes into its `.index`, and the lookup table is why:
    the index is written with `repr()` and read back with `eval()`, which a
    several-hundred-row array does not survive, while a MetaArray file stores
    it natively and keeps it with the pixels it belongs to.

    The transform is stored as the six numbers `QTransform(m11, m12, m21, m22,
    dx, dy)` is built from, in that order, so putting the frame back is that
    constructor and nothing else.
    """
    image = np.asarray(item.image)
    levels = item.getLevels()
    t = item.transform()
    display = {
        "transform": [t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy()],
        "levels": None if levels is None else np.asarray(levels).tolist(),
        "lut": item.lut,
        "zValue": item.zValue(),
    }
    axes = [
        {"name": _AXIS_NAMES[i]} if i < len(_AXIS_NAMES) else {}
        for i in range(image.ndim)
    ]
    return MetaArray(image, info=axes + [display])


def archivePinnedFrames(frames, dirHandle) -> list[str]:
    """Write `frames` into `dirHandle` as one MetaArray each. Returns the names.

    The imagery that oriented a whole slice is destroyed by the clear at the
    start of the next one, and nothing else on the rig holds a copy: the Camera
    module's pinned frames are rendered items, not acquired data, and no frame
    of them is written anywhere by the act of pinning. Archiving them into the
    slice they belong to is what makes a finished slice reconstructable at all
    -- the regions Slice.saveState() records are coordinates on tissue, and
    these are the picture of that tissue those coordinates were drawn onto.

    Numbered in the order the source holds them, which is also their z order
    (ImagingCtrl.addPinnedFrame stacks each new frame one above the last), so
    the file names alone put a mosaic back in the order it was built.

    An empty set writes nothing and creates no directory: a slice whose
    operator pinned nothing should not leave an empty folder behind claiming
    otherwise.
    """
    frames = list(frames)
    if not frames:
        return []
    archive = dirHandle.getDir(PINNED_FRAMES_DIR, create=True)
    names = []
    for i, item in enumerate(frames):
        name = f"frame_{i:03d}.ma"
        archive.writeFile(_frameArray(item), name, fileType="MetaArray")
        names.append(name)
    return names


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

    def beginSlice(self, archiveDir=None) -> None:
        """New slice's entry point: bind, offer to clear, then recompute.

        `archiveDir` is the **outgoing** slice's data directory, and the frames
        about to be cleared are written into it before they go. It has to be
        passed in rather than looked up because by the time this runs the new
        slice has already replaced the old one -- the caller captures the
        directory before that swap. None is ordinary and means there is nowhere
        to archive to: the first slice of a session has no outgoing slice, and
        a slice that came into existence to hold a region never had a directory
        of its own.

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
            # Only on the branch that actually destroys them. A Cancel loses
            # nothing, and archiving anyway would rewrite the same frames into
            # the same directory on every slice the operator declines to clear.
            self._archive(source.pinnedFrames, archiveDir)
            # Emits sigPinnedFramesChanged, so the recompute below is
            # belt-and-braces rather than the only path.
            source.clearPinnedFrames()
        self._refresh()

    @staticmethod
    def _archive(frames, archiveDir) -> None:
        """Archive `frames`, logging rather than raising if that fails.

        The operator has physically swapped the tissue by the time this runs,
        and the clear it precedes is what lets them get on with the new slice.
        A save that failed -- no storage directory chosen, a full disk, a
        network mount that went away -- must not leave them holding the
        previous slice's frames with no way forward, so the loss is recorded in
        the log and the slice opens regardless.
        """
        if archiveDir is None:
            return
        try:
            archivePinnedFrames(frames, archiveDir)
        except Exception:
            logger.exception(
                "Could not archive the outgoing slice's pinned frames; "
                "clearing them anyway"
            )

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
