from acq4.util.FileLoader import FileLoader
from PyQt4 import QtCore, QtGui

class STDPFileLoader(FileLoader):

    def __init__(self, dataManager, host=None, showFileTree=True):
        FileLoader.__init__(self, dataManager, host, showFileTree)

        self.ui.loadBtn.setText('Load EPSP File')
        self.ui.loadBtn.clicked.disconnect()

        self.ui.loadPairingBtn = QtGui.QPushButton('Load Pairing File')
        self.ui.verticalLayout_2.insertWidget(1, self.ui.loadPairingBtn)

        self.ui.loadBtn.clicked.connect(self.loadEPSPClicked)
        self.ui.loadPairingBtn.clicked.connect(self.loadPairingClicked)

    def loadEPSPClicked(self):
        files = self.ui.dirTree.selectedFiles()
        #self.loadFile(fh)
        try:
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
            for fh in files:
                if self.host is None:
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
                elif self.host.loadEPSPFileRequested([fh]):
                    name = fh.name(relativeTo=self.ui.dirTree.baseDirHandle())
                    item = QtGui.QTreeWidgetItem([name])
                    item.file = fh
                    self.ui.fileTree.addTopLevelItem(item)
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
        finally:
            QtGui.QApplication.restoreOverrideCursor()

    def loadPairingClicked(self):
        files = self.ui.dirTree.selectedFiles()
        #self.loadFile(fh)
        try:
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
            for fh in files:
                if self.host is None:
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
                elif self.host.loadPairingFileRequested([fh]):
                    name = fh.name(relativeTo=self.ui.dirTree.baseDirHandle())
                    item = QtGui.QTreeWidgetItem([name])
                    item.file = fh
                    self.ui.fileTree.addTopLevelItem(item)
                    self.sigFileLoaded.emit(fh)
                    self.loaded.append(fh)
        finally:
            QtGui.QApplication.restoreOverrideCursor()
     