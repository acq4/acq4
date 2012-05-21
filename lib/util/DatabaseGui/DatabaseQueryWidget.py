from PyQt4 import QtGui, QtCore
import QueryTemplate


class DatabaseQueryWidget(QtGui.QWidget):
    
    sigTableChanged = QtCore.Signal()
    
    def __init__(self, dm):  ## datamanager tells us which DB is currently loaded.
        QtGui.QWidget.__init__(self)
        self.dm = dm
        self.ui = QueryTemplate.Ui_Form()
        self.ui.setupUi(self)
        self._table = None ## for storing results of queries
        self.dbChanged()
        self.ui.queryBtn.clicked.connect(self.runQuery)
        self.dm.sigAnalysisDbChanged.connect(self.dbChanged)

    def runQuery(self):
        try:
            q = str(self.ui.queryText.text())
            res = self.db(q, toArray=True)
            self.ui.queryTable.setData(res)
            if res is not None:
                self.ui.queryBtn.success("OK (%d rows)" % len(res))
            else:
                self.ui.queryBtn.success("OK")
            self._table = res
            self.sigTableChanged.emit()
            return res
        except:
            self.ui.queryBtn.failure("Error.")
            raise

    def dbChanged(self):
        self.db = self.dm.currentDatabase()

    def table(self):
        return self._table