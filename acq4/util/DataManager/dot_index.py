import contextlib
import os
import re
import shutil
import time
from collections import OrderedDict
from typing import Callable

import numpy as np

from acq4 import filetypes
from acq4.logging_config import get_logger
from acq4.util import Qt, advancedTypes as advancedTypes
from acq4.util.Mutex import Mutex
from pyqtgraph import SignalProxy, BusyCursor
from pyqtgraph.configfile import readConfigFile, writeConfigFile, appendConfigFile
from .common import abspath

logger = get_logger(__name__)


class FileHandle:
    def __init__(self, path, manager):
        super().__init__()
        self.sigChanged = Qt.signalEmitter(object, object, object)
        self.sigDelayedChange = Qt.signalEmitter(object, object)
        self.manager = manager
        self.delayedChanges = []
        self.path = abspath(path)
        self.parentDir = None
        self.lock = Mutex(Qt.QMutex.Recursive)
        if Qt.QApplication.instance() is not None:
            self.sigproxy = SignalProxy(self.sigChanged, slot=self.delayedChange)
        else:
            self.sigproxy = None

    def getFile(self, fn):
        return self.manager.getFileHandle(os.path.join(self.name(), fn))

    def __repr__(self):
        return f"<{self.__class__.__name__} '{self.name()}' (0x{self.__hash__():x})>"

    def __reduce__(self):
        return (self.manager.getHandle, (self.name(),))

    def name(self, relativeTo=None) -> str:
        """Return the full name of this file with its absolute path"""
        path = self.path
        if relativeTo == self:
            path = ''
        elif relativeTo is not None:
            commonParent = relativeTo
            pcount = 0
            while not (self is commonParent or self.isGrandchildOf(commonParent)):
                pcount += 1
                commonParent = commonParent.parent()
                if commonParent is None:
                    raise Exception(
                        f"No relative path found from {relativeTo.name()} to {self.name()}."
                    )
            rpath = path[len(os.path.join(commonParent.name(), '')):]
            if pcount == 0:
                return rpath
            ppath = os.path.join(*(['..'] * pcount))
            if rpath == '':
                return ppath
            else:
                return os.path.join(ppath, rpath)
        return path

    def shortName(self):
        """Return the name of this file without its path"""
        return os.path.split(self.name())[1]

    def ext(self):
        """Return file's extension"""
        return os.path.splitext(self.name())[1]

    def parent(self):
        self.checkExists()
        if self.parentDir is None:
            dirName = os.path.split(self.name())[0]
            self.parentDir = self.manager.getDirHandle(dirName)
        return self.parentDir

    def info(self):
        self.checkExists()
        info = self.parent()._fileInfo(self.shortName())
        return advancedTypes.ProtectedDict(info)

    def setInfo(self, info=None, **args):
        """Set meta-information for this file. Updates all keys specified in info, leaving others unchanged."""
        if info is None:
            info = args
        self.checkExists()
        self.emitChanged('meta')
        return self.parent()._setFileInfo(self.shortName(), info)

    def isManaged(self):
        self.checkExists()
        return self.parent().isManaged(self.shortName())

    def move(self, newDir):
        self.checkExists()
        with self.lock:
            oldDir = self.parent()
            fn1 = self.name()
            name = self.shortName()
            fn2 = os.path.join(newDir.name(), name)
            if os.path.exists(fn2):
                raise FileExistsError(f"Destination file {fn2} already exists.")

            if oldDir.isManaged() and not newDir.isManaged():
                raise ValueError("Not moving managed file to unmanaged location--this would cause loss of meta info.")

            os.rename(fn1, fn2)
            self.path = fn2
            self.parentDir = None
            self.manager._handleChanged(self, 'moved', fn1, fn2)

            if oldDir.isManaged() and newDir.isManaged():
                newDir.indexFile(name, info=oldDir._fileInfo(name))
            elif newDir.isManaged():
                newDir.indexFile(name)

            if oldDir.isManaged() and oldDir.isManaged(name):
                oldDir.forget(name)

            self.emitChanged('moved', fn1, fn2)

            oldDir._childChanged()
            newDir._childChanged()

    def rename(self, newName):
        """Rename this file.

        *newName* should be the new name of the file *excluding* its path.
        """
        self.checkExists()
        with self.lock:
            parent = self.parent()
            fn1 = self.name()
            oldName = self.shortName()
            fn2 = os.path.join(parent.name(), newName)
            if os.path.exists(fn2):
                raise FileExistsError(f"Destination file {fn2} already exists.")
            info = {}
            managed = parent.isManaged(oldName)
            if managed:
                info = parent._fileInfo(oldName)
                parent.forget(oldName)
            os.rename(fn1, fn2)
            self.path = fn2
            self.manager._handleChanged(self, 'renamed', fn1, fn2)
            if managed:
                parent.indexFile(newName, info=info)

            self.emitChanged('renamed', fn1, fn2)
            self.parent()._childChanged()

    def delete(self):
        self.checkExists()
        with self.lock:
            parent = self.parent()
            fn1 = self.name()
            oldName = self.shortName()
            if parent.isManaged():
                parent.forget(oldName)
            if self.isFile():
                os.remove(fn1)
            else:
                shutil.rmtree(fn1)
            self.manager._handleChanged(self, 'deleted', fn1)
            self.path = None
            self.emitChanged('deleted', fn1)
            parent._childChanged()

    def read(self, *args, **kargs):
        self.checkExists()
        with self.lock:
            typ = self.fileType()

            if typ is None:
                with open(self.name(), 'r') as fd:
                    data = fd.read()
            else:
                cls = filetypes.getFileType(typ)
                data = cls.read(self, *args, **kargs)

            return data

    def readlines(self):
        if self.fileType() is not None:
            raise TypeError("readlines() can only be used on text files.")
        self.checkExists()
        with self.lock:
            with open(self.name(), 'r') as fd:
                return list(fd)

    def nearestLogFile(self):
        """Return the nearest log file to this file, or None if no log file is found."""
        self.checkExists()
        fh = self
        while fh is not None:
            if fh.shortName() in ['log.txt', 'log.json']:
                return fh
            elif fh.isDir():
                if fh.exists('log.json'):
                    return fh['log.json']
                if fh.exists('log.txt'):
                    return fh['log.txt']
            fh = fh.parent()
        return None

    def __eq__(self, other):
        if not isinstance(other, FileHandle):
            return False
        return abspath(self.name()) == abspath(other.name())

    def __hash__(self):
        return hash(id(self))

    def fileType(self):
        info = self.info()
        # Use the recorded object_type to read the file if possible.
        # Otherwise, ask the filetypes to choose the type for us.
        if '__object_type__' not in info:
            return filetypes.suggestReadType(self)
        else:
            return info['__object_type__']

    def emitChanged(self, change, *args):
        self.delayedChanges.append(change)
        self.sigChanged.emit(self, change, args)

    def delayedChange(self, args):
        changes = list(set(self.delayedChanges))
        self.delayedChanges = []
        self.sigDelayedChange.emit(self, changes)

    def hasChildren(self):
        # self.checkExists()
        return False

    def _parentMoved(self, oldDir, newDir):
        """Inform this object that it has been moved as a result of its (grand)parent having moved."""
        prefix = os.path.join(oldDir, '')
        if self.path[:len(prefix)] != prefix:
            raise ValueError(f"File {self.path} is not in moved tree {oldDir}, should not update!")
        subName = self.path[len(prefix):]
        newName = os.path.join(newDir, subName)
        if not os.path.exists(newName):
            raise FileNotFoundError(f"File {newName} does not exist.")
        self.path = newName
        self.parentDir = None
        self.emitChanged('parent')

    def exists(self, name=None):
        if self.path is None:
            return False
        if name is not None:
            raise TypeError("Cannot check for subpath existence on FileHandle.")
        return os.path.exists(self.path)

    def checkExists(self):
        if not self.exists():
            raise FileNotFoundError(f"File '{self.path}' does not exist.")

    def checkDeleted(self):
        if self.path is None:
            raise Exception("File has been deleted.")

    def isDir(self, path=None):
        return False

    def isFile(self):
        return True

    def _deleted(self):
        self.path = None

    def isGrandchildOf(self, grandparent):
        """Return true if this files is anywhere in the tree beneath grandparent."""
        gname = os.path.join(abspath(grandparent.name()), '')
        return abspath(self.name())[:len(gname)] == gname

    def write(self, data, **kwargs):
        self.parent().writeFile(data, self.shortName(), **kwargs)

    def flushSignals(self):
        """If any delayed signals are pending, send them now."""
        if self.sigproxy is not None:
            self.sigproxy.flush()


class DirHandle(FileHandle):
    def __init__(self, path, manager, create=False):
        FileHandle.__init__(self, path, manager)
        self._index = None
        self.lsCache = {}  # sortMode: [files...]
        self.cTimeCache = {}
        self._indexFileExists = False

        if not os.path.isdir(self.path) and create:
            os.mkdir(self.path)
            self.createIndex()

        # Let's avoid reading the index unless we really need to.
        self._indexFileExists = os.path.isfile(self._indexFile())

    def _indexFile(self):
        """Return the name of the index file for this directory. NOT the same as indexFile()"""
        return os.path.join(self.path, '.index')

    def __getitem__(self, item):
        item = item.lstrip(os.path.sep)
        fileName = os.path.join(self.name(), item)
        return self.manager.getHandle(fileName)

    def createIndex(self):
        if self.isManaged():
            raise Exception("Directory is already managed!")
        self._writeIndex(OrderedDict([('.', {})]))

    def subDirs(self):
        """Return a list of string names for all sub-directories."""
        ls = self.ls()
        return [d for d in ls if os.path.isdir(os.path.join(self.name(), d))]

    def incrementFileName(self, fileName, useExt=True):
        """Given fileName.ext, finds the next available fileName_NNN.ext"""
        files = self.ls()
        if useExt:
            (fileName, ext) = os.path.splitext(fileName)
        else:
            ext = ''
        fileName = os.path.normcase(fileName)
        ext = os.path.normcase(ext)
        regex = re.compile(fileName + r'_(\d{3,})' + ext + r'$')
        files = [f for f in files if regex.match(f)]
        if len(files) > 0:
            files.sort()
            maxVal = int(regex.match(files[-1])[1]) + 1
        else:
            maxVal = 0
        return f'{fileName}_{maxVal:03d}{ext}'

    def mkdir(self, name, autoIncrement=False, info=None):
        """Create a new subdirectory, return a new DirHandle object. If autoIncrement is true, add a number to the
        end of the dir name if it already exists."""
        if info is None:
            info = {}
        with self.lock:
            if autoIncrement:
                fullName = self.incrementFileName(name, useExt=False)
            else:
                fullName = name
            newDir = os.path.join(self.path, fullName)
            if os.path.isdir(newDir):
                raise Exception(f"Directory {newDir} already exists.")

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

    def getDir(self, subdir, create=False, autoIncrement=False) -> "DirHandle":
        """Return a DirHandle for the specified subdirectory. If the subdir does not exist, it will be created only
        if create==True"""
        with self.lock:
            ndir = os.path.join(self.path, subdir)
            if create and not os.path.isdir(ndir):
                return self.mkdir(subdir, autoIncrement=autoIncrement)
            return self.manager.getDirHandle(ndir)

    def getFile(self, fileName):
        """return a File handle for the named file."""
        fullName = os.path.join(self.name(), fileName)
        fh = self[fileName]
        if not fh.isManaged():
            self.indexFile(fileName)
        return fh

    def dirExists(self, dirName):
        return os.path.isdir(os.path.join(self.path, dirName))

    def ls(self, normcase=False, sortMode='date', useCache=False):
        """Return a list of all files in the directory.
        If normcase is True, normalize the case of all names in the list.
        sortMode may be 'date', 'alpha', or None."""
        if (not useCache) or (sortMode not in self.lsCache):
            self._updateLsCache(sortMode)
        files = self.lsCache[sortMode]

        if normcase:
            return list(map(os.path.normcase, files))
        else:
            return files[:]

    def _updateLsCache(self, sortMode):
        try:
            files = os.listdir(self.name())
        except Exception:
            logger.exception(f"Error while listing files in {self.name()}:")
            files = []
        for i in ['.index']:
            if i in files:
                files.remove(i)

        if sortMode == 'date':
            # Sort files by creation time
            with BusyCursor():
                for f in files:
                    if f not in self.cTimeCache:
                        self.cTimeCache[f] = self._getFileCTime(f)
            files.sort(key=lambda f: (self.cTimeCache[f], f))  ## sort by time first, then name.
        elif sortMode == 'alpha':
            # show directories first when sorting alphabetically.
            files.sort(key=lambda a: (os.path.isdir(os.path.join(self.name(), a)), a))
        elif sortMode is None:
            pass
        else:
            raise ValueError(f'Unrecognized sort mode "{sortMode}"')

        self.lsCache[sortMode] = files

    def __iter__(self):
        for f in self.ls():
            yield self[f]

    def _getFileCTime(self, fileName):
        if self.isManaged():
            index = self._readIndex()
            with contextlib.suppress(KeyError):
                return index[fileName]['__timestamp__']
            # try getting time directly from file
            with contextlib.suppress(Exception):
                return self[fileName].info()['__timestamp__']
        # if the file has an obvious date in it, use that
        m = re.search(r'(20\d\d\.\d\d?\.\d\d?)', fileName)
        if m is not None:
            return time.mktime(time.strptime(m.groups()[0], "%Y.%m.%d"))

        # if all else fails, just ask the file system
        try:
            return os.path.getctime(os.path.join(self.name(), fileName))
        except Exception:
            return 0

    def isGrandparentOf(self, child):
        """Return true if child is anywhere in the tree below this directory."""
        return child.isGrandchildOf(self)

    def hasChildren(self):
        return len(self.ls()) > 0

    def info(self):
        self._readIndex(unmanagedOk=True)  ## returns None if this directory has no index file
        return advancedTypes.ProtectedDict(self._fileInfo('.'))

    def _fileInfo(self, file):
        """Return a dict of the meta info stored for file"""
        if not self.isManaged():
            return {}
        index = self._readIndex()
        if file in index:
            return index[file]
        else:
            return {}

    def isDir(self, path=None):
        if path is None:
            return True
        else:
            return self[path].isDir()

    def isFile(self, fileName=None):
        if fileName is None:
            return False
        fn = abspath(os.path.join(self.path, fileName))
        return os.path.isfile(fn)

    def createFile(self, fileName, info=None, autoIncrement=False):
        """Create a blank file"""
        if info is None:
            info = {}   ## never put {} in the function default

        t = time.time()
        with self.lock:
            ## Increment file name
            if autoIncrement:
                fileName = self.incrementFileName(fileName)

            ## Write file
            open(os.path.join(self.name(), fileName), 'w')

            self._childChanged()

            ## Write meta-info
            if '__timestamp__' not in info:
                info['__timestamp__'] = t
            self._setFileInfo(fileName, info)
            self.emitChanged('children', fileName)
            return self[fileName]

    def writeFile(self, obj, fileName, info=None, autoIncrement=False, fileType=None, **kwargs):
        """Write a file to this directory using obj.write(fileName), store info in the index.
        Will try to convert obj into a FileType if the correct type exists.
        """
        if info is None:
            info = {}   ## never put {} in the function default
        else:
            info = info.copy()  ## we modify this later; need to copy first

        t = time.time()
        with self.lock:
            if fileType is None:
                fileType = filetypes.suggestWriteType(obj, fileName)

            if fileType is None:
                raise TypeError(f"Can not create file from object of type {type(obj)}")

            fileClass = filetypes.getFileType(fileType)

            # Add extension before incrementing
            fileName = fileClass.addExtension(fileName)

            # Increment file name
            if autoIncrement:
                fileName = self.incrementFileName(fileName)

            # Write file
            fileName = fileClass.write(obj, self, fileName, **kwargs)

            self._childChanged()
            # Write meta-info
            if '__object_type__' not in info:
                info['__object_type__'] = fileType
            if '__timestamp__' not in info:
                info['__timestamp__'] = t
            self._setFileInfo(fileName, info)
            self.emitChanged('children', fileName)
            return self[fileName]

    def indexFile(self, fileName, info=None, protect=False):
        """Add a pre-existing file into the index. Overwrites any pre-existing info for the file unless protect is True"""
        if info is None:
            info = {}
        with self.lock:
            if not self.isManaged():
                self.createIndex()
            index = self._readIndex()
            fn = os.path.join(self.path, fileName)
            if not (os.path.isfile(fn) or os.path.isdir(fn)):
                raise Exception("File %s does not exist." % fn)

            if fileName in index:
                if protect:
                    raise Exception("File %s is already indexed." % fileName)

            self._setFileInfo(fileName, info)
            self.emitChanged('meta', fileName)

    def forget(self, fileName):
        """Remove fileName from the index for this directory"""
        with self.lock:
            if not self.isManaged(fileName):
                return
            index = self._readIndex(lock=False)
            if fileName in index:
                try:
                    del index[fileName]
                except:
                    print(type(index))
                    raise
                self._writeIndex(index, lock=False)
                self.emitChanged('meta', fileName)

    def isManaged(self, fileName=None):
        if not self._indexFileExists:
            return False
        if fileName is None:
            return True
        ind = self._readIndex(unmanagedOk=True)
        if ind is None:
            return False
        return fileName in ind

    def setInfo(self, *args, **kargs):
        self._setFileInfo('.', *args, **kargs)

    def exists(self, name=None):
        """Returns True if the file 'name' exists in this directory, False otherwise."""
        if self.path is None:
            return False
        if name is None:
            return os.path.exists(self.path)

        try:
            fn = abspath(os.path.join(self.path, name))
        except:
            print(self.path, name)
            raise
        return os.path.exists(fn)

    def hasMatchingChildren(self, test: Callable[[FileHandle], bool]):
        """Returns True if any child of this directory matches the given test function."""
        return any(test(self[f]) for f in self.ls())

    def representativeFramesForAllImages(self):
        from acq4.util.imaging import Frame
        from acq4.util.surface import find_surface

        frames = []
        for f in self:
            if f.fileType() == "ImageFile" and 'background' not in f.shortName().lower():
                frames.append(Frame.loadFromFileHandle(f))
            elif f.fileType() == "MetaArray" and 'pixelSize' in f.info():
                frame_s = Frame.loadFromFileHandle(f)
                if not isinstance(frame_s, Frame):
                    frame_s = frame_s[find_surface(frame_s) or len(frame_s) // 2]
                frames.append(frame_s)
            elif f.shortName().startswith("ImageSequence_"):
                frames.extend(f.representativeFramesForAllImages())
        return frames

    def _setFileInfo(self, fileName, info=None, **args):
        """Set or update meta-information array for fileName. If merge is false, the info dict is completely overwritten."""
        if info is None:
            info = args
        with self.lock:
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
                self._appendIndex({fileName: info})

            else:
                self._writeIndex(index, lock=False)
            self.emitChanged('meta', fileName)

    def _readIndex(self, lock=True, unmanagedOk=False):
        with self.lock:
            indexFile = self._indexFile()
            if self._index is None or os.path.getmtime(indexFile) != self._indexMTime:
                if not os.path.isfile(indexFile):
                    if unmanagedOk:
                        return None
                    else:
                        raise Exception("Directory '%s' is not managed!" % (self.name()))
                try:
                    self._index = readConfigFile(indexFile, np=np)
                    self._indexMTime = os.path.getmtime(indexFile)
                except:
                    print("***************Error while reading index file %s!*******************" % indexFile)
                    raise
            return self._index

    def _writeIndex(self, newIndex, lock=True):
        with self.lock:
            writeConfigFile(newIndex, self._indexFile())
            self._index = newIndex
            self._indexMTime = os.path.getmtime(self._indexFile())
            self._indexFileExists = True

    def _appendIndex(self, info):
        with self.lock:
            indexFile = self._indexFile()
            appendConfigFile(info, indexFile)
            self._indexFileExists = True
            for k in info:
                self._index[k] = info[k]
            self._indexMTime = os.path.getmtime(indexFile)

    def checkIndex(self):
        ind = self._readIndex(unmanagedOk=True)
        if ind is None:
            return
        changed = False
        for f in ind:
            if not self.exists(f):
                print("File %s is no more, removing from index." % (os.path.join(self.name(), f)))
                del ind[f]
                changed = True
        if changed:
            self._writeIndex(ind)

    def _childChanged(self):
        self.lsCache = {}
        self.emitChanged('children')
