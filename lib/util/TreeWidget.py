# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore


class TreeWidget(QtGui.QTreeWidget):
    """Extends QTreeWidget to allow internal drag/drop with widgets in the tree.
    Also maintains the expanded state of subtrees as they are moved.
    This class demonstrates the absurd lengths one must go to to make drag/drop work."""
    def __init__(self):
        QtGui.QTreeWidget.__init__(self)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setEditTriggers(QtGui.QAbstractItemView.EditKeyPressed|QtGui.QAbstractItemView.SelectedClicked)

    def setItemWidget(self, item, col, wid):
        w = QtGui.QWidget()  ## foster parent / surrogate child widget
        wid.__pw = w  ## keep an extra reference to the parent
        exp = item.isExpanded()
        QtGui.QTreeWidget.setItemWidget(self, item, col, w)
        l = QtGui.QVBoxLayout()
        l.setContentsMargins(0,0,0,0)
        w.setLayout(l)
        l.addWidget(wid)
        w.realChild = wid
        item.setExpanded(False)
        QtGui.QApplication.instance().processEvents()
        item.setExpanded(exp)

    def dropMimeData(self, parent, index, data, action):
        item = self.currentItem()
        db = item.delBtn
        exp = item.isExpanded()
        sub = item.child(0)
        if sub is not None:
            widget = self.itemWidget(sub, 0).realChild
        if index > self.invisibleRootItem().indexOfChild(item):
            index -= 1
        self.invisibleRootItem().removeChild(item)
        self.insertTopLevelItem(index, item)
        if sub is not None:
            item.addChild(sub)
            self.setItemWidget(sub, 0, widget)
        self.setItemWidget(item, 1, db)
        item.setExpanded(False)
        QtGui.QApplication.instance().processEvents()
        item.setExpanded(exp)
        self.emit(QtCore.SIGNAL('itemMoved'), item, index)
        return True
