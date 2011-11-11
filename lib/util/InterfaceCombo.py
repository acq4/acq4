# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.Manager import getManager
import pyqtgraph.parametertree as parametertree
import pyqtgraph.parametertree.parameterTypes as ptypes

### TODO: inherit from util/ComboBox instead.

class InterfaceCombo(QtGui.QComboBox):
    def __init__(self, types=None, parent=None):
        self.dir = getManager().interfaceDir
        QtGui.QComboBox.__init__(self, parent)
        #QtCore.QObject.connect(self.dir, QtCore.SIGNAL('interfaceListChanged'), self.updateList)
        self.dir.sigInterfaceListChanged.connect(self.updateList)
        if self.count() > 0:
            self.firstItem = str(self.itemText(0))
        else:
            self.firstItem = "Select.."
            
        if types is not None:
            self.setTypes(types)
        
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


#class InterfaceParameterItem(ptypes.ListParameterItem):
    #def makeWidget(self):
        #w = InterfaceCombo(types=self.param.opts['interfaceTypes'])
        #w.setMaximumHeight(20)  ## set to match height of spin box and line edit
        #w.sigChanged = w.currentIndexChanged
        #w.value = self.value
        #w.setValue = self.setValue
        #self.widget = w
        #return self.widget
        


class InterfaceParameter(ptypes.ListParameter):
    type = 'interface'
    itemClass = ptypes.ListParameterItem    
    
    def __init__(self, **args):
        ptypes.ListParameter.__init__(self, **args)
        self.dir = getManager().interfaceDir
        self.dir.sigInterfaceListChanged.connect(self.updateList)
        self.updateList()

    def setOpts(self, **args):
        ptypes.ListParameter.setOpts(self, **args)
        if 'interfaceTypes' in args:
            self.updateList()

    def updateList(self):
        ints = self.dir.listInterfaces(self.opts['interfaceTypes'])
        #print "set limits:", ints
        self.setLimits(ints)


parametertree.registerParameterType('interface', InterfaceParameter, override=True)