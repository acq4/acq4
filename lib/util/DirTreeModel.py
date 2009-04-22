# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import traceback, os, sys

    


class DirTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, baseDir, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)
        print "dirTree", baseDir
        self.baseDir = baseDir
        self.paths = {}
        self.dirCache = {}
        
    def clearCache(self, path=None):
        if path is None:
            self.dirCache = {}
            return
        if path in self.dirCache:
            del self.dirCache[path]
        else:
            self.dirCache = {}
        
    def pathKey(self, path):
        ## This function is very important.
        ## self.createIndex() requires a unique pointer for every item in the tree,
        ## so we must make sure that we keep a list of objects--1 for each item--
        ## since Qt won't protect them for us.
        
        path = os.path.normpath(path)
        if path not in self.paths:
            self.paths[path] = path  ## Index key must be stored locally--Qt won't protect it for us!
        return self.paths[path]
        
    def dirIndex(self, dirName):
        if dirName == '' or dirName is None:
            return QtCore.QModelIndex()
        if not os.path.exists(os.path.join(self.baseDir, dirName)):
            raise Exception("Dir %s does not exist" % dirName)
        row = self.pathRow(dirName)
        return self.createIndex(row, 0, self.pathKey(dirName))
        
    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        if not parent.isValid():
            path = ''
        else:
            path = parent.internalPointer()
        c = self.listdir(path)
        if row >= len(c):
            return QtCore.QModelIndex()
        path = os.path.join(path, c[row])
        pathStr = self.pathKey(path)
        return self.createIndex(row, column, pathStr)
            
    def cmp(self, path, a, b):
        a1 = os.path.join(self.baseDir, path, a)
        b1 = os.path.join(self.baseDir, path, b)
        aid = os.path.isdir(a1)
        bid = os.path.isdir(b1)
        if aid and not bid:
            return -1
        elif bid and not aid:
            return 1
        else:
            return cmp(a,b)
            
    def listdir(self, path):
        if path not in self.dirCache:
            c = filter(lambda s: s[0] != '.', os.listdir(os.path.join(self.baseDir, path)))
            c.sort(lambda a,b: self.cmp(path, a, b))
            self.dirCache[path] = c
        return self.dirCache[path]
        
    def pathRow(self, path):
        try:
            base, last = os.path.split(os.path.normpath(path))
            c = self.listdir(base)
            return c.index(last)
        except:
            print "path", path, "base", base, "last", last
            raise
            
    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        path = os.path.normpath(index.internalPointer())
        base, last = os.path.split(path)
        if base == '/' or base == '':
            return QtCore.QModelIndex()
        pathStr = self.pathKey(base)
        return self.createIndex(self.pathRow(pathStr), 0, pathStr)
        
    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            p = ''
        else:
            p = parent.internalPointer()
        p = os.path.normpath(p)
        if not os.path.isdir(os.path.join(self.baseDir, p)):
            return 0
        c = self.listdir(p)
        return len(c)
            
    def columnCount(self, index):
        return 1
    
    def data(self, index, role):
        if not index.isValid():
            return QtCore.QVariant()
        path = os.path.normpath(index.internalPointer())
        base, last = os.path.split(path)
        fullPath = os.path.join(self.baseDir, path)
        if role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
            ret = last
        elif role == QtCore.Qt.TextColorRole:
            if os.path.isdir(fullPath):
                ret = QtGui.QColor(0,0,100)
            else:
                ret = QtGui.QColor(0,0,0)
        else:
            ret = QtCore.QVariant()
        return QtCore.QVariant(ret)

    def flags(self, index):
        #return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable
        if index is None:
            return None
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDropEnabled
        path = os.path.normpath(index.internalPointer())
        fullPath = os.path.join(self.baseDir, path)
        if os.path.isdir(fullPath):
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled
            
    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant("Files")
        return QtCore.QVariant()
        
    def setData(self, index, value, role):
        if not index.isValid():
            return False
        if role == QtCore.Qt.EditRole:
            newName = str(value.toString())
            if newName == '':
                return False
            fn = os.path.normpath(index.internalPointer())
            fn = os.path.join(self.baseDir, fn)
            dirName = os.path.split(fn)[0]
            fn2 = os.path.join(dirName, newName)
            if fn == fn2:
                return False
            try:
                os.rename(fn, fn2)
                self.clearCache(dirName)
                self.emit(QtCore.SIGNAL('dataChanged(const QModelIndex &, const QModelIndex &)'), index, index)
                #print "Data changed, editable:", int(self.flags(index))
                return True
            except:
                print fn, fn2
                sys.excepthook(*sys.exc_info())
                return False
        else:
            print "setData ignoring role", int(role)
            return False

    def supportedDropActions(self):
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    def supportedDragActions(self):
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    #def insertRows(self, row, count, parent):
        #print "inasertRows"
        #return False
        
    #def insertColumns(self, column, count, parent):
        #return False

    def dropMimeData(self, data, action, row, column, parent):
        files = str(data.text()).split('\n')
        
        for f in files:
            fn = os.path.join(self.baseDir, f)
            if not os.path.exists(fn):
                print "Can not move %s (File does not exist)" % fn
                return False
            if os.path.split(f)[0] == parent.internalPointer():
                print "Can not move %s (Same parent dir)"  % fn
                return False
        try:
            for f in files:
                fullName = os.path.join(self.baseDir, f)
                subDir = parent.internalPointer()
                if subDir is None:
                    subDir = ''
                newName = os.path.join(self.baseDir, subDir, os.path.split(f)[1])
                #os.rename(fullName, newName)
                if action == QtCore.Qt.MoveAction:
                    os.rename(fullName, newName)
                elif action == QtCore.Qt.CopyAction:
                    os.copy(fullName, newName)
                self.clearCache()
                self.emitTreeChanged(os.path.split(f)[0])
                self.emitTreeChanged(parent.internalPointer())
            return True
        except:
            sys.excepthook(*sys.exc_info())
            return False
        
    def emitTreeChanged(self, dirName):
        root = self.dirIndex(dirName)
        ch1 = self.index(0,0,root)
        numc = self.rowCount(root)
        ch2 = self.index(numc-1, 0, root)
        print "emit changed:", dirName, ch1, ch2
        self.emit(QtCore.SIGNAL('dataChanged(const QModelIndex &, const QModelIndex &)'), ch1, ch2)
        
        
    def insertRows(self, row, count, parent):
        print "Not inserting row"
        return False
        
    def removeRows(self, row, count, parent):
        print "not removing row"
        return False

    def insertRow(self, row, parent):
        print "Not inserting row"
        return False
        
    def removeRow(self, row, parent):
        print "not removing row"
        return False


    def mimeData(self, indexes):
        s = "\n".join([i.internalPointer() for i in indexes])
        m = QtCore.QMimeData()
        m.setText(s)
        return m
        
    def mimeTypes(self):
        return QtCore.QStringList(['text/plain'])
        
if __name__ == '__main__':
    app = QtGui.QApplication([])
    w = QtGui.QMainWindow()
    t = QtGui.QTreeView()
    m = SimpleTreeModel(sys.argv[1])
    t.setModel(m)
    w.setCentralWidget(t)
    w.show()
    app.exec_()
