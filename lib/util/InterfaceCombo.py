# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from Manager import getManager
        
def InterfaceCombo(QtGui.QComboBox):
    def __init__(self, parent=None):
        self.dir = getManager().interfaceDir
        QtGui.QComboBox.__init__(self, parent)
        QtCore.QObject.connect(self.dir, QtCore.SIGNAL('interfaceListChanged'), self.updateList)
        
    def setTypes(self, types):
        self.types = types
        self.updateList()
        
    def updateList(self):
        ints = self.dir.listInterfaces(self.types)
        self.clear()
        for n in ints:
            self.addItem(n)
            
    def getSelectedObj(self):
        return self.dir.getInterface(str(self.currentItemText()))
