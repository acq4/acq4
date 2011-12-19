# -*- coding: utf-8 -*-
#import lib.util.PySideImporter  ## Use PySide instead of PyQt

from PyQt4 import QtCore, QtGui
import database
from AnalysisTemplate import *
import lib.Manager
import lib.analysis.modules as analysis
import lib.analysis.AnalysisHost as AnalysisHost
import lib.analysis.dataModels as models
#QtCore.QString = str
#def noop(x):
#   return x
#QtCore.QVariant = noop
from pyqtgraph import FileDialog

class FileAnalysisView(QtGui.QWidget):
    
    sigDbChanged = QtCore.Signal()
    
    def __init__(self, parent, mod):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.man = lib.Manager.getManager()
        #print self.window().objectName()
        #self.dm = self.window().dm  ## get module from window
        self.mod = mod
        self.dbFile = None
        self.db = None
        self.mods = []
        self.currentModel = None
        
        self.populateModuleList()
        self.populateModelList()
        
        #self.connect(self.ui.openDbBtn, QtCore.SIGNAL('clicked()'), self.openDbClicked)
        self.ui.openDbBtn.clicked.connect(self.openDbClicked)
        #self.connect(self.ui.createDbBtn, QtCore.SIGNAL('clicked()'), self.createDbClicked)
        self.ui.createDbBtn.clicked.connect(self.createDbClicked)
        #self.connect(self.ui.addFileBtn, QtCore.SIGNAL('clicked()'), self.addFileClicked)
        #self.connect(self.ui.analysisCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.loadModule)
        self.ui.analysisCombo.currentIndexChanged.connect(self.loadModule)
        self.ui.refreshDbBtn.clicked.connect(self.refreshDb)
        self.ui.dataModelCombo.currentIndexChanged.connect(self.loadModel)
        

    def openDbClicked(self):
        self.fileDialog = FileDialog(self, "Select Database File", self.man.getBaseDir().name(), "SQLite Database (*.sqlite *.sql);;All Files (*.*)")
        #self.fileDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        self.fileDialog.show()
        self.fileDialog.fileSelected.connect(self.openDb)
            
    def openDb(self, fileName):
        #fn = str(QtGui.QFileDialog.getOpenFileName(self, "Select Database File", self.man.getBaseDir().name(), "SQLite Database (*.sqlite)"))
        fileName = str(fileName)
        if fileName == '':
            return
        
        #if not fileName[-7:] == '.sqlite' and '.' not in fileName:
        #    fileName =+ '.sqlite'
            
        self.ui.databaseText.setText(fileName)
        self.dbFile = fileName
        self.db = database.AnalysisDatabase(self.dbFile)
        self.sigDbChanged.emit()
        
    def createDbClicked(self):
        self.fileDialog = FileDialog(self, "Create Database File", self.man.getBaseDir().name(), "SQLite Database (*.sqlite *.sql);;All Files (*.*)")
        #self.fileDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        self.fileDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave) 
        self.fileDialog.setOption(QtGui.QFileDialog.DontConfirmOverwrite)
        self.fileDialog.show()
        self.fileDialog.fileSelected.connect(self.createDb)
        
    def createDb(self, fileName):
        #fn = str(QtGui.QFileDialog.getSaveFileName(self, "Create Database File", self.man.getBaseDir().name(), "SQLite Database (*.sqlite)", None, QtGui.QFileDialog.DontConfirmOverwrite))
        fileName = str(fileName)
        if fileName is '':
            return
        self.ui.databaseText.setText(fileName)
        self.dbFile = fileName
        self.db = database.AnalysisDatabase(self.dbFile, self.man.getBaseDir())
        self.sigDbChanged.emit()
        
    def refreshDb(self):
        if self.db is None:
            return
        self.db._readTableList()
        
    def addFileClicked(self):
        cf = self.mod.selectedFile()
        self.db.addDir(cf)
        
    def populateModuleList(self):
        for m in analysis.listModules():
            self.ui.analysisCombo.addItem(m)
    
    def loadModule(self):
        if self.ui.analysisCombo.currentIndex() == 0:
            return
        modName = str(self.ui.analysisCombo.currentText())
        self.ui.analysisCombo.setCurrentIndex(0)
        mod = AnalysisHost.AnalysisHost(dataManager=self.mod, dataModel=self.currentModel, module=modName)
        self.mods.append(mod)
        self.man.modules[modName] = mod

    def populateModelList(self):
        self.ui.dataModelCombo.clear()
        self.ui.dataModelCombo.addItem('Load...')
        mods = models.listModels()
        for m in mods:
            self.ui.dataModelCombo.addItem(m)
        if len(mods) == 1:
            self.ui.dataModelCombo.setCurrentIndex(1)
            self.loadModel()
    
    def loadModel(self):
        if self.ui.dataModelCombo.currentIndex() == 0:
            return
        modName = str(self.ui.dataModelCombo.currentText())
        self.currentModel = models.loadModel(modName)
        lib.Manager.getManager().dataModel = self.currentModel  ## make model globally available
    
    
    def currentDatabase(self):
        return self.db


