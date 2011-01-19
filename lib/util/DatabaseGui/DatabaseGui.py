# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
import DatabaseTemplate
import os

class DatabaseGui(QtGui.QWidget):
    """Presents a very simple interface for interacting with a database.
    Allows the user to:
    - Run queries and display/select results
    - Select tables"""
    
    sigTableChanged = QtCore.Signal(str, str)  ## table purpose, table name
    
    def __init__(self, dm, tables):
        """tables should be a dict like {'owner': 'default', ...}"""
        QtGui.QWidget.__init__(self)
        self.dm = dm
        #self.ident = identity
        self.tables = tables
        self.db = None
        self.ui = DatabaseTemplate.Ui_Form()
        self.ui.setupUi(self)
        self.ui.dbLabel.setText("[No DB Loaded]")
        self.tableWidgets = {}
        self.dbChanged()
        
        self.dm.sigAnalysisDbChanged.connect(self.dbChanged)
        self.ui.queryBtn.clicked.connect(self.runQuery)
        
    def dbChanged(self):
        self.db = self.dm.currentDatabase()
        if self.db is None:
            return
        self.ui.dbLabel.setText(os.path.split(self.db.file)[1])
        self.generateTableLists()
        
    def generateTableLists(self):
        for l, c in self.tableWidgets.itervalues():
            self.tableArea.layout().removeWidget(l)
            self.tableArea.layout().removeWidget(c)
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
        
    def runQuery(self):
        q = str(self.ui.queryText.text())
        res = self.db._queryToDict(self.db(q))
        self.ui.queryTable.setData(res)

    def getTableName(self, ident):
        return self.tableWidgets[ident][1].currentText()
        
    def getDb(self):
        return self.db