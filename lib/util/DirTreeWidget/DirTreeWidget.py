# -*- coding: utf-8 -*-
from DirTreeTemplate import Ui_Form
from lib.util.DirTreeModel import *

class DirTreeWidget(QtGui.QWidget):
    def __init__(self, baseDir, *args):
        QtGui.QWidget.__init__(self, *args)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.baseDir = baseDir
        
        self.fileTree = DirTreeModel(baseDir)
        self.ui.fileTree.setModel(self.fileTree)
        self.deleteState = 0


        QtCore.QObject.connect(self.ui.newBtn, QtCore.SIGNAL('clicked()'), self.newClicked)
        QtCore.QObject.connect(self.ui.newDirBtn, QtCore.SIGNAL('clicked()'), self.newDirClicked)
        QtCore.QObject.connect(self.ui.saveBtn, QtCore.SIGNAL('clicked()'), self.saveClicked)
        QtCore.QObject.connect(self.ui.loadBtn, QtCore.SIGNAL('clicked()'), self.loadClicked)
        QtCore.QObject.connect(self.ui.saveAsBtn, QtCore.SIGNAL('clicked()'), self.saveAsClicked)
        QtCore.QObject.connect(self.ui.deleteBtn, QtCore.SIGNAL('clicked()'), self.deleteClicked)


    def newClicked(self):
        if self.new():
            self.ui.currentLabel.setText('[ new ]')
            self.ui.saveBtn.setEnabled(False)
    
    def new(self):
        raise Exception("Function must be reimplemented in subclass.")
    
    def saveClicked(self):
        self.save()
        
    def save(self, fileName=None):
        raise Exception("Function must be reimplemented in subclass.")
    
    def loadClicked(self):
        if index is None:
            sel = list(self.ui.fileTree.selectedIndexes())
            if len(sel) == 1:
                index = sel[0]
            else:
                raise Exception("Can not load--%d items selected" % len(sel))
            
        fn = self.fileTree.getFileName(index)
        
        if self.load(fn):
            pn = fn.replace(self.fileTree.baseDir, '')
            self.ui.currentLabel.setText(pn)
            self.ui.saveBtn.setEnabled(True)

    def load(self):
        raise Exception("Function must be reimplemented in subclass.")
    
    def saveAsClicked(self):
        ## Decide on new file name
        baseFile = self.suggestNewFilename()
            
        c = 2
        newFile = None
        while True:
            newFile = baseFile + '_%02d' % c
            if not os.path.exists(newFile):
                break
            c += 1
            
        ## write
        if not self.save(newFile):
            return
        
        
        ## Start editing new file name
        index = self.fileTree.findIndex(newFile)
        #self.ui.fileTree.update(index)
        self.ui.fileTree.scrollTo(index)
        self.ui.fileTree.edit(index)
        
        pn = newFile.replace(self.fileTree.baseDir, '')
        self.ui.currentLabel.setText(pn)
        self.ui.saveBtn.setEnabled(True)

    def suggestNewFileName(self):
        """Suggest a file name to use when saveAs is clicked. saveAsClicked will 
        automatically add a numerical suffix if the suggested name exists already."""
        if self.currentFile is not None:
            return self.currentFile
        else:
            return os.path.join(self.baseDir, 'protocol')
        

    def deleteClicked(self):
        ## Delete button must be clicked twice.
        if self.deleteState == 0:
            self.ui.deleteBtn.setText('Really?')
            self.deleteState = 1
        elif self.deleteState == 1:
            try:
                fn = self.selectedFileName()
                os.remove(fn)
                self.protocolList.clearCache()
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
        self.ui.deleteProtocolBtn.setText('Delete')
        pass
    
    def newDirClicked(self):
        pass
        
    