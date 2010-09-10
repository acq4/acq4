# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from weakref import *

class TreeWidget(QtGui.QTreeWidget):
    """Extends QTreeWidget to allow internal drag/drop with widgets in the tree.
    Also maintains the expanded state of subtrees as they are moved.
    This class demonstrates the absurd lengths one must go to to make drag/drop work."""
    def __init__(self, parent=None):
        QtGui.QTreeWidget.__init__(self, parent)
        #self.itemWidgets = WeakKeyDictionary()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setEditTriggers(QtGui.QAbstractItemView.EditKeyPressed|QtGui.QAbstractItemView.SelectedClicked)

    def setItemWidget(self, item, col, wid):
        w = QtGui.QWidget()  ## foster parent / surrogate child widget
        QtGui.QTreeWidget.setItemWidget(self, item, col, w)
        l = QtGui.QVBoxLayout()
        l.setContentsMargins(0,0,0,0)
        w.setLayout(l)
        w.setSizePolicy(wid.sizePolicy())
        w.setMinimumHeight(wid.minimumHeight())
        w.setMinimumWidth(wid.minimumWidth())
        l.addWidget(wid)
        w.realChild = wid

    def itemWidget(self, item, col):
        w = QtGui.QTreeWidget.itemWidget(self, item, col)
        if w is not None:
            w = w.realChild
        return w

    def dropMimeData(self, parent, index, data, action):
        item = self.currentItem()
        p = parent
        while True:
            if p is None:
                break
            if p == item:
                raise Exception("Can not move item into itself.")
            p = p.parent()
        
        if not self.itemMoving(item, parent, index):
            return False
        
        currentParent = item.parent()
        if currentParent is None:
            currentParent = self.invisibleRootItem()
        if parent is None:
            parent = self.invisibleRootItem()
            
        if currentParent == parent and index > parent.indexOfChild(item):
            index -= 1
            
        self.prepareMove(item)
            
        currentParent.removeChild(item)
        parent.insertChild(index, item)  ## index will not be correct
        self.setCurrentItem(item)
        
        self.recoverMove(item)
        self.emit(QtCore.SIGNAL('itemMoved'), item, parent, index)
        return True

    def itemMoving(self, item, parent, index):
        """Called when item has been dropped elsewhere in the tree.
        Return True to accept the move, False to reject."""
        return True
        
    def prepareMove(self, item):
        item.__widgets = []
        item.__expanded = item.isExpanded()
        for i in range(self.columnCount()):
            w = self.itemWidget(item, i)
            item.__widgets.append(w)
            if w is None:
                continue
            w.setParent(None)
        for i in range(item.childCount()):
            self.prepareMove(item.child(i))
        
    def recoverMove(self, item):
        for i in range(self.columnCount()):
            w = item.__widgets[i]
            if w is None:
                continue
            self.setItemWidget(item, i, w)
        for i in range(item.childCount()):
            self.recoverMove(item.child(i))
        
        item.setExpanded(False)  ## Items do not re-expand correctly unless they are collapsed first.
        QtGui.QApplication.instance().processEvents()
        item.setExpanded(item.__expanded)
        
    def collapseTree(self, item):
        item.setExpanded(False)
        for i in range(item.childCount()):
            self.collapseTree(item.child(i))
            
    def removeTopLevelItem(self, item):
        for i in range(self.topLevelItemCount()):
            if self.topLevelItem(i) is item:
                self.takeTopLevelItem(i)
                return