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
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)

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
