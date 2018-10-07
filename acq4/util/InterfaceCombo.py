# -*- coding: utf-8 -*-
from __future__ import print_function

import six

from acq4.util import Qt
from acq4.Manager import getManager
import acq4.pyqtgraph.parametertree as parametertree
import acq4.pyqtgraph.parametertree.parameterTypes as ptypes

### TODO: inherit from util/ComboBox instead.

class InterfaceCombo(Qt.QComboBox):
    """
    ComboBox that displays a list of objects registered with the ACQ4 interface directory. 

    This is used, for example, to allow the user to select from an up-to-date list of devices, modules, etc.
    """
    def __init__(self, parent=None, types=None):
        self.dir = getManager().interfaceDir
        self.interfaceMap = []
        self.preferred = None
        Qt.QComboBox.__init__(self, parent)
        #Qt.QObject.connect(self.dir, Qt.SIGNAL('interfaceListChanged'), self.updateList)
        self.dir.sigInterfaceListChanged.connect(self.updateList)
        
        if types is not None:
            self.setTypes(types)
        
    def setTypes(self, types):
        if isinstance(types, six.string_types):
            types = [types]
        self.types = types
        self.updateList()
        
    def updateList(self):        
        ints = self.dir.listInterfaces(self.types)
        self.interfaceMap = []
        objects = set()
        
        try:
            preferred = self.preferredValue()
            current = self.currentText()
        except RuntimeError:
            return # This happens when the combo has been deleted, but we are still receiving signals.

        try:
            self.blockSignals(True)
            self.clear()
            man = getManager()
            for typ,intList in ints.items():
                for name in intList:
                    obj = man.getInterface(typ, name)
                    if obj in objects:
                        continue
                    objects.add(obj)
                    self.interfaceMap.append((typ, name))
                    self.addItem(name)
                    if name == preferred:
                        self.setCurrentIndex(self.count()-1)
        finally:
            self.blockSignals(False)
        
        if self.currentText() != current:
            self.currentIndexChanged.emit(self.currentIndex())
            
            
            
    def preferredValue(self):
        ## return the value we would most like to have selected if available
        if self.preferred is not None:
            return self.preferred
        else:
            return self.currentText()
        
            
    def getSelectedObj(self):
        #if self.currentIndex() == 0:
            #return None
        if self.currentIndex() == -1:
            return None
        return self.dir.getInterface(*self.interfaceMap[self.currentIndex()])

    def currentText(self):
        return str(Qt.QComboBox.currentText(self))
        
    def setCurrentText(self, text):
        """Set the current item by name"""
        self.preferred = text
        index = self.findText(text)
        if index == -1:
            return
        self.setCurrentIndex(index)
        
    def setCurrentObject(self, obj):
        pass
        
    def widgetGroupInterface(self):
        return (self.currentIndexChanged, self.currentText, self.setCurrentText)
        
        
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
        if isinstance(ints, dict):
            interfaces = []
            for i in ints.values():
                interfaces.extend(i)
        else:
            interfaces = ints
        
        #print "set limits:", ints
        self.setLimits(tuple(interfaces))


parametertree.registerParameterType('interface', InterfaceParameter, override=True)