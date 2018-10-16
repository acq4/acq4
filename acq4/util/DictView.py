# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from collections import OrderedDict

import six


class DictView(Qt.QTreeWidget):
    def __init__(self, data, parent=None):
        Qt.QTreeWidget.__init__(self, parent)
        self.setData(data)
        self.setColumnCount(2)
        self.setHeaderLabels(['key', 'value'])
        self.setVerticalScrollMode(self.ScrollPerPixel)
        
    def setData(self, data):
        """data should be a dictionary."""
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
            inds = list(map(six.text_type, range(len(v))))
            v = OrderedDict(zip(inds, v))
        if isinstance(v, dict):
            #print "\nadd tree", k, v
            node = Qt.QTreeWidgetItem([name])
            for k in v:
                newNode = self.mkNode(k, v[k])
                node.addChild(newNode)
        else:
            #print "\nadd value", k, str(v)
            node = Qt.QTreeWidgetItem([six.text_type(name), six.text_type(v)])
        return node
        
    def close(self):
        self.clear()
        self.setParent(None)
        