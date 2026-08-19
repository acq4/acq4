"""Tests for ReferenceImagery: the pinned-frames workflow that starts a slice."""
from __future__ import annotations

from unittest import mock

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


def test_ask_to_clear_offers_yes_no_and_defaults_to_no(qapp):
    """The dialog is a yes/no question, and Enter/Escape must not clear."""
    from acq4.modules.Autopatch.reference_imagery import _askToClear

    with mock.patch.object(Qt.QMessageBox, "question", return_value=Qt.QMessageBox.No) as question:
        _askToClear("some text")

    args, kwargs = question.call_args
    buttons = kwargs.get("buttons", args[3] if len(args) > 3 else None)
    assert buttons == Qt.QMessageBox.Yes | Qt.QMessageBox.No
    defaultButton = kwargs.get("defaultButton", args[4] if len(args) > 4 else None)
    assert defaultButton == Qt.QMessageBox.No


def test_ask_to_clear_returns_true_only_for_yes(qapp):
    from acq4.modules.Autopatch.reference_imagery import _askToClear

    with mock.patch.object(Qt.QMessageBox, "question", return_value=Qt.QMessageBox.No):
        assert _askToClear("some text") is False
    with mock.patch.object(Qt.QMessageBox, "question", return_value=Qt.QMessageBox.Yes):
        assert _askToClear("some text") is True


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
