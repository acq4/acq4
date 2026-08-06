"""FileType and data-tab view for .acqtrack cell tracking history files.
Files are written through CellTracker.save_history and replayed in acq4-automation's
LiveTrackerVisualizer.
"""
import os

from acq4.filetypes.FileType import FileType
from acq4.logging_config import get_logger
from acq4.util import Qt
from acq4.util.task import QtFriendlyTask

logger = get_logger(__name__)

LOADING = 'loading'
OPEN = 'open'
FAILED = 'failed'


def _loadHistory(path):
    """Load a .acqtrack file, returning a tracker that can be replayed.

    Imported lazily: acq4_automation is an optional dependency, and
    filetypes.listFileTypes() imports every module in this package at startup.
    """
    from acq4_automation.feature_tracking.tracking_history import load_history

    return load_history(path)


def _openVisualizer(tracker):
    """Show a tracking history in its own visualizer window."""
    from acq4_automation.feature_tracking.visualization import LiveTrackerVisualizer

    viz = LiveTrackerVisualizer(tracker)
    viz.show()
    return viz


def _visualizerWindow(viz):
    """The top-level window whose closing ends a visualizer's session."""
    return viz.window


class _VisualizerRegistry(Qt.QObject):
    """Tracks, per file path, which tracking histories are being read and which already
    have a visualizer window on screen.

    This state cannot live on the AcqTrackWidget that starts it. Visualizer windows are
    top-level and parentless, so something must hold a Python reference for them to stay
    on screen, and FileDataView.clear() closes, unparents and drops its widgets as soon
    as another file is selected -- which would take any window they owned down with
    them. Keeping the registry at module scope also means a rebuilt widget still knows
    that its file already has a window open.
    """

    sigChanged = Qt.Signal(object)  # path

    def __init__(self):
        Qt.QObject.__init__(self)
        self._loading = {}  # path -> QtFriendlyTask reading the file
        self._open = {}  # path -> visualizer
        self._failed = set()  # paths whose last read raised

    def stateOf(self, path):
        """LOADING, OPEN, FAILED, or None if this path has no visualizer activity."""
        if path in self._loading:
            return LOADING
        if path in self._open:
            return OPEN
        if path in self._failed:
            return FAILED
        return None

    def load(self, path, readFn):
        """Read a tracking history off the GUI thread and then visualize it.

        Does nothing if this path is already loading or already visualized: a tracking
        history holds every image and object stack the tracker saw, so a second read is
        both slow and pointless.
        """
        if self.stateOf(path) in (LOADING, OPEN):
            return
        self._failed.discard(path)
        # Construct, connect, then start: the read can finish before start() returns,
        # and sigFinished only reaches a slot connected before that happens.
        task = QtFriendlyTask(readFn, name=f"read {path}", start=False)
        task.sigFinished.connect(self._readFinished)
        self._loading[path] = task
        self.sigChanged.emit(path)
        task.start()

    def _readFinished(self, task):
        """Open the visualizer for a finished read.

        Connected to a bound method of this GUI-thread QObject on purpose: the finish
        callback fires on the worker thread, and the queued connection is what marshals
        window construction back onto the GUI thread.
        """
        path = _keyFor(self._loading, task)
        if path is None:
            return
        del self._loading[path]
        try:
            tracker = task.wait(0)
        except Exception:
            # Reported on the button rather than raised: this runs in a Qt slot, and the
            # user's recourse is simply to click Visualize again.
            logger.exception(f"Error loading tracking history {path!r}")
            self._failed.add(path)
            self.sigChanged.emit(path)
            return
        viz = _openVisualizer(tracker)
        self._open[path] = viz
        _visualizerWindow(viz).installEventFilter(self)
        self.sigChanged.emit(path)

    def eventFilter(self, obj, event):
        """Retire a session when the user closes its window.

        The visualizer is a plain object wrapping a QMainWindow, so there is no close
        signal to connect to.
        """
        if event.type() == Qt.QEvent.Close:
            path = _keyFor(self._open, obj, key=_visualizerWindow)
            if path is not None:
                del self._open[path]
                obj.removeEventFilter(self)
                self.sigChanged.emit(path)
        return False


def _keyFor(mapping, wanted, key=lambda v: v):
    """The key whose value identifies *wanted*, or None. Mappings here hold one or two
    entries, so a scan is cheaper than maintaining a reverse index."""
    return next((k for k, v in mapping.items() if key(v) is wanted), None)


visualizers = _VisualizerRegistry()


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
    selected in the tree -- and enough to hang the GUI, so the read runs on a worker
    thread. The button reports the file's progress through that and stays disabled
    until the window it opened is closed again.
    """

    def __init__(self, fileHandle, parent=None):
        Qt.QWidget.__init__(self, parent)
        self._fileHandle = fileHandle
        self._path = fileHandle.name()
        layout = Qt.QVBoxLayout(self)
        self.visualizeBtn = Qt.QPushButton()
        self.visualizeBtn.clicked.connect(self.visualize)
        layout.addWidget(self.visualizeBtn)
        layout.addStretch()
        visualizers.sigChanged.connect(self._visualizerStateChanged)
        self._updateButton()

    def visualize(self):
        visualizers.load(self._path, self._fileHandle.read)

    def _visualizerStateChanged(self, path):
        if path == self._path:
            self._updateButton()

    def _updateButton(self):
        state = visualizers.stateOf(self._path)
        if state == LOADING:
            self.visualizeBtn.setText("Loading...")
            self.visualizeBtn.setToolTip("Reading the tracking history")
            self.visualizeBtn.setEnabled(False)
        elif state == OPEN:
            self.visualizeBtn.setText("Visualizer open")
            self.visualizeBtn.setToolTip("Close the visualizer window to reopen it")
            self.visualizeBtn.setEnabled(False)
        elif state == FAILED:
            self.visualizeBtn.setText("Load failed")
            self.visualizeBtn.setToolTip("See the log for details; click to try again")
            self.visualizeBtn.setEnabled(True)
        else:
            self.visualizeBtn.setText("Visualize")
            self.visualizeBtn.setToolTip("")
            self.visualizeBtn.setEnabled(True)
