from __future__ import print_function
from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
#import acq4.analysis.modules.EventDetector as EventDetector
#import MapCtrlTemplate
import acq4.util.DatabaseGui as DatabaseGui
#from flowchart import *
#import flowchart.library.EventDetection as FCEventDetection
import os
from collections import OrderedDict
import acq4.util.debug as debug
import acq4.util.ColorMapper as ColorMapper
import acq4.pyqtgraph as pg
#import acq4.pyqtgraph.TreeWidget as TreeWidget


class DatabaseExplorer(AnalysisModule):
    
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
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
        
        