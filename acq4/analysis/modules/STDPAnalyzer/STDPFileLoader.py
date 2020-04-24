from __future__ import print_function
from acq4.util.FileLoader import FileLoader
from acq4.util import Qt

class STDPFileLoader(FileLoader):

    def __init__(self, dataManager, host=None, showFileTree=True):
        FileLoader.__init__(self, dataManager, host, showFileTree)

        self.ui.loadBtn.setText('Load EPSP File')
        self.ui.loadBtn.clicked.disconnect()

        self.ui.loadPairingBtn = Qt.QPushButton('Load Pairing File')
        self.ui.verticalLayout_2.insertWidget(1, self.ui.loadPairingBtn)

        self.ui.loadBtn.clicked.connect(self.loadEPSPClicked)
        self.ui.loadPairingBtn.clicked.connect(self.loadPairingClicked)

    def loadEPSPClicked(self):
        files = self.ui.dirTree.selectedFiles()
        #self.loadFile(fh)
        try:
            Qt.QApplication.setOverrideCursor(Qt.QCursor(Qt.Qt.WaitCursor))
            for fh in files:
                if self.host is None:
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
                elif self.host.loadEPSPFileRequested([fh]):
                    name = fh.name(relativeTo=self.ui.dirTree.baseDirHandle())
                    item = Qt.QTreeWidgetItem([name])
                    item.file = fh
                    self.ui.fileTree.addTopLevelItem(item)
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
        finally:
            Qt.QApplication.restoreOverrideCursor()

    def loadPairingClicked(self):
        files = self.ui.dirTree.selectedFiles()
        #self.loadFile(fh)
        try:
            Qt.QApplication.setOverrideCursor(Qt.QCursor(Qt.Qt.WaitCursor))
            for fh in files:
                if self.host is None:
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
                elif self.host.loadPairingFileRequested([fh]):
                    name = fh.name(relativeTo=self.ui.dirTree.baseDirHandle())
                    item = Qt.QTreeWidgetItem([name])
                    item.file = fh
                    self.ui.fileTree.addTopLevelItem(item)
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
        finally:
            Qt.QApplication.restoreOverrideCursor()
     