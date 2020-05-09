# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.util import Qt
import os
import acq4.util.database as database
import acq4.Manager
import acq4.analysis.modules as analysis
import acq4.analysis.AnalysisHost as AnalysisHost
import acq4.analysis.dataModels as models
from pyqtgraph import FileDialog
from six.moves import range

Ui_Form = Qt.importTemplate('.AnalysisTemplate')


class FileAnalysisView(Qt.QWidget):
    
    sigDbChanged = Qt.Signal()
    
    def __init__(self, parent, mod):
        Qt.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.man = acq4.Manager.getManager()
        self.mod = mod
        self.dbFile = None
        self.db = None
        self.mods = []
        self.currentModel = None
        
        self.populateModuleList()
        self.populateModelList()
        
        stateFile = os.path.join('modules', self.mod.name + '_db_file_list')
        files = self.mod.manager.readConfigFile(stateFile).get('db_file_list', [])
        self.ui.databaseCombo.addItem('')
        for f in files:
            self.ui.databaseCombo.addItem(f)
        
        
        self.ui.openDbBtn.clicked.connect(self.openDbClicked)
        self.ui.createDbBtn.clicked.connect(self.createDbClicked)
        self.ui.loadModuleBtn.clicked.connect(self.loadModule)
        self.ui.refreshDbBtn.clicked.connect(self.refreshDb)
        self.ui.dataModelCombo.currentIndexChanged.connect(self.loadModel)
        self.ui.analysisModuleList.currentItemChanged.connect(self.showModuleDescription)
        self.ui.analysisModuleList.itemDoubleClicked.connect(self.loadModule)
        self.ui.databaseCombo.currentIndexChanged.connect(self.dbComboChanged)
        

    def openDbClicked(self):
        bd = self.man.getBaseDir()
        if bd is None:
            bd = ""
        else:
            bd = bd.name()
        self.fileDialog = FileDialog(self, "Select Database File", bd, "SQLite Database (*.sqlite *.sql);;All Files (*.*)")
        #self.fileDialog.setFileMode(Qt.QFileDialog.AnyFile)
        self.fileDialog.show()
        self.fileDialog.fileSelected.connect(self.openDb)
            
    def openDb(self, fileName):
        #fn = str(Qt.QFileDialog.getOpenFileName(self, "Select Database File", self.man.getBaseDir().name(), "SQLite Database (*.sqlite)"))
        fileName = str(fileName)
        if fileName == '':
            return
        
        #if not fileName[-7:] == '.sqlite' and '.' not in fileName:
        #    fileName =+ '.sqlite'
        self.ui.databaseCombo.blockSignals(True)
        try:
            ## put fileName at the top of the list, write to disk
            files = [self.ui.databaseCombo.itemText(i) for i in range(self.ui.databaseCombo.count())]
            files.remove('')
            if fileName in files:
                files.remove(fileName)
            files = [fileName] + files
            self.ui.databaseCombo.clear()
            self.ui.databaseCombo.addItem('')
            for f in files:
                self.ui.databaseCombo.addItem(f)
            stateFile = os.path.join('modules', self.mod.name + '_db_file_list')
            self.mod.manager.writeConfigFile({'db_file_list': files}, stateFile)
            self.ui.databaseCombo.setCurrentIndex(1)
        finally:
            self.ui.databaseCombo.blockSignals(False)
            
        
        self.dbFile = fileName
        self.db = database.AnalysisDatabase(self.dbFile, dataModel=self.currentModel)
        self.sigDbChanged.emit()
        
    def dbComboChanged(self):
        fn = self.ui.databaseCombo.currentText()
        if fn == '':
            return
        if not os.path.exists(fn):
            raise Exception("Database file does not exist: %s" % fn)
        self.openDb(fn)
        
    def quit(self):
        if self.db is not None:
            self.db.close()
        
    def createDbClicked(self):
        bd = self.man.getBaseDir()
        if bd is None:
            raise Exception("Must select a base directory before creating database.")
        self.fileDialog = FileDialog(self, "Create Database File", bd.name(), "SQLite Database (*.sqlite *.sql);;All Files (*.*)")
        #self.fileDialog.setFileMode(Qt.QFileDialog.AnyFile)
        self.fileDialog.setAcceptMode(Qt.QFileDialog.AcceptSave) 
        self.fileDialog.setOption(Qt.QFileDialog.DontConfirmOverwrite)
        self.fileDialog.show()
        self.fileDialog.fileSelected.connect(self.createDb)
        
    def createDb(self, fileName):
        #fn = str(Qt.QFileDialog.getSaveFileName(self, "Create Database File", self.man.getBaseDir().name(), "SQLite Database (*.sqlite)", None, Qt.QFileDialog.DontConfirmOverwrite))
        fileName = str(fileName)
        if fileName == '':
            return
            
        self.dbFile = fileName
        self.db = database.AnalysisDatabase(self.dbFile, dataModel=self.currentModel, baseDir=self.man.getBaseDir())
        self.ui.databaseCombo.blockSignals(True)
        try:
            self.ui.databaseCombo.addItem(fileName)
            self.ui.databaseCombo.setCurrentIndex(self.ui.databaseCombo.count()-1)
        finally:
            self.ui.databaseCombo.blockSignals(False)
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
            self.ui.analysisModuleList.addItem(m)
    
    def loadModule(self):
        mod = self.ui.analysisModuleList.currentItem()
        if mod is None:
            return
        modName = str(mod.text())
        #if self.ui.analysisCombo.currentIndex() == 0:
            #return
        #modName = str(self.ui.analysisCombo.currentText())
        #self.ui.analysisCombo.setCurrentIndex(0)
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
        acq4.Manager.getManager().dataModel = self.currentModel  ## make model globally available
        if self.db is not None:
            self.db.setDataModel(self.currentModel)
    
    
    def currentDatabase(self):
        return self.db
        
    def currentDataModel(self):
        return self.currentModel

    def showModuleDescription(self):
        mod = self.ui.analysisModuleList.currentItem()
        if mod is None:
            return
        modName = str(mod.text())
        cls = analysis.getModuleClass(modName)
        doc = cls.__doc__
        self.ui.modDescriptionText.setPlainText(doc)
