import contextlib
import os
import pathlib
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
from coorx import Transform
from pyqtgraph import SignalProxy, BusyCursor
from pyqtgraph.configfile import readConfigFile, writeConfigFile, appendConfigFile
from .common import abspath, casedAbspath, foldCase, isCaseInsensitiveDir, CASE_FOLDING

logger = get_logger(__name__)


def _serializer(obj):
    if isinstance(obj, Transform):
        return obj.save_state()
    return obj


def _deserializer(obj):
    if isinstance(obj, dict) and 'type' in obj and obj['type'] == 'Transform':
        return Transform.from_state(obj)
    return obj


def _indexSignature(indexFile):
    """Return a value that changes whenever *indexFile* is rewritten."""
    st = os.stat(indexFile)
    return st.st_mtime_ns, st.st_size


def _foldName(name):
    """Return the comparison form of a file name in a case-insensitive directory."""
    return foldCase(name) if CASE_FOLDING else name.lower()


def _valuesEqual(a, b):
    try:
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            return bool(np.array_equal(a, b))
        return bool(a == b)
    except Exception:
        return False


def _pathParts(path):
    """Split an absolute path into its components, drive and root first."""
    return pathlib.PurePath(path).parts


def _handleForPath(path):
    """Unpickle a handle as the cached handle for *path*."""
    from . import getHandle

    return getHandle(path)


class FileHandle:
    def __init__(self, path, manager):
        super().__init__()
        self.sigChanged = Qt.signalEmitter(object, object, object)
        self.sigDelayedChange = Qt.signalEmitter(object, object)
        self.manager = manager
        self.delayedChanges = []
        self.path = casedAbspath(path)
        self._spellingResolved = os.path.exists(self.path)
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
        self.checkDeleted()
        return (_handleForPath, (self.name(),))

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
            rpath = os.path.join('', *_pathParts(path)[len(_pathParts(commonParent.name())):])
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
            if os.path.exists(fn2) and not os.path.samefile(fn1, fn2):
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
            if fh.shortName().lower() in ['log.txt', 'log.json']:
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
        if self.path is None or other.path is None:
            # A deleted handle has no path to compare, so it is only equal to itself.
            # Comparing paths here would make every deleted handle equal to every other
            # one while __hash__ keeps them distinct, breaking the eq/hash contract.
            return self is other
        return abspath(self.name()) == abspath(other.name())

    def __hash__(self):
        # Identity-based, so the hash stays stable across renames and deletion (which
        # sets path to None). Handles are singletons per path via DataManager's cache,
        # so identity hashing does not split entries that should share a key.
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

    def _movedPath(self, oldDir, newDir):
        """Return this handle's path after its (grand)parent directory moved from *oldDir* to *newDir*."""
        oldParts = _pathParts(oldDir)
        parts = _pathParts(self.path)
        if len(parts) <= len(oldParts) or abspath(os.path.join(*parts[:len(oldParts)])) != abspath(oldDir):
            raise ValueError(f"File {self.path} is not in moved tree {oldDir}, should not update!")
        return os.path.join(newDir, *parts[len(oldParts):])

    def _parentMoved(self, newPath):
        """Inform this object that a (grand)parent move has put it at *newPath*."""
        self.path = newPath
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
        self._refreshSpelling()

    def _refreshSpelling(self):
        """Respell this handle's path as on disk, once, if it was created before the path existed."""
        if self._spellingResolved or self.path is None or not os.path.exists(self.path):
            return
        newPath = casedAbspath(self.path)
        if abspath(newPath) != abspath(self.path):
            raise RuntimeError(f"Respelling {self.path!r} as {newPath!r} would change its identity.")
        self.path = newPath
        self._spellingResolved = True

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
        self._foldedKeys = None  # _foldName(key): [keys] for self._index; None means rebuild
        self._caseInsensitive = None  # probed lazily by _isCaseInsensitive()
        self.lsCache = {}  # sortMode: [files...]
        self.cTimeCache = {}
        self._indexFileExists = False

        if create:
            self._create()

        # Let's avoid reading the index unless we really need to.
        self._indexFileExists = os.path.isfile(self._indexFile())

    def _create(self):
        """Create this directory with an empty index, unless it already exists."""
        if os.path.isdir(self.path):
            return
        os.mkdir(self.path)
        self._writeIndex(OrderedDict([('.', {})]))
        self.lsCache = {}

    def _indexFile(self):
        """Return the name of the index file for this directory. NOT the same as indexFile()"""
        return os.path.join(self.path, '.index')

    def __getitem__(self, item):
        item = item.lstrip('/' + os.path.sep)
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
        if useExt:
            (fileName, ext) = os.path.splitext(fileName)
        else:
            ext = ''
        flags = re.IGNORECASE if self._isCaseInsensitive() else 0
        regex = re.compile(re.escape(fileName) + r'_(\d{3,})' + re.escape(ext) + r'$', flags)
        used = [int(m[1]) for m in map(regex.match, os.listdir(self.path)) if m is not None]
        nextVal = max(used) + 1 if used else 0
        return f'{fileName}_{nextVal:03d}{ext}'

    def mkdir(self, name, autoIncrement=False, info=None):
        """Create a new subdirectory, return a new DirHandle object. If autoIncrement is true, add a number to the
        end of the dir name if it already exists."""
        info = {} if info is None else dict(info)
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
                self._setFileInfo(ndm.shortName(), {'__timestamp__': t})

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
            files.sort(key=lambda a: (not os.path.isdir(os.path.join(self.name(), a)), a))
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
            with contextlib.suppress(KeyError):
                return self._fileInfo(fileName)['__timestamp__']
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
        keys = self._indexKeys(file)
        if len(keys) == 0:
            return {}
        if len(keys) == 1:
            return index[keys[0]]
        return self._mergeSpellings(file, keys)

    def _mergeSpellings(self, fileName, keys):
        """Merge the index entries under *keys* (all spellings of *fileName*), later keys winning.

        Logs a warning naming any field whose value differs between spellings.
        """
        index = self._readIndex()
        merged = {}
        conflicts = set()
        for k in keys:
            for field, value in index[k].items():
                if field in merged and not _valuesEqual(merged[field], value):
                    conflicts.add(field)
                merged[field] = value
        if conflicts:
            logger.warning(
                f"Index for {self.name()!r} stores {fileName!r} under {keys}, with conflicting values "
                f"for {sorted(map(str, conflicts))}; using the values from {keys[-1]!r}."
            )
        return merged

    def _isCaseInsensitive(self):
        """Return True if this directory looks up names case-insensitively.

        Probed once a conclusive answer is available. Until then (no entry has a name with
        letters, so no two names can differ only in case) returns the platform default.
        """
        if self._caseInsensitive is None:
            probed = isCaseInsensitiveDir(self.path)
            if probed is None:
                return CASE_FOLDING
            self._caseInsensitive = probed
        return self._caseInsensitive

    def _indexKeys(self, fileName):
        """Return the index keys that refer to *fileName*, in index order.

        In a case-insensitive directory every key matching *fileName* regardless of case is
        returned; older versions could store one file's info under several spellings.
        """
        index = self._readIndex()
        if not self._isCaseInsensitive():
            return [fileName] if fileName in index else []
        if self._foldedKeys is None:
            self._foldedKeys = {}
            for k in index:
                self._foldedKeys.setdefault(_foldName(k), []).append(k)
        return list(self._foldedKeys.get(_foldName(fileName), []))

    def isDir(self, path=None):
        if path is None:
            return True
        else:
            return self[path].isDir()

    def isFile(self, fileName=None):
        if fileName is None:
            return False
        return os.path.isfile(os.path.join(self.path, fileName))

    def createFile(self, fileName, info=None, autoIncrement=False):
        """Create a blank file"""
        if info is None:
            info = {}   ## never put {} in the function default

        t = time.time()
        with self.lock:
            ## Increment file name
            if autoIncrement:
                fileName = self.incrementFileName(fileName)

            path = os.path.join(self.name(), fileName)
            self.manager.checkCanCreate(path, FileHandle)
            with open(path, 'w'):
                pass

            self._childChanged()
            fh = self[fileName]

            ## Write meta-info
            if '__timestamp__' not in info:
                info['__timestamp__'] = t
            self._setFileInfo(fh.shortName(), info)
            self.emitChanged('children', fh.shortName())
            return fh

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
            self.manager.checkCanCreate(os.path.join(self.name(), fileName), FileHandle)
            fileName = fileClass.write(obj, self, fileName, **kwargs)

            self._childChanged()
            fh = self[fileName]
            # Write meta-info
            if '__object_type__' not in info:
                info['__object_type__'] = fileType
            if '__timestamp__' not in info:
                info['__timestamp__'] = t
            self._setFileInfo(fh.shortName(), info)
            self.emitChanged('children', fh.shortName())
            return fh

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

            if protect and self._indexKeys(fileName):
                raise Exception("File %s is already indexed." % fileName)

            self._setFileInfo(self[fileName].shortName(), info)
            self.emitChanged('meta', fileName)

    def forget(self, fileName):
        """Remove fileName from the index for this directory"""
        with self.lock:
            if not self.isManaged(fileName):
                return
            index = self._readIndex(lock=False)
            for k in self._indexKeys(fileName):
                del index[k]
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
        return len(self._indexKeys(fileName)) > 0

    def setInfo(self, *args, **kargs):
        self._setFileInfo('.', *args, **kargs)

    def exists(self, name=None):
        """Returns True if the file 'name' exists in this directory, False otherwise."""
        if self.path is None:
            return False
        if name is None:
            return os.path.exists(self.path)

        return os.path.exists(os.path.join(self.path, name))

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
        """Update the index entry for *fileName*, which must be spelled as on disk (or be '.').

        Entries stored under other spellings of the same name are merged into it.
        """
        if info is None:
            info = args
        with self.lock:
            if not self.isManaged():
                self.createIndex()
            index = self._readIndex(lock=False)
            keys = self._indexKeys(fileName)
            append = len(keys) == 0
            if append:
                index[fileName] = {}
            elif keys != [fileName]:
                merged = self._mergeSpellings(fileName, keys)
                for k in keys:
                    del index[k]
                index[fileName] = merged

            for k in info:
                index[fileName][k] = info[k]

            if append:
                self._appendIndex({fileName: index[fileName]})

            else:
                self._writeIndex(index, lock=False)
            self.emitChanged('meta', fileName)

    def _readIndex(self, lock=True, unmanagedOk=False):
        with self.lock:
            indexFile = self._indexFile()
            try:
                signature = _indexSignature(indexFile)
            except (FileNotFoundError, NotADirectoryError):
                if self._indexFileExists:
                    raise FileNotFoundError(f"Index file {indexFile!r} has disappeared.") from None
                self._index = None
                self._foldedKeys = None
                if unmanagedOk:
                    return None
                else:
                    raise Exception("Directory '%s' is not managed!" % (self.name()))
            if self._index is None or signature != self._indexSignature:
                try:
                    self._index = readConfigFile(indexFile, deserializer=_deserializer, np=np)
                    self._foldedKeys = None
                    self._indexSignature = signature
                    self._indexFileExists = True
                except:
                    print("***************Error while reading index file %s!*******************" % indexFile)
                    raise
            return self._index

    def _writeIndex(self, newIndex, lock=True):
        with self.lock:
            writeConfigFile(newIndex, self._indexFile(), serializer=_serializer)
            self._index = newIndex
            self._foldedKeys = None
            self._indexSignature = _indexSignature(self._indexFile())
            self._indexFileExists = True

    def _appendIndex(self, info):
        with self.lock:
            indexFile = self._indexFile()
            appendConfigFile(info, indexFile, serializer=_serializer)
            self._indexFileExists = True
            for k in info:
                self._index[k] = info[k]
                if self._foldedKeys is not None:
                    spellings = self._foldedKeys.setdefault(_foldName(k), [])
                    if k not in spellings:
                        spellings.append(k)
            self._indexSignature = _indexSignature(indexFile)

    def checkIndex(self):
        ind = self._readIndex(unmanagedOk=True)
        if ind is None:
            return
        changed = False
        for f in list(ind):
            if f != '.' and not self.exists(f):
                print("File %s is no more, removing from index." % (os.path.join(self.name(), f)))
                del ind[f]
                changed = True
        if changed:
            self._writeIndex(ind)

    def _childChanged(self):
        self.lsCache = {}
        self.emitChanged('children')
