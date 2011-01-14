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
        
    def dataManager(self):
        return self.dm
        
    def loadModule(self, modName):
        if self.mod is not None:
            raise Exception("No fair loading extra modules in one host.")
        self.mod = modules.load(modName, self)
        
        elems = self.mod.listElements()
        for name, el in elems.iteritems():
            w = self.mod.getElement(name)
            d = DockArea.Dock(name=name, size=el.size())
            if w is not None:
                d.addWidget(w)
            pos = el.pos()
            if pos is None:
                pos = ()
            #print d, pos
            self.dockArea.addDock(d, *pos)
        
        self.setWindowTitle(modName)
        