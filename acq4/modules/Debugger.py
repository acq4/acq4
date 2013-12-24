from acq4.modules.Module import Module
from PyQt4 import QtGui, QtCore
from acq4.pyqtgraph import DataTreeWidget

class Debugger(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        self.man = manager
        self.win = QtGui.QMainWindow()
        self.cw = DataTreeWidget()
        self.win.setCentralWidget(self.cw)
        self.win.show()
        self.man.sigTaskCreated.connect(self.showTask)
        
    def showTask(self, cmd, task):
        self.cw.setData(cmd)
        
        
    


