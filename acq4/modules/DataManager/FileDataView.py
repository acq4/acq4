import pyqtgraph as pg
from acq4.util import Qt
from acq4.util.DictView import DictView


class FileDataView(Qt.QSplitter):
    def __init__(self, parent):
        Qt.QSplitter.__init__(self, parent)
        self.setOrientation(Qt.Qt.Vertical)
        self._current = None
        self._widgets = []
        self._dictWidget = None
        self._imageWidget = None

    def setCurrentFile(self, fh):
        if fh is self._current:
            return
        self._current = fh
        if fh is None or fh.isDir() or (typ := fh.fileType()) is None:
            self.clear()
            return

        with pg.BusyCursor():
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
            elif typ == 'MultiPatchLog':
                self.displayMultiPatchLog(data)

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
        w = pg.MultiPlotWidget(self)
        self.addWidget(w)
        w.plot(data)
        self._widgets.append(w)

    def displayDataAsImage(self, data):
        if self._imageWidget is None:
            self.clear()
            w = pg.ImageView(self)
            self._imageWidget = w
            self.addWidget(w)
            self._widgets.append(w)
        self._imageWidget.setImage(data, autoRange=False)

    def clear(self):
        for w in self._widgets:
            w.close()
            w.setParent(None)
        self._widgets = []
        self._dictWidget = None
        self._imageWidget = None
