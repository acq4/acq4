# -*- coding: utf-8 -*-
import threading, os, re, sys
##  import fcntl  ## linux only?
from lib.util.functions import strncmp
from lib.util.configfile import *
from lib.util.MetaArray import MetaArray
from lib.util.advancedTypes import Locker
import lib.util.ptime as ptime
from PyQt4 import QtCore

class DataManager(QtCore.QObject):
    """Class for creating and caching DirHandle objects to make sure there is only one manager object per file/directory. 
    This class is (supposedly) thread-safe.
    """
    
    CREATED = False
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        if DataManager.CREATED:
            raise Exception("Attempted to create more than one DataManager!")
        DataManager.CREATED = True
        self.cache = {}
        self.lock = threading.RLock()
        
    def getDirHandle(self, dirName, create=False):
        l = Locker(self.lock)
        dirName = os.path.abspath(dirName)
        if not (create or os.path.isdir(dirName)):
            if not os.path.exists(dirName):
                raise Exception("Directory %s does not exist" % dirName)
            else:
                raise Exception("Not a directory: %s" % dirName)
        if dirName not in self.cache:
            self._addHandle(dirName, DirHandle(dirName, self, create=create))
        return self.cache[dirName]
        
    def getFileHandle(self, fileName):
        l = Locker(self.lock)
        fileName = os.path.abspath(fileName)
        if not os.path.isfile(fileName):
            if not os.path.exists(fileName):
                raise Exception("File %s does not exist" % fileName)
            else:
                raise Exception("Not a regular file: %s" % fileName)
        if fileName not in self.cache:
            self._addHandle(fileName, FileHandle(fileName, self))
        return self.cache[fileName]
        
    def getHandle(self, fileName):
        try:
            return self.getFileHandle(fileName)
        except:
            return self.getDirHandle(fileName)

    def _addHandle(self, dirName, handle):
        """Cache a handle and watch it for changes"""
        self.cache[dirName] = handle
        QtCore.QObject.connect(handle, QtCore.SIGNAL('changed'), self._handleChanged)
        
    def _handleChanged(self, handle, change, *args):
        l = Locker(self.lock)
        #print "Manager handling changes", handle, change, args
        if change == 'renamed' or change == 'moved':
            oldName = args[0]
            newName = args[1]
            #print oldName, newName
            ## Inform all children that they have been moved and update cache
            tree = self._getTree(oldName)
            #print "  Affected handles:", tree
            for h in tree:
                ## Update key to cached handle
                newh = os.path.abspath(os.path.join(newName, h[len(oldName+os.path.sep):]))
                #print "update key %s, (newName=%s, )" % (newh, newName)
                self.cache[newh] = self.cache[h]
                
                ## If the change originated from h's parent, inform it that this change has occurred.
                if h != oldName:
                    #print "  Informing", h, oldName
                    self.cache[h]._parentMoved(oldName, newName)
                del self.cache[h]
            
        if change == 'deleted':
            oldName = args[0]
            del self.cache[oldName]

            ## Inform all children that they have been deleted and remove from cache
            tree = self._getTree(oldName)
            for path in tree:
                self.cache[path]._deleted()
                del self.cache[path]
                

    def _getTree(self, parent):
        """Return the entire list of cached handles which are children or grandchildren of this handle"""
        
        ## If handle has no children, then there is no need to search for its tree.
        tree = [parent]
        ph = self.cache[parent]
        prefix = parent + os.path.sep
        
        if ph.hasChildren():
            for h in self.cache:
                #print "    tree checking", h[:len(parent)], parent + os.path.sep
                #print "    tree checking:"
                #print "       ", parent
                #print "       ", h
                #if self.cache[h].isGrandchildOf(ph):
                if h[:len(prefix)] == prefix:
                    #print "        hit"
                    tree.append(h)
        return tree

class FileHandle(QtCore.QObject):
    def __init__(self, path, manager):
        QtCore.QObject.__init__(self)
        self.manager = manager
        self.path = os.path.abspath(path)
        self.parentDir = None
        self.lock = threading.RLock()
        
    def name(self, relativeTo=None):
        self.checkDeleted()
        l = Locker(self.lock)
        path = self.path
        if relativeTo == self:
            path = ''
        elif relativeTo is not None:
            rpath = relativeTo.name()
            if not self.isGrandchildOf(relativeTo):
                raise Exception("Path %s is not child of %s" % (path, rpath))
            return path[len(rpath + os.path.sep):]
        return path
        
    def shortName(self):
        self.checkDeleted()
        return os.path.split(self.name())[1]
        
    #def name(self, full=True):
        #if full:
            #return self.path
        #else:
            #return os.path.split(self.path)[1]
        
    def parent(self):
        self.checkDeleted()
        l = Locker(self.lock)
        if self.parentDir is None:
            dirName = os.path.split(self.name())[0]
            self.parentDir = self.manager.getDirHandle(dirName)
        return self.parentDir
        
    def info(self):
        self.checkDeleted()
        return self.parent()._fileInfo(self.shortName())
        
    def setInfo(self, info):
        """Set meta-information for this file. Updates all keys specified in info, leaving others unchanged."""
        self.checkDeleted()
        self.emitChanged('meta')
        return self.parent()._setFileInfo(self.shortName(), info)
        
    def isManaged(self):
        self.checkDeleted()
        return self.parent().isManaged(self.shortName())
        
    def move(self, newDir):
        self.checkDeleted()
        l = Locker(self.lock)
        oldDir = self.parent()
        fn1 = self.name()
        name = self.shortName()
        fn2 = os.path.join(newDir.name(), name)
        if os.path.exists(fn2):
            raise Exception("Destination file %s already exists." % fn2)
        os.rename(fn1, fn2)
        self.path = fn2
        if oldDir.isManaged() and newDir.isManaged():
            newDir.addFile(name, info=oldDir._fileInfo(name))
        elif newDir.isManaged():
            newDir.addFile(name)
        if oldDir.isManaged():
            oldDir.forget(name)
        self.emitChanged('moved', fn1, fn2)
        
    def rename(self, newName):
        self.checkDeleted()
        l = Locker(self.lock)
        parent = self.parent()
        fn1 = self.name()
        oldName = self.shortName()
        fn2 = os.path.join(parent.name(), newName)
        if os.path.exists(fn2):
            raise Exception("Destination file %s already exists." % fn2)
        #print "rename", fn1, fn2
        os.rename(fn1, fn2)
        self.path = fn2
        if parent.isManaged():
            parent.addFile(newName, info=parent._fileInfo(oldName))
            parent.forget(oldName)
        self.emitChanged('renamed', fn1, fn2)
        
    def delete(self):
        self.checkDeleted()
        l = Locker(self.lock)
        parent = self.parent()
        fn1 = self.name()
        oldName = self.shortName()
        os.remove(fn1)
        self.path = None
        if self.isManaged():
            parent.forget(oldName)
        self.emitChanged('deleted', fn1)
        
    def read(self):
        self.checkDeleted()
        pass
        
    def emitChanged(self, change, *args):
        self.emit(QtCore.SIGNAL('changed'), self.name(), change, *args)
    
    def hasChildren(self):
        self.checkDeleted()
        return False
    
    def _parentMoved(self, oldDir, newDir):
        """Inform this object that it has been moved as a result of its (grand)parent having moved."""
        prefix = oldDir + os.path.sep
        if self.path[:len(prefix)] != prefix:
            raise Exception("File %s is not in moved tree %s, should not update!" % (self.path, oldDir))
        subName = self.path[len(prefix):]
        #while subName[0] == os.path.sep:
            #subName = subName[1:]
        newName = os.path.join(newDir, subName)
        #print "===", oldDir, newDir, subName, newName
        if not os.path.exists(newName):
            raise Exception("File %s does not exist." % newName)
        self.path = newName
        #print "parent of %s changed" % self.name()
        self.emitChanged('parent')

    def checkDeleted(self):
        if self.path is None:
            raise Exception("File has been deleted.")

    def isDir(self, path=None):
        return False
        
    def _deleted(self):
        self.path = None
    
    def isGrandchildOf(self, grandparent):
        """Return true if this files is anywhere in the tree beneath grandparent."""
        gname = grandparent.name() + os.path.sep
        return self.name()[:len(gname)] == gname
    
    #def getFile(self, fileName):
        #l = Locker(self.lock)
        
        #info = self.fileInfo(fileName)
        #typ = info['__object_type__']
        #cls = self.getFileClass(typ)
        #return cls.fromFile(fileName=os.path.join(self.path, fileName))
        ##return MetaArray(file=os.path.join(self.path, fileName))

    #def getFileClass(self, className):
        #mod = __import__('lib.filetypes.%s' % modName, fromlist=['*'])
        #return getattr(mod, modName)






class DirHandle(FileHandle):
    def __init__(self, path, manager, create=False):
        FileHandle.__init__(self, path, manager)
        self._index = None
        
        if not os.path.isdir(path):
            if create:
                os.mkdir(path)
                self.createIndex()
            else:
                raise Exception("Directory %s does not exist." % path)
        
        if os.path.isfile(self._indexFile()):
            ## read the index and cache it.
            self._readIndex()
        else:
            ## If directory is unmanaged, just leave it that way.
            pass
        
    def __repr__(self):
        return "<%s '%s'>" % (self.__class__.__name__, self.name())
        
    def __del__(self):
        pass
    
    def _indexFile(self):
        return os.path.join(self.path, '.index')
    
    def _logFile(self):
        return os.path.join(self.path, '.log')
    
    def __getitem__(self, item):
        #print self.name(), " -> ", item
        while item[0] == os.path.sep:
            item = item[1:]
        fileName = os.path.join(self.name(), item)
        return self.manager.getHandle(fileName)
    
    
    def createIndex(self):
        if self.isManaged():
            raise Exception("Directory is already managed!")
        self._writeIndex({'.': {}})
        
    def logMsg(self, msg, tags={}):
        """Write a message into the log for this directory."""
        l = Locker(self.lock)
        if type(tags) is not dict:
            raise Exception("tags argument must be a dict")
        tags['__timestamp__'] = ptime.time()
        tags['__message__'] = str(msg)
        
        fd = open(self._logFile(), 'a')
        #fcntl.flock(fd, fcntl.LOCK_EX)
        fd.write("%s\n" % repr(tags))
        fd.close()
        self.emitChanged('log', tags)
        
    def readLog(self, recursive=0):
        """Return a list containing one dict for each log line"""
        l = Locker(self.lock)
        logf = self._logFile()
        if not os.path.exists(logf):
            log = []
        else:
            try:
                fd = open(logf, 'r')
                lines = fd.readlines()
                fd.close()
                log = map(eval, lines)
            except:
                print "****************** Error reading log file! *********************"
                raise
        
        if recursive > 0:
            for d in self.subDirs():
                dh = self[d]
                subLog = dh.readLog(recursive=recursive-1)
                for msg in subLog:
                    if 'subdir' not in msg:
                        msg['subdir'] = ''
                    msg['subdir'] = os.path.join(dh.shortName(), msg['subdir'])
                log  = log + subLog
            log.sort(lambda a,b: cmp(a['__timestamp__'], b['__timestamp__']))
        
        return log
        
    def subDirs(self):
        l = Locker(self.lock)
        ls = self.ls()
        subdirs = filter(lambda d: os.path.isdir(os.path.join(self.name(), d)), ls)
        return subdirs
    
    def mkdir(self, name, autoIncrement=False, info={}):
        """Create a new subdirectory, return a new DirHandle object. If autoIndex is true, add a number to the end of the dir name if it already exists."""
        l = Locker(self.lock)
        
        if autoIncrement:
            fullName = name+"_000"
        else:
            fullName = name
            
        if autoIncrement:
            files = os.listdir(self.path)
            files = filter(lambda f: re.match(name + r'_\d+$', f), files)
            if len(files) > 0:
                files.sort()
                maxVal = int(files[-1][-3:])
                fullName = name + "_%03d" % (maxVal+1)
            
        newDir = os.path.join(self.path, fullName)
        if os.path.isdir(newDir):
            raise Exception("Directory %s already exists." % newDir)
        
        ## Create directory
        ndm = self.manager.getDirHandle(newDir, create=True)
        t = ptime.time()
        
        ## Mark the creation time in the parent directory so it can sort its full list of files without 
        ## going into each subdir
        self._setFileInfo(fullName, {'__timestamp__': t})
        
        ## create the index file in the new directory
        info['__timestamp__'] = t
        ndm.setInfo(info)
        self.emitChanged('children', newDir)
        return ndm
        
    def getDir(self, subdir, create=False, autoIncrement=False):
        """Return a DirHandle for the specified subdirectory. If the subdir does not exist, it will be created only if create==True"""
        l = Locker(self.lock)
        ndir = os.path.join(self.path, subdir)
        if os.path.isdir(ndir):
            return self.manager.getDirHandle(ndir)
        else:
            if create:
                return self.mkdir(subdir, autoIncrement=autoIncrement)
            else:
                raise Exception('Directory %s does not exist.' % ndir)
        
    def dirExists(self, dirName):
        return os.path.isdir(os.path.join(self.path, dirName))
            
    def ls(self):
        """Return a list of all files in the directory"""
        l = Locker(self.lock)
        #self._readIndex()
        #ls = self.index.keys()
        #ls.remove('.')
        ls = os.listdir(self.name())
        for i in ['.index', '.log']:
            if i in ls:
                ls.remove(i)
        ls.sort(self._cmpFileTimes)
        return ls
    
    def _cmpFileTimes(self, a, b):
        l = Locker(self.lock)
        t1 = t2 = None
        if self.isManaged():
            index = self._readIndex()
            if a in index:
                t1 = index[a]['__timestamp__']
            if b in index:
                t2 = index[b]['__timestamp__']
        if t1 is None:
            t1 = os.path.getctime(os.path.join(self.name(), a))
        if t2 is None:
            t2 = os.path.getctime(os.path.join(self.name(), b))
        #print "compare", a, b, t1, t2
        return cmp(t1, t2)
    
    def isGrandparentOf(self, child):
        """Return true if child is anywhere in the tree below this directory."""
        return child.isGrandchildOf(self)
    
    def hasChildren(self):
        return len(self.ls()) > 0
    
    def info(self):
        return self._fileInfo('.')
    
    def _fileInfo(self, file):
        """Return a dict of the meta info stored for file"""
        l = Locker(self.lock)
        #if file != '.' and self.isDir(file):  ## directory meta-info is stored within the directory, not in the parent.
            #return self.getDir(file).fileInfo('.')
        
        index = self._readIndex()
        if index.has_key(file):
            return index[file]
        else:
            raise Exception("File %s is not indexed" % file)
    
    def isDir(self, path=None):
        l = Locker(self.lock)
        #fn = os.path.abspath(os.path.join(self.path, fileName))
        #return os.path.isdir(fn)
        if path is None:
            return True
        else:
            return self[path].isDir()
        
    def isFile(self, fileName):
        l = Locker(self.lock)
        fn = os.path.abspath(os.path.join(self.path, fileName))
        return os.path.isfile(fn)
        
    
    def writeFile(self, obj, fileName, info=None, autoIncrement=False):
        """Write a file to this directory using obj.write(fileName), store info in the index."""
        if info is None:
            info = {}   ## never put {} in the function default
            
        if not hasattr(obj, 'write') or not callable(obj.write):
            raise Exception("Can not create file from object of type %s" % str(type(obj)))
        
        t = ptime.time()
        l = Locker(self.lock)
        name = fileName
        fullFn = os.path.join(self.path, name)
        appendInfo = False

        if autoIncrement:
            appendInfo = True
            d = 0
            base, ext = os.path.splitext(name)
            while True:
                name = "%s_%04d%s" % (base, d, ext)
                fullFn = os.path.join(self.path, name)
                if not os.path.exists(fullFn):
                    break
                d += 1
        #fd = open(fn, 'w')
        #fcntl.flock(fd, fcntl.LOCK_EX)
        
        obj.write(fullFn)
        #print "Wrote file %s" % fullFn
        
        #fd.close()
        
        if not info.has_key('__object_type__'):
            if hasattr(obj, 'typeName'):
                info['__object_type__'] = obj.typeName()
            else:
                info['__object_type__'] = type(obj).__name__
        if not info.has_key('__timestamp__'):
            info['__timestamp__'] = t
        self._setFileInfo(name, info, append=appendInfo)
        self.emitChanged('children', fileName)
        return name
    
    def addFile(self, fileName, info={}, protect=False):
        """Add a pre-existing file into the index. Overwrites any pre-existing info for the file unless protect is True"""
        #print "Adding file %s to index" % fileName
        l = Locker(self.lock)
        index = self._readIndex()
        fn = os.path.join(self.path, fileName)
        if not (os.path.isfile(fn) or os.path.isdir(fn)):
            raise Exception("File %s does not exist." % fn)
            
        append = True
        if fileName in index:
            append = False
            if protect:
                raise Exception("File %s is already indexed." % fileName)

        self._setFileInfo(fileName, info, append=append)
        self.emitChanged('children', fileName)
    
    def forget(self, fileName):
        l = Locker(self.lock)
        if not self.isManaged(fileName):
            raise Exception("Can not forget %s, not managed" % fileName)
        index = self._readIndex(lock=False)
        index.remove(fileName)
        self._writeIndex(index, lock=False)
        self.emitChanged('children', fileName)
        
    def isManaged(self, fileName=None):
        l = Locker(self.lock)
        if self._index is None:
            return False
        if fileName is None:
            return True
        else:
            return (fileName in self._readIndex())

    
    def setInfo(self, *args):
        self._setFileInfo('.', *args)
        
        
        
        
    #def _setFileAttr(self, fileName, attr, value):
        #"""Set a single meta-info attribute for fileName"""
        #l = Locker(self.lock)
        #if fileName != '.' and self.isDir(fileName):
            #self.setFileAttr('.', attr, value)
        #else:
            #if not self.index.has_key(fileName):
                #self.setFileInfo(fileName, {attr: value}, append=True)
            #else:
                ##fd = open(self.indexFile, 'r')
                ##fcntl.flock(fd, fcntl.LOCK_EX)
                #self._readIndex(lock=False)
                #self.index[fileName][attr] = value
                #self._writeIndex(lock=False)
                ##fd.close()
        #self.emitChanged(fileName)
        
    def parent(self):
        l = Locker(self.lock)
        #pdir = re.sub(r'/[^/]+/$', '', self.path)
        pdir = os.path.normpath(os.path.join(self.path, '..'))
        return self.manager.getDirHandle(pdir)

        

    def exists(self, name):
        l = Locker(self.lock)
        try:
            fn = os.path.abspath(os.path.join(self.path, name))
        except:
            print self.path, name
            raise
        return os.path.exists(fn)

    def _setFileInfo(self, fileName, info, append=False):
        """Set or update meta-information array for fileName."""
        l = Locker(self.lock)
        
        #fd = open(self.indexFile, 'r')
        #fcntl.flock(fd, fcntl.LOCK_EX)
        #if fileName != '.' and self.isDir(fileName):
            #self.getDir(fileName)._setFileInfo('.', info)
        #else:
        #print "setFileInfo", self.name(), fileName, info, append
        if append:
            #print "appending"
            appendConfigFile({fileName: info}, self._indexFile())
        else:
            index = self._readIndex(lock=False)
            if fileName not in index:
                #print fileName, "not in", self.index
                index[fileName] = {}
            for k in info:
                #print "%s Setting %s = %s for file %s"  % (self.name(), k, info[k], fileName)
                index[fileName][k] = info[k]
            #self.index[fileName] = info   ## Update dict, do not completely overwrite.
            self._writeIndex(index, lock=False)
        #fd.close()
        self.emitChanged('meta', fileName)
        
    def _readIndex(self, lock=True):
        l = Locker(self.lock)
        #fd = open(self.indexFile)
        #if lock:
            #pass
            #fcntl.flock(fd, fcntl.LOCK_EX)
        indexFile = self._indexFile()
        if self._index is None or os.path.getmtime(indexFile) != self._indexMTime:
            if not os.path.isfile(indexFile):
                raise Exception("Directory '%s' is not managed!" % (self.name()))
            try:
                #print "Reading index", indexFile
                self._index = readConfigFile(indexFile)
                self._indexMTime = os.path.getmtime(indexFile)
            except:
                print "***************Error while reading index file %s!*******************" % indexFile
                raise
        return self._index
            
        #fd.close()
        
    def _writeIndex(self, newIndex, lock=True):
        l = Locker(self.lock)
        
        #if not self.isManaged():
            #raise Exception("Directory is not managed!")
        #fd = open(self.indexFile, 'w')
        #if lock:
            #pass
#            fcntl.flock(fd, fcntl.LOCK_EX)
        #fd.write(str(self.index))
        #fd.close()
        writeConfigFile(newIndex, self._indexFile())
        self._index = newIndex
        self._indexMTime = os.path.getmtime(self._indexFile())
        
        
    #def _parentMoved(self, oldDir, newDir):
        #"""Inform this object that it has been moved as a result of its (grand)parent having moved."""
        #if self.path[len(oldDir):] != oldDir:
            #raise Exception("File %s is not in moved tree %s, should not update!" % (self.path, oldDir))
        #subName = self.path[len(oldDir):]
        #newName = os.path.join(newDir, subName)
        #if not os.path.isdir(newName):
            #raise Exception("File %s does not exist." % newName)
        #self.path = fileName


