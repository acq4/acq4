"""FileType and data-tab view for .acqtrack cell tracking history files.
Files are written through CellTracker.save_history and replayed in acq4-automation's
LiveTrackerVisualizer.
"""
import os

from acq4.filetypes.FileType import FileType
from acq4.util import Qt

# Visualizer windows are top-level and parentless, so something must hold a Python
# reference for them to stay on screen. It cannot be the AcqTrackWidget that opened
# them: FileDataView.clear() closes, unparents and drops its widgets as soon as another
# file is selected, which would take any window they owned down with them.
_openVisualizers = []


def _loadHistory(path):
    """Load a .acqtrack file, returning a tracker that can be replayed.

    Imported lazily: acq4_automation is an optional dependency, and
    filetypes.listFileTypes() imports every module in this package at startup.
    """
    from acq4_automation.feature_tracking.tracking_history import load_history

    return load_history(path)


def _openVisualizer(tracker):
    """Show a tracking history in its own visualizer window and keep it alive."""
    from acq4_automation.feature_tracking.visualization import LiveTrackerVisualizer

    viz = LiveTrackerVisualizer(tracker)
    _openVisualizers.append(viz)
    viz.show()
    return viz


class AcqTrackFile(FileType):
    """Cell tracking history, as written by CellTracker.save_history()."""

    extensions = ['.acqtrack']
    dataTypes = []  # trackers are written by explicit fileType=, never by data sniffing

    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        fileName = cls.addExtension(fileName)
        data.save_history(os.path.join(dirHandle.name(), fileName))
        return fileName

    @classmethod
    def read(cls, fileHandle):
        return _loadHistory(fileHandle.name())


class AcqTrackWidget(Qt.QWidget):
    """Data-tab view for a .acqtrack file: a button that opens it in the visualizer.

    Reading is deferred to the click. A tracking history holds every image and object
    stack the tracker saw, which is far too much to load just because a file was
    selected in the tree.
    """

    def __init__(self, fileHandle, parent=None):
        Qt.QWidget.__init__(self, parent)
        self._fileHandle = fileHandle
        layout = Qt.QVBoxLayout(self)
        self.visualizeBtn = Qt.QPushButton("Visualize")
        self.visualizeBtn.clicked.connect(self.visualize)
        layout.addWidget(self.visualizeBtn)
        layout.addStretch()

    def visualize(self):
        _openVisualizer(self._fileHandle.read())
