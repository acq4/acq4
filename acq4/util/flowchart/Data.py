# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.pyqtgraph.flowchart.Node import Node
from acq4.util import Qt
from acq4.util.DirTreeWidget import *
import numpy as np
import acq4.util.metaarray as metaarray
from acq4.pyqtgraph.flowchart.library.common import *
from acq4.pyqtgraph import SRTTransform, Point
#from acq4.pyqtgraph import TreeWidget
import acq4.util.functions as functions

class SubtreeNode(Node):
    """Select files from within a directory. Input must be a DirHandle."""
    nodeName = "Subtree"
    def __init__(self, name):
        Node.__init__(self, name, terminals={'In': {'io': 'in'}})
        self.root = None
        self.files = set()
        self.lastInput = None
        self.fileList = DirTreeWidget(checkState=False, allowMove=False, allowRename=False)
        #Qt.QObject.connect(self.fileList, Qt.SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.itemChanged)
        self.fileList.itemChanged.connect(self.itemChanged)
        
    def process(self, In, display=True):
        #print "subtree process", In
        self.lastInput = In
        if display:
            if In is not self.root:
                #self.removeAll()
                self.fileList.blockSignals(True)
                self.fileList.setBaseDirHandle(In)
                self.root = In
                for f in self.files:
                    if In.exists(f):
                        fh = In[f]
                        item = self.fileList.item(fh)
                        item.setChecked(True)
                    else:
                        self.files.remove(f)
                
                self.fileList.blockSignals(False)
        out = {}
        for f in self.files:
            f2 = In[f]
            if f2.isFile():
                out[f] = f2.read()
            else:
                out[f] = f2
        return out
        
    def ctrlWidget(self):
        return self.fileList

    def removeAll(self):
        for f in self.files:
            self.removeTerminal(f)
        self.files = set()

    def itemChanged(self, item):
        fname = item.handle.name(relativeTo=self.root)
        if item.checkState(0) == Qt.Qt.Checked:
            if fname not in self.files:
                self.files.add(fname)
                self.addOutput(fname)
        else:
            if fname in self.files:
                self.files.remove(fname)
                self.removeTerminal(fname)
        self.update()

    def saveState(self):
        state = Node.saveState(self)
        state['selected'] = list(self.files)
        return state
        
    def restoreState(self, state):
        Node.restoreState(self, state)
        self.files = set(state.get('selected', []))
        for f in self.files:
            self.addOutput(f)

