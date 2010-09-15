# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.util.DataManager import *
from lib.util.debug import *
import os

depth = 0
def profile(fn):
    def newFn(*args, **kargs):
        global depth
        p = Profiler("  " * depth + fn.__name__)
        depth += 1
        ret = fn(*args, **kargs)
        p.mark('finished')
        depth -= 1
        return ret
    return newFn

class DMModel(QtCore.QAbstractItemModel):
    """Based on DirTreeModel, used for displaying the contents of directories created and managed by DataManager"""
    def __init__(self, baseDirHandle=None, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)
        self.baseDir = baseDirHandle
        self.currentDir = None
        self.handles = {}
        
    def setBaseDirHandle(self, d):
        if self.baseDir is not None:
            self.unwatch(self.baseDir)
        self.baseDir = d
        self.watch(self.baseDir)
        self.layoutChanged()
        
    def setCurrentDir(self, d):
        self.currentDir = d
        
    def watch(self, handle):
        QtCore.QObject.connect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    def unwatch(self, handle):
        QtCore.QObject.disconnect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    def dirChanged(self, path, change, *args):
        self.layoutChanged()

    #@profile
    def handleIndex(self, handle):
        """Create an index from a file handle"""
        if not isinstance(handle, FileHandle):
            raise Exception("Function requires FileHandle or DirHandle as argument")
        #print handle, handle.parent()
        if handle.parent() is handle:
            return self.createIndex(0, 0, handle)
            
        if handle not in self.handles:
            self.handles[handle] = None
            self.watch(handle)
        try:
            row = handle.parent().ls().index(handle.shortName())
        except:
            print handle.name(), handle.parent().name(), handle.parent().ls(normcase=True), handle.shortName()
            raise
        return self.createIndex(row, 0, handle)
        
    #@profile
    def handle(self, index):  ## must be optimized!
        """Return the file handle from an index"""
        if not index.isValid():
            return self.baseDir
        h = index.internalPointer()
        if h is None:
            return self.baseDir
        else:
            return h

    #@profile
    def index(self, row, column, parent=QtCore.QModelIndex()):  ## must be optimized!
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        ph = self.handle(parent)
        childs = ph.ls()
        if row > len(childs):
            return QtCore.QModelIndex()
        dh = ph[childs[row]]
        return self.createIndex(row, column, dh)
            
    #@profile
    def parent(self, index):  ## must be optimized!
        p = self.handle(index).parent()
        if p is self.baseDir or self.baseDir.name() not in p.name():
            return QtCore.QModelIndex()
        return self.handleIndex(p)
            
    #@profile
    def rowCount(self, index=QtCore.QModelIndex()):  ## must be optimized!
        dh = self.handle(index)
        if index.column() > 0:
            return 0
        if not dh.isDir():
            return 0
        return len(dh.ls())
        
    def columnCount(self, index):
        return 1
    
    #@profile
    def data(self, index, role):  ## must be optimized!
        if not index.isValid():
            return QtCore.QVariant()
        dh = self.handle(index)
        ph = dh.parent()
        
        ret = QtCore.QVariant()
        if role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
            ret = dh.shortName()
        elif role == QtCore.Qt.TextColorRole:
            if dh.isDir():
                ret = QtGui.QColor(0,0,150)
            else:
                ret = QtGui.QColor(0,0,0)
        elif role == QtCore.Qt.BackgroundRole:
            if dh == self.currentDir:
                ret = QtGui.QBrush(QtGui.QColor(150, 220, 150))
        elif role == QtCore.Qt.FontRole:
            if dh.isManaged():
                info = dh.info()
                if ('important' in info) and (info['important'] is True):
                    ret = QtGui.QFont()
                    ret.setWeight(QtGui.QFont.Bold)
        return QtCore.QVariant(ret)

    #@profile
    def flags(self, index):
        defaults = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable
        if index is None:
            return None
        if not index.isValid():
            return defaults  | QtCore.Qt.ItemIsDropEnabled
        dh = self.handle(index)
        if dh.isDir():
            return defaults | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled
        else:
            return defaults | QtCore.Qt.ItemIsDragEnabled
            
    #@profile
    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant("Files")
        return QtCore.QVariant()
        
    #@profile
    def setData(self, index, value, role):
        if not index.isValid():
            return False
        handle = self.handle(index)
        
        if role == QtCore.Qt.EditRole:
            newName = str(value.toString())
            if newName == '':
                return False
            if handle.shortName() == newName:
                return False
            try:
                fn1 = handle.name()
                handle.rename(newName)
                fn2 = handle.name()
                self.layoutChanged()
                self.emit(QtCore.SIGNAL('dataChanged(const QModelIndex &, const QModelIndex &)'), index, index)
                return True
            except:
                printExc('Error while renaming file %s):' % fn1)
                return False
        else:
            print "setData ignoring role", int(role)
            return False

    def supportedDropActions(self):
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    def supportedDragActions(self):
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    #@profile
    def dropMimeData(self, data, action, row, column, parent):
        files = str(data.text()).split('\n')
        parent = self.handle(parent)
        
        ## Do error checking on the entire set before moving anything
        try:
            for f in files:
                handle = self.baseDir[f]
                if handle.parent() == parent:
                    print "Can not move %s (Same parent dir)"  % handle.name()
                    return False
        except:
            printExc("Error while trying to move files (don't worry, nothing moved yet)")
            return False
                    
                    
        ## Now attempt the moves
        try:
            for f in files:
                handle = self.baseDir[f]
                oldName = handle.name()
                if action == QtCore.Qt.MoveAction:
                    handle.move(parent)
                elif action == QtCore.Qt.CopyAction:
                    raise Exception("Copy not supported")
                self.layoutChanged()
            return True
        except:
            printExc("<<WARNING>> Error while moving files:")
            return False

    def layoutChanged(self):
        self.emit(QtCore.SIGNAL('layoutChanged()'))
        
    def insertRows(self, row, count, parent):
        #print "Not inserting row"
        return False
        
    def removeRows(self, row, count, parent):
        #print "not removing row"
        return False

    def insertRow(self, row, parent):
        #print "Not inserting row"
        return False
        
    def removeRow(self, row, parent):
        #print "not removing row"
        return False


    def mimeData(self, indexes):
        s = "\n".join([self.handle(i).name(relativeTo=self.baseDir) for i in indexes])
        m = QtCore.QMimeData()
        m.setText(s)
        return m
        
    def mimeTypes(self):
        return QtCore.QStringList(['text/plain'])
