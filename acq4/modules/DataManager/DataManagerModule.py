# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import time

import six
from pyqtgraph import FileDialog
from six.moves import range

from acq4.Manager import logMsg
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.DataManager import getDataManager, getHandle, DirHandle
from acq4.util.StatusBar import StatusBar
from acq4.util.debug import printExc
from . import FileAnalysisView
from . import FileLogView

Ui_MainWindow = Qt.importTemplate('.DataManagerTemplate')


class Window(Qt.QMainWindow):
    sigClosed = Qt.Signal()

    def closeEvent(self, ev):
        ev.accept()
        self.sigClosed.emit()


class DataManager(Module):
    moduleDisplayName = "Data Manager"
    moduleCategory = "Acquisition"

    sigAnalysisDbChanged = Qt.Signal()

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.dm = getDataManager()
        self.win = Window()
        mp = os.path.dirname(__file__)
        self.win.setWindowIcon(Qt.QIcon(os.path.join(mp, 'icon.png')))
        self.win.dm = self  ## so embedded widgets can find the module easily
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.ui.analysisWidget = FileAnalysisView.FileAnalysisView(self.ui.analysisTab, self)
        self.ui.analysisTab.layout().addWidget(self.ui.analysisWidget)
        self.ui.logWidget = FileLogView.FileLogView(self.ui.logTab, self)
        self.ui.logTab.layout().addWidget(self.ui.logWidget)

        self.win.show()
        w = self.ui.splitter.width()
        self.ui.splitter.setSizes([int(w * 0.4), int(w * 0.6)])
        self.ui.logDock.hide()
        self.dialog = None
        self.ui.fileTreeWidget.setSelectionMode(Qt.QAbstractItemView.ExtendedSelection)
        try:
            self.baseDirChanged()
        except Exception:
            printExc("Could not set base directory:")
        try:
            self.currentDirChanged()
        except Exception:
            printExc("Could not set current directory:")

        self.selFile = None
        self.updateNewFolderList()

        ## Make all connections needed
        self.manager.sigBaseDirChanged.connect(self.baseDirChanged)
        self.manager.sigConfigChanged.connect(self.updateNewFolderList)
        self.manager.sigCurrentDirChanged.connect(self.currentDirChanged)
        self.manager.sigLogDirChanged.connect(self.updateLogDir)
        self.ui.analysisWidget.sigDbChanged.connect(self.analysisDbChanged)
        self.ui.baseDirText.editingFinished.connect(self.baseDirTextChanged)
        self.ui.fileDisplayTabs.currentChanged.connect(self.tabChanged)
        self.ui.fileTreeWidget.itemSelectionChanged.connect(self.fileSelectionChanged)
        self.ui.newFolderList.currentIndexChanged.connect(self.newFolder)
        self.ui.selectDirBtn.clicked.connect(self.showFileDialog)
        self.ui.setCurrentDirBtn.clicked.connect(self.setCurrentClicked)
        self.ui.setLogDirBtn.clicked.connect(self.setLogDir)
        self.win.sigClosed.connect(self.quit)

        self.win.setStatusBar(StatusBar())

    def updateNewFolderList(self):
        self.ui.newFolderList.clear()
        conf = self.manager._folderTypesConfig()
        self.ui.newFolderList.clear()
        self.ui.newFolderList.addItems(['New...', 'Folder'] + list(conf.keys()))

    def baseDirChanged(self):
        dh = self.manager.getBaseDir()
        self.baseDir = dh
        if dh is None:
            self.ui.baseDirText.setText('')
        else:
            self.ui.baseDirText.setText(dh.name())
        self.ui.fileTreeWidget.setBaseDirHandle(dh)

    def loadLog(self, *args, **kwargs):
        pass

    def selectFile(self, path):
        if isinstance(path, six.string_types):
            path = getHandle(path)
        self.ui.fileTreeWidget.select(path)

    def setLogDir(self):
        d = self.selectedFile()
        if not isinstance(d, DirHandle):
            d = d.parent()
        self.manager.setLogDir(d)

    def updateLogDir(self, d):
        self.ui.logDirText.setText(d.name(relativeTo=self.baseDir))

    def setCurrentClicked(self):
        # print "click"
        handle = self.selectedFile()
        if handle is None:
            # print "no selection"
            return
        if not handle.isDir():
            handle = handle.parent()
        self.manager.setCurrentDir(handle)

    def currentDirChanged(self, name=None, change=None, args=()):
        if change in [None, 'moved', 'renamed', 'parent']:
            try:
                newDir = self.manager.getCurrentDir()
            except:
                newDir = None
                dirName = ""
            else:
                dirName = newDir.name(relativeTo=self.baseDir)
            self.ui.currentDirText.setText(str(dirName))
            self.ui.fileTreeWidget.setCurrentDir(newDir)
        elif change == 'log':
            self.updateLogView(*args)
        if change == None:
            try:
                newDir = self.manager.getCurrentDir()
            except:
                newDir = None
            else:
                self.loadLog(newDir, self.ui.logView)

    def showFileDialog(self):
        bd = self.manager.getBaseDir()
        if self.dialog is None:
            self.dialog = FileDialog()
            self.dialog.setFileMode(Qt.QFileDialog.DirectoryOnly)
            self.dialog.filesSelected.connect(self.setBaseDir)
        if bd is not None:
            self.dialog.setDirectory(bd.name())
        self.dialog.show()

    def baseDirTextChanged(self):
        path = str(self.ui.baseDirText.text())
        if path.strip() == '':
            self.baseDirChanged()
            return
        if not os.path.isdir(path):
            raise ValueError("Path %s does not exist" % path)
        self.setBaseDir(path)

    def setBaseDir(self, dirName):
        if isinstance(dirName, list):
            if len(dirName) == 1:
                dirName = dirName[0]
            else:
                raise Exception("Caught. Please to be examined: %s" % str(dirName))
        if dirName is None:
            return
        if os.path.isdir(dirName):
            self.manager.setBaseDir(dirName)
        else:
            raise Exception("Storage directory is invalid")

    def selectedFile(self):
        """Return the currently selected file"""
        items = self.ui.fileTreeWidget.selectedItems()
        if len(items) > 0:
            return items[0].handle
        else:
            return None

    def newFolder(self):
        if self.ui.newFolderList.currentIndex() < 1:
            return

        ftype = str(self.ui.newFolderList.currentText())
        self.ui.newFolderList.setCurrentIndex(0)

        cdir = self.manager.getCurrentDir()
        if not cdir.isManaged():
            cdir.createIndex()

        if ftype == 'Folder':
            nd = cdir.mkdir('NewFolder', autoIncrement=True)
            # item = self.model.handleIndex(nd)
            self.ui.fileTreeWidget.editItem(nd)
        else:
            spec = self.manager._folderTypesConfig()[ftype]
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
                    # else:
                    # print "dir no match:", spec, inf
                    checkDir = checkDir.parent()
            except:
                printExc("Error while deciding where to put new folder (using currentDir by default)")

            ## make
            nd = parent.mkdir(name, autoIncrement=True)

            ## Add meta-info
            info = {'dirType': ftype}
            if spec.get('experimentalUnit', False):
                info['expUnit'] = True
            nd.setInfo(info)

            self.ui.fileTreeWidget.refresh(
                parent)  ## fileTreeWidget waits a while before updating; force it to refresh immediately.
            self.ui.fileTreeWidget.select(nd)

        logMsg("Created new folder: %s" % nd.name(relativeTo=self.baseDir), msgType='status', importance=7)
        self.manager.setCurrentDir(nd)

    def fileSelectionChanged(self):
        # print "file selection changed"
        if self.selFile is not None:
            try:
                self.selFile.sigChanged.disconnect(self.selectedFileAltered)
            except TypeError:
                pass

        fh = self.selectedFile()
        self.manager.currentFile = fh  ## Make this really easy to pick up from an interactive prompt.
        self.loadFile(fh)
        self.selFile = fh
        if fh is not None:
            self.selFile.sigChanged.connect(self.selectedFileAltered)

    def loadFile(self, fh):
        if fh is None:
            self.ui.fileInfo.setCurrentFile(None)
            self.ui.dataViewWidget.setCurrentFile(None)
            self.ui.logWidget.selectedFileChanged(None)
            self.ui.fileNameLabel.setText('')
        else:
            self.ui.fileNameLabel.setText(fh.name(relativeTo=self.baseDir))
            self.tabChanged()

    def tabChanged(self, n=None):
        if n is None:
            n = self.ui.fileDisplayTabs.currentIndex()
        fh = self.selectedFile()
        if n == 0:
            self.ui.fileInfo.setCurrentFile(fh)
        elif n == 1:
            self.ui.logWidget.selectedFileChanged(fh)
        elif n == 2:
            self.ui.dataViewWidget.setCurrentFile(fh)

    def selectedFileAltered(self, name, change, args):
        if change in ['parent', 'renamed', 'moved'] and self.selFile is not None:
            self.ui.fileTreeWidget.select(self.selFile)  ## re-select file if it has moved.
            self.ui.fileNameLabel.setText(self.selFile.name(relativeTo=self.baseDir))

    def quit(self):
        ## Silly: needed to prevent lockup on some systems.
        self.ui.fileTreeWidget.quit()
        self.ui.analysisWidget.quit()
        Module.quit(self)

    def currentDatabase(self):
        return self.ui.analysisWidget.currentDatabase()

    def dataModel(self):
        return self.ui.analysisWidget.currentDataModel()

    def analysisDbChanged(self):
        self.sigAnalysisDbChanged.emit()
