# -*- coding: utf-8 -*-
from DataManagerTemplate import *
from lib.modules import Module

class DataManager(Module):
    def __init__(self, dm):
        Module.__init__(self)
        self.dm = dm
        self.win = QtGui.QMainWindow()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.dialog = QtGui.QFileDialog()
        self.dialog.setFileMode(QtGui.QFileDialog.DirectoryOnly)
        
        ## Load values into GUI
        self.baseDirChanged()
        
        ## Make all connections needed
        QtCore.QObject.connect(self.dm, QtCore.SIGNAL("baseDirChanged()"), self.baseDirChanged)
        QtCore.QObject.connect(self.ui.selectDirBtn, QtCore.SIGNAL("clicked()"), self.showFileDialog)
        QtCore.QObject.connect(ui.ui.txtStorageDir, QtCore.SIGNAL('textEdited(const QString)'), self.selectDir)
        QtCore.QObject.connect(self.dialog, QtCore.SIGNAL('filesSelected(const QStringList)'), self.selectDir)
        
        self.win.show()
        
    def baseDirChanged(self):
        newDir = self.dm.getBaseDir()
        self.ui.storageDirText.setText(newDir)
        
        # refresh file tree view
        
    def showFileDialog(self):
        self.dialog.show()

    def selectDir(self, dirName=None):
        if dirName is None:
            dirName = QtGui.QFileDialog.getExistingDirectory()
        elif type(dirName) is QtCore.QStringList:
            dirName = str(dirName[0])
        elif type(dirName) is QtCore.QString:
            dirName = str(dirName)
        if dirName is None:
            return
        if os.path.isdir(dirName):
            l = QtCore.QMutexLocker(self.lock)
            self.dm.setBaseDir(dirName)
        else:
            raise Exception("Storage directory is invalid")







