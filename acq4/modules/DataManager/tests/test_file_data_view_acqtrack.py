"""Tests that the Data tab renders an .acqtrack file as a Visualize panel.

Selecting the file must not deserialize it: an .acqtrack holds every image and object
stack the tracker saw.
"""
import pytest

from acq4.filetypes.AcqTrackFile import AcqTrackWidget
from acq4.modules.DataManager.FileDataView import FileDataView
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeFileHandle:
    def __init__(self, path, fileType):
        self._path = str(path)
        self._fileType = fileType
        self.readCount = 0

    def isDir(self):
        return False

    def fileType(self):
        return self._fileType

    def name(self, relativeTo=None):
        return self._path

    def read(self):
        self.readCount += 1
        return None


def test_acqtrack_file_gets_visualize_panel(qapp, tmp_path):
    view = FileDataView(None)
    fh = _FakeFileHandle(tmp_path / "tracking_history.acqtrack", "AcqTrackFile")

    view.setCurrentFile(fh)

    assert len(view.findChildren(AcqTrackWidget)) == 1
    assert fh.readCount == 0


def test_switching_away_from_acqtrack_clears_the_panel(qapp, tmp_path):
    view = FileDataView(None)
    view.setCurrentFile(_FakeFileHandle(tmp_path / "tracking_history.acqtrack", "AcqTrackFile"))

    view.setCurrentFile(None)

    assert view.findChildren(AcqTrackWidget) == []
