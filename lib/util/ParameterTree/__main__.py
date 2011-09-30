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
        
        self.addChild({'name': 'SubParam1', 'type': 'int', 'value': 7})
        self.addChild({'name': 'SubParam2', 'type': 'float', 'value': 1/7.})
        self.addChild({'name': 'SubParam3', 'type': 'int', 'value': 9})

        self.param('SubParam1').sigValueChanged.connect(self.param1Changed)
        self.param('SubParam2').sigValueChanged.connect(self.param2Changed)
        
    def param1Changed(self):
        self.param('SubParam2').sigValueChanged.disconnect(self.param2Changed)
        self['SubParam2'] = 1.0 / self['SubParam1']
        self.param('SubParam2').sigValueChanged.connect(self.param2Changed)

    def param2Changed(self):
        self.param('SubParam1').sigValueChanged.disconnect(self.param1Changed)
        self['SubParam1'] = 1.0 / self['SubParam2']
        self.param('SubParam1').sigValueChanged.connect(self.param1Changed)


## test add/remove

class ScalableGroupItem(ParameterItem):
    def __init__(self, param, depth):
        ParameterItem.__init__(self, param, depth)
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

class ScalableGroup(Parameter):
    itemClass = ScalableGroupItem
    
    def __init__(self, **opts):
        opts['type'] = 'group'
        Parameter.__init__(self, **opts)
    
    def addNew(self):
        self.addChild(name="ScalableParam %d" % (len(self.childs)+1), type="str", value="", removable=True)


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
    {'name': 'Param 6', 'type': 'color', 'value': "FF0", 'tip': "This is a checkbox"},
]

p = ParameterSet("params", params)



t = ParameterTree()
t.setParameters(p)
t.show()
t.resize(400,600)
    
