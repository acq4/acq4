# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.DataManager import *
from lib.util.debug import *
import os

 
 
class FileTreeWidget(QtGui.QTreeWidget):
    def __init__(self, parent, baseDirHandle=None):
        QtGui.QTreeWidget.__init__(self, parent)
        #QtCore.QAbstractItemModel.__init__(self, parent)
        self.baseDir = baseDirHandle
        self.currentDir = None
        self.handles = {}
        self.items = {}
        QtCore.QObject.connect(self, QtCore.SIGNAL('itemExpanded(QTreeWidgetItem*)'), self.itemExpanded)
        QtCore.QObject.connect(self, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.itemChanged)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        
    def __del__(self):
        self.quit()
        
    def quit(self):
        ## not sure if any of this is necessary..
        QtCore.QObject.disconnect(self, QtCore.SIGNAL('itemExpanded(QTreeWidgetItem*)'), self.itemExpanded)
        QtCore.QObject.disconnect(self, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.itemChanged)
        for h in self.items:
            self.unwatch(h)
        self.handles = {}
        self.items = {}
        self.clear()
        
        
    def itemChanged(self, item, col):
        handle = self.handles[item]
        try:
            newName = str(item.text(0))
            if handle.shortName() != newName:
                if re.search(os.path.sep, newName):
                    raise Exception("Can't rename file to have slashes in it.")
                handle.rename(newName)
                #print "Rename %s -> %s" % (handle.shortName(), item.text(0))
        except:
            printExc("Error while renaming file:")
        finally:
            item.setText(0, handle.shortName())

    def setBaseDirHandle(self, d):
        print "set base", d.name()
        if self.baseDir is not None:
            self.unwatch(self.baseDir)
        self.baseDir = d
        self.watch(self.baseDir)
        
        for h in self.items:
            self.unwatch(h)
        self.handles = {}
        self.items = {}
        self.clear()
        self.rebuildChildren(self.invisibleRootItem())
        #self.rebuildTree()
        
    def setCurrentDir(self, d):
        print "set current", d.name()
        ## uncolor previous current item
        if self.currentDir in self.items:
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
        print "Change: %s %s"% (change, handle.name())
        if handle is self.baseDir:
            item = self.invisibleRootItem()
        else:
            item = self.items[handle]
            
        if change == 'moved':
            parent = handle.parent()
            if parent in self.items:           ## this node should be moved elsewhere in the tree
                pItem = self.items[parent]
                self.rebuildChildren(pItem)
            else:                              ## file was moved to a directory not yet loaded into the tree; just forget it
                self.forgetHandle(handle)
        elif change == 'renamed':
            item.setText(0, handle.shortName())
        elif change == 'deleted':
            self.forgetHandle(handle)
        elif change == 'children':
            self.rebuildChildren(item)
            item.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)
        #self.rebuildTree(self.items[handle])

    def addHandle(self, handle):
        if handle in self.items:
            raise Exception("Tried to add handle '%s' twice." % handle.name())
        item = FileTreeItem(handle)
        self.items[handle] = item
        self.handles[item] = handle
        self.watch(handle)
        return item

    def forgetHandle(self, handle):
        item = self.items[handle]
        del self.items[handle]
        del self.handles[item]
        self.unwatch(handle)

    def rebuildChildren(self, root):
        """Make sure all children are present and in the correct order"""
        if root is self.invisibleRootItem():
            handle = self.baseDir
        else:
            handle = root.handle
        #print "REBUILD %s:" % handle.name()
        files = handle.ls()
        handles = [handle[f] for f in files]
        
        
        #for i in range(root.childCount()):
            #c = root.child(i)
            #h = self.handles[c]
            #if h not in handles:
                #root.removeChild(c)
                #print "  - forget", h.shortName()
                #self.forgetHandle(h)
                
        #childs = [root.child(i) for i in range(root.childCount())]
        #for h in handles:
            #if h not in self.items:
                #item = self.addHandle(h)
                #print "  - add", h.shortName()
                ##childs.append(item)
            ##else:
                ##item = self.items[h]
                ##if item not in childs:
                    ##childs.append(item)
        
        #for i in range(len(handles)):
            #h = handles[i]
            #c = self.items[h]
            #root.insertChild(i, c)
            #print "  - insert", h.shortName()
        
        
        
        items = []
        #expanded = {}
        while root.childCount() > 0:        ## Remove all nodes
            #expanded[root.child(0)] = root.child(0).isExpanded()
            items.append(root.takeChild(0))
        
        for h in handles:                   ## Re-insert in correct order
            if h in self.items:
                item = self.items[h]
                #print "   - reinsert %s" % h.shortName()
            else:
                item = self.addHandle(h)
                #print "   - create %s" % h.shortName()
            if item in items:
                items.remove(item)
            root.addChild(item)
            item.recallExpand()  ## looks like a bug that improperly closes nodes.
            #if item in expanded:
                #item.setExpanded(expanded[item])
            
        
        for i in items:                     ## ..and remove anything that is left over
            #print "   - forget %s" % i.handle.shortName()
            self.forgetHandle(i.handle)
            
    def editItem(self, handle):
        item = self.items[handle]
        QtGui.QTreeWidget.editItem(self, item, 0)

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
            if isinstance(child, FileTreeItem):
                self.clearTree(child)
                handle = self.handles[child]
                self.unwatch(handle)
                del self.handles[child]
                del self.items[handle]
            root.removeChild(child)
            
            
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
        
    def select(self, handle):
        item = self.items[handle]
        self.setCurrentItem(item)

    def dropEvent(self, ev):
        if ev.source() is self:
            return QtGui.QAbstractItemView.dropEvent(self, ev)
        else:
            ev.ignore()

    def dropMimeData(self, parent, index, data, action):
        #print "dropMimeData:", parent, self.currentItem()
        source = self.handles[self.currentItem()]
        if parent is None:
            target = self.baseDir
        else:
            target = self.handles[parent]
        try:
            source.move(target)
            return True
        except:
            printExc('Move failed:')
            return False
        
    #def supportedDropActions(self):
        #return QtCore.Qt.CopyAction|QtCore.Qt.MoveAction|QtCore.Qt.LinkAction|QtCore.Qt.IgnoreAction|QtCore.Qt.TargetMoveAction
        
    #def dragEnterEvent(self, ev):
        #QtGui.QTreeWidget.dragEnterEvent(self, ev)
        #ev.accept()
        
    #def dragMoveEvent(self, ev):
        #ev.accept()
        
    #def dropEvent(self, ev):
        
        #files = str(ev.mimeData().text()).split('\n')
        #if len(files)  > 1:
            #print "Multi-item drops not supported."
            #ev.ignore()
            #return
        #handle = self.baseDir[files[0]]
        #try:
            #item = self.items[handle]
            #parent = item.parent()
            #print handle, item, parent
            #if parent is self.invisibleRootItem():
                #pHandle = self.baseDir
            #else:
                #pHandle = self.handles[parent]
            #print "Move %s -> %s" % (handle.shortName(), pHandle.shortName())
            ##handle.move(
        #except:
            #ev.ignore()
            #printExc("Move failed:")
        
    #def mimeData(self, items):
        #md = QtCore.QMimeData()
        #md.setText('\n'.join([self.handles[i].name(relativeTo=self.baseDir) for i in items]))
        #return md
        
    #def mimeTypes(self):
        #return ["text/plain"]
        
        
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
        self.expandState = False
            
            
    def expanded(self):
        """Called whenever this item is expanded or collapsed."""
        #print "Expand:", self.isExpanded()
        self.expandState = self.isExpanded()

    def recallExpand(self):
        if self.expandState:
            #print "re-expanding", self.handle.shortName()
            self.setExpanded(False)
            self.setExpanded(True)
        for i in range(self.childCount()):
            self.child(i).recallExpand()
        
        