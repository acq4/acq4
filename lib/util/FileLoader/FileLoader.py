import template
from PyQt4 import QtCore, QtGui

class FileLoader(QtGui.QWidget):
    def __init__(self, dataManager):
        self.dataManager = dataManager
        QtGui.QWidget.__init__(self)
        self.ui = template.Ui_Form()
        self.ui.setupUi(self)
        
        self.ui.setDirBtn.clicked.connect(self.setBaseClicked)
        self.ui.loadBtn.clicked.connect(self.loadClicked)
        
    def setBaseClicked(self):
        dh = self.dataManager.selectedFile()
        if dh is None:
            raise Exception("No directory selected in data manager")
        self.ui.dirTree.setBaseDirHandle(dh)
        
    def loadClicked(self):
        fh = self.ui.dirTree.selectedFile()
        self.loadFile(fh)
        
    def loadFile(self, fh):
        name = fh.name(relativeTo=self.ui.dirTree.baseDirHandle())
        self.ui.fileTree.addTopLevelItem(QtGui.QTreeWidgetItem([name]))
        self.emit(QtCore.SIGNAL('fileLoaded'), fh)
        