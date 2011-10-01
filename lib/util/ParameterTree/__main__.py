## tests for ParameterTree

## make sure util is available
import sys,os
md = os.path.dirname(__file__)
sys.path.append(os.path.abspath(os.path.join(md, '..')))

from PyQt4 import QtCore, QtGui
import collections, user
app = QtGui.QApplication([])
import parameterTypes as pTypes
from ParameterTree import *


## test subclassing parameters
class ComplexParameter(Parameter):
    def __init__(self, **opts):
        opts['type'] = 'bool'
        opts['value'] = True
        Parameter.__init__(self, **opts)
        
        self.addChild({'name': 'A = 1/B', 'type': 'float', 'value': 7, 'suffix': 'Hz', 'siPrefix': True})
        self.addChild({'name': 'B = 1/A', 'type': 'float', 'value': 1/7., 'suffix': 's', 'siPrefix': True})
        self.a = self.param('A = 1/B')
        self.b = self.param('B = 1/A')
        self.a.sigValueChanged.connect(self.aChanged)
        self.b.sigValueChanged.connect(self.bChanged)
        
    def aChanged(self):
        try:
            self.b.sigValueChanged.disconnect(self.bChanged)
            self.b.setValue(1.0 / self.a.value())
        finally:
            self.b.sigValueChanged.connect(self.bChanged)

    def bChanged(self):
        try:
            self.a.sigValueChanged.disconnect(self.aChanged)
            self.a.setValue(1.0 / self.b.value())
        finally:
            self.a.sigValueChanged.connect(self.aChanged)


## test add/remove

class ScalableGroupItem(pTypes.GroupParameterItem):
    def __init__(self, param, depth):
        pTypes.GroupParameterItem.__init__(self, param, depth)
        self.addBtn = QtGui.QPushButton("Add new")
        self.addBtnItem = QtGui.QTreeWidgetItem([])
        ParameterItem.addChild(self, self.addBtnItem)
        self.addBtn.clicked.connect(self.addClicked)
        
    def updateWidgets(self):
        ParameterItem.updateWidgets(self)
        self.treeWidget().setItemWidget(self.addBtnItem, 0, self.addBtn)
        
    def addClicked(self):
        self.param.addNew()

    def addChild(self, child):  ## make sure added childs are actually inserted before add btn
        ParameterItem.insertChild(self, self.childCount()-1, child)

class ScalableGroup(pTypes.GroupParameter):
    itemClass = ScalableGroupItem
    
    def __init__(self, **opts):
        opts['type'] = 'group'
        pTypes.GroupParameter.__init__(self, **opts)
    
    def addNew(self):
        self.addChild(dict(name="ScalableParam %d" % (len(self.childs)+1), type="str", value="", removable=True))


params = [
    {'name': 'Group 0', 'type': 'group', 'params': [
        {'name': 'Param 1', 'type': 'int', 'value': 10},
        {'name': 'Param 2', 'type': 'float', 'value': 10},
    ]},
    {'name': 'Group 1', 'type': 'group', 'params': [
        {'name': 'Param 1.1', 'type': 'float', 'value': 1.2e-6, 'dec': True, 'siPrefix': True, 'suffix': 'V'},
        {'name': 'Param 1.2', 'type': 'float', 'value': 1.2e6, 'dec': True, 'siPrefix': True, 'suffix': 'Hz'},
        {'name': 'Group 1.3', 'type': 'group', 'params': [
            {'name': 'Param 1.3.1', 'type': 'int', 'value': 11, 'max': 15, 'min': -7, 'default': -6},
            {'name': 'Param 1.3.2', 'type': 'float', 'value': 1.2e6, 'dec': True, 'siPrefix': True, 'suffix': 'Hz', 'readonly': True},
        ]},
        {'name': 'Param 1.4', 'type': 'str', 'value': "hi"},
        {'name': 'Param 1.5', 'type': 'list', 'values': [1,2,3], 'value': 2},
        {'name': 'Param 1.6', 'type': 'list', 'values': {"one": 1, "two": 2, "three": 3}, 'value': 2},
        ComplexParameter(name='ComplexParam'),
        ScalableGroup(name="ScalableGroup", params=[
            {'name': 'ScalableParam 1', 'type': 'str', 'value': "hi"},
            {'name': 'ScalableParam 2', 'type': 'str', 'value': "hi"},
            
        ])
    ]},
    {'name': 'Param 5', 'type': 'bool', 'value': True, 'tip': "This is a checkbox"},
    {'name': 'Param 6', 'type': 'color', 'value': "FF0", 'tip': "This is a checkbox", 'renamable': True},
]

p = ParameterSet("params", params)
def change(*args):
    print "change:", args
p.sigStateChanged.connect(change)


t = ParameterTree()
t.setParameters(p)
t.show()
t.resize(400,600)
    
