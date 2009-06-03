# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.DataManager import *
import os

class DMModel(QtCore.QAbstractItemModel):
    """Based on DirTreeModel, used for displaying the contents of directories created and managed by DataManager"""
    def __init__(self, baseDirHandle=None, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)
        self.baseDir = baseDirHandle
        self.currentDir = None
        #self.paths = {}
        #self.dirCache = {}
        self.handles = {}
        
    def setBaseDirHandle(self, d):
        if self.baseDir is not None:
            self.unwatch(self.baseDir)
        self.baseDir = d
        self.watch(self.baseDir)
        self.layoutChanged()
        #self.clearCache()
        
    def setCurrentDir(self, d):
        self.currentDir = d
        
    def watch(self, handle):
        #if not isinstance(handle, QtCore.QObject):
            #raise Exception("Can not watch object of type %s" % str(type(d)))
        #print "watch", d, d.dirName()
        QtCore.QObject.connect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    def unwatch(self, handle):
        #if not isinstance(d, QtCore.QObject):
            #raise Exception("Can not unwatch object of type %s" % str(type(d)))
        QtCore.QObject.disconnect(handle, QtCore.SIGNAL('changed'), self.dirChanged)
        
    #def clearCache(self, path=None):
        #if path is None:
            #for k in self.handles:
                #self.unwatch(self.handles[k])
            ##self.dirCache = {}
            ##self.paths = {}
            #self.handles = {}
            #self.emit(QtCore.SIGNAL('layoutChanged()'))
            ##self.reset()
            #return
        #if path in self.dirCache:
            ##del self.dirCache[path]
            #rm = []
            #for k in self.paths:
                #if path == k[:len(path)]:
                   #rm.append(k)
            #for k in rm:
                ##del self.paths[k]
                #if k in self.dirCache:
                    #del self.dirCache[k]
                #self.unwatch(self.handles[k])
                #del self.handles[k]
        #else:
            #self.dirCache = {}
            #self.emit(QtCore.SIGNAL('layoutChanged()'))
            ##self.reset()
        
    #def pathKey(self, path):
        #return self.handleKey(self.baseDir[path])
        
    #def handleKey(self, handle):
        ### This function is very important.
        ### self.createIndex() requires a unique pointer for every item in the tree,
        ### so we must make sure that we keep a list of objects--1 for each item--
        ### since Qt won't protect them for us.
        
        ##path = os.path.normpath(path)
        #if handle not in self.handles:
            #self.handles[handle] = None
            #self.watch(handle)
            ##self.paths[path] = path  ## Index key must be stored locally--Qt won't protect it for us!
        #return handle
        
    #def isDir(self, path):
        #return self.baseDir.isDir(path)  #os.path.isdir(os.path.join(self.baseDir.name(), path))
        
    def dirChanged(self, path, change, *args):
        self.layoutChanged()
        ##print "Model handling directory change", path, change, args
        ##print "Sender path:", self.sender().name()
        #if change == 'children':
            #self.clearCache(self.sender().name())
        #elif change in ['renamed', 'deleted']:
            #self.clearCache(self.sender().parent().name())
        #elif change == 'moved':
            #print "Moved"
        ##print "dirChanged:", self.sender(), path
        
    #def dirIndex(self, dirHandle):
        #"""Return the index for a specific directory relative to its siblings"""
        ##if isinstance(dirName, DirHandle):
            ##dirName = dirName.name()
            
        ##if dirName == '' or dirName is None:
            ##return QtCore.QModelIndex()
        ##if not self.baseDir.exists(dirName):
            ##raise Exception("Dir %s does not exist" % dirName)
        #row = self.pathRow(dirHandle)
        ##return self.createIndex(row, 0, self.pathKey(dirName))
        #return self.createIndex(row, 0, self.pathKey(dirHandle))

    def handleIndex(self, handle):
        """Create an index from a file handle"""
        if not isinstance(handle, FileHandle):
            raise Exception("Function requires FileHandle or DirHandle as argument")
        #print handle, handle.parent()
        if handle not in self.handles:
            self.handles[handle] = None
            self.watch(handle)
        try:
            row = handle.parent().ls().index(handle.shortName())
        except:
            print handle.name(), handle.parent().name(), handle.parent().ls(), handle.shortName()
            raise
        return self.createIndex(row, 0, handle)
        
    def handle(self, index):
        """Return the file handle from an index"""
        if not index.isValid():
            return self.baseDir
        h = index.internalPointer()
        if h is None:
            return self.baseDir
        else:
            return h

    #def getFileName(self, index):
        #subDir = index.internalPointer()
        #if subDir is None:
            #return self.baseDir.name()
        #else:
            #return self.baseDir[subDir].name()
        
    #def findIndex(self, fileName):
        #fileName = os.path.normpath(fileName)
        #if self.baseDir.name() in fileName:
            #fileName = fileName.replace(self.baseDir.name(), '')
        #while len(fileName) > 0 and fileName[0] in ['/', '\\']:
            #fileName = fileName[1:]
        #return self.dirIndex(fileName)
        
    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        #if not parent.isValid():
            #path = ''
        #else:
            #path = parent.internalPointer()
        ph = self.handle(parent)
        childs = ph.ls()
        if row > len(childs):
            return QtCore.QModelIndex()
        dh = ph[childs[row]]
        return self.createIndex(row, column, dh)
            
    #def cmp(self, path, a, b):
        #a1 = os.path.join(self.baseDir.name(), path, a)
        #b1 = os.path.join(self.baseDir.name(), path, b)
        #aid = os.path.isdir(a1)
        #bid = os.path.isdir(b1)
        #if aid and not bid:
            #return -1
        #elif bid and not aid:
            #return 1
        #else:
            #return cmp(a,b)
            
    #def listdir(self, path):
        #if path not in self.dirCache:
            #c = filter(lambda s: s[0] != '.', os.listdir(os.path.join(self.baseDir.name(), path)))
            ##c.sort(lambda a,b: self.cmp(path, a, b))
            #self.dirCache[path] = c
        #return self.dirCache[path]
        
    #def pathRow(self, path):
        ##try:
        #base, last = os.path.split(os.path.normpath(path))
        #c = self.listdir(base)
        #return c.index(last)
        ##except:
            ##print "path", path, "base", base, "last", last
            ##raise
            
    def parent(self, index):
        #if not index.isValid():
            #return QtCore.QModelIndex()
        #path = os.path.normpath(index.internalPointer())
        #base, last = os.path.split(path)
        #if base == '/' or base == '':
            #return QtCore.QModelIndex()
        #pathStr = self.pathKey(base)
        ##print "Finding parent of", path, pathStr
        #try:
            #return self.createIndex(self.pathRow(pathStr), 0, pathStr)
        #except:
            #return QtCore.QModelIndex()
            
        p = self.handle(index).parent()
        if p is self.baseDir or self.baseDir.name() not in p.name():
            return QtCore.QModelIndex()
        return self.handleIndex(p)
            
    def rowCount(self, index=QtCore.QModelIndex()):
        dh = self.handle(index)
        if index.column() > 0:
            return 0
        if not dh.isDir():
            return 0
        return len(dh.ls())
        
        #if not parent.isValid():
            #p = ''
        #else:
            #p = parent.internalPointer()
        #p = os.path.normpath(p)
        #if not os.path.isdir(os.path.join(self.baseDir.name(), p)):
            #return 0
        #c = self.listdir(p)
        #return len(c)
            
    def columnCount(self, index):
        return 1
    
    def data(self, index, role):
        if not index.isValid():
            return QtCore.QVariant()
        dh = self.handle(index)
        ph = dh.parent()
        #path = os.path.normpath(index.internalPointer())
        #base, last = os.path.split(path)
        #fullPath = os.path.join(self.baseDir.name(), path)
        #parent = self.baseDir.getDir(os.path.join(self.baseDir.name(), base))
        
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
            else:
                ret = QtCore.QVariant()
        elif role == QtCore.Qt.FontRole:
            info = dh.info()
            if ('important' in info) and (info['important'] is True):
                ret = QtGui.QFont()
                ret.setWeight(QtGui.QFont.Bold)
            else:
                ret = QtCore.QVariant()
        else:
            ret = QtCore.QVariant()
        return QtCore.QVariant(ret)

    def flags(self, index):
        defaults = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable
        if index is None:
            return None
        if not index.isValid():
            return defaults  | QtCore.Qt.ItemIsDropEnabled
        dh = self.handle(index)
        #path = os.path.normpath(index.internalPointer())
        #fullPath = os.path.join(self.baseDir.name(), path)
        if dh.isDir():
            return defaults | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled
        else:
            return defaults | QtCore.Qt.ItemIsDragEnabled
            
    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant("Files")
        return QtCore.QVariant()
        
    def setData(self, index, value, role):
        if not index.isValid():
            return False
        handle = self.handle(index)
        
        if role == QtCore.Qt.EditRole:
            newName = str(value.toString())
            if newName == '':
                return False
            #dh = self.baseDir[os.path.normpath(index.internalPointer())]
            
            #fn = os.path.join(self.baseDir.name(), fn)
            #dirName = os.path.split(fn)[0]
            #fn2 = os.path.join(dirName, newName)
            if handle.shortName() == newName:
                return False
            try:
                #dh = self.baseDir.getDir(base)
                
                ## request that the datahandler rename the file so meta info stays in sync
                #dh.rename(fn, newName)
                #os.rename(fn, fn2)
                
                fn1 = handle.name()
                handle.rename(newName)
                fn2 = handle.name()
                self.layoutChanged()
               #self.clearCache(dh.parent().name(relativeTo=self.baseDir))
                
                ## Inform anyone interested that the file name has changed
                #fn1 = os.path.join(dh.name(), fn)
                #fn2 = os.path.join(dh.name(), newName)
                #self.emit(QtCore.SIGNAL('fileRenamed'), fn1, fn2)
                self.emit(QtCore.SIGNAL('dataChanged(const QModelIndex &, const QModelIndex &)'), index, index)
                #print "Data changed, editable:", int(self.flags(index))
                return True
            except:
                sys.excepthook(*sys.exc_info())
                print fn1, fn2
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
        parent = self.handle(parent)
        
        ## Do error checking on the entire set before moving anything
        try:
            for f in files:
                #fn = os.path.join(self.baseDir.name(), f)
                handle = self.baseDir[f]
                if handle.parent() == parent:
                    print "Can not move %s (Same parent dir)"  % handle.name()
                    return False
        except:
            sys.excepthook(*sys.exc_info())
            return False
                    
                    
        ## Now attempt the moves
        try:
            for f in files:
                handle = self.baseDir[f]
                #fullName = os.path.join(self.baseDir.name(), f)
                #oldDirName, name = os.path.split(f)
                #newDirName = os.path.join(self.baseDir.name(), parent.internalPointer())
                oldName = handle.name()
                #print handle.name(), parent.name()
                #raise Exception()
                #if newDirName is None:  ## Move to baseDir
                    #newDirName = ''
                #newName = os.path.join(self.baseDir.name(), newDirName, os.path.split(f)[1])
                #os.rename(fullName, newName)
                if action == QtCore.Qt.MoveAction:
                    #oldDir = self.baseDir.getDir(oldDirName)
                    #newDir = self.baseDir.getDir(newDirName)
                    #oldDir.move(name, newDir)
                    handle.move(parent)
                    ##os.rename(fullName, newName)
                    #self.emit(QtCore.SIGNAL('fileRenamed(PyQt_PyObject, PyQt_PyObject)'), oldName, handle.name())
                elif action == QtCore.Qt.CopyAction:
                    raise Exception("Copy not supported")
                    #os.copy(fullName, newName)
                #self.clearCache()
                #self.emitTreeChanged(os.path.split(f)[0])
                #self.emitTreeChanged(parent.internalPointer())
                #self.emit(QtCore.SIGNAL('layoutChanged()'))
                self.layoutChanged()
            return True
        except:
            sys.excepthook(*sys.exc_info())
            return False

    def layoutChanged(self):
        self.emit(QtCore.SIGNAL('layoutChanged()'))

    #def emitTreeChanged(self, dirName):
        #root = self.dirIndex(dirName)
        #ch1 = self.index(0,0,root)
        #numc = self.rowCount(root)
        #ch2 = self.index(numc-1, 0, root)
        ##print "emit changed:", dirName, ch1, ch2
        #self.emit(QtCore.SIGNAL('dataChanged(const QModelIndex &, const QModelIndex &)'), ch1, ch2)
        
        
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
