from lib.modules.ProtocolRunner.analysisModules import AnalysisModule
from PyQt4 import QtCore, QtGui
class UncagingModule(AnalysisModule):
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        
    def gui(self):
        return QtGui.QLabel('GUI')