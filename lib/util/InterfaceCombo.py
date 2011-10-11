# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.Manager import getManager

### TODO: inherit from util/ComboBox instead.

class InterfaceCombo(QtGui.QComboBox):
    def __init__(self, parent=None):
        self.dir = getManager().interfaceDir
        QtGui.QComboBox.__init__(self, parent)
        #QtCore.QObject.connect(self.dir, QtCore.SIGNAL('interfaceListChanged'), self.updateList)
        self.dir.sigInterfaceListChanged.connect(self.updateList)
        if self.count() > 0:
            self.firstItem = str(self.itemText(0))
        else:
            self.firstItem = "Select.."
        
    def setTypes(self, types):
        self.types = types
        self.updateList()
        
    def updateList(self):
        ints = self.dir.listInterfaces(self.types)
        if self.currentIndex() == 0:
            current = None
        else:
            current = str(self.currentText())
        self.blockSignals(True)
        self.clear()
        self.addItem(self.firstItem)
        for n in ints:
            self.addItem(n)
        self.blockSignals(False)
            
            
    def getSelectedObj(self):
        if self.currentIndex() == 0:
            return None
        return self.dir.getInterface(str(self.currentText()))
