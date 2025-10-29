from MetaArray import MetaArray

from acq4.util.future import Future


class CellHandle:
    """Class for managing data associated with a specific cell.

    CellHandles are created and cached by DataManager. Each CellHandle is associated
    with a unique identifier (uid) and a DirHandle for storing cell-specific files.
    """

    def __init__(self, uid, dir_handle, **kwargs):
        super().__init__()
        self.id = uid
        self._dh = dir_handle
        if kwargs:
            self.set_info(kwargs)

        if self.position is None:
            raise ValueError("CellHandle must be initialized with a 'position' in info")

        from acq4_automation.feature_tracking.cell import Cell
        self._tracker = Cell(self.position)
        self.sigPositionChanged = self._tracker.sigPositionChanged
        self.sigTrackingMultipleFramesStart = self._tracker.sigTrackingMultipleFramesStart
        self.sigTrackingMultipleFramesFinish = self._tracker.sigTrackingMultipleFramesFinish

    def set_info(self, info: dict = None, **kwargs) -> None:
        """Store metadata associated with this cell."""
        self._dh.setInfo(info, **kwargs)

    def info(self) -> dict:
        """Retrieve metadata associated with this cell."""
        return self._dh.info()

    def set_cellfie(self, data) -> None:
        self._dh.writeFile(data, "cellfie.ma")

    def get_cellfie(self) -> MetaArray | None:
        if self._dh.isFile("cellfie.ma"):
            return self._dh["cellfie.ma"].read()
        return None

    @property
    def position(self):
        return self.info().get("position", None)

    def initialize_tracker(self, camera) -> Future:
        return self._tracker.initializeTracker(camera)

    def enable_tracking(self):
        self._tracker.enableTracking()
