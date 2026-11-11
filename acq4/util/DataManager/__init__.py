"""
DataManager.py - DataManager, FileHandle, and DirHandle classes
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

These classes implement a data management system that allows modules
to easily store and retrieve data files along with metadata. The objects
probably only need to be created via functions in the Manager class.
"""
import os
import weakref

from acq4.logging_config import get_logger
from acq4.util import Qt
from .dot_index import FileHandle, DirHandle
from .common import abspath
from acq4.util.Mutex import Mutex
from coorx import Transform
from pyqtgraph import SignalProxy, BusyCursor
from pyqtgraph.configfile import readConfigFile, writeConfigFile, appendConfigFile

logger = get_logger(__name__)


def _stillOutside(oldPath, newPath):
    """Return True if a handle at *oldPath* was not inside a tree just moved to contain *newPath*.

    A real descendant no longer exists at its old path (or, after a case-only rename, its old
    path is the same entry as its new one). Only a case-variant name in a case-sensitive
    directory still exists where it was.
    """
    if not os.path.exists(oldPath):
        return False
    return not (os.path.exists(newPath) and os.path.samefile(oldPath, newPath))


def getDataManager():
    if DataManager.INSTANCE is None:
        return DataManager()
    return DataManager.INSTANCE


def getHandle(fileName):
    return getDataManager().getHandle(fileName)


def getDirHandle(fileName, create=False):
    return getDataManager().getDirHandle(fileName, create=create)


def getFileHandle(fileName):
    return getDataManager().getFileHandle(fileName)


def getInfo(name) -> dict:
    return getDataManager().getInfo(name)


class DataManager(Qt.QObject):
    """Class for creating and caching DirHandle objects to make sure there is only one manager object per
    file/directory. This class is (supposedly) thread-safe.
    """

    INSTANCE = None

    def __init__(self):
        Qt.QObject.__init__(self)
        if DataManager.INSTANCE is not None:
            raise ValueError("Attempted to create more than one DataManager!")
        DataManager.INSTANCE = self
        self.cache = {}
        self.lock = Mutex(Qt.QMutex.Recursive)

    def getDirHandle(self, dirName, create=False) -> DirHandle:
        """Return the DirHandle for *dirName*, creating the directory first if *create* is True.

        A handle may be requested for a directory that does not exist yet. Raises TypeError if a
        FileHandle is already cached for the path, and NotADirectoryError if it is an existing file.
        """
        with self.lock:
            handle = self._lookup(dirName)
            if handle is None:
                if os.path.isfile(dirName):
                    raise NotADirectoryError(f"Cannot open a DirHandle for file {dirName!r}.")
                handle = DirHandle(dirName, self, create=create)
                self._addHandle(dirName, handle)
            elif not isinstance(handle, DirHandle):
                raise TypeError(f"A FileHandle is already cached for {handle.name()!r}; cannot open it as a directory.")
            elif os.path.isfile(handle.path):
                raise NotADirectoryError(f"{handle.path!r} is cached as a directory but is now a file.")
            elif create:
                handle._create()
            return handle

    def getFileHandle(self, fileName) -> FileHandle:
        """Return the FileHandle for *fileName*, which need not exist yet.

        Raises TypeError if a DirHandle is already cached for the path, and IsADirectoryError if it
        is an existing directory.
        """
        with self.lock:
            handle = self._lookup(fileName)
            if handle is None:
                if os.path.isdir(fileName):
                    raise IsADirectoryError(f"Cannot open a FileHandle for directory {fileName!r}.")
                handle = FileHandle(fileName, self)
                self._addHandle(fileName, handle)
            elif isinstance(handle, DirHandle):
                raise TypeError(f"A DirHandle is already cached for {handle.name()!r}; cannot open it as a file.")
            elif os.path.isdir(handle.path):
                raise IsADirectoryError(f"{handle.path!r} is cached as a file but is now a directory.")
            return handle

    def getHandle(self, fileName):
        """Return a DirHandle or FileHandle for the existing path *fileName*.

        Raises FileNotFoundError if nothing exists there; use getDirHandle or getFileHandle to get a
        handle for a path that does not exist yet.
        """
        if os.path.isdir(fileName):
            return self.getDirHandle(fileName)
        if os.path.exists(fileName):
            return self.getFileHandle(fileName)
        raise FileNotFoundError(f"No file or directory at {os.path.abspath(fileName)!r}.")

    def checkCanCreate(self, path, cls):
        """Raise TypeError if a handle of a type other than *cls* is cached for *path*.

        Call before creating a file or directory at *path*, so a conflict fails before the disk is touched.
        """
        with self.lock:
            handle = self._lookup(path)
            if handle is not None and isinstance(handle, DirHandle) != issubclass(cls, DirHandle):
                raise TypeError(
                    f"A {type(handle).__name__} is already cached for {handle.name()!r}; "
                    f"cannot create a {cls.__name__} there."
                )

    def _lookup(self, name):
        """Return the cached handle for *name*, or None.

        Cache keys fold case and Windows short names. When *name* is spelled differently from the
        cached handle, the two must name the same entry on disk; raises FileExistsError if they do not
        (e.g. 'a.txt' and 'A.txt' in a case-sensitive directory).
        """
        key = abspath(name)
        handle = self.cache.get(key)
        if handle is None:
            return None
        requested = os.path.abspath(name)
        if requested != handle.path and os.path.exists(handle.path):
            if not (os.path.exists(requested) and os.path.samefile(requested, handle.path)):
                raise FileExistsError(
                    f"{requested!r} and {handle.path!r} are different files, but the DataManager cannot "
                    f"tell their paths apart (their names differ only in case)."
                )
        handle._refreshSpelling()
        return handle

    def getInfo(self, name):
        return self.getHandle(name).info().deepcopy()

    def cleanup(self):
        """
        Free memory by deleting cached handles that are not in use elsewhere.
        This is useful in situations where a very large number of handles are
        being created, such as when scanning through large data sets.
        """
        import gc

        with self.lock:
            tmp = weakref.WeakValueDictionary(self.cache)
            self.cache = None
            gc.collect()
            self.cache = dict(tmp)

    def _addHandle(self, fileName, handle):
        """Cache a handle and watch it for changes"""
        self._setCache(fileName, handle)

    def _handleChanged(self, handle, change, *args):
        with self.lock:
            if change in ['renamed', 'moved']:
                oldName = args[0]
                newName = args[1]
                oldKey = abspath(oldName)
                moves = []
                for key in self._getTree(oldName):
                    child = self.cache[key]
                    if key == oldKey:
                        moves.append((key, child, newName))  # the changed handle already has its new path
                        continue
                    newPath = child._movedPath(oldName, newName)
                    if _stillOutside(child.path, newPath):
                        continue
                    moves.append((key, child, newPath))
                for key, _, _ in moves:
                    del self.cache[key]
                for key, child, newPath in moves:
                    if key != oldKey:
                        child._parentMoved(newPath)
                    self._setCache(newPath, child)

            elif change == 'deleted':
                oldName = args[0]

                oldKey = abspath(oldName)
                for key in self._getTree(oldName):
                    child = self.cache[key]
                    if key != oldKey and os.path.exists(child.path):
                        continue  # a case-variant sibling's descendant, not inside the deleted tree
                    child._deleted()
                    del self.cache[key]

    def _getTree(self, parent):
        """Return cache keys for *parent* and every cached handle beneath it."""
        key = abspath(parent)
        prefix = os.path.join(key, '')
        tree = [key] if key in self.cache else []
        tree.extend(h for h in self.cache if h.startswith(prefix))
        return tree

    def _getCache(self, name):
        return self.cache[abspath(name)]

    def _setCache(self, name, value):
        self.cache[abspath(name)] = value

    def _delCache(self, name):
        del self.cache[abspath(name)]

    def _cacheHasName(self, name):
        return abspath(name) in self.cache


__all__ = [
    "getDataManager",
    "getHandle",
    "getDirHandle",
    "getFileHandle",
    "FileHandle",
    "DirHandle",
]
