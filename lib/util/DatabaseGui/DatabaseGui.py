# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
import DatabaseTemplate, QueryTemplate
import os

class DatabaseGui(QtGui.QWidget):
    """Presents a very simple interface for interacting with a database.
    Allows the user to:
    - Run queries and display/select results
    - Select tables"""
    
    sigTableChanged = QtCore.Signal(str, str)  ## table purpose, table name
    #sigStoreToDB = QtCore.Signal()
    
    def __init__(self, dm, tables):  ## datamanager tells us which DB is currently loaded.
        """tables should be a dict like {'owner': 'default', ...}"""
        QtGui.QWidget.__init__(self)
        self.dm = dm
        #self.ident = identity
        self.tables = tables
        self.db = None
        self.ui = DatabaseTemplate.Ui_Form()
        self.ui.setupUi(self)
        #self.ui.dbLabel.setText("[No DB Loaded]")
        self.tableWidgets = {}
        self.dbChanged()
        
        self.dm.sigAnalysisDbChanged.connect(self.dbChanged)
        
    def getTableName(self, ident):
        return str(self.tableWidgets[ident][1].currentText())
        
    def getDb(self):
        return self.db
        
    def dbChanged(self):
        self.db = self.dm.currentDatabase()
        if self.db is None:
            return
        self.ui.dbLabel.setText(os.path.split(self.db.file)[1])
        self.generateTableLists()
        
    def generateTableLists(self):
        for l, c in self.tableWidgets.itervalues():
            self.ui.tableArea.layout().removeWidget(l)
            self.ui.tableArea.layout().removeWidget(c)
        self.tableWidgets = {}
            
        for ident, default in self.tables.iteritems():
            label = QtGui.QLabel(ident)
            combo = QtGui.QComboBox()
            combo.setEditable(True)
            tables = self.db.listTablesOwned(ident)
            if default not in tables:
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
        combo = QtCore.sender()
        self.sigTableChanged.emit(combo.ident, combo.currentText())
        
        
            
        
        
class QueryGui(QtGui.QWidget):
    def __init__(self, dm):  ## datamanager tells us which DB is currently loaded.
        QtGui.QWidget.__init__(self)
        self.ui = QueryTemplate.Ui_Form()
        self.ui.setupUi(self)
        self.dbChanged()
        self.ui.queryBtn.clicked.connect(self.runQuery)
        self.dm.sigAnalysisDbChanged.connect(self.dbChanged)

    def runQuery(self):
        try:
            q = str(self.ui.queryText.text())
            res = self.db(q)
            self.ui.queryTable.setData(res)
            self.ui.queryBtn.success("OK (%d rows)" % len(res))
        except:
            self.ui.queryBtn.failure("Error.")
            raise

    def dbChanged(self):
        self.db = self.dm.currentDatabase()
