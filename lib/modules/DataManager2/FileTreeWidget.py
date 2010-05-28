# -*- coding: utf-8 -*-
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
        self.items = {}
        QtCore.QObject.connect(self, QtCore.SIGNAL('itemExpanded(QTreeWidgetItem*)'), self.itemExpanded)
        
    def __del__(self):
        self.quit()
        
    def quit(self):
        ## not sure if any of this is necessary..
        QtCore.QObject.disconnect(self, QtCore.SIGNAL('itemExpanded(QTreeWidgetItem*)'), self.itemExpanded)
        for h in self.items:
            self.unwatch(h)
        self.handles = {}
        self.items = {}
        self.clear()
        

    def setBaseDirHandle(self, d):
        #print "set base", d.name()
        if self.baseDir is not None:
            self.unwatch(self.baseDir)
        self.baseDir = d
        self.watch(self.baseDir)
        
        self.rebuildTree()
        #self.layoutChanged()
        
    def setCurrentDir(self, d):
        ## uncolor previous current item
        if self.currentDir not in [None, self.baseDir]:
            item = self.items[self.currentDir]
            item.setBackground(0, QtGui.QBrush(QtGui.QColor(255,255,255)))
            
        self.currentDir = d
        if d is self.baseDir:
            return
        
        try:
            item = self.items[d]
        except:
            print "DH:", d
            print
            print self.items
            raise
        item.setBackground(0, QtGui.QBrush(QtGui.QColor(200, 50, 50)))
        item.setExpanded(True)
        self.scrollToItem(item)
        
    def watch(self, handle):
        QtCore.QObject.connect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    def unwatch(self, handle):
        QtCore.QObject.disconnect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    def dirChanged(self, handle, change, *args):
        if change == 'moved':
            item = self.items[handle]
            parent = handle.parent()
            if parent in self.items:           ## this node should be moved elsewhere in the tree
                pItem = self.items[parent]
                self.rebuildChildren(pItem)
            else:                              ## file was moved to a directory not yet loaded into the tree; just forget it
                self.forgetHandle(handle)
        elif change == 'renamed':
            item = self.items[handle]
            item.setText(0, handle.shortName())
        elif change == 'deleted':
            self.forgetHandle(handle)
        elif change == 'children':
            self.rebuildChildren(self.items[handle])
        #self.rebuildTree(self.items[handle])

    def addHandle(self, handle):
        if handle in self.items:
            raise Exception("Tried to add handle '%s' twice." % handle.name())
        item = FileTreeItem(childHandle)
        self.items[childHandle] = item
        self.handles[item] = childHandle
        self.watch(handle)
        return item

    def forgetHandle(self, handle):
        item = self.items[handle]
        del self.items[handle]
        del self.handles[item]
        self.unwatch(handle)

    def rebuildChildren(self, root):
        """Make sure all children are present and in the correct order"""
        files = root.handle.ls()
        handles = [root.handle[f] for f in files]
        items = []
        while root.childCount() > 0:        ## Remove all nodes
            items.append(root.takeChild(0))
        
        for h in handles:                   ## Re-insert in correct order
            if h in self.items:
                item = self.items[h]
            else:
                item = self.addHandle(h)
            if item in items:
                items.remove(item)
            root.addChild(item)
            
        
        for i in items:                     ## ..and remove anything that is left over
            self.forgetHandle(i.handle)
            
            

    def rebuildTree(self, root=None):
        """Completely clear and rebuild the entire tree starting at root"""
        #print "rebuildTree"
        if root is None:
            root = self.invisibleRootItem()
            handle = self.baseDir
        else:
            handle = root.handle
            
        self.clearTree(root)
            
        for f in handle.ls():
            #print "Add handle", f
            try:
                childHandle = handle[f]
            except:
                printExc("Error getting file handle:")
                continue
            item = self.addHandle(childHandle)
            root.addChild(item)
            
    def clearTree(self, root):
        while root.childCount() > 0:
            child = root.child(0)
            self.clearTree(child)
            handle = self.handles[child]
            root.removeChild(child)
            self.unwatch(handle)
            del self.handles[child]
            del self.items[handle]
            
            
    def itemExpanded(self, item):
        """Called whenever an item in the tree is expanded; responsible for loading children if they have not been loaded yet."""
        if not item.childrenLoaded:
            ## Display loading message before starting load
            if item.handle.isDir():
                item.addChild(QtGui.QTreeWidgetItem(['loading..']))
            QtGui.QApplication.instance().processEvents()
            ## now load all children
            self.rebuildTree(item)
            item.childrenLoaded = True
        item.expanded()
        
    def supportedDropActions(self):
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    #def supportedDragActions(self):
        #return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    #def dropMimeData(self, data, action, row, column, parent):
        #files = str(data.text()).split('\n')
        #parent = self.handle(parent)
        
        ### Do error checking on the entire set before moving anything
        #try:
            #for f in files:
                #handle = self.baseDir[f]
                #if handle.parent() == parent:
                    #print "Can not move %s (Same parent dir)"  % handle.name()
                    #return False
        #except:
            #printExc("Error while trying to move files (don't worry, nothing moved yet)")
            #return False
                    
                    
        ### Now attempt the moves
        #try:
            #for f in files:
                #handle = self.baseDir[f]
                #oldName = handle.name()
                #if action == QtCore.Qt.MoveAction:
                    #handle.move(parent)
                #elif action == QtCore.Qt.CopyAction:
                    #raise Exception("Copy not supported")
                #self.layoutChanged()
            #return True
        #except:
            #printExc("<<WARNING>> Error while moving files:")
            #return False
        
class FileTreeItem(QtGui.QTreeWidgetItem):
    def __init__(self, handle):
        QtGui.QTreeWidgetItem.__init__(self, [handle.shortName()])
        self.handle = handle
        self.childrenLoaded = False
        if self.handle.isDir():
            self.setExpanded(False)
            self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)
            self.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsEnabled)
        else:
            self.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsEnabled)
            
            
    def expanded(self):
        """Called whenever this item is expanded or collapsed."""
        pass
    