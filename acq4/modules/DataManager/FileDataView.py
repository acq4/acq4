import traceback
from typing import Optional

import pyqtgraph as pg
from MetaArray.plotting import MetaArrayPlotWidget
from acq4.filetypes.MultiPatchLog import MultiPatchLogWidget
from acq4.util import Qt
from acq4.util.DataManager import FileHandle
from acq4.util.DictView import DictView
from acq4.logging_config import get_logger

logger = get_logger(__name__)


class FileDataView(Qt.QSplitter):
    def __init__(self, parent):
        Qt.QSplitter.__init__(self, parent)
        self.setOrientation(Qt.Qt.Vertical)
        self._current = None
        self._widgets = []
        self._dictWidget = None
        self._cursorText = None
        self._imageWidget: Optional[pg.ImageView] = None
        self._multiPatchLogWidget = None

    def setCurrentFile(self, fh: FileHandle):
        if fh is self._current:
            return
        if fh is None or fh.isDir():
            self._current = fh
            self.clear()
            return

        typ = fh.fileType()
        if typ is None:
            self._current = fh
            self.displayMessage(
                f"No file type could be detected for {fh.name()!r}.\n\n"
                "A MultiPatch log must be named 'MultiPatch_*.log' (or have its "
                "'__object_type__' recorded as 'MultiPatchLog' in the .index) to be "
                "recognized by the data viewer."
            )
            return

        try:
            with pg.BusyCursor():
                if typ == 'MultiPatchLog':
                    self.displayMultiPatchLog(fh)
                else:
                    data = fh.read()
                    if typ == 'ImageFile':
                        self.displayDataAsImage(data)
                        self.displayMetaInfoForData(data)
                    elif typ == 'MetaArray':
                        if data.ndim == 2 and not data.axisHasColumns(0) and not data.axisHasColumns(1):
                            self.displayDataAsImage(data)
                        elif data.ndim > 2:
                            self.displayDataAsImage(data)
                        else:
                            self.displayDataAsPlot(data)
                        self.displayMetaInfoForData(data)
                    else:
                        self.displayMessage(f"No data view available for file type {typ!r}.")
        except Exception:
            # Don't mark the file as current so the user can retry by re-selecting it.
            # Surface the error in the tab itself; otherwise it is only quietly logged
            # by the global excepthook and the tab simply appears blank.
            self._current = None
            logger.exception(f"Error displaying data for {fh.name()!r} (type {typ!r})")
            self.displayError(fh, typ)
            return
        self._current = fh

    def displayError(self, fh: FileHandle, typ: str):
        """Show a traceback in the data tab instead of leaving it blank."""
        self.displayMessage(
            f"Error displaying {fh.name()!r} (detected file type: {typ!r}):\n\n"
            f"{traceback.format_exc()}"
        )

    def displayMessage(self, text: str):
        """Show a plain-text message in the data tab instead of leaving it blank."""
        self.clear()
        w = Qt.QTextEdit()
        w.setReadOnly(True)
        w.setLineWrapMode(Qt.QTextEdit.NoWrap)
        w.setText(text)
        self.addWidget(w)
        self._widgets.append(w)

    def displayMetaInfoForData(self, data):
        if not hasattr(data, 'implements') or not data.implements('MetaArray'):
            return
        info = data.infoCopy()
        if self._dictWidget is None:
            w = DictView(info)
            self._dictWidget = w
            self.addWidget(w)
            self._widgets.append(w)
            h = self.size().height()
            self.setSizes([int(h * 0.8), int(h * 0.2)])
        else:
            self._dictWidget.setData(info)

    def displayDataAsPlot(self, data):
        self.clear()
        w = MetaArrayPlotWidget(self)
        w.setObjectName("DataManager_multiPlotWidget")
        self.addWidget(w)
        w.plot(data)
        self._widgets.append(w)

    def displayDataAsImage(self, data):
        if self._imageWidget is None:
            self.clear()
            w = pg.ImageView(self)
            self._imageWidget = w
            self._imageWidget.scene.sigMouseMoved.connect(self.noticeMouseMove)
            self._cursorText = pg.TextItem()
            self._imageWidget.scene.addItem(self._cursorText)
            self.addWidget(w)
            self._widgets.append(w)
        self._imageWidget.setImage(data, autoRange=False)

    def noticeMouseMove(self, pos):
        if self._imageWidget is None:
            return
        view = self._imageWidget.getView()
        if not view.sceneBoundingRect().contains(pos):
            return
        self._cursorText.setPos(pos.x() + 12, pos.y())
        pos = view.mapSceneToView(pos)
        self._cursorText.setText(f'({int(pos.x())}, {int(pos.y())})', color='y')

    def displayMultiPatchLog(self, fh):
        self.clear()
        self._multiPatchLogWidget = MultiPatchLogWidget(self)
        self.addWidget(self._multiPatchLogWidget)
        self._widgets.append(self._multiPatchLogWidget)
        self._multiPatchLogWidget.show()
        self._multiPatchLogWidget.addLog(fh)

    def clear(self):
        for w in self._widgets:
            w.close()
            w.setParent(None)
        if self._imageWidget is not None:
            self._imageWidget.scene.sigMouseMoved.disconnect(self.noticeMouseMove)
        self._widgets = []
        self._dictWidget = None
        self._imageWidget = None
        self._cursorText = None
        self._multiPatchLogWidget = None
