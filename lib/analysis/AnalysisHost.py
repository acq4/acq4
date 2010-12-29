from PyQt4 import QtCore, QtGui

class AnalysisHost(QtGui.QMainWindow):
    """Window for hosting analysis widgets.
    Provides:
     - File / DB access for module
     - 
    
    
    """
    
    def __init__(self, dataManager=None):
        QtGui.QMainWindow.__init__(self)
        self.dm = dataManager
        self.show()
        
    def loadModule(self, mod):
        