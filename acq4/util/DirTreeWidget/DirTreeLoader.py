# -*- coding: utf-8 -*-
from __future__ import print_function

import six

from .DirTreeTemplate import Ui_Form
from acq4.util import Qt
from acq4.util.debug import *
import acq4.util.DataManager as DataManager

class DirTreeLoader(Qt.QWidget):
    
    sigCurrentFileChanged = Qt.Signal(object, object, object)
    
    def __init__(self, baseDir, sortMode='alpha', create=False, *args):
        Qt.QWidget.__init__(self, *args)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        if isinstance(baseDir, six.string_types):
            baseDir = DataManager.getDirHandle(baseDir, create=create)
        self.baseDir = baseDir
        self.currentFile = None
        
        self.ui.fileTree.setSortMode(sortMode)
        self.ui.fileTree.setBaseDirHandle(baseDir)
        
        self.deleteState = 0

        self.ui.deleteBtn.focusOutEvent = self.delBtnLostFocus

        self.ui.newBtn.clicked.connect(self.newClicked)
        self.ui.newDirBtn.clicked.connect(self.newDirClicked)
        self.ui.saveBtn.clicked.connect(self.saveClicked)
        self.ui.loadBtn.clicked.connect(self.loadClicked)
        self.ui.saveAsBtn.clicked.connect(self.saveAsClicked)
        self.ui.deleteBtn.clicked.connect(self.deleteClicked)
        self.ui.fileTree.itemDoubleClicked.connect(self.loadClicked)


    def selectedFile(self):
        return self.ui.fileTree.selectedFile()

    def newClicked(self):
        if self.new():
            self.setCurrentFile(None)
    
    def new(self):
        raise Exception("Function must be reimplemented in subclass.")
    
    def saveClicked(self):
        self.save(self.currentFile)
        
    def save(self, fileHandle):
        raise Exception("Function must be reimplemented in subclass.")
    
    def loadClicked(self, item=None, column=0):
        if item == None or isinstance(item, bool):
            fh = self.ui.fileTree.selectedFile()
        else:
            fh = self.ui.fileTree.handle(item)
            
        if self.load(fh):
            fn = fh.name(relativeTo=self.baseDir)
            self.setCurrentFile(fh)

    def load(self, handle):
        raise Exception("Function must be reimplemented in subclass.")
    
    def saveAsClicked(self):
        ## Decide on new file name
        fileName = self.suggestNewFilename(self.currentFile)
        baseDir = self.selectedDir()
        
        fh = baseDir.createFile(fileName, autoIncrement=True)
            
        ## write
        if not self.save(fh):
            fh.delete()
            return
        
        
        ## Start editing new file name
        self.ui.fileTree.flushSignals()
        self.ui.fileTree.editItem(fh)
        
        self.setCurrentFile(fh)
        #self.ui.currentLabel.setText(fh.name(relativeTo=self.baseDir))
        #self.ui.saveBtn.setEnabled(True)
        #self.currentFile = fh

    def suggestNewFilename(self, fh):
        """Suggest a file name to use when saveAs is clicked. saveAsClicked will 
        automatically add a numerical suffix if the suggested name exists already."""
        if fh is None:
            return "NewFile"
        else:
            return fh.shortName()

    def deleteClicked(self):
        ## Delete button must be clicked twice.
        if self.deleteState == 0:
            self.ui.deleteBtn.setText('Really?')
            self.deleteState = 1
        elif self.deleteState == 1:
            try:
                self.selectedFile().delete()
            except:
                printExc('Error while deleting protocol file:')
                return
            finally:
                self.resetDeleteState()
                
    def selectedFileName(self):
        """Return the file name of the selected item"""
        sel = list(self.ui.fileTree.selectedIndexes())
        if len(sel) == 1:
            index = sel[0]
        else:
            raise Exception("Can not load--%d items selected" % len(sel))
        return self.protocolList.getFileName(index)
    
    def resetDeleteState(self):
        self.deleteState = 0
        self.ui.deleteBtn.setText('Delete')

    def selectedDir(self):
        """Return the directory of the selected file"""
        fh = self.selectedFile()
        if fh is None:
            dh = self.baseDir
        else:
            if fh.isDir():
                dh = fh
            else:
                dh = fh.parent()
        return dh
        
    def newDirClicked(self):
        dh = self.selectedDir()
        
        ndh = dh.mkdir("NewDirectory", autoIncrement=True)
        self.ui.fileTree.flushSignals()   ## Item may take time to appear in the tree..
        self.ui.fileTree.editItem(ndh) 
        
    def delBtnLostFocus(self, ev):
        self.resetDeleteState()
        
    def setCurrentFile(self, handle):
        if self.currentFile is not None:
            #Qt.QObject.disconnect(self.currentFile, Qt.SIGNAL('changed'), self.currentFileChanged)
            try:
                self.currentFile.sigChanged.disconnect(self.currentFileChanged)
            except TypeError:
                pass
            
        if handle is None:
            self.ui.currentLabel.setText("")
            self.ui.saveBtn.setEnabled(False)
        else:
            self.ui.currentLabel.setText(handle.name(relativeTo=self.baseDir))
            self.ui.saveBtn.setEnabled(True)
            #Qt.QObject.connect(handle, Qt.SIGNAL('changed'), self.currentFileChanged)
            handle.sigChanged.connect(self.currentFileChanged)
            
        self.currentFile = handle
            
        
    def currentFileChanged(self, handle, change, args):
        if change == 'deleted':
            self.ui.currentLabel.setText("[deleted]")
        else:
            self.ui.currentLabel.setText(self.currentFile.name(relativeTo=self.baseDir))
        self.sigCurrentFileChanged.emit(handle, change, args)