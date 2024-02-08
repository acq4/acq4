from acq4.util import Qt
from .FileType import FileType


class MultiPatchLog(FileType):
    """File type written by MultiPatch module.
    """
    extensions = ['.log']   # list of extensions handled by this class
    dataTypes = []    # list of python types handled by this class
    priority = 0      # priority for this class when multiple classes support the same file types
    
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        from ..modules.MultiPatch.logfile import MultiPatchLog
        return MultiPatchLog(fileHandle.name())
        
    @classmethod
    def acceptsFile(cls, fileHandle):
        """Return priority value if the file can be read by this class.
        Otherwise, return False.
        The default implementation just checks for the correct name extensions."""
        name = fileHandle.shortName()
        if name.startswith('MultiPatch_') and name.endswith('.log'):
            return cls.priority
        return False


class MultiPatchLogWidget(Qt.QWidget):
    # TODO look at mosaic editor
    # TODO make a graphics view
    # TODO load pinned images from parent directory
    # TODO add plot of events on timeline (tags?)
    #    selectable event types to display?
    # TODO images saved in this directory should be displayed as the timeline matches?
    # TODO option to add plots for anything else
    # TODO add target position
    # TODO add pipette position (and paths?)
    #    we don't poll the position, so the movement requests are all we have
    # TODO investigate what logging autopatch module does
    # TODO associate all images and recordings with the cell
    # TODO multipatch logs are one-per-cell
    # TODO they can reference each other?
    # TODO widget should be able to handle multiple log files
    # TODO selectable cells, pipettes
    # TODO filter log messages by type
    # TODO raw log? just events on the time plot may be enough
    # TODO don't try to display position Z
    def __init__(self, parent=None):
        Qt.QWidget.__init__(self, parent)
        self._layout = Qt.QVBoxLayout()
        self.setLayout(self._layout)
        self._logFiles = []
        self._pipettes = []
        self._cells = []
        self._events = []

    def addLog(self, log):
        self._logFiles.append(log)
        log_file = log.read()
        self._pipettes.extend(log_file.devices())
        # TODO

    def clear(self):
        pass  # TODO
