from PyQt4 import QtGui, QtCore
import QueryTemplate


class DatabaseQueryWidget(QtGui.QWidget):
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
            return res
        except:
            self.ui.queryBtn.failure("Error.")
            raise

    def dbChanged(self):
        self.db = self.dm.currentDatabase()
