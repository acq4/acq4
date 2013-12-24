# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from MosaicTemplate import *
from acq4.Manager import getManager

class MosaicEditor(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.show()
        self.items = {}
        self.connect(self.ui.setRootBtn, QtCore.SIGNAL('clicked()'), self.setRootClicked)
        self.connect(self.ui.loadBtn, QtCore.SIGNAL('clicked()'), self.loadClicked)
        self.connect(self.ui.canvas, QtCore.SIGNAL('itemTransformChangeFinished'), self.itemMoved)
        
    def loadClicked(self):
        f = self.ui.fileTree.selectedFile()
        if f is None:
            return
            
        item = self.ui.canvas.addFile(f)
        self.items[item] = f
        
        
    def setRootClicked(self):
        m = getManager()
        f = m.currentFile
        self.ui.fileTree.setRoot(f)
        
    def itemMoved(self, canvas, item):
        """Save an item's transformation if the user has moved it. 
        This is saved in the 'userTransform' attribute; the original position data is not affected."""
        if item not in self.items:
            return
        fh = self.items[item]
        trans = item.saveTransform()
        fh.setInfo(userTransform=trans)