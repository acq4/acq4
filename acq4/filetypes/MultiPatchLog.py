import pyqtgraph as pg
from acq4.util import Qt
from acq4.filetypes.FileType import FileType
from acq4.util.MultiPatchLog import MultiPatchLog as MultiPatchLogData


class MultiPatchLog(FileType):
    """File type written by MultiPatch module.
    """
    extensions = ['.log']   # list of extensions handled by this class
    dataTypes = []    # list of python types handled by this class
    priority = 0      # priority for this class when multiple classes support the same file types
    
    @classmethod
    def read(cls, fileHandle) -> MultiPatchLogData:
        """Read a file, return a data object"""
        return MultiPatchLogData(fileHandle.name())
        
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
        self._logFiles = []
        self._pipettes = []
        self._cells = []
        self._events = []
        self._widgets = []
        self._pinned_image_z = -10000
        self._layout = Qt.QVBoxLayout()
        self.setLayout(self._layout)
        self._visual_field = pg.GraphicsLayoutWidget()
        self._widgets.append(self._visual_field)
        self._layout.addWidget(self._visual_field)
        self._plot = self._visual_field.addPlot(title="")

    def addLog(self, log: "FileHandle"):
        self._logFiles.append(log)
        log_data = log.read()
        self._pipettes.extend(log_data.devices())
        if log.parent():
            self.loadImagesFromDir(log.parent().parent())
        self.loadImagesFromDir(log.parent())
        for dev in log_data.devices():
            path = log_data[dev]['position'][:, 1:3]  # TODO time as color
            self._plot.plot(path[:, 0], path[:, 1], pen=pg.mkPen('r', width=2))

    def loadImagesFromDir(self, directory: "DirHandle"):
        # TODO images associated with the correct slice and cell only
        # TODO integrate with time-slider to set the Z values
        from acq4.util.imaging import Frame

        for f in directory.ls():
            if f.endswith('.tif'):
                f = directory[f]
                frame = Frame(f.read(), f.info().deepcopy())
                frame.loadLinkedFiles(directory)
                img = frame.imageItem()
                img.setZValue(self._pinned_image_z)
                self._pinned_image_z += 1
                self._plot.addItem(img)

    def clear(self):
        for w in self._widgets:
            w.setParent(None)
            w.deleteLater()
