"""Tests for AcqTrackFile: the .acqtrack FileType and its Data-tab Visualize widget.

Cover extension matching, write/read delegation to the tracking-history seams, and
that the widget defers every read until Visualize is clicked.
"""
import os

import pytest

import acq4.filetypes.AcqTrackFile as acqtrack
from acq4.filetypes import filetypes
from acq4.filetypes.AcqTrackFile import AcqTrackFile, AcqTrackWidget
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeFileHandle:
    """Stands in for a FileHandle: exposes the name/shortName/read trio the filetypes
    machinery and the widget use, and counts reads."""

    def __init__(self, path, data=None):
        self._path = str(path)
        self._data = data
        self.readCount = 0

    def name(self):
        return self._path

    def shortName(self):
        return os.path.basename(self._path)

    def read(self):
        self.readCount += 1
        return self._data


class _FakeDirHandle:
    def __init__(self, path):
        self._path = str(path)

    def name(self):
        return self._path


class _FakeTracker:
    """Stands in for a CellTracker: records the paths save_history was asked for."""

    def __init__(self):
        self.savedTo = []

    def save_history(self, path):
        self.savedTo.append(path)


class TestAcceptsFile:
    def test_accepts_acqtrack_extension(self, tmp_path):
        fh = _FakeFileHandle(tmp_path / "tracking_history.acqtrack")
        assert AcqTrackFile.acceptsFile(fh) == AcqTrackFile.priority

    def test_accepts_uppercase_extension(self, tmp_path):
        fh = _FakeFileHandle(tmp_path / "TRACKING_HISTORY.ACQTRACK")
        assert AcqTrackFile.acceptsFile(fh) is not False

    def test_rejects_other_extensions(self, tmp_path):
        fh = _FakeFileHandle(tmp_path / "image.tif")
        assert AcqTrackFile.acceptsFile(fh) is False


class TestAddExtension:
    def test_adds_missing_extension(self):
        assert AcqTrackFile.addExtension("tracking_history") == "tracking_history.acqtrack"

    def test_leaves_existing_extension_alone(self):
        assert AcqTrackFile.addExtension("tracking_history.acqtrack") == "tracking_history.acqtrack"


class TestWrite:
    def test_saves_via_tracker_and_returns_extended_name(self, tmp_path):
        tracker = _FakeTracker()
        name = AcqTrackFile.write(tracker, _FakeDirHandle(tmp_path), "tracking_history")
        assert name == "tracking_history.acqtrack"
        assert tracker.savedTo == [os.path.join(str(tmp_path), "tracking_history.acqtrack")]

    def test_does_not_double_up_extension(self, tmp_path):
        tracker = _FakeTracker()
        name = AcqTrackFile.write(tracker, _FakeDirHandle(tmp_path), "tracking_history.acqtrack")
        assert name == "tracking_history.acqtrack"


class _WritingTracker(_FakeTracker):
    """A tracker whose save_history actually puts a file on disk, so a real DirHandle
    has something to index."""

    def save_history(self, path):
        super().save_history(path)
        with open(path, "wb"):
            pass


class TestWriteThroughDirHandle:
    def test_indexes_type_and_announces_new_child(self, qapp, tmp_path):
        """The point of routing the save through DirHandle.writeFile: the file lands in
        the index carrying its type, and the directory announces a 'children' change so
        the Data Manager tree shows it without a manual refresh."""
        from acq4.util.DataManager import getDirHandle

        dh = getDirHandle(str(tmp_path), create=True)
        changes = []
        dh.sigChanged.connect(lambda handle, change, args: changes.append((change, args)))

        fh = dh.writeFile(_WritingTracker(), "tracking_history", fileType="AcqTrackFile")

        assert os.path.exists(os.path.join(str(tmp_path), "tracking_history.acqtrack"))
        assert fh.fileType() == "AcqTrackFile"
        assert ("children", ("tracking_history.acqtrack",)) in changes


class TestRead:
    def test_delegates_to_load_history(self, tmp_path, monkeypatch):
        requested = []
        history = object()

        def fakeLoad(path):
            requested.append(path)
            return history

        monkeypatch.setattr(acqtrack, "_loadHistory", fakeLoad)
        fh = _FakeFileHandle(tmp_path / "tracking_history.acqtrack")
        assert AcqTrackFile.read(fh) is history
        assert requested == [str(tmp_path / "tracking_history.acqtrack")]


class TestFileTypeDiscovery:
    def test_suggest_read_type_finds_acqtrack_file(self, tmp_path):
        """listFileTypes() imports every module in acq4/filetypes; make sure this one
        is discovered there, not just when imported directly by these tests."""
        path = tmp_path / "tracking_history.acqtrack"
        path.write_bytes(b"")
        assert filetypes.suggestReadType(_FakeFileHandle(path)) == "AcqTrackFile"


class TestRealRoundTrip:
    """End-to-end against the real format: a real CellTracker saved through a real
    DirHandle and read back through the FileType, with nothing faked. Skipped where
    acq4_automation is not installed, since the file format lives there."""

    @staticmethod
    def _stackFrames(nFrames=30, nRows=80, nCols=80, xyPx=1e-6, zStep=1e-6):
        import coorx
        import numpy as np
        from acq4.util.imaging import Frame

        frames = []
        for i in range(nFrames):
            m = np.eye(4)
            m[0, 0] = xyPx
            m[1, 1] = xyPx
            m[2, 2] = zStep
            m[2, 3] = i * zStep
            xform = coorx.AffineTransform.from_matrix(m, from_cs=f"frame_{i}.xyz", to_cs="global")
            data = np.zeros((nRows, nCols), dtype=np.float32)
            frames.append(Frame(data, {"transform": xform, "pixelSize": (xyPx, xyPx)}))
        return frames

    def test_tracker_survives_write_and_read(self, qapp, tmp_path):
        pytest.importorskip("acq4_automation")
        import coorx
        from acq4.util.DataManager import getDirHandle
        from acq4_automation.feature_tracking.cell import Cell

        cell = Cell(coorx.Point((40e-6, 40e-6, 15e-6), "global"))
        cell.initializeTrackerFromStack(None, self._stackFrames())
        original = cell._tracker.motion_estimator.original_object_stack.data

        dh = getDirHandle(str(tmp_path), create=True)
        fh = dh.writeFile(cell._tracker, "tracking_history", fileType="AcqTrackFile")

        assert fh.fileType() == "AcqTrackFile"
        replay = fh.read()
        assert replay.motion_estimator.current_object_stack.data.shape == original.shape


class TestAcqTrackWidget:
    def test_has_visualize_button(self, qapp, tmp_path):
        w = AcqTrackWidget(_FakeFileHandle(tmp_path / "tracking_history.acqtrack"))
        assert [b.text() for b in w.findChildren(Qt.QPushButton)] == ["Visualize"]

    def test_reads_nothing_until_clicked(self, qapp, tmp_path):
        fh = _FakeFileHandle(tmp_path / "tracking_history.acqtrack")
        AcqTrackWidget(fh)
        assert fh.readCount == 0

    def test_click_opens_visualizer_with_loaded_history(self, qapp, tmp_path, monkeypatch):
        history = object()
        fh = _FakeFileHandle(tmp_path / "tracking_history.acqtrack", data=history)
        opened = []
        monkeypatch.setattr(acqtrack, "_openVisualizer", opened.append)

        w = AcqTrackWidget(fh)
        w.findChildren(Qt.QPushButton)[0].click()

        assert opened == [history]
        assert fh.readCount == 1
