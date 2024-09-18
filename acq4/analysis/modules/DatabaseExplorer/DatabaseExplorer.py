from collections import OrderedDict

import acq4.util.DatabaseGui as DatabaseGui
from acq4.util import Qt
from acq4.util.AnalysisModule import AnalysisModule


class DatabaseExplorer(AnalysisModule):
    
    def __init__(self, host):
        super().__init__(host)
        
        self.dbIdentity = 'Explorer'
        
        self.dbCtrl = DBCtrl(host, self.dbIdentity)
        self.ctrl = PlotCtrl(host, self.dbIdentity)
        
        self._elements = OrderedDict([
            ('Database', {'type': 'ctrl', 'object':self.dbCtrl, 'size': (200, 300), 'host': self}),
            ('Scatter Plot', {'type': 'plot', 'pos':('right',), 'size': (800, 600)}),
            ('Plot Opts', {'type': 'ctrl', 'object': self.ctrl, 'pos':('bottom', 'Database'), 'size':(200,300)})
            ])


class DBCtrl(Qt.QWidget):
    
    def __init__(self, host, identity):
        Qt.QWidget.__init__(self)
        self.host = host
        self.dm = host.dataManager()
        self.db = self.dm.currentDatabase()
        
        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)
        self.dbgui = DatabaseGui.DatabaseGui(dm=self.dm, tables={})

        self.layout.addWidget(self.dbgui)
        #self.layout.addWidget(self.storeBtn)
        for name in ['getTableName', 'getDb']:
            setattr(self, name, getattr(self.dbgui, name))


class PlotCtrl(Qt.QWidget):
    
    def __init__(self, host, identity):
        Qt.QWidget.__init__(self)
        self.host = host
        self.dm = host.dataManager()
