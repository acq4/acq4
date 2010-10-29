# -*- coding: utf-8 -*-
from DataManagerTemplate import *
from DataManagerModel import *
from lib.modules.Module import *
from lib.util.DataManager import *
import os, re, sys, time, sip
from lib.util.debug import *
import FileAnalysisView

class Window(QtGui.QMainWindow):
    def closeEvent(self, ev):
        ev.accept()
        self.emit(QtCore.SIGNAL('closed'))

class DataManager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.dm = self.manager.dataManager
        self.win = Window()
        self.win.dm = self  ## so embedded widgets can find the module easily
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.ui.analysisWidget = FileAnalysisView.FileAnalysisView(self.ui.analysisTab, self)
        self.ui.analysisTab.layout().addWidget(self.ui.analysisWidget)
        w = self.ui.splitter.width()
        self.ui.splitter.setSizes([int(w*0.2), int(w*0.8)])
        self.dialog = QtGui.QFileDialog()
        self.dialog.setFileMode(QtGui.QFileDialog.DirectoryOnly)
        ## Load values into GUI
        #self.model = DMModel(self.manager.getBaseDir())
        #self.ui.fileTreeView.setModel(self.model)
        self.baseDirChanged()
        self.currentDirChanged()
        self.selFile = None
        self.updateNewFolderList()
        
        
        ## Make all connections needed
        #QtCore.QObject.connect(self.dm, QtCore.SIGNAL("baseDirChanged()"), self.baseDirChanged)
        QtCore.QObject.connect(self.ui.selectDirBtn, QtCore.SIGNAL("clicked()"), self.showFileDialog)
        QtCore.QObject.connect(self.ui.setCurrentDirBtn, QtCore.SIGNAL("clicked()"), self.setCurrentClicked)
        #QtCore.QObject.connect(self.ui.storageDirText, QtCore.SIGNAL('textEdited(const QString)'), self.selectDir)
        QtCore.QObject.connect(self.dialog, QtCore.SIGNAL('filesSelected(const QStringList)'), self.setBaseDir)
        QtCore.QObject.connect(self.manager, QtCore.SIGNAL('baseDirChanged'), self.baseDirChanged)
        QtCore.QObject.connect(self.manager, QtCore.SIGNAL('currentDirChanged'), self.currentDirChanged)
        QtCore.QObject.connect(self.manager, QtCore.SIGNAL('configChanged'), self.updateNewFolderList)
        QtCore.QObject.connect(self.ui.newFolderList, QtCore.SIGNAL('currentIndexChanged(int)'), self.newFolder)
        #QtCore.QObject.connect(self.ui.fileTreeWidget.selectionModel(), QtCore.SIGNAL('selectionChanged(const QItemSelection&, const QItemSelection&)'), self.fileSelectionChanged)
        QtCore.QObject.connect(self.ui.fileTreeWidget, QtCore.SIGNAL('itemSelectionChanged()'), self.fileSelectionChanged)
        QtCore.QObject.connect(self.ui.logEntryText, QtCore.SIGNAL('returnPressed()'), self.logEntry)
        QtCore.QObject.connect(self.ui.fileDisplayTabs, QtCore.SIGNAL('currentChanged(int)'), self.tabChanged)
        QtCore.QObject.connect(self.win, QtCore.SIGNAL('closed'), self.quit)
        self.win.show()
        
    #def hasInterface(self, interface):
        #return interface in ['DataSource']

    def updateNewFolderList(self):
        self.ui.newFolderList.clear()
        conf = self.manager.config['folderTypes']
        #print "folderTypes:", self.manager.config['folderTypes'].keys()
        self.ui.newFolderList.clear()
        self.ui.newFolderList.addItems(['New...', 'Folder'] + conf.keys())
        
    def baseDirChanged(self):
        dh = self.manager.getBaseDir()
        self.baseDir = dh
        self.ui.baseDirText.setText(QtCore.QString(dh.name()))
        self.ui.fileTreeWidget.setBaseDirHandle(dh)
        #self.currentDirChanged()

    def setCurrentClicked(self):
        handle = self.selectedFile()
        if handle is None:
            return
        if not handle.isDir():
            handle = handle.parent()
        #dh = self.manager.dirHandle(newDir)
        self.manager.setCurrentDir(handle)

    def currentDirChanged(self, name=None, change=None, *args):
        if change in [None, 'moved', 'renamed', 'parent']:
            newDir = self.manager.getCurrentDir()
            dirName = newDir.name(relativeTo=self.baseDir)
            self.ui.currentDirText.setText(QtCore.QString(dirName))
            self.ui.logDock.setWindowTitle(QtCore.QString('Current Log - ' + dirName))
            self.ui.fileTreeWidget.setCurrentDir(newDir)
            #dirIndex = self.ui.fileTreeWidget.handleIndex(newDir)
            #self.ui.fileTreeWidget.setExpanded(dirIndex, True)
            #self.ui.fileTreeWidget.scrollTo(dirIndex)
        elif change == 'log':
            self.updateLogView(*args)
        if change == None:
            self.loadLog(self.manager.getCurrentDir(), self.ui.logView)

    def loadLog(self, dirHandle, widget, recursive=0):
        widget.clear()
        log = dirHandle.readLog(recursive)
        for line in self.logRender(log):
            widget.append(line)
            

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
        """Return the currently selected file"""
        items = self.ui.fileTreeWidget.selectedItems()
        if len(items) > 0:
            return items[0].handle
        else:
            return None
        #sel = list(self.ui.fileTreeWidget.selectedIndexes())
        #if len(sel) == 0:
        #    return None
        #if len(sel) == 1:
        #    index = sel[0]
        #else:
        #    raise Exception("Error - multiple items selected")
        ##print "index:", index.internalPointer()
        #if index.internalPointer() is None:
        #    return None
        #return self.model.handle(index)

    def newFolder(self):
        if self.ui.newFolderList.currentIndex() < 1:
            return
            
        ftype = str(self.ui.newFolderList.currentText())
        self.ui.newFolderList.setCurrentIndex(0)
        
        cdir = self.manager.getCurrentDir()
        if ftype == 'Folder':
            nd = cdir.mkdir('NewFolder', autoIncrement=True)
            #item = self.model.handleIndex(nd)
            self.ui.fileTreeWidget.editItem(nd)
        else:
            spec = self.manager.config['folderTypes'][ftype]
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
                printExc("Error while deciding where to put new folder (using currentDir by default)")
            
            ## make
            nd = parent.mkdir(name, autoIncrement=True)
            
            ## Add meta-info
            info = {'dirType': ftype}
            nd.setInfo(info)
            
            ## set display to info
            #self.showFileInfo(nd)
            
            #index = self.model.handleIndex(nd)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Clear)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Select)
            self.ui.fileTreeWidget.refresh(parent)  ## fileTreeWidget waits a while before updating; force it to refresh immediately.
            self.ui.fileTreeWidget.select(nd)
            ##self.ui.fileInfo.setCurrentFile(nd)
            
            
        self.manager.setCurrentDir(nd)


    def fileSelectionChanged(self):
        #print "file selection changed"
        if self.selFile is not None:
            QtCore.QObject.disconnect(self.selFile, QtCore.SIGNAL('changed'), self.selectedFileAltered)
        
        fh = self.selectedFile()
        self.manager.currentFile = fh  ## Make this really easy to pick up from an interactive prompt.
        self.loadFile(fh)
        self.selFile = fh
        if fh is not None:
            QtCore.QObject.connect(self.selFile, QtCore.SIGNAL('changed'), self.selectedFileAltered)
        
    def loadFile(self, fh):
        self.ui.selectedLogView.clear()
        if fh is None:
            self.ui.fileInfo.setCurrentFile(None)
            self.ui.dataViewWidget.setCurrentFile(None)
            self.ui.fileNameLabel.setText('')
        else:
            #self.ui.fileInfo.setCurrentFile(fh)
            #self.ui.dataViewWidget.setCurrentFile(fh)
            self.ui.fileNameLabel.setText(fh.name(relativeTo=self.baseDir))
            #if fh.isDir():
                #self.loadLog(fh, self.ui.selectedLogView, recursive=3)
            self.tabChanged()

    def tabChanged(self, n=None):
        if n is None:
            n = self.ui.fileDisplayTabs.currentIndex()
        fh = self.selectedFile()
        if n == 0:
            self.ui.fileInfo.setCurrentFile(fh)
        elif n == 1:
            if fh.isDir():
                self.loadLog(fh, self.ui.selectedLogView, recursive=3)
        elif n == 2:
            self.ui.dataViewWidget.setCurrentFile(fh)
            

    def selectedFileAltered(self, name, change, *args):
        if change in ['parent', 'renamed', 'moved'] and self.selFile is not None:
            #index = self.model.handleIndex(self.selFile)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Clear)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Select)
            self.ui.fileTreeWidget.select(self.selFile)  ## re-select file if it has moved.
            self.ui.fileNameLabel.setText(self.selFile.name(relativeTo=self.baseDir))
        
        #self.fileSelectionChanged()
        
    def logEntry(self):
        text = str(self.ui.logEntryText.text())
        cd = self.manager.getCurrentDir()
        self.ui.logEntryText.setText('')
        if text == '' or cd is None:
            return
        cd.logMsg(text, {'source': 'user'})
        
    def updateLogView(self, *args):
        msg = args[0]
        self.ui.logView.append(self.logRender(msg))
        #print "new log msg"
        
    def logRender(self, log):
        returnList = True
        if type(log) is dict:
            log = [log]
            returnList = False
        elif type(log) is not list:
            raise Exception('logRender requires dict or list of dicts as argument')
            
        lines = []
        for msg in log:
            t = time.strftime('%Y.%m.%d %H:%M:%S', time.localtime(msg['__timestamp__']))
            style = 'color: #000; font-style: normal'
            sourceStyles = {
                'user': 'color: #008; font-style: italic'
            }
            if 'source' in msg and msg['source'] in sourceStyles:
                style = sourceStyles[msg['source']]
            parts = ["<span style='color: #888'>[%s]</span>" % t]
            if 'subdir' in msg:
                parts.append(msg['subdir'])
            parts.append("<span style='%s'>%s</span>" % (style, msg['__message__']))
            lines.append('&nbsp;&nbsp;'.join(parts))
        if returnList:
            return lines
        else:
            return lines[0]
            
    def quit(self):
        ## Silly: needed to prevent lockup on some systems.
        #print "      module quitting.."
        self.ui.fileTreeWidget.quit()
        #sip.delete(self.dialog)
        #print "      deleted dialog, calling superclass quit.."
        Module.quit(self)
        #print "      module quit done"
        #print backtrace()
        
