import pyqtgraph as pg
from acq4.util import Qt
from acq4.util.DictView import DictView


class FileDataView(Qt.QSplitter):
    def __init__(self, parent):
        Qt.QSplitter.__init__(self, parent)
        self.setOrientation(Qt.Qt.Vertical)
        self.current = None
        self.currentType = None
        self.widgets = []
        self.dictWidget = None
        self._imageWidget = None

    def setCurrentFile(self, file):
        if file is self.current:
            return
        if file is None:
            self.clear()
            self.current = None
            return
        if file.isDir():
            self.clear()
            return
        typ = file.fileType()
        if typ is None:
            self.clear()
            return

        image = False
        with pg.BusyCursor():
            data = file.read()
        if typ == 'ImageFile': 
            image = True
        elif typ == 'MetaArray':
            if data.ndim == 2 and not data.axisHasColumns(0) and not data.axisHasColumns(1):
                image = True
            elif data.ndim > 2:
                image = True
        else:
            return

        with pg.BusyCursor():
            if image:
                self.displayDataAsImage(data)
            else:
                self.displayDataAsPlot(data)

        self.displayMetaInfoForData(data)

    def displayMetaInfoForData(self, data):
        if not hasattr(data, 'implements') or not data.implements('MetaArray'):
            return
        info = data.infoCopy()
        if self.dictWidget is None:
            w = DictView(info)
            self.dictWidget = w
            self.addWidget(w)
            self.widgets.append(w)
            h = self.size().height()
            self.setSizes([int(h * 0.8), int(h * 0.2)])
        else:
            self.dictWidget.setData(info)

    def displayDataAsPlot(self, data):
        self.clear()
        w = pg.MultiPlotWidget(self)
        self.addWidget(w)
        w.plot(data)
        self.currentType = 'plot'
        self.widgets.append(w)

    def displayDataAsImage(self, data):
        if self._imageWidget is None:
            self.clear()
            w = pg.ImageView(self)
            self._imageWidget = w
            self.addWidget(w)
            self.widgets.append(w)
        self._imageWidget.setImage(data, autoRange=False)
        self.currentType = 'image'

    def clear(self):
        for w in self.widgets:
            w.close()
            w.setParent(None)
        self.widgets = []
        self.dictWidget = None
        self._imageWidget = None
