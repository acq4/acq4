from PyQt4 import QtCore, QtGui
import modules
import DockArea

class AnalysisHost(QtGui.QMainWindow):
    """Window for hosting analysis widgets.
    Provides:
     - File / DB access for module
     - 
    
    
    """
    
    def __init__(self, dataManager=None, module=None):
        QtGui.QMainWindow.__init__(self)
        self.dm = dataManager
        self.mod = None
        self.dockArea = DockArea.DockArea()
        self.setCentralWidget(self.dockArea)
        if module is not None:
            self.loadModule(module)
        self.show()
        
    def loadModule(self, modName):
        if self.mod is not None:
            raise Exception("No fair loading extra modules in one host.")
        self.mod = modules.load(modName, self)
        
        el = self.mod.listElements()
        for e in el:
            w = self.mod.getElement(e)
            d = DockArea.Dock(name=e)
            d.addWidget(w)
            self.dockArea.addDock(d)
        
        