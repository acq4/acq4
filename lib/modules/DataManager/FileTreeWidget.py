# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.util.DataManager import *
from debug import *
import os

 
 
class FileTreeWidget(QtGui.QTreeWidget):
    def __init__(self, parent, baseDirHandle=None):
        QtGui.QTreeWidget.__init__(self, parent)
        #QtCore.QAbstractItemModel.__init__(self, parent)
        self.baseDir = baseDirHandle
        self.currentDir = None
        #self.handles = {}
        self.items = {}
        QtCore.QObject.connect(self, QtCore.SIGNAL('itemExpanded(QTreeWidgetItem*)'), self.itemExpanded)
        QtCore.QObject.connect(self, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.itemChanged)
        QtCore.QObject.connect(self, QtCore.SIGNAL('currentItemChanged(QTreeWidgetItem*, QTreeWidgetItem*)'), self.selectionChanged)
        
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        #self.setDropIndicatorShown(False)
        
    def __del__(self):
        try:
            self.quit()
        except:
            pass
        
    def quit(self):
        ## not sure if any of this is necessary..
        QtCore.QObject.disconnect(self, QtCore.SIGNAL('itemExpanded(QTreeWidgetItem*)'), self.itemExpanded)
        QtCore.QObject.disconnect(self, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.itemChanged)
        for h in self.items:
            self.unwatch(h)
        #self.handles = {}
        self.items = {}
        self.clear()
        
    def refresh(self, handle):
        try:
            item = self.item(handle)
        except:
            return
        self.rebuildChildren(item)
        
    def selectionChanged(self, item=None, _=None):
        """Selection has changed; check to see whether currentDir item needs to be recolored"""
        if item is None:
            item = self.currentItem()
        if not isinstance(item, FileTreeItem):
            return
        #print "select:", item
        if self.handle(item) is self.currentDir:
            self.setStyleSheet('selection-background-color: #BB00BB;')
        else:
            self.setStyleSheet('')
        
    def handle(self, item):
        """Given a tree item, return the corresponding file handle"""
        if hasattr(item, 'handle'):
            return item.handle
        elif item is self.invisibleRootItem():
            return self.baseDir
        else:
            raise Exception("Can't determine handle for item '%s'" % item.text(0))
        
    def item(self, handle, create=False):
        """Given a file handle, return the corresponding tree item."""
        if handle in self.items:
            return self.items[handle]
        elif create:
            return self.addHandle(handle)
        else:
            raise Exception("Can't find tree item for file '%s'" % handle.name())
        
        
    def itemChanged(self, item, col):
        """Item text has changed; try renaming the file"""
        handle = self.handle(item)
        try:
            newName = str(item.text(0))
            if handle.shortName() != newName:
                if os.path.sep in newName:
                    raise Exception("Can't rename file to have slashes in it.")
                handle.rename(newName)
                #print "Rename %s -> %s" % (handle.shortName(), item.text(0))
        except:
            printExc("Error while renaming file:")
        finally:
            item.setText(0, handle.shortName())

    def setBaseDirHandle(self, d):
        #print "set base", d.name()
        if self.baseDir is not None:
            self.unwatch(self.baseDir)
        self.baseDir = d
        self.watch(self.baseDir)
        
        for h in self.items:
            self.unwatch(h)
        #self.handles = {}
        self.items = {self.baseDir: self.invisibleRootItem()}
        self.clear()
        self.rebuildChildren(self.invisibleRootItem())
        #self.rebuildTree()
        
    def setCurrentDir(self, d):
        #print "set current %s -> %s" % (self.currentDir, d)
        ## uncolor previous current item
        if self.currentDir in self.items:
            item = self.items[self.currentDir]
            item.setBackground(0, QtGui.QBrush(QtGui.QColor(255,255,255)))
            #print "  - uncolor item ", item, self.handle(item)
            
        self.currentDir = d
        if d is self.baseDir:
            return
        
        self.expandTo(d)
        
        if d in self.items:
            self.updateCurrentDirItem()
        #else:
            #print "   - current dir changed but new dir not yet present in tree."
        
    def updateCurrentDirItem(self):
        """Color the currentDir item, expand, and scroll-to"""
        #print "UpdateCurrentDirItem"
        item = self.item(self.currentDir)
        item.setBackground(0, QtGui.QBrush(QtGui.QColor(250, 100, 100)))
        item.setExpanded(True)
        self.scrollToItem(item)
        self.selectionChanged()
        
    def expandTo(self, dh):
        """Expand all nodes from baseDir up to dh"""
        dirs = dh.name(relativeTo=self.baseDir).split(os.path.sep)
        node = self.baseDir
        while len(dirs) > 0:
            item = self.items[node]
            item.setExpanded(True)
            node = node[dirs.pop(0)] 
        
    def watch(self, handle):
        QtCore.QObject.connect(handle, QtCore.SIGNAL('delayedChange'), self.dirChanged)
        
    def unwatch(self, handle):
        QtCore.QObject.disconnect(handle, QtCore.SIGNAL('delayedChange'), self.dirChanged)
        
    def dirChanged(self, handle, changes):
        #print "Change: %s %s"% (change, handle.name())
        if handle is self.baseDir:
            item = self.invisibleRootItem()
        else:
            item = self.items[handle]
            
        #if change == 'moved':
        #    parent = handle.parent()
        #    if parent in self.items:           ## this node should be moved elsewhere in the tree
        #        pItem = self.items[parent]
        #        self.rebuildChildren(pItem)
        #    else:                              ## file was moved to a directory not yet loaded into the tree; just forget it
        #        self.forgetHandle(handle)
        if 'renamed' in changes:
            item.setText(0, handle.shortName())
        if 'deleted' in changes:
            self.forgetHandle(handle)
        if 'children' in changes:
            self.rebuildChildren(item)
            item.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)

    def addHandle(self, handle):
        if handle in self.items:
            raise Exception("Tried to add handle '%s' twice." % handle.name())
        item = FileTreeItem(handle)
        self.items[handle] = item
        #self.handles[item] = handle
        self.watch(handle)
        if handle is self.currentDir:
            self.updateCurrentDirItem()
        return item

    def forgetHandle(self, handle):
        item = self.item(handle)
        del self.items[handle]
        #del self.handles[item]
        self.unwatch(handle)

    def rebuildChildren(self, root):
        """Make sure all children are present and in the correct order"""
        #prof = Profiler('rebuildChildren')
        handle = self.handle(root)
#        print "RebuildChildren", root, handle
        files = handle.ls()
        handles = [handle[f] for f in files]
        #prof.mark('make handle list')
#        for f, h in zip(files, handles):
#            print "     ", f, h
        #ph = 0
        #pi = 0
        i = 0
        while True:
            if i >= len(handles):
                ##  no more handles; remainder of items should be removed
                while root.childCount() > i:
                    ch = root.takeChild(i)
                    #self.forgetHandle(self.handle(ch))
#                    print "  remove", i, ch
                break
                
            h = handles[i]
#            print "  - check handle %d: %s" % (i, h)
            #i = items[pi]
            if (i >= root.childCount()) or (h not in self.items) or (h is not self.handle(root.child(i))):
                #print "insert %d" % i
                item = self.item(h, create=True)
                #if i >= root.childCount():
                #    print "  Insert; past end of item list"
                #elif h not in self.items:
                #    print "  Insert; no item yet created for this handle"
                #else:
                #    print "  Insert; %s != %s" % (str(h), str(self.handle(root.child(i))))
                #print "  insert new:", i, item
                
                #print "     (before) root now has %d childs: %s" % (root.childCount(), ', '.join([str(root.child(j).text(0)) for j in range(root.childCount())]))
                parent = self.itemParent(item)
                if parent is not None:
                    parent.removeChild(item)
                    #print "     (removed) root now has %d childs: %s" % (root.childCount(), ', '.join([str(root.child(j).text(0)) for j in range(root.childCount())]))
                root.insertChild(i, item)
                #print "     (after) root now has %d childs: %s" % (root.childCount(), ', '.join([str(root.child(j).text(0)) for j in range(root.childCount())]))
                item.recallExpand()
            #else:
                #print "item %d ok"%i
                    
            i += 1
            #prof.mark("item %d" % i)
            
        #prof.mark("done.")
        
        #items = []
        #while root.childCount() > 0:        ## Remove all nodes
            #items.append(root.takeChild(0))
        
        #for h in handles:                   ## Re-insert in correct order
            #item = self.item(h, create=True)
            #print "   - insert handle", h
            #if item in items:
                #items.remove(item)
            #root.addChild(item)
            #item.recallExpand()  ## looks like a bug that improperly closes nodes.
        
        #for i in items:                     ## ..and remove anything that is left over
            #print "   - forget handle", self.handle(i)
            #self.forgetHandle(self.handle(i))
            
    def itemParent(self,  item):
        """Return the parent of an item (since item.parent can not be trusted). Note: damn silly."""
        if item.parent() is None:
            root = self.invisibleRootItem()
            tlc = [root.child(i) for i in range(root.childCount())]
            if item in tlc:
                return root
            else:
                return None
        else:
            return item.parent()
            
    def editItem(self, handle):
        item = self.item(handle)
        QtGui.QTreeWidget.editItem(self, item, 0)

    def rebuildTree(self, root=None):
        """Completely clear and rebuild the entire tree starting at root"""
        if root is None:
            root = self.invisibleRootItem()
            
        handle = self.handle(root)
            
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
                handle = self.handle(child)
                self.unwatch(handle)
                #del self.handles[child]
                del self.items[handle]
            root.removeChild(child)
            
            
    def itemExpanded(self, item):
        """Called whenever an item in the tree is expanded; responsible for loading children if they have not been loaded yet."""
        if not item.childrenLoaded:
            ## Display loading message before starting load
            loading = None
            if item.handle.isDir():
                loading = QtGui.QTreeWidgetItem(['loading..'])
                item.addChild(loading)
            QtGui.QApplication.instance().processEvents()  ## make sure the 'loading' item is displayed before building the tree
            if loading is not None:
                item.removeChild(loading)
            ## now load all children
            self.rebuildChildren(item)
            item.childrenLoaded = True
        item.expanded()
        self.scrollToItem(item.child(item.childCount()-1))
        self.scrollToItem(item)
        
        
    def select(self, handle):
        item = self.item(handle)
        self.setCurrentItem(item)

    #def dropEvent(self, ev):
        #if ev.source() is self:
        #    print "dropEvent", self.itemAt(ev.pos())
        #    #return QtGui.QAbstractItemView.dropEvent(self, ev)
        #    return QtGui.QTreeView.dropEvent(self, ev)
        #else:
            #ev.ignore()

    def dropMimeData(self, parent, index, data, action):
#        print "dropMimeData:", parent, index, self.currentItem()
        source = self.handle(self.currentItem())
        if parent is None:
            target = self.baseDir
        else:
            target = self.handle(parent)
        try:
            source.move(target)
            return True
        except:
            printExc('Move failed:')
            return False
        #return True

    def handleScheduledMove(self, item, parent):
        handle = self.handle(item)
        try:
            handle.move(self.handle(parent))
        except:
            printExc("Move failed:")
        

    #def dropEvent(self, ev):
    #    #ev.ignore()
    #    if ev.source() is self:
    #        #ev.ignore()
    #        parent = self.itemAt(ev.pos())
    #        item = self.currentItem()
    #        handle = self.handle(item)
    #        #print "dropEvent", parent, handle
    #        
    #        ## Qt bug: can't mess with tree items until AFTER the drop has been handled.
    #        ## Instead, schedule the move to be done later.
    #        #QtCore.QTimer.singleShot(0, lambda: self.handleScheduledMove(item, parent))
    #        
    #        #try:
    #            #handle.move(self.handle(parent))
    #        #except:
    #            #printExc("Move failed:")

        



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
            if self.handle.hasChildren():
                self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)
            self.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsEnabled)
            self.setForeground(0, QtGui.QBrush(QtGui.QColor(0, 0, 150)))
        else:
            self.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsEnabled)
        self.expandState = False
        QtCore.QObject.connect(self.handle, QtCore.SIGNAL('changed'), self.handleChanged)
        self.updateBoldState()
        
        
    def updateBoldState(self):
        if self.handle.isManaged():
            info = self.handle.info()
            font = self.font(0)
            if ('important' in info) and (info['important'] is True):
                font.setWeight(QtGui.QFont.Bold)
            else:
                font.setWeight(QtGui.QFont.Normal)
            self.setFont(0, font)
            
    def handleChanged(self, handle, change, *args):
        #print "handleChanged:", change
        if change == 'children':
            if self.handle.hasChildren() > 0:
                self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)
            else:
                self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.DontShowIndicatorWhenChildless)
        elif change == 'meta':
            self.updateBoldState()
            
            
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
        
        
