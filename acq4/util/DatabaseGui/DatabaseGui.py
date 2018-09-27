# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from . import DatabaseTemplate, QueryTemplate
import os

class DatabaseGui(Qt.QWidget):
    """Presents a very simple interface for selecting tables from an AnalysisDatabase."""
    
    sigTableChanged = Qt.Signal(str, str)  ## table purpose, table name
    #sigStoreToDB = Qt.Signal()
    
    def __init__(self, parent=None, dm=None, tables=None):  ## datamanager tells us which DB is currently loaded.
        """tables should be a dict like {'owner': 'default', ...}"""
        Qt.QWidget.__init__(self)
        self.dm = dm
        #self.ident = identity
        self.tables = {}
        self.db = None
        self.ui = DatabaseTemplate.Ui_Form()
        self.ui.setupUi(self)
        #self.ui.dbLabel.setText("[No DB Loaded]")
        self.tableWidgets = {}
        if dm is not None:
            self.setDataManager(dm)
        if tables is not None:
            self.setTables(tables)
        
    def getTableName(self, ident):
        return str(self.tableWidgets[ident][1].currentText())
        
    def setDataManager(self, dm):
        self.dm = dm
        self.dm.sigAnalysisDbChanged.connect(self.dbChanged)
        self.dbChanged()
        
    def setTables(self, tables):
        """
        Set the list of tables to request from the user.
        Format is {owner: defaultTableName, ...}
        """
        self.tables = tables
        self.generateTableLists()
        
    def getDb(self):
        return self.db
        
    def dbChanged(self):
        if self.dm is None:
            return
        self.db = self.dm.currentDatabase()
        if self.db is None:
            return
        self.ui.dbLabel.setText(os.path.split(self.db.file)[1])
        self.generateTableLists()
        
    def generateTableLists(self):
        for l, c in self.tableWidgets.values():
            self.ui.tableArea.layout().removeWidget(l)
            self.ui.tableArea.layout().removeWidget(c)
        self.tableWidgets = {}
        
        if self.db is None or self.tables is None:
            return
            
        for ident, default in self.tables.items():
            label = Qt.QLabel(ident)
            combo = Qt.QComboBox()
            combo.setEditable(True)
            tables = self.db.listTablesOwned(ident)
            if (default is not None) and (default not in tables):
                tables.insert(0, default)
            for t in tables:
                combo.addItem(t)
            combo.ident = ident
            row = len(self.tableWidgets)
            self.ui.tableArea.layout().addWidget(label, row, 0)
            self.ui.tableArea.layout().addWidget(combo, row, 1)
            self.tableWidgets[ident] = (label, combo)
            combo.currentIndexChanged.connect(self.tableChanged)
            
    def tableChanged(self, ind):
        combo = self.sender()
        self.sigTableChanged.emit(combo.ident, combo.currentText())
        
        
            
        
        
#class QueryGui(Qt.QWidget):
    #def __init__(self, dm):  ## datamanager tells us which DB is currently loaded.
        #Qt.QWidget.__init__(self)
        #self.ui = QueryTemplate.Ui_Form()
        #self.ui.setupUi(self)
        #self.dbChanged()
        #self.ui.queryBtn.clicked.connect(self.runQuery)
        #self.dm.sigAnalysisDbChanged.connect(self.dbChanged)

    #def runQuery(self):
        #try:
            #q = str(self.ui.queryText.text())
            #res = self.db(q)
            #self.ui.queryTable.setData(res)
            #self.ui.queryBtn.success("OK (%d rows)" % len(res))
        #except:
            #self.ui.queryBtn.failure("Error.")
            #raise

    #def dbChanged(self):
        #self.db = self.dm.currentDatabase()
