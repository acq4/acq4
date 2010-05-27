from PyQt4 import QtCore, QtGui
from lib.DataManager import *
from lib.util.debug import *
import os

 
 
class FileTreeWidget(QtGui.QTreeWidget):
    def __init__(self, parent, baseDirHandle=None):
        QtGui.QTreeWidget.__init__(self, parent)
        QtCore.QAbstractItemModel.__init__(self, parent)
        self.baseDir = baseDirHandle
        self.currentDir = None
        self.handles = {}

    def setBaseDirHandle(self, d):
        print "set base", d.name()
        if self.baseDir is not None:
            self.unwatch(self.baseDir)
        self.baseDir = d
        self.watch(self.baseDir)
        
        self.rebuildTree()
        #self.layoutChanged()
        
    def setCurrentDir(self, d):
        self.currentDir = d
        
    def watch(self, handle):
        QtCore.QObject.connect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    def unwatch(self, handle):
        QtCore.QObject.disconnect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    def dirChanged(self, path, change, *args):
        pass
        #self.layoutChanged()

    def rebuildTree(self, root=None):
        print "rebuildTree"
        if root is None:
            root = self.invisibleRootItem()
            handle = self.baseDir
        else:
            handle = root.handle
            
        while root.childCount() > 0:
            root.removeChild(root.child(0))   ## Need to disconnect these?
            
        for f in handle.ls():
            print "Add handle", f
            item = FileTreeItem(self.baseDir[f])
            root.addChild(item)
        
class FileTreeItem(QtGui.QTreeWidgetItem):
    def __init__(self, handle):
        QtGui.QTreeWidgetItem.__init__(self, [handle.shortName()])
        self.handle = handle
        if self.handle.isDir():
            self.setExpanded(False)
            self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)
            
        
    