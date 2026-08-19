"""Tests for ReferenceImagery: the pinned-frames workflow that starts a slice."""
from __future__ import annotations

import pytest

from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException


class _FakeImagingCtrl(Qt.QObject):
    """Stands in for the Camera module's ImagingCtrl.

    clearPinnedFrames() genuinely empties the list and emits, because the real
    one does (via removePinnedFrame): a fake that skipped either would hide a
    missing recompute in the code under test.

    Two things it does not reproduce from the real removePinnedFrame-based
    clearPinnedFrames (acq4/util/imaging/imaging_ctrl.py): it emits
    sigPinnedFramesChanged once for the whole clear rather than once per
    removed frame, and it rebinds self.pinnedFrames to a new empty list
    rather than mutating the existing list in place with .remove(). Nothing
    in ReferenceImagery depends on emission count or on the list identity
    surviving a clear, so neither divergence is exercised by these tests.
    """

    sigPinnedFramesChanged = Qt.Signal()

    def __init__(self, frames=()):
        super().__init__()
        self.pinnedFrames = list(frames)

    def clearPinnedFrames(self):
        self.pinnedFrames = []
        self.sigPinnedFramesChanged.emit()

    def pin(self, frame="frame"):
        self.pinnedFrames.append(frame)
        self.sigPinnedFramesChanged.emit()

    def unpinAll(self):
        self.pinnedFrames = []
        self.sigPinnedFramesChanged.emit()


def _imagery(source, answer=True):
    from acq4.modules.Autopatch.reference_imagery import ReferenceImagery

    asked = []

    def prompt(text):
        asked.append(text)
        return answer

    return ReferenceImagery(lambda: source, prompt=prompt), asked


def test_nothing_pinned_means_no_prompt(qapp):
    source = _FakeImagingCtrl()
    imagery, asked = _imagery(source)

    imagery.beginSlice()

    assert asked == []


def test_a_yes_clears_the_pinned_frames(qapp):
    source = _FakeImagingCtrl(["a", "b"])
    imagery, asked = _imagery(source, answer=True)

    imagery.beginSlice()

    assert len(asked) == 1
    assert source.pinnedFrames == []


def test_a_no_leaves_the_pinned_frames(qapp):
    source = _FakeImagingCtrl(["a", "b"])
    imagery, asked = _imagery(source, answer=False)

    imagery.beginSlice()

    assert len(asked) == 1
    assert source.pinnedFrames == ["a", "b"]


def test_an_empty_slice_asks_for_frames(qapp):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)

    imagery.beginSlice()

    assert imagery.instruction() == PIN_FRAMES_INSTRUCTION


def test_there_is_no_instruction_before_a_slice(qapp):
    # Bound to a source with nothing pinned -- if a slice were considered
    # active here, this would show PIN_FRAMES_INSTRUCTION. rebind() alone
    # does not begin a slice, so no instruction should appear.
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)

    imagery.rebind()

    assert imagery.instruction() == ""


def test_release_ends_the_slice(qapp):
    # A later bare rebind() (a camera-change handler, say) must not publish
    # the pin-frames instruction as though a new slice had begun.
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)
    imagery.beginSlice()
    assert imagery.instruction() == PIN_FRAMES_INSTRUCTION

    imagery.release()
    imagery.rebind()

    assert imagery.instruction() == ""


def test_rebind_recomputes_for_the_new_source(qapp):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION, ReferenceImagery

    sources = {"current": _FakeImagingCtrl()}
    imagery = ReferenceImagery(lambda: sources["current"], prompt=lambda text: True)
    imagery.beginSlice()
    assert imagery.instruction() == PIN_FRAMES_INSTRUCTION

    # The operator switches the selected camera mid-slice; the new one
    # already has frames pinned.
    sources["current"] = _FakeImagingCtrl(["a"])
    imagery.rebind()

    assert imagery.instruction() == ""


def test_pinning_a_frame_retracts_the_instruction(qapp):
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)
    imagery.beginSlice()

    source.pin()

    assert imagery.instruction() == ""


def test_unpinning_the_last_frame_brings_it_back(qapp):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    source = _FakeImagingCtrl(["a"])
    imagery, _ = _imagery(source, answer=False)
    imagery.beginSlice()
    assert imagery.instruction() == ""

    source.unpinAll()

    assert imagery.instruction() == PIN_FRAMES_INSTRUCTION


def test_the_signal_carries_only_real_changes(qapp):
    source = _FakeImagingCtrl(["a"])
    imagery, _ = _imagery(source, answer=False)
    imagery.beginSlice()
    seen = []
    imagery.sigInstructionChanged.connect(seen.append)

    source.pin("b")

    assert seen == []


def test_the_signal_reports_the_new_text(qapp):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    source = _FakeImagingCtrl(["a"])
    imagery, _ = _imagery(source, answer=False)
    imagery.beginSlice()
    seen = []
    imagery.sigInstructionChanged.connect(seen.append)

    source.unpinAll()

    assert seen == [PIN_FRAMES_INSTRUCTION]


def test_a_closed_camera_module_propagates(qapp):
    from acq4.modules.Autopatch.reference_imagery import ReferenceImagery

    def getter():
        raise HelpfulException("The Camera module is not open.")

    imagery = ReferenceImagery(getter, prompt=lambda text: True)

    with pytest.raises(HelpfulException, match="Camera"):
        imagery.beginSlice()


def test_release_disconnects_from_the_source(qapp):
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)
    imagery.beginSlice()
    assert source.receivers(source.sigPinnedFramesChanged) == 1

    imagery.release()

    assert source.receivers(source.sigPinnedFramesChanged) == 0


def test_rebinding_does_not_stack_connections(qapp):
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)

    imagery.rebind()
    imagery.rebind()

    assert source.receivers(source.sigPinnedFramesChanged) == 1


# ---- archiving the outgoing slice's frames ----


@pytest.fixture
def slice_dir(tmp_path):
    """A real managed directory, because what is being tested is the record on
    disk: the point of archiving is that a frame can be read back and put on
    screen again, and only a real file proves that."""
    import acq4.util.DataManager as dm

    return dm.getDirHandle(str(tmp_path), create=True)


def _pinnedFrame(image=None, levels=(10.0, 900.0), lut=True, z=-10000.0):
    """An ImageItem in the state ImagingCtrl.pinCurrentFrame leaves one in:
    an image, a global transform, explicit levels, a lookup table, and a
    deliberately very low z-value that puts it under everything else."""
    import numpy as np
    import pyqtgraph as pg
    from acq4.util import Qt

    if image is None:
        image = np.arange(48, dtype=np.uint16).reshape(6, 8) * 37
    # autoLevels=False so that "no levels" is genuinely reachable: an ImageItem
    # handed an image and left to itself picks levels from that image's own
    # contents, which is the very behaviour a pinned frame spells levels out to
    # avoid. pinCurrentFrame passes them explicitly for the same reason.
    item = pg.ImageItem(image, autoLevels=False)
    # A transform with rotation, scale and translation all present: an
    # implementation that dropped a term, or stored the six in another order,
    # would put the frame back somewhere else on the tissue.
    item.setTransform(Qt.QTransform(2.5e-7, 1.5e-8, -3.0e-8, 2.5e-7, 1.1e-3, -2.2e-3))
    if levels is not None:
        item.setLevels(levels)
    if lut:
        item.setLookupTable(
            (np.arange(256 * 3).reshape(256, 3) % 256).astype(np.ubyte)
        )
    item.setZValue(z)
    return item


def test_archiving_writes_one_file_per_pinned_frame(qapp, slice_dir):
    from acq4.modules.Autopatch.reference_imagery import (
        PINNED_FRAMES_DIR,
        archivePinnedFrames,
    )

    written = archivePinnedFrames([_pinnedFrame(), _pinnedFrame()], slice_dir)

    assert len(written) == 2
    archive = slice_dir.getDir(PINNED_FRAMES_DIR)
    assert sorted(archive.ls()) == ["frame_000.ma", "frame_001.ma"]


def test_an_archived_frame_keeps_its_pixels(qapp, slice_dir):
    import numpy as np
    from MetaArray import MetaArray

    from acq4.modules.Autopatch.reference_imagery import (
        PINNED_FRAMES_DIR,
        archivePinnedFrames,
    )

    image = (np.arange(48, dtype=np.uint16).reshape(6, 8) * 37)
    archivePinnedFrames([_pinnedFrame(image=image)], slice_dir)

    back = MetaArray(file=slice_dir.getDir(PINNED_FRAMES_DIR)["frame_000.ma"].name())
    assert np.array_equal(np.asarray(back), image)
    assert back.dtype == image.dtype


def test_an_archived_frame_keeps_enough_to_be_redisplayed(qapp, slice_dir):
    # Pixels alone are not a reference frame. Where it sits on the tissue is
    # the whole reason it was pinned, and an ImageItem handed neither levels
    # nor a lookup table scales itself to its own contents -- so a 16-bit frame
    # with a narrow range comes back near-flat and adjacent frames in one
    # mosaic no longer match. The same four things PinnedFrameMirror copies
    # across to rebuild an item are the four that have to survive to disk.
    import numpy as np
    from MetaArray import MetaArray

    from acq4.modules.Autopatch.reference_imagery import (
        PINNED_FRAMES_DIR,
        archivePinnedFrames,
    )

    frame = _pinnedFrame()
    archivePinnedFrames([frame], slice_dir)

    back = MetaArray(file=slice_dir.getDir(PINNED_FRAMES_DIR)["frame_000.ma"].name())
    saved = back.infoCopy()[-1]
    t = frame.transform()
    assert list(saved["transform"]) == [
        t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy()
    ]
    assert list(saved["levels"]) == [10.0, 900.0]
    assert np.array_equal(saved["lut"], frame.lut)
    assert saved["zValue"] == -10000.0


def test_a_frame_with_no_levels_or_lookup_table_archives_anyway(qapp, slice_dir):
    # Both are optional on the way in (see PinnedFrameMirror.refresh), so an
    # absent one is recorded as absent rather than invented or refused.
    from MetaArray import MetaArray

    from acq4.modules.Autopatch.reference_imagery import (
        PINNED_FRAMES_DIR,
        archivePinnedFrames,
    )

    archivePinnedFrames([_pinnedFrame(levels=None, lut=False)], slice_dir)

    back = MetaArray(file=slice_dir.getDir(PINNED_FRAMES_DIR)["frame_000.ma"].name())
    saved = back.infoCopy()[-1]
    assert saved["levels"] is None
    assert saved["lut"] is None


def test_archiving_no_frames_creates_no_archive(qapp, slice_dir):
    from acq4.modules.Autopatch.reference_imagery import (
        PINNED_FRAMES_DIR,
        archivePinnedFrames,
    )

    assert archivePinnedFrames([], slice_dir) == []
    assert not slice_dir.exists(PINNED_FRAMES_DIR)


def test_beginning_a_slice_archives_the_outgoing_frames_before_clearing(qapp, slice_dir):
    # The ordering is the whole point: clearPinnedFrames() destroys the
    # imagery that oriented the entire previous slice, and nothing else on the
    # rig holds a copy of it.
    from acq4.modules.Autopatch.reference_imagery import PINNED_FRAMES_DIR

    source = _FakeImagingCtrl([_pinnedFrame(), _pinnedFrame()])
    imagery, asked = _imagery(source, answer=True)

    imagery.beginSlice(archiveDir=slice_dir)

    assert source.pinnedFrames == []
    assert sorted(slice_dir.getDir(PINNED_FRAMES_DIR).ls()) == [
        "frame_000.ma",
        "frame_001.ma",
    ]


def test_frames_the_operator_keeps_are_not_archived(qapp, slice_dir):
    # Nothing is being lost when the answer is Cancel, and archiving anyway
    # would write the same frames again into the same directory on every slice
    # the operator declines to clear.
    from acq4.modules.Autopatch.reference_imagery import PINNED_FRAMES_DIR

    source = _FakeImagingCtrl([_pinnedFrame()])
    imagery, _ = _imagery(source, answer=False)

    imagery.beginSlice(archiveDir=slice_dir)

    assert len(source.pinnedFrames) == 1
    assert not slice_dir.exists(PINNED_FRAMES_DIR)


def test_a_slice_with_nowhere_to_archive_still_clears(qapp):
    # The outgoing slice may have had no directory of its own -- the "Add
    # region here" slice never got one -- and the very first slice of a session
    # has no outgoing slice at all.
    source = _FakeImagingCtrl([_pinnedFrame()])
    imagery, _ = _imagery(source, answer=True)

    imagery.beginSlice()

    assert source.pinnedFrames == []


class _RefusesToArchive:
    """A DirHandle that cannot be written to -- a full disk, or a storage
    directory that went away with a network mount."""

    def getDir(self, *args, **kwargs):
        raise OSError("no space left on device")

    def exists(self, *args, **kwargs):
        return False


def test_a_failed_archive_still_opens_the_new_slice(qapp):
    # The operator has physically swapped the tissue; a save that failed must
    # not leave them with the previous slice's frames still on screen and no
    # way forward.
    source = _FakeImagingCtrl([_pinnedFrame()])
    imagery, _ = _imagery(source, answer=True)

    imagery.beginSlice(archiveDir=_RefusesToArchive())

    assert source.pinnedFrames == []
