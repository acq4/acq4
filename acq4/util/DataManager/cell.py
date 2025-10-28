from MetaArray import MetaArray


class CellHandle:
    """Class for managing data associated with a specific cell.

    CellHandles are created and cached by DataManager. Each CellHandle is associated
    with a unique identifier (uid) and a DirHandle for storing cell-specific files.
    """

    def __init__(self, uid, dirHandle, dataManager):
        super().__init__()
        self.id = uid
        self.dirHandle = dirHandle
        self.dataManager = dataManager

    def setInfo(self, info: dict = None, **kwargs) -> None:
        """Store metadata associated with this cell."""
        self.dirHandle.setInfo(info, **kwargs)

    def info(self) -> dict:
        """Retrieve metadata associated with this cell."""
        return self.dirHandle.info()

    def setCellfie(self, data) -> None:
        self.dirHandle.writeFile(data, "cellfie.ma")

    def getCellfie(self) -> MetaArray | None:
        if self.dirHandle.isFile("cellfie.ma"):
            return self.dirHandle["cellfie.ma"].read()
        return None
