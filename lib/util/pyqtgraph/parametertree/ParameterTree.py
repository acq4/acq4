from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.TreeWidget import TreeWidget
import collections, os, weakref, re
#import functions as fn
        
            

class ParameterTree(TreeWidget):
    """Widget used to display or control data from a ParameterSet"""
    
    def __init__(self, parent=None):
        TreeWidget.__init__(self, parent)
        self.setAnimated(False)
        self.setColumnCount(2)
        self.setHeaderLabels(["Parameter", "Value"])
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.paramSet = None
        self.header().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.itemChanged.connect(self.itemChangedEvent)
        self.lastSel = None
        self.setRootIsDecorated(False)
        
    def setParameters(self, param, root=None, depth=0, showTop=True):
        item = param.makeTreeItem(depth=depth)
        if root is None:
            root = self.invisibleRootItem()
            ## Hide top-level item
            if not showTop:
                item.setSizeHint(0, QtCore.QSize(0,0))
                item.setSizeHint(1, QtCore.QSize(0,0))
                depth -= 1
        root.addChild(item)
        item.treeWidgetChanged()
            
        for ch in param:
            self.setParameters(ch, root=item, depth=depth+1)

    def contextMenuEvent(self, ev):
        item = self.currentItem()
        if hasattr(item, 'contextMenuEvent'):
            item.contextMenuEvent(ev)
            
    def itemChangedEvent(self, item, col):
        if hasattr(item, 'columnChangedEvent'):
            item.columnChangedEvent(col)
            
    def selectionChanged(self, *args):
        sel = self.selectedItems()
        if len(sel) != 1:
            sel = None
        if self.lastSel is not None:
            self.lastSel.selected(False)
        if sel is None:
            self.lastSel = None
            return
        self.lastSel = sel[0]
        if hasattr(sel[0], 'selected'):
            sel[0].selected(True)
        return TreeWidget.selectionChanged(self, *args)
        

