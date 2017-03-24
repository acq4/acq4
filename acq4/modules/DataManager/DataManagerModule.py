# -*- coding: utf-8 -*-
from DataManagerTemplate import *
from acq4.modules.Module import *
from acq4.util.DataManager import *
import os, re, sys, time
from acq4.util.debug import *
import FileAnalysisView
from acq4.LogWindow import LogButton, LogWindow
import FileLogView
from acq4.pyqtgraph import FileDialog
from acq4.Manager import logMsg, logExc
from acq4.util.StatusBar import StatusBar

class Window(QtGui.QMainWindow):
    
    sigClosed = QtCore.Signal()
    
    def closeEvent(self, ev):
        ev.accept()
        #self.emit(QtCore.SIGNAL('closed'))
        self.sigClosed.emit()

class DataManager(Module):
    
    sigAnalysisDbChanged = QtCore.Signal()
    
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        #self.dm = self.manager.dataManager
        self.dm = getDataManager()
        self.win = Window()
        mp = os.path.dirname(__file__)
        self.win.setWindowIcon(QtGui.QIcon(os.path.join(mp, 'icon.png')))
        self.win.dm = self  ## so embedded widgets can find the module easily
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.ui.analysisWidget = FileAnalysisView.FileAnalysisView(self.ui.analysisTab, self)
        self.ui.analysisTab.layout().addWidget(self.ui.analysisWidget)
        self.ui.logWidget = FileLogView.FileLogView(self.ui.logTab, self)
        self.ui.logTab.layout().addWidget(self.ui.logWidget)
        
        self.win.show()
        w = self.ui.splitter.width()
        self.ui.splitter.setSizes([int(w*0.4), int(w*0.6)])
        self.ui.logDock.hide()
        self.dialog = FileDialog()
        self.dialog.setFileMode(QtGui.QFileDialog.DirectoryOnly)
        self.ui.fileTreeWidget.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        ## Load values into GUI
        #self.model = DMModel(self.manager.getBaseDir())
        #self.ui.fileTreeView.setModel(self.model)
        self.baseDirChanged()
        self.currentDirChanged()
        self.selFile = None
        self.updateNewFolderList()
        
        
        ## Make all connections needed
        self.ui.selectDirBtn.clicked.connect(self.showFileDialog)
        self.ui.setCurrentDirBtn.clicked.connect(self.setCurrentClicked)
        self.dialog.filesSelected.connect(self.setBaseDir)
        self.manager.sigBaseDirChanged.connect(self.baseDirChanged)
        self.manager.sigCurrentDirChanged.connect(self.currentDirChanged)
        self.manager.sigConfigChanged.connect(self.updateNewFolderList)
        self.manager.sigLogDirChanged.connect(self.updateLogDir)
        self.ui.setLogDirBtn.clicked.connect(self.setLogDir)
        self.ui.newFolderList.currentIndexChanged.connect(self.newFolder)
        self.ui.fileTreeWidget.itemSelectionChanged.connect(self.fileSelectionChanged)
        #self.ui.logEntryText.returnPressed.connect(self.logEntry)
        self.ui.fileDisplayTabs.currentChanged.connect(self.tabChanged)
        self.win.sigClosed.connect(self.quit)
        self.ui.analysisWidget.sigDbChanged.connect(self.analysisDbChanged)
        
        #self.logBtn = LogButton('Log')
        self.win.setStatusBar(StatusBar())
        #self.win.statusBar().addPermanentWidget(self.logBtn)
        #self.win.statusBar().setFixedHeight(25)
        #self.win.statusBar().layout().setSpacing(0)
        
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
        if dh is None:
            self.ui.baseDirText.setText('')
        else:
            self.ui.baseDirText.setText(dh.name())
        self.ui.fileTreeWidget.setBaseDirHandle(dh)
        
    def loadLog(self, *args, **kwargs):
        pass

    def setLogDir(self):
        d = self.selectedFile()
        if not isinstance(d, DirHandle):
            d = d.parent()
        self.manager.setLogDir(d)
        
    def updateLogDir(self, d):
        self.ui.logDirText.setText(d.name(relativeTo=self.baseDir))
    
    def setCurrentClicked(self):
        #print "click"
        handle = self.selectedFile()
        if handle is None:
            #print "no selection"
            return
        if not handle.isDir():
            handle = handle.parent()
        #dh = self.manager.dirHandle(newDir)
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

    #def loadLog(self, dirHandle, widget, recursive=0):
        #widget.clear()
        #log = dirHandle.readLog(recursive)
        #for line in self.logRender(log):
            #widget.append(line)
            

    def showFileDialog(self):
        bd = self.manager.getBaseDir()
        if bd is not None:
            self.dialog.setDirectory(bd.name())
        self.dialog.show()

    def setBaseDir(self, dirName):
        if isinstance(dirName, list):
            if len(dirName) == 1:
                dirName = dirName[0]
            else:
                raise Exception("Caught. Please to be examined: %s" % str(dirName))
        #if dirName is None:
            #dirName = QtGui.QFileDialog.getExistingDirectory()
        #if type(dirName) is QtCore.QStringList:
        #    dirName = str(dirName[0])
            #raise Exception("Caught. Please to be examined.")
        #if type(dirName) is QtCore.QStringList:
            #dirName = str(dirName[0])
        #elif type(dirName) is QtCore.QString:
            #dirName = str(dirName)
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
        if not cdir.isManaged():
            cdir.createIndex()
        
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
            if spec.get('experimentalUnit', False):
                info['expUnit'] = True
            nd.setInfo(info)
            
            ## set display to info
            #self.showFileInfo(nd)
            
            #index = self.model.handleIndex(nd)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Clear)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Select)
            self.ui.fileTreeWidget.refresh(parent)  ## fileTreeWidget waits a while before updating; force it to refresh immediately.
            self.ui.fileTreeWidget.select(nd)
            ##self.ui.fileInfo.setCurrentFile(nd)

        logMsg("Created new folder: %s" %nd.name(relativeTo=self.baseDir), msgType='status', importance=7)   
        self.manager.setCurrentDir(nd)


    def fileSelectionChanged(self):
        #print "file selection changed"
        if self.selFile is not None:
            #QtCore.QObject.disconnect(self.selFile, QtCore.SIGNAL('changed'), self.selectedFileAltered)
            try:
                self.selFile.sigChanged.disconnect(self.selectedFileAltered)
            except TypeError:
                pass
        
        fh = self.selectedFile()
        self.manager.currentFile = fh  ## Make this really easy to pick up from an interactive prompt.
        self.loadFile(fh)
        self.selFile = fh
        if fh is not None:
            #QtCore.QObject.connect(self.selFile, QtCore.SIGNAL('changed'), self.selectedFileAltered)
            self.selFile.sigChanged.connect(self.selectedFileAltered)
        
    def loadFile(self, fh):
        #self.ui.selectedLogView.clear()
        if fh is None:
            self.ui.fileInfo.setCurrentFile(None)
            self.ui.dataViewWidget.setCurrentFile(None)
            self.ui.logWidget.selectedFileChanged(None)
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
            self.ui.logWidget.selectedFileChanged(fh)
            #if fh.isDir():
                #self.loadLog(fh, self.ui.selectedLogView, recursive=3)
        elif n == 2:
            self.ui.dataViewWidget.setCurrentFile(fh)
            

    def selectedFileAltered(self, name, change, args):
        if change in ['parent', 'renamed', 'moved'] and self.selFile is not None:
            #index = self.model.handleIndex(self.selFile)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Clear)
            #self.ui.fileTreeView.selectionModel().select(index, QtGui.QItemSelectionModel.Select)
            self.ui.fileTreeWidget.select(self.selFile)  ## re-select file if it has moved.
            self.ui.fileNameLabel.setText(self.selFile.name(relativeTo=self.baseDir))
        
        #self.fileSelectionChanged()
        
    #def logEntry(self):
        #text = str(self.ui.logEntryText.text())
        #cd = self.manager.getCurrentDir()
        #self.ui.logEntryText.setText('')
        #if text == '' or cd is None:
            #return
        #cd.logMsg(text, {'source': 'user'})
        
    #def updateLogView(self, *args):
        #msg = args[0]
        #self.ui.logView.append(self.logRender(msg))
        ##print "new log msg"
        
    #def logRender(self, log):
        #returnList = True
        #if type(log) is dict:
            #log = [log]
            #returnList = False
        #elif type(log) is not list:
            #raise Exception('logRender requires dict or list of dicts as argument')
            
        #lines = []
        #for msg in log:
            #t = time.strftime('%Y.%m.%d %H:%M:%S', time.localtime(msg['__timestamp__']))
            #style = 'color: #000; font-style: normal'
            #sourceStyles = {
                #'user': 'color: #008; font-style: italic'
            #}
            #if 'source' in msg and msg['source'] in sourceStyles:
                #style = sourceStyles[msg['source']]
            #parts = ["<span style='color: #888'>[%s]</span>" % t]
            #if 'subdir' in msg:
                #parts.append(msg['subdir'])
            #parts.append("<span style='%s'>%s</span>" % (style, msg['__message__']))
            #lines.append('&nbsp;&nbsp;'.join(parts))
        #if returnList:
            #return lines
        #else:
            #return lines[0]
            
    def quit(self):
        ## Silly: needed to prevent lockup on some systems.
        #print "      module quitting.."
        self.ui.fileTreeWidget.quit()
        self.ui.analysisWidget.quit()
        #sip.delete(self.dialog)
        #print "      deleted dialog, calling superclass quit.."
        Module.quit(self)
        #print "      module quit done"
        #print backtrace()
        
    def currentDatabase(self):
        return self.ui.analysisWidget.currentDatabase()
        
    def dataModel(self):
        return self.ui.analysisWidget.currentDataModel()
        
    def analysisDbChanged(self):
        self.sigAnalysisDbChanged.emit()
        
        