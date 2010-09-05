# -*- coding: utf-8 -*-

from PyQt4 import QtCore, QtGui
from TreeWidget import *

class DirTreeWidget(TreeWidget):
    def __init__(self, dirHandle=None, parent=None, defaultFlags=None, defaultCheckState=None):
        self.defaultFlags = defaultFlags
        self.defaultCheckState = defaultCheckState
        TreeWidget.__init__(self, parent)
        QtCore.QObject.connect(self, QtCore.SIGNAL("itemExpanded(QTreeWidgetItem*)"), self.itemExpanded)
        self.setRoot(dirHandle)

    def setRoot(self, handle):
        if handle == self.handle:
            return
        self.handle = handle
        self.clear()
        if handle is None:
            return
        for f in handle.ls():
            ch = DirTreeItem(handle[f], flags=self.defaultFlags, checkState=self.defaultCheckState)
            self.invisibleRootItem().addChild(ch)

    def itemExpanded(self, item):
        item.expanded()
        
        
class DirTreeItem(QtGui.QTreeWidgetItem):
    def __init__(self, handle, flags=None, checkState=None):
        QtGui.QTreeWidgetItem.__init__(self, [handle.shortName()])
        if flags is None:
            flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        self.handle = handle
        self.isLoaded = False
        if handle.isDir():
            self.setChildIndicatorPolicy(self.ShowIndicator)
        if flags is not None:
            self.setFlags(flags)
        if checkState is not None:
            self.setCheckState(0, checkState)
        self.defaultFlags = flags
        self.defaultCheckState = checkState
        
    def expanded(self):
        if not self.isLoaded:
            for f in self.handle.ls():
                item = DirTreeItem(self.handle[f], flags=self.defaultFlags, checkState=self.defaultCheckState)
                self.addChild(item)
            self.isLoaded = True
        