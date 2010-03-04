from PyQt4 import QtGui, QtCore
from advancedTypes import OrderedDict

class DictView(QtGui.QTreeWidget):
    def __init__(self, data, parent=None):
        QtGui.QTreeWidget.__init__(self, parent)
        self.setData(data)
        self.setColumnCount(2)
        self.setHeaderLabels(['key', 'value'])
        
    def setData(self, data):
        self.clear()
        node = self.mkNode('', data)
        while node.childCount() > 0:
            c = node.child(0)
            node.removeChild(c)
            self.invisibleRootItem().addChild(c)
        self.expandToDepth(3)
        self.resizeColumnToContents(0)
        
    def mkNode(self, name, v):
        if type(v) is list and len(v) > 0 and isinstance(v[0], dict):
            inds = map(str, range(len(v)))
            v = OrderedDict(zip(inds, v))
        if isinstance(v, dict):
            #print "\nadd tree", k, v
            node = QtGui.QTreeWidgetItem([name])
            for k in v:
                newNode = self.mkNode(k, v[k])
                node.addChild(newNode)
        else:
            #print "\nadd value", k, str(v)
            node = QtGui.QTreeWidgetItem([name, str(v)])
        return node
        
        
        