class PatchAttemptHandle:
    def __init__(self, uid, dirHandle, dataManager):
        super().__init__()
        self.id = uid
        self.dirHandle = dirHandle
        self.dataManager = dataManager

    def setInfo(self, info: dict = None, **kwargs):
        """Store metadata associated with this patch attempt."""
        self.dirHandle.setInfo(info, **kwargs)

    def info(self) -> dict:
        return self.dirHandle.info()

    def getCell(self) -> 'CellHandle | None':
        cell_id = self.info().get('cell_id', None)
        if cell_id is not None:
            return self.dirHandle.parent().getCellHandle(cell_id)
        return None

    def setCell(self, cell: 'CellHandle') -> None:
        self.setInfo(cell_id=cell.id)
