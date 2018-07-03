# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from acq4.util.DataManager import *
from acq4.util.debug import *
import os



class DirTreeWidget(Qt.QTreeWidget):

    sigSelectionChanged = Qt.Signal(object)
    ### something funny is happening with sigSelectionChanged and currentItemChanged; the signals seem to be emitted before the DirTreeWidget actually knows that the item changed.
    ### ie. if a function is connected to the signal, and the function asks DirTreeWidget.selectedFile() the previously selected file is returned, not the new selection.
    ### you can get around this by using the (current, previous) items that are passed with the currentItemChanged signal.

    def __init__(self, parent=None, baseDirHandle=None, checkState=None, allowMove=True, allowRename=True, sortMode='date'):
        Qt.QTreeWidget.__init__(self, parent)
        self.baseDir = None
        self.checkState = checkState
        self.allowMove = allowMove
        self.allowRename = allowRename
        self.currentDir = None
        self.sortMode = sortMode
        self.setEditTriggers(Qt.QAbstractItemView.SelectedClicked)
        self.items = {}
        self.itemExpanded.connect(self.itemExpandedEvent)
        self.itemChanged.connect(self.itemChangedEvent)
        self.currentItemChanged.connect(self.selectionChanged)

        self.setAcceptDrops(True)
        self.setDragEnabled(True)

        if baseDirHandle is not None:
            self.setBaseDirHandle(baseDirHandle)

    def __del__(self):
        try:
            self.quit()
        except:
            pass

    def setSortMode(self, mode):
        """Set the method used to sort. Must be 'date' or 'alpha'."""
        self.sortMode = mode
        self.rebuildTree()

    def flushSignals(self):
        for h in self.items.keys():
            h.flushSignals()

    def quit(self):
        ## not sure if any of this is necessary..
        try:
            self.itemExpanded.disconnect(self.itemExpandedEvent)
        except TypeError:
            pass
        
        try:
            self.itemChanged.disconnect(self.itemChangedEvent)
        except TypeError:
            pass
        
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
        self.sigSelectionChanged.emit(self)
        if item is None:
            item = self.currentItem()
        if not isinstance(item, FileTreeItem):
            return

        if self.handle(item) is self.currentDir:
            self.setStyleSheet('selection-background-color: #BB00BB;')
        else:
            self.setStyleSheet('')

    def selectedFile(self):
        """Return the handle for the currently selected file.
        If no items are selected, return None.
        If multiple items are selected, raise an exception."""
        items = self.selectedItems()
        if len(items) == 0:
            return None
        if len(items) > 1:
            raise Exception('Multiple items selected. Use selectedFiles instead.')
        return self.handle(items[0])

    def selectedFiles(self):
        """Return list of handles for the currently selected file(s)."""
        items = self.selectedItems()
        return [self.handle(items[i]) for i in range(len(items))]

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
        else:
            self.flushSignals()  ## might be something waiting to be added to the tree
            
        if handle in self.items:
            return self.items[handle]
        elif create:
            return self.addHandle(handle)
        else:
            raise Exception("Can't find tree item for file '%s'" % handle.name())

    def itemChangedEvent(self, item, col):
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

        if d is not None:
            self.watch(self.baseDir)

        for h in self.items:
            self.unwatch(h)
        #self.handles = {}
        if d is not None:
            self.items = {self.baseDir: self.invisibleRootItem()}
        self.clear()
        if d is not None:
            self.rebuildChildren(self.invisibleRootItem())
        #self.rebuildTree()

    def baseDirHandle(self):
        return self.baseDir

    def setRoot(self, d):
        """Synonym for setBaseDirHandle"""
        return self.setBaseDirHandle(d)

    def setCurrentDir(self, d):
        #print "set current %s -> %s" % (self.currentDir, d)
        ## uncolor previous current item
        if self.currentDir in self.items:
            item = self.items[self.currentDir]
            item.setBackground(0, Qt.QBrush(Qt.QColor(255,255,255)))
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
        item.setBackground(0, Qt.QBrush(Qt.QColor(250, 100, 100)))
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
        #Qt.QObject.connect(handle, Qt.SIGNAL('delayedChange'), self.dirChanged)
        handle.sigDelayedChange.connect(self.dirChanged)

    def unwatch(self, handle):
        #Qt.QObject.disconnect(handle, Qt.SIGNAL('delayedChange'), self.dirChanged)
        try:
            handle.sigDelayedChange.disconnect(self.dirChanged)
        except:
            pass

    def dirChanged(self, handle, changes):
        if handle is self.baseDir:
            item = self.invisibleRootItem()
        else:
            item = self.items[handle]

        if 'renamed' in changes:
            item.setText(0, handle.shortName())
        if 'deleted' in changes:
            self.forgetHandle(handle)
        if 'children' in changes:
            self.rebuildChildren(item)
            item.setChildIndicatorPolicy(Qt.QTreeWidgetItem.ShowIndicator)

    def addHandle(self, handle):
        if handle in self.items:
            raise Exception("Tried to add handle '%s' twice." % handle.name())
        item = FileTreeItem(handle, self.checkState, self.allowMove, self.allowRename)
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
        scroll = self.verticalScrollBar().value()
        handle = self.handle(root)
        files = handle.ls(sortMode=self.sortMode)
        handles = [handle[f] for f in files]
        i = 0
        while True:
            if i >= len(handles):
                ##  no more handles; remainder of items should be removed
                while root.childCount() > i:
                    ch = root.takeChild(i)
                break

            h = handles[i]
            if (i >= root.childCount()) or (h not in self.items) or (h is not self.handle(root.child(i))):
                item = self.item(h, create=True)
                parent = self.itemParent(item)
                if parent is not None:
                    parent.removeChild(item)
                root.insertChild(i, item)
                item.recallExpand()
            i += 1
        self.verticalScrollBar().setValue(scroll)

    def itemParent(self,  item):
        """Return the parent of an item (since item.parent can not be trusted). Note: damn silly."""
        if item.parent() is None:
            root = self.invisibleRootItem()
            tlc = [root.child(i) for i in range(root.childCount())]
            #if item in tlc:
                #return root
            #else:
                #return None
            for tli in tlc:
                if tli is item:
                    return root
            return None
        else:
            return item.parent()

    def editItem(self, handle):
        item = self.item(handle)
        Qt.QTreeWidget.editItem(self, item, 0)

    def rebuildTree(self, root=None, useCache=True):
        """Completely clear and rebuild the entire tree starting at root"""
        if root is None:
            root = self.invisibleRootItem()

        handle = self.handle(root)
        if handle is None:
            return
        if handle.isFile():
            handle = handle.parent()
            root = self.itemParent(root)
        if root is None:
            return

        self.clearTree(root)
        if handle is None:
            return
        
        for f in handle.ls(useCache=useCache):
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

    def itemExpandedEvent(self, item):
        """Called whenever an item in the tree is expanded; responsible for loading children if they have not been loaded yet."""
        if not item.childrenLoaded:
            try:
                Qt.QApplication.setOverrideCursor(Qt.QCursor(Qt.Qt.WaitCursor))
                ## Display loading message before starting load
                loading = None
                if item.handle.isDir():
                    loading = Qt.QTreeWidgetItem(['loading..'])
                    item.addChild(loading)
                Qt.QApplication.instance().processEvents()  ## make sure the 'loading' item is displayed before building the tree
                if loading is not None:
                    item.removeChild(loading)
                ## now load all children
                self.rebuildChildren(item)
                item.childrenLoaded = True
            finally:
                Qt.QApplication.restoreOverrideCursor()

        item.expanded()
        self.scrollToItem(item.child(item.childCount()-1))
        self.scrollToItem(item)

    def select(self, handle):
        item = self.item(handle, create=True)
        self.expandTo(handle)
        self.setCurrentItem(item)

    def dropMimeData(self, parent, index, data, action):
        #print "dropMimeData:", parent, index, self.selectedFiles()
        source = self.selectedFiles()
        if parent is None:
            target = self.baseDir
        else:
            target = self.handle(parent)
        try:
            for s in source:
                s.move(target)
            return True
        except:
            printExc('Move failed:')
            return False

    def contextMenuEvent(self, ev):
        item = self.itemAt(ev.pos())
        if item is None:
            return
        self.menu = Qt.QMenu(self)
        act = self.menu.addAction('refresh', self.refreshClicked)
        self.contextItem = item
        self.menu.popup(ev.globalPos())
        
    def refreshClicked(self):
        self.rebuildTree(self.contextItem, useCache=False)


class FileTreeItem(Qt.QTreeWidgetItem):
    def __init__(self, handle, checkState=None, allowMove=True, allowRename=True):
        Qt.QTreeWidgetItem.__init__(self, [handle.shortName()])
        self.handle = handle
        self.childrenLoaded = False

        if self.handle.isDir():
            self.setExpanded(False)
            self.setChildIndicatorPolicy(Qt.QTreeWidgetItem.ShowIndicator)
            self.setFlags(Qt.Qt.ItemIsSelectable|Qt.Qt.ItemIsDropEnabled|Qt.Qt.ItemIsEnabled)
            self.setForeground(0, Qt.QBrush(Qt.QColor(0, 0, 150)))
        else:
            self.setFlags(Qt.Qt.ItemIsSelectable|Qt.Qt.ItemIsEnabled)

        if allowMove:
            self.setFlag(Qt.Qt.ItemIsDragEnabled)
        if allowRename:
            self.setFlag(Qt.Qt.ItemIsEditable)

        if checkState is not None:
            self.setFlag(Qt.Qt.ItemIsUserCheckable)
            if checkState:
                self.setCheckState(0, Qt.Qt.Checked)
            else:
                self.setCheckState(0, Qt.Qt.Unchecked)
        self.expandState = False
        self.handle.sigChanged.connect(self.handleChanged)
        self.updateBoldState()

    def setFlag(self, flag, v=True):
        if v:
            self.setFlags(self.flags() | flag)
        else:
            self.setFlags(self.flags() & ~flag)


    def updateBoldState(self):
        if self.handle.isManaged():
            info = self.handle.info()
            font = self.font(0)
            if ('important' in info) and (info['important'] is True):
                font.setWeight(Qt.QFont.Bold)
            else:
                font.setWeight(Qt.QFont.Normal)
            self.setFont(0, font)

    def handleChanged(self, handle, change, *args):
        #print "handleChanged:", change
        if change == 'children':
            if self.handle.hasChildren() > 0:
                self.setChildIndicatorPolicy(Qt.QTreeWidgetItem.ShowIndicator)
            else:
                self.setChildIndicatorPolicy(Qt.QTreeWidgetItem.DontShowIndicatorWhenChildless)
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

    def setChecked(self, c):
        if c:
            self.setCheckState(0, Qt.Qt.Checked)
        else:
            self.setCheckState(0, Qt.Qt.Unchecked)
