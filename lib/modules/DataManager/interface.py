# -*- coding: utf-8 -*-
from DataManagerTemplate import *
from DataManagerModel import *
from lib.modules.Module import *
from lib.DataManager import *
import os, re, sys, time

class DataManager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.dm = self.manager.dataManager
        self.win = QtGui.QMainWindow()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.dialog = QtGui.QFileDialog()
        self.dialog.setFileMode(QtGui.QFileDialog.DirectoryOnly)
        ## Load values into GUI
        self.model = DMModel(self.manager.getBaseDir())
        self.ui.fileTreeView.setModel(self.model)
        self.baseDirChanged()
        self.currentDirChanged()
        self.selFile = None
        
        
        ## Make all connections needed
        #QtCore.QObject.connect(self.dm, QtCore.SIGNAL("baseDirChanged()"), self.baseDirChanged)
        QtCore.QObject.connect(self.ui.selectDirBtn, QtCore.SIGNAL("clicked()"), self.showFileDialog)
        QtCore.QObject.connect(self.ui.setCurrentDirBtn, QtCore.SIGNAL("clicked()"), self.setCurrentClicked)
        #QtCore.QObject.connect(self.ui.storageDirText, QtCore.SIGNAL('textEdited(const QString)'), self.selectDir)
        QtCore.QObject.connect(self.dialog, QtCore.SIGNAL('filesSelected(const QStringList)'), self.setBaseDir)
        QtCore.QObject.connect(self.manager, QtCore.SIGNAL('baseDirChanged'), self.baseDirChanged)
        QtCore.QObject.connect(self.manager, QtCore.SIGNAL('currentDirChanged'), self.currentDirChanged)
        QtCore.QObject.connect(self.ui.newFolderList, QtCore.SIGNAL('currentIndexChanged(int)'), self.newFolder)
        QtCore.QObject.connect(self.ui.fileTreeView.selectionModel(), QtCore.SIGNAL('selectionChanged(const QItemSelection&, const QItemSelection&)'), self.fileSelectionChanged)
        self.win.show()
        
    def updateNewFolderList(self):
        conf = self.manager.conf['folderTypes']
        self.ui.newFolderList.clear()
        self.ui.newFolderList.addItems(['New...', 'Folder'] + conf.keys())
        
    def baseDirChanged(self):
        dh = self.manager.getBaseDir()
        self.baseDir = dh
        self.ui.baseDirText.setText(QtCore.QString(dh.name()))
        self.model.setBaseDirHandle(dh)
        self.currentDirChanged()

    def setCurrentClicked(self):
        handle = self.selectedFile()
        if handle is None:
            return
        if not handle.isDir():
            handle = handle.parent()
        #dh = self.manager.dirHandle(newDir)
        self.manager.setCurrentDir(handle)

    def currentDirChanged(self):
        newDir = self.manager.getCurrentDir()
        dirName = newDir.name(relativeTo=self.baseDir)
        self.ui.currentDirText.setText(QtCore.QString(dirName))
        
        self.model.setCurrentDir(newDir)
        dirIndex = self.model.handleIndex(newDir)
        self.ui.fileTreeView.setExpanded(dirIndex, True)
        self.ui.fileTreeView.scrollTo(dirIndex)
        
        # refresh file tree view
        
    def showFileDialog(self):
        self.dialog.setDirectory(self.manager.getBaseDir().name())
        self.dialog.show()

    def setBaseDir(self, dirName):
        #if dirName is None:
            #dirName = QtGui.QFileDialog.getExistingDirectory()
        if type(dirName) is QtCore.QStringList:
            dirName = str(dirName[0])
        elif type(dirName) is QtCore.QString:
            dirName = str(dirName)
        if dirName is None:
            return
        if os.path.isdir(dirName):
            self.manager.setBaseDir(dirName)
        else:
            raise Exception("Storage directory is invalid")
            
    def selectedFile(self):
        sel = list(self.ui.fileTreeView.selectedIndexes())
        if len(sel) == 0:
            return None
        if len(sel) == 1:
            index = sel[0]
        else:
            raise Exception("Error - multiple items selected")
        #print "index:", index.internalPointer()
        if index.internalPointer() is None:
            return None
        return self.model.handle(index)

    def newFolder(self):
        if self.ui.newFolderList.currentIndex() == 0:
            return
            
        ftype = str(self.ui.newFolderList.currentText())
        self.ui.newFolderList.setCurrentIndex(0)
        
        cdir = self.manager.getCurrentDir()
        if ftype == 'Folder':
            nd = cdir.mkdir('NewFolder', autoIncrement=True)
            item = self.model.handleIndex(nd)
            self.ui.fileTreeView.edit(item)
        else:
            spec = self.manager.conf['folderTypes'][ftype]
            name = time.strftime(spec['name'])
                
            ## Determine where to put the new directory
            parent = cdir
            try:
                checkDir = cdir
                for i in range(5):
                    if not checkDir.isManaged():
                        break
                    inf = checkDir.info()
                    if 'dirType' in inf and inf['dirType'] == ftype:
                        parent = checkDir.parent()
                        break
                    #else:
                        #print "dir no match:", spec, inf
                    checkDir = checkDir.parent()
            except:
                sys.excepthook(*sys.exc_info())
                print "Error while deciding where to put new folder (using currentDir by default)"
            
            ## make
            nd = parent.mkdir(name, autoIncrement=True)
            
            ## Add meta-info
            info = {'dirType': ftype}
            nd.setInfo(info)
            
            ## set display to info
            #self.showFileInfo(nd)
            
            index = self.model.handleIndex(nd)
            self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Clear)
            self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Select)
            #self.ui.fileInfo.setCurrentFile(nd)
            
            
        self.manager.setCurrentDir(nd)


    def fileSelectionChanged(self):
        if self.selFile is not None:
            QtCore.QObject.disconnect(self.selFile, QtCore.SIGNAL('changed'), self.selectedFileAltered)
        
        
        fh = self.selectedFile()
        if fh is None:
            self.ui.fileInfo.setCurrentFile(None)
            self.ui.fileNameLabel.setText('')
        else:
            self.selFile = fh
            QtCore.QObject.connect(self.selFile, QtCore.SIGNAL('changed'), self.selectedFileAltered)
            self.ui.fileInfo.setCurrentFile(self.selFile)
            self.ui.fileNameLabel.setText(fh.name(relativeTo=self.baseDir))
        
    def selectedFileAltered(self):
        self.fileSelectionChanged()
        
        
        
        

