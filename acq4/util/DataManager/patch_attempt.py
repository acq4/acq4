class PatchAttemptHandle:
    def __init__(self, uid, dir_handle, **kwargs):
        super().__init__()
        self.id = uid
        self._dh = dir_handle
        if kwargs:
            self.set_info(kwargs)

    def set_info(self, info: dict = None, **kwargs):
        """Store metadata associated with this patch attempt."""
        self._dh.setInfo(info, **kwargs)

    def info(self) -> dict:
        return self._dh.info()

    def get_cell(self) -> 'CellHandle | None':
        cell_id = self.info().get('cell_id', None)
        if cell_id is not None:
            return self._dh.parent().parent().getCellHandle(cell_id)
        return None

    def set_cell(self, cell: 'CellHandle') -> None:
        self.set_info(cell_id=cell.id)
