"""ReferenceImagery: the pinned-frames workflow that opens a slice -- archive the
previous slice's frames into its own data directory, clear them, then ask the
operator to pin a fresh set -- and that keeps the live slice's archive current."""
from __future__ import annotations

import functools
import hashlib

import numpy as np
import pyqtgraph as pg
from MetaArray import MetaArray

from acq4.experiment.slice import _FRAME_FILE, PINNED_FRAMES_DIR, writePinnedFrames
from acq4.logging_config import get_logger
from acq4.util import Qt

logger = get_logger(__name__)

PIN_FRAMES_INSTRUCTION = (
    "Pin reference frames of this slice in the Camera module."
)

# How long the pinned set must sit unchanged before it is archived into the
# live slice: a mosaic pinned frame by frame is one write, not one per frame.
PIN_ARCHIVE_DEBOUNCE_S = 1.0


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
    """Default prompt: a Yes/No dialog asking to clear the pinned frames.

    Its title and two-paragraph body are specific to a slice starting, not a
    copy of ImagingCtrl's own Clear button confirmation. `parent` places the
    dialog over the calling window instead of centring it on the primary
    screen with no owner. Defaults to No so that an Enter or Escape typed
    without reading the dialog leaves the pinned frames alone rather than
    clearing them.
    """
    answer = Qt.QMessageBox.question(
        parent, "Clear pinned frames?", text,
        Qt.QMessageBox.Yes | Qt.QMessageBox.No,
        Qt.QMessageBox.No,
    )
    return answer == Qt.QMessageBox.Yes


def _frameArray(item, camera=None) -> MetaArray:
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

    `camera` names the camera the frame was pinned from, or None when unknown,
    so a restore can hand it back to that camera's imaging control.
    """
    image = np.asarray(item.image)
    levels = item.getLevels()
    t = item.transform()
    display = {
        "transform": [t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy()],
        "levels": None if levels is None else np.asarray(levels).tolist(),
        "lut": item.lut,
        "zValue": item.zValue(),
        "camera": camera,
    }
    axes = [
        {"name": _AXIS_NAMES[i]} if i < len(_AXIS_NAMES) else {}
        for i in range(image.ndim)
    ]
    return MetaArray(image, info=axes + [display])


def archivePinnedFrames(frames, dirHandle, cameras=None) -> list[str]:
    """Write `frames` into `dirHandle` as one MetaArray each. Returns the names.

    The imagery that oriented a whole slice is destroyed by the clear at the
    start of the next one, and nothing else on the rig holds a copy: the Camera
    module's pinned frames are rendered items, not acquired data. Archiving
    them into the slice they belong to is what makes a finished slice
    reconstructable at all -- the regions Slice.saveState() records are
    coordinates on tissue, and these are the picture of that tissue those
    coordinates were drawn onto.

    Numbered in the order the source holds them, which is also their z order
    (ImagingCtrl.addPinnedFrame stacks each new frame one above the last), so
    the file names alone put a mosaic back in the order it was built.

    `cameras`, when given, names each frame's camera, in the same order.

    The archive is made to equal `frames` exactly (see writePinnedFrames): an
    empty set creates no directory, and frame files beyond the count are
    deleted.
    """
    frames = list(frames)
    if cameras is None:
        cameras = [None] * len(frames)
    return writePinnedFrames(
        dirHandle,
        [_frameArray(item, camera=camera) for item, camera in zip(frames, cameras)],
    )


def loadPinnedFrames(dirHandle) -> tuple[list, int]:
    """Rebuild the frames archived into `dirHandle`, as `(camera name, item)`
    pairs in file order -- which is the order they were pinned in -- and the
    count of frame files that could not be read.

    The inverse of `_frameArray`: each item gets back its pixels, transform,
    zValue, and the levels and lookup table when they were recorded. A
    directory with no archive has nothing to load.

    An unreadable frame file is logged, skipped, and renamed aside to
    `<name>.unreadable`: left under its own name, the next archive would
    renumber the readable frames over it, or delete it as surplus.
    """
    if not dirHandle.exists(PINNED_FRAMES_DIR):
        return [], 0
    archive = dirHandle.getDir(PINNED_FRAMES_DIR)
    loaded = []
    unreadable = 0
    for name in sorted(archive.ls()):
        if not _FRAME_FILE.fullmatch(name):
            continue
        try:
            loaded.append(_loadFrame(archive[name].name()))
        except Exception:
            logger.exception("Could not read the pinned frame %s; setting it aside", name)
            archive[name].rename(_asideName(archive, name))
            unreadable += 1
    return loaded, unreadable


def _loadFrame(path) -> tuple:
    data = MetaArray(file=path)
    display = data.infoCopy()[-1]
    item = pg.ImageItem(np.asarray(data), autoLevels=False)
    item.setTransform(Qt.QTransform(*display["transform"]))
    if display["levels"] is not None:
        item.setLevels(display["levels"])
    if display["lut"] is not None:
        item.setLookupTable(display["lut"])
    item.setZValue(display["zValue"])
    return display.get("camera"), item


def _asideName(archive, name) -> str:
    aside = f"{name}.unreadable"
    n = 1
    while archive.exists(aside):
        aside = f"{name}.unreadable.{n}"
        n += 1
    return aside


def frameIdentity(item) -> tuple:
    """What makes two pinned frames the same frame: the six transform numbers
    `_frameArray` records, and the pixels, by shape, dtype and a digest of
    their bytes."""
    image = np.ascontiguousarray(item.image)
    t = item.transform()
    return (
        (t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy()),
        image.shape,
        image.dtype.str,
        hashlib.sha1(image.tobytes()).hexdigest(),
    )


def _namedFrames(sources) -> list:
    """`(camera name, item)` for every frame pinned on `sources`, in order."""
    return [(camera, item) for camera, source in sources for item in source.pinnedFrames]


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
    # The live slice's pinned set, as the MetaArrays to write into its
    # PINNED_FRAMES_DIR. Built here on the GUI thread because _frameArray reads
    # Qt items; the listener writes them wherever it writes the slice.
    sigArchiveRequested = Qt.Signal(object)

    def __init__(self, imagingCtrlsGetter, prompt=None, parent=None):
        """`imagingCtrlsGetter()` returns `(camera name, imaging control)` for
        every camera; frames pinned from any of them count as reference
        imagery."""
        super().__init__()
        self._getter = imagingCtrlsGetter
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
        self._sources = []
        self._instruction = ""
        # No slice yet, and the instruction is about a slice that has none of
        # its own imagery -- not about the window having just opened.
        self._sliceActive = False
        self._liveDir = None
        self._archiveTimer = Qt.QTimer(self)
        self._archiveTimer.setSingleShot(True)
        self._archiveTimer.setInterval(int(PIN_ARCHIVE_DEBOUNCE_S * 1000))
        self._archiveTimer.timeout.connect(self._requestArchive)

    def beginSlice(self, archiveDir=None, liveDir=None) -> None:
        """New slice's entry point: bind, offer to clear, then recompute.

        `archiveDir` is the **outgoing** slice's data directory, and the frames
        about to be cleared are written into it before they go. It has to be
        passed in rather than looked up because by the time this runs the new
        slice has already replaced the old one -- the caller captures the
        directory before that swap. None is ordinary and means there is nowhere
        to archive to: the first slice of a session has no outgoing slice, and
        a slice that came into existence to hold a region never had a directory
        of its own.

        `liveDir` is the **new** slice's data directory, or None. While one is
        bound, every change to the pinned set is archived into it after
        PIN_ARCHIVE_DEBOUNCE_S (see sigArchiveRequested), and frames the
        operator keeps across the slice change are archived into it too.

        A change still waiting out its debounce belongs to the outgoing slice,
        so it is written into `archiveDir` now even when the operator keeps the
        frames: otherwise that slice's archive would be left a second behind
        what was pinned on it.

        Whatever the getter raises propagates rather than being caught here.
        A Camera module closed after startup is an error rather than a state
        to degrade into. `_sliceActive` is only set once `rebind()` has
        returned successfully, so a raised getter leaves this component as if
        no slice had begun rather than stuck active with no source.

        A getter answering an empty list (rather than raising) is not that
        case, though, and is not a slice to skip either: a Camera module with
        no imaging controls is ordinary, so the offer to clear is simply
        skipped rather than raised through, exactly as _refresh() already
        treats a None source as "nothing to show" rather than an error.
        """
        unarchived = self._archiveTimer.isActive()
        self._archiveTimer.stop()
        self.rebind()
        self._sliceActive = True
        self._liveDir = liveDir
        self._refresh()
        # Bound to a local before the prompt: the prompt is modal and re-enters
        # the Qt event loop, and release() (teardown, dispatched from inside
        # that loop) empties self._sources. Reading self._sources again
        # after the prompt would see the emptied list and clear nothing.
        sources = list(self._sources)
        named = _namedFrames(sources)
        if named and self._prompt(_CLEAR_PROMPT):
            # Only on the branch that actually destroys them, or (below) when
            # a change is not yet written. A Cancel otherwise loses nothing,
            # and archiving anyway would rewrite the same frames into the same
            # directory on every slice the operator declines to clear.
            self._archive(named, archiveDir)
            # Each emits sigPinnedFramesChanged, so the recompute below is
            # belt-and-braces rather than the only path.
            for _, source in sources:
                source.clearPinnedFrames()
        else:
            if unarchived:
                self._archive(named, archiveDir)
            if named:
                self._archiveTimer.start()
        self._refresh()

    @staticmethod
    def _archive(named, archiveDir) -> None:
        """Archive the `(camera name, item)` pairs in `named`, logging rather
        than raising if that fails.

        The operator has physically swapped the tissue by the time this runs,
        and the clear it usually precedes is what lets them get on with the new
        slice.
        A save that failed -- no storage directory chosen, a full disk, a
        network mount that went away -- must not leave them holding the
        previous slice's frames with no way forward, so the loss is recorded in
        the log and the slice opens regardless.
        """
        if archiveDir is None:
            return
        try:
            archivePinnedFrames(
                [item for _, item in named], archiveDir, [camera for camera, _ in named]
            )
        except Exception:
            logger.exception(
                "Could not archive the outgoing slice's pinned frames"
            )

    def rebind(self) -> None:
        """Re-resolve the imaging controls and move the subscriptions to them.

        Re-resolved per slice because cameras may have been added or removed
        since the last one.

        Tolerant of the getter answering an empty list: a Camera module with
        no imaging controls is ordinary, and there is nothing to subscribe
        to -- exactly the state
        _refresh() and _disconnect() already treat an empty source list as,
        not an error.
        """
        self._disconnect()
        self._sources = list(self._getter())
        for _, source in self._sources:
            source.sigPinnedFramesChanged.connect(self._onPinnedFramesChanged)
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
        self._liveDir = None
        self._archiveTimer.stop()
        self._disconnect()
        self._refresh()

    def flushArchive(self) -> None:
        """Request now the archive a pending change is still waiting to make,
        so a window closing inside the debounce does not lose it."""
        if self._archiveTimer.isActive():
            self._archiveTimer.stop()
            self._requestArchive()

    def _onPinnedFramesChanged(self) -> None:
        self._refresh()
        self._archiveTimer.start()

    def _requestArchive(self) -> None:
        if self._liveDir is None:
            return
        arrays = [
            _frameArray(item, camera=camera) for camera, item in _namedFrames(self._sources)
        ]
        self.sigArchiveRequested.emit(arrays)

    def _disconnect(self) -> None:
        sources, self._sources = self._sources, []
        for _, source in sources:
            try:
                Qt.disconnect(source.sigPinnedFramesChanged, self._onPinnedFramesChanged)
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
        if self._sliceActive and self._sources:
            if not any(source.pinnedFrames for _, source in self._sources):
                text = PIN_FRAMES_INSTRUCTION
        if text != self._instruction:
            self._instruction = text
            self.sigInstructionChanged.emit(text)
