# -*- coding: utf-8 -*-
"""
DataManager.py - DataManager, FileHandle, and DirHandle classes 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

These classes implement a data management system that allows modules
to easily store and retrieve data files along with meta data. The objects
probably only need to be created via functions in the Manager class.
"""

from __future__ import with_statement
import threading, os, re, sys
##  import fcntl  ## linux only?
from lib.util.functions import strncmp
from lib.util.configfile import *
from metaarray import MetaArray
import time
from lib.util.Mutex import Mutex, MutexLocker
from PyQt4 import QtCore
#from lib.filetypes.FileType import *
import lib.filetypes as filetypes
from debug import *

def abspath(fileName):
    """Return an absolute path string which is guaranteed to uniquely identify a file."""
    return os.path.normcase(os.path.abspath(fileName))
    



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
        #self.lock = threading.RLock()
        self.lock = Mutex(QtCore.QMutex.Recursive)
        
    def getDirHandle(self, dirName, create=False):
        with MutexLocker(self.lock):
            dirName = os.path.abspath(dirName)
            if not (create or os.path.isdir(dirName)):
                if not os.path.exists(dirName):
                    raise Exception("Directory %s does not exist" % dirName)
                else:
                    raise Exception("Not a directory: %s" % dirName)
            if not self._cacheHasName(dirName):
                self._addHandle(dirName, DirHandle(dirName, self, create=create))
            return self._getCache(dirName)
        
    def getFileHandle(self, fileName):
        with MutexLocker(self.lock):
            fileName = os.path.abspath(fileName)
            if not os.path.isfile(fileName):
                if not os.path.exists(fileName):
                    raise Exception("File %s does not exist" % fileName)
                else:
                    raise Exception("Not a regular file: %s" % fileName)
            if not self._cacheHasName(fileName):
                self._addHandle(fileName, FileHandle(fileName, self))
            return self._getCache(fileName)
        
    def getHandle(self, fileName):
        try:
            return self.getFileHandle(fileName)
        except:
            return self.getDirHandle(fileName)

    def _addHandle(self, fileName, handle):
        """Cache a handle and watch it for changes"""
        self._setCache(fileName, handle)
        QtCore.QObject.connect(handle, QtCore.SIGNAL('changed'), self._handleChanged)
        
    def _handleChanged(self, handle, change, *args):
        with MutexLocker(self.lock):
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
                    self._setCache(newh, self._getCache(h))
                    
                    ## If the change originated from h's parent, inform it that this change has occurred.
                    if h != oldName:
                        #print "  Informing", h, oldName
                        self._getCache(h)._parentMoved(oldName, newName)
                    self._delCache(h)
                
            if change == 'deleted':
                oldName = args[0]
                self._delCache(oldName)

                ## Inform all children that they have been deleted and remove from cache
                tree = self._getTree(oldName)
                for path in tree:
                    self._getCache(path)._deleted()
                    self._delCache(path)
                

    def _getTree(self, parent):
        """Return the entire list of cached handles which are children or grandchildren of this handle"""
        
        ## If handle has no children, then there is no need to search for its tree.
        tree = [parent]
        ph = self._getCache(parent)
        prefix = os.path.normcase(os.path.join(parent, ''))
        
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

    def _getCache(self, name):
        return self.cache[abspath(name)]
        
    def _setCache(self, name, value):
        self.cache[abspath(name)] = value
        
    def _delCache(self, name):
        del self.cache[abspath(name)]
        
    def _cacheHasName(self, name):
        return abspath(name) in self.cache
        


class FileHandle(QtCore.QObject):
    def __init__(self, path, manager):
        QtCore.QObject.__init__(self)
        self.manager = manager
        self.path = os.path.abspath(path)
        self.parentDir = None
        #self.lock = threading.RLock()
        self.lock = Mutex(QtCore.QMutex.Recursive)
        
    def __repr__(self):
        return "<%s '%s'>" % (self.__class__.__name__, self.name())
        
    def name(self, relativeTo=None):
        self.checkDeleted()
        with MutexLocker(self.lock):
            path = self.path
            if relativeTo == self:
                path = ''
            elif relativeTo is not None:
                rpath = relativeTo.name()
                if not self.isGrandchildOf(relativeTo):
                    raise Exception("Path %s is not child of %s" % (path, rpath))
                return path[len(os.path.join(rpath, '')):]
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
        with MutexLocker(self.lock):
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
        with MutexLocker(self.lock):
            oldDir = self.parent()
            fn1 = self.name()
            name = self.shortName()
            fn2 = os.path.join(newDir.name(), name)
            if os.path.exists(fn2):
                raise Exception("Destination file %s already exists." % fn2)
            os.rename(fn1, fn2)
            oldDir._childChanged()
            newDir._childChanged()
            self.path = fn2
            self.parentDir = None
            if oldDir.isManaged() and newDir.isManaged():
                newDir.indexFile(name, info=oldDir._fileInfo(name))
            elif newDir.isManaged():
                newDir.indexFile(name)
            if oldDir.isManaged():
                oldDir.forget(name)
            self.emitChanged('moved', fn1, fn2)
        
    def rename(self, newName):
        self.checkDeleted()
        with MutexLocker(self.lock):
            parent = self.parent()
            fn1 = self.name()
            oldName = self.shortName()
            fn2 = os.path.join(parent.name(), newName)
            if os.path.exists(fn2):
                raise Exception("Destination file %s already exists." % fn2)
            #print "rename", fn1, fn2
            os.rename(fn1, fn2)
            self.parent()._childChanged()
            self.path = fn2
            if parent.isManaged():
                parent.indexFile(newName, info=parent._fileInfo(oldName))
                parent.forget(oldName)
            self.emitChanged('renamed', fn1, fn2)
        
    def delete(self):
        self.checkDeleted()
        with MutexLocker(self.lock):
            parent = self.parent()
            fn1 = self.name()
            oldName = self.shortName()
            os.remove(fn1)
            self.parent()._childChanged()
            self.path = None
            if self.isManaged():
                parent.forget(oldName)
            self.emitChanged('deleted', fn1)
        
    def read(self):
        self.checkDeleted()
        with MutexLocker(self.lock):
            typ = self.fileType()
            
            if typ is None:
                fd = open(self.name(), 'r')
                data = fd.read()
                fd.close()
            else:
                cls = filetypes.getFileType(typ)
                data = cls.read(self)
                #mod = __import__('lib.filetypes.%s' % typ, fromlist=['*'])
                #func = getattr(mod, 'fromFile')
                #data = func(fileName=self.name())
            
            return data
        
    def fileType(self):
        with MutexLocker(self.lock):
            info = self.info()
            
            ## Use the recorded object_type to read the file if possible.
            ## Otherwise, ask the filetypes to choose the type for us.
            if '__object_type__' not in info:
                typ = filetypes.suggestReadType(self)
            else:
                typ = info['__object_type__']
            return typ



    def emitChanged(self, change, *args):
        self.emit(QtCore.SIGNAL('changed'), self.name(), change, *args)
    
    def hasChildren(self):
        self.checkDeleted()
        return False
    
    def _parentMoved(self, oldDir, newDir):
        """Inform this object that it has been moved as a result of its (grand)parent having moved."""
        prefix = os.path.join(oldDir, '')
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
        self.parentDir = None
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
        gname = os.path.join(grandparent.name(), '')
        return self.name()[:len(gname)] == gname
    
    def write(self, data, **kwargs):
        self.parent().writeFile(data, self.shortName(), **kwargs)
        





class DirHandle(FileHandle):
    def __init__(self, path, manager, create=False):
        FileHandle.__init__(self, path, manager)
        self._index = None
        self.lsCache = None
        self.cTimeCache = {}
        
        if not os.path.isdir(self.path):
            if create:
                os.mkdir(self.path)
                self.createIndex()
            else:
                raise Exception("Directory %s does not exist." % self.path)
        
        if os.path.isfile(self._indexFile()):
            ## read the index and cache it.
            self._readIndex()
        else:
            ## If directory is unmanaged, just leave it that way.
            pass
        
        
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
        
    def logMsg(self, msg, tags=None):
        """Write a message into the log for this directory."""
        if tags is None:
            tags = {}
        with MutexLocker(self.lock):
            if type(tags) is not dict:
                raise Exception("tags argument must be a dict")
            tags['__timestamp__'] = time.time()
            tags['__message__'] = str(msg)
            
            fd = open(self._logFile(), 'a')
            #fcntl.flock(fd, fcntl.LOCK_EX)
            fd.write("%s\n" % repr(tags))
            fd.close()
            self.emitChanged('log', tags)
        
    def readLog(self, recursive=0):
        """Return a list containing one dict for each log line"""
        with MutexLocker(self.lock):
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
        with MutexLocker(self.lock):
            ls = self.ls()
            subdirs = filter(lambda d: os.path.isdir(os.path.join(self.name(), d)), ls)
            return subdirs
    
    def incrementFileName(self, fileName, useExt=True):
        """Given fileName.ext, finds the next available fileName_NNN.ext"""
        #p = Profiler('   increment:')
        files = self.ls()
        #p.mark('ls')
        if useExt:
            (fileName, ext) = os.path.splitext(fileName)
        else:
            ext = ''
        regex = re.compile(fileName + r'_(\d+)')
        files = filter(lambda f: regex.match(f), files)
        #p.mark('filter')
        if len(files) > 0:
            files.sort()
            maxVal = int(regex.match(files[-1]).group(1)) + 1
        else:
            maxVal = 0
        ret = fileName + ('_%03d' % maxVal) + ext
        #p.mark('done')
        #print "incremented name %s to %s" %(fileName, ret)
        return ret
    
    def mkdir(self, name, autoIncrement=False, info=None):
        """Create a new subdirectory, return a new DirHandle object. If autoIncrement is true, add a number to the end of the dir name if it already exists."""
        if info is None:
            info = {}
        with MutexLocker(self.lock):
            
            if autoIncrement:
                fullName = self.incrementFileName(name, useExt=False)
            else:
                fullName = name
                
            newDir = os.path.join(self.path, fullName)
            if os.path.isdir(newDir):
                raise Exception("Directory %s already exists." % newDir)
            
            ## Create directory
            ndm = self.manager.getDirHandle(newDir, create=True)
            t = time.time()
            self._childChanged()
            
            if self.isManaged():
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
        with MutexLocker(self.lock):
            ndir = os.path.join(self.path, subdir)
            if os.path.isdir(ndir):
                return self.manager.getDirHandle(ndir)
            else:
                if create:
                    return self.mkdir(subdir, autoIncrement=autoIncrement)
                else:
                    raise Exception('Directory %s does not exist.' % ndir)
        
    def getFile(self, fileName):
        """return a File handle for the named file."""
        fullName = os.path.join(self.name(), fileName)
        #if create:
            #self.createFile(fileName, autoIncrement=autoIncrement, useExt=useExt)
        if not os.path.isfile(fullName):
            raise Exception('File "%s" does not exist.' % fullName)
        fh = self[fileName]
        if not fh.isManaged():
            self.indexFile(fileName)
        return fh
        
    #def createFile(self, fileName, **kwargs):   ## autoIncrement=False, useExt=True, info=None):
        #self.writeFile(None, fileName=fileName, **kwargs)
        
        
    def dirExists(self, dirName):
        return os.path.isdir(os.path.join(self.path, dirName))
            
    def ls(self, normcase=False):
        """Return a list of all files in the directory.
        If normcase is True, normalize the case of all names in the list."""
        #p = Profiler('      DirHandle.ls:')
        with MutexLocker(self.lock):
            #p.mark('lock')
            #self._readIndex()
            #ls = self.index.keys()
            #ls.remove('.')
            if self.lsCache is None:
                #p.mark('(cache miss)')
                try:
                    files = os.listdir(self.name())
                except:
                    printExc("Error while listing files in %s:" % self.name())
                    files = []
                #p.mark('listdir')
                for i in ['.index', '.log']:
                    if i in files:
                        files.remove(i)
                #self.lsCache.sort(self._cmpFileTimes)  ## very expensive!
                
                ## Sort files by creation time
                for f in files:
                    if f not in self.cTimeCache:
                        self.cTimeCache[f] = self._getFileCTime(f)
                files.sort(lambda a,b: cmp(self.cTimeCache[a], self.cTimeCache[b]))
                self.lsCache = files
                #p.mark('sort')
            if normcase:
                ret = map(os.path.normcase, self.lsCache)
                #p.mark('return norm')
                return ret
            else:
                ret = self.lsCache[:]
                #p.mark('return copy')
                return ret
    
    def _getFileCTime(self, fileName):
        if self.isManaged():
            index = self._readIndex()
            try:
                t = index[fileName]['__timestamp__']
                return t
            except KeyError:
                pass
        return os.path.getctime(os.path.join(self.name(), fileName))
    
    #def _cmpFileTimes(self, a, b):
    #    with MutexLocker(self.lock):
    #        t1 = t2 = None
    #        if self.isManaged():
    #            index = self._readIndex()
    #            if a in index and '__timestamp__' in index[a]:
    #                t1 = index[a]['__timestamp__']
    #            if b in index and '__timestamp__' in index[b]:
    #                t2 = index[b]['__timestamp__']
    #        if t1 is None:
    #            t1 = os.path.getctime(os.path.join(self.name(), a))
    #        if t2 is None:
    #            t2 = os.path.getctime(os.path.join(self.name(), b))
    #        #print "compare", a, b, t1, t2
    #        return cmp(t1, t2)
    
    def isGrandparentOf(self, child):
        """Return true if child is anywhere in the tree below this directory."""
        return child.isGrandchildOf(self)
    
    def hasChildren(self):
        return len(self.ls()) > 0
    
    def info(self):
        return self._fileInfo('.')
    
    def _fileInfo(self, file):
        """Return a dict of the meta info stored for file"""
        with MutexLocker(self.lock):
            if not self.isManaged():
                return {}
            index = self._readIndex()
            if index.has_key(file):
                return index[file]
            else:
                return {}
                #raise Exception("File %s is not indexed" % file)
    
    def isDir(self, path=None):
        with MutexLocker(self.lock):
            if path is None:
                return True
            else:
                return self[path].isDir()
        
    def isFile(self, fileName):
        with MutexLocker(self.lock):
            fn = os.path.abspath(os.path.join(self.path, fileName))
            return os.path.isfile(fn)
        
    
    def writeFile(self, obj, fileName, info=None, autoIncrement=False, fileType=None, **kwargs):
        """Write a file to this directory using obj.write(fileName), store info in the index.
        Will try to convert obj into a FileType if the correct type exists.
        """
        #print "Write file", fileName
        #p = Profiler('  ' + fileName + ': ')
        
        if info is None:
            info = {}   ## never put {} in the function default
        
        t = time.time()
        with MutexLocker(self.lock):
            #p.mark('lock')
            ## Convert object to FileType if needed
            #if not isinstance(obj, FileType):
                #try:
                    #if hasattr(obj, '__class__'):
                        #objType = obj.__class__.__name__
                    #else:
                        #objType = type(obj).__name__
                    #mod = __import__('lib.filetypes.%s' % objType, fromlist=['*'])
                    #cls = getattr(mod, objType)
                    #obj = cls(obj)
                #except:
                    #raise Exception("Can not create file from object of type %s" % str(type(obj)))
                    
            if fileType is None:
                fileType = filetypes.suggestWriteType(obj, fileName)
                
            if fileType is None:
                raise Exception("Can not create file from object of type %s" % str(type(obj)))

            #p.mark('type')
            ## Add on default extension if there is one   ### Removed--FileTypes now handle this.
            #ext = obj.extension(**kwargs)
            #if fileName[-len(ext):] != ext:
                #fileName = fileName + ext
                
            fileClass = filetypes.getFileType(fileType)
            #p.mark('get class')

            ## Increment file name
            if autoIncrement:
                fileName = self.incrementFileName(fileName)
            
            #p.mark('increment')
            ## Write file
            fileName = fileClass.write(obj, self, fileName, **kwargs)
            
            #p.mark('write')
            self._childChanged()
            #p.mark('update')
            ## Write meta-info
            if not info.has_key('__object_type__'):
                info['__object_type__'] = fileType
            if not info.has_key('__timestamp__'):
                info['__timestamp__'] = t
            self._setFileInfo(fileName, info)
            #p.mark('meta')
            self.emitChanged('children', fileName)
            #p.mark('emit')
            return self[fileName]
    
    def indexFile(self, fileName, info=None, protect=False):
        """Add a pre-existing file into the index. Overwrites any pre-existing info for the file unless protect is True"""
        #print "Adding file %s to index" % fileName
        if info is None:
            info = {}
        with MutexLocker(self.lock):
            if not self.isManaged():
                self.createIndex()
            index = self._readIndex()
            fn = os.path.join(self.path, fileName)
            if not (os.path.isfile(fn) or os.path.isdir(fn)):
                raise Exception("File %s does not exist." % fn)
                
            #append = True
            if fileName in index:
                #append = False
                if protect:
                    raise Exception("File %s is already indexed." % fileName)

            self._setFileInfo(fileName, info)
            self.emitChanged('children', fileName)
    
    def forget(self, fileName):
        with MutexLocker(self.lock):
            if not self.isManaged(fileName):
                raise Exception("Can not forget %s, not managed" % fileName)
            index = self._readIndex(lock=False)
            if fileName in index:
                index.remove(fileName)
                self._writeIndex(index, lock=False)
                self.emitChanged('children', fileName)
        
    def isManaged(self, fileName=None):
        with MutexLocker(self.lock):
            if self._index is None:
                return False
            if fileName is None:
                return True
            else:
                ind = self._readIndex(unmanagedOk=True)
                if ind is None:
                    return False
                return (fileName in ind)

    
    def setInfo(self, *args):
        self._setFileInfo('.', *args)
        
        
        
        
    #def parent(self):
        #with MutexLocker(self.lock):
            #pdir = os.path.normpath(os.path.join(self.path, '..'))
            #return self.manager.getDirHandle(pdir)

        

    def exists(self, name):
        with MutexLocker(self.lock):
            try:
                fn = os.path.abspath(os.path.join(self.path, name))
            except:
                print self.path, name
                raise
            return os.path.exists(fn)

    def _setFileInfo(self, fileName, info):
        """Set or update meta-information array for fileName. If merge is false, the info dict is completely overwritten."""
        with MutexLocker(self.lock):
            if not self.isManaged():
                self.createIndex()
            index = self._readIndex(lock=False)
            append = False
            if fileName not in index:
                index[fileName] = {}
                append = True
                
            for k in info:
                index[fileName][k] = info[k]
                
            if append:
                appendConfigFile({fileName: info}, self._indexFile())
            else:
                self._writeIndex(index, lock=False)
            self.emitChanged('meta', fileName)
        
    def _readIndex(self, lock=True, unmanagedOk=False):
        with MutexLocker(self.lock):
            indexFile = self._indexFile()
            if self._index is None or os.path.getmtime(indexFile) != self._indexMTime:
                if not os.path.isfile(indexFile):
                    if unmanagedOk:
                        return None
                    else:
                        raise Exception("Directory '%s' is not managed!" % (self.name()))
                try:
                    self._index = readConfigFile(indexFile)
                    self._indexMTime = os.path.getmtime(indexFile)
                    self.checkIndex()
                except:
                    print "***************Error while reading index file %s!*******************" % indexFile
                    raise
            return self._index
        
    def _writeIndex(self, newIndex, lock=True):
        with MutexLocker(self.lock):
            
            writeConfigFile(newIndex, self._indexFile())
            self._index = newIndex
            self._indexMTime = os.path.getmtime(self._indexFile())
        
    def checkIndex(self):
        ind = self._readIndex(unmanagedOk=True)
        if ind is None:
            return
        changed = False
        for f in ind:
            if not self.exists(f):
                print "File %s is no more, removing from index." % (os.path.join(self.name(), f))
                ind.remove(f)
                changed = True
        self._writeIndex(ind)
            
        
    def _childChanged(self):
        self.lsCache = None

