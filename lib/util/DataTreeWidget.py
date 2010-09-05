# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from advancedTypes import OrderedDict

class DataTreeWidget(QtGui.QTreeWidget):
    def __init__(self, data, parent=None):
        QtGui.QTreeWidget.__init__(self, parent)
        self.setData(data)
        self.setColumnCount(3)
        self.setHeaderLabels(['key', 'type', 'value'])
        
    def setData(self, data):
        """data should be a dictionary."""
        self.clear()
        self.buildTree(data, self.invisibleRootItem())
        #node = self.mkNode('', data)
        #while node.childCount() > 0:
            #c = node.child(0)
            #node.removeChild(c)
            #self.invisibleRootItem().addChild(c)
        self.expandToDepth(3)
        self.resizeColumnToContents(0)
        
    def buildTree(self, data, parent, name=''):
        node = QtGui.QTreeWidgetItem([name, str(type(data)), ""])
        parent.addChild(node)
        
        if isinstance(data, dict):
            for k in data:
                self.buildTree(data[k], node, k)
        elif isinstance(data, list) or isinstance(data, tuple):
            for i in range(len(data)):
                self.buildTree(data[k], node, str(k))
        else:
            node.setText(2, str(data))
        
        
    #def mkNode(self, name, v):
        #if type(v) is list and len(v) > 0 and isinstance(v[0], dict):
            #inds = map(unicode, range(len(v)))
            #v = OrderedDict(zip(inds, v))
        #if isinstance(v, dict):
            ##print "\nadd tree", k, v
            #node = QtGui.QTreeWidgetItem([name])
            #for k in v:
                #newNode = self.mkNode(k, v[k])
                #node.addChild(newNode)
        #else:
            ##print "\nadd value", k, str(v)
            #node = QtGui.QTreeWidgetItem([unicode(name), unicode(v)])
        #return node
        
        
        