from PyQt4 import QtGui, QtCore

class DatabaseGui(QtGui.QWidget):
    """Presents a very simple interface for interacting with a database.
    Allows the user to:
    - Run queries and display/select results
    - Select tables"""
    
    sigTableChanged = QtCore.Signal(str, str)  ## table purpose, table name
    
    def __init__(self, dm, name, tables):
        """tables should be a dict like {'purpose': 'default', ...}"""
        QtGui.QWidget.__init__(self)
        self.dm = dm
        self.name = name
        self.tables = tables
        
        self.ui = template.Ui_Form()
        self.ui.setupUi(self)
        self.tableWidgets = []
        self.dbChanged()
        
        self.dm.sigAnalysisDatabaseChanged.connect(self.dbChanged)
        self.ui.queryBtn.clicked.connect(self.runQuery)
        
    def dbChanged(self):
        self.db = self.dm.currentDatabase()
        self.generateTableLists()
        
    def generateTableLists(self):
        for l, c in self.tableWidgets:
            self.tableArea.layout().removeWidget(l)
            self.tableArea.layout().removeWidget(c)
        self.tableWidgets = []
            
        for purpose, default in self.tables.iteritems():
            label = QtGui.QLabel(purpose)
            combo = QtGui.QComboBox()
            tables = self.db.listTablesUsed(name, purpose)
            if default not in tables:
                tables.insert(0, default)
            for t in tables:
                combo.addItem(t)
            combo.purpose = purpose
            row = len(self.tableWidgets)
            self.tableArea.layout().addWidget(label, row, 0)
            self.tableArea.layout().addWidget(combo, row, 1)
            self.tableWidgets.append(label, combo)
            combo.currentIndexChanged.connect(self.tableChanged)
            
    def tableChanged(self, ind):
        combo = QtCore.sender()
        self.sigTableChanged.emit(purpose, combo.currentText())
        
        
        