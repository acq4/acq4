# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from MosaicTemplate import *
from lib.Manager import getManager

class MosaicEditor(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.show()
        
        QtCore.QObject.connect(self.ui.setRootBtn, QtCore.SIGNAL('clicked()'), self.setRootClicked)
        QtCore.QObject.connect(self.ui.loadBtn, QtCore.SIGNAL('clicked()'), self.loadClicked)
        
        
    def loadClicked(self):
        f = self.ui.fileTree.selectedFile()
        if f is None:
            return
            
        
        
    def setRootClicked(self):
        m = getManager()
        f = m.currentFile
        self.ui.fileTree.setRoot(f)
        
