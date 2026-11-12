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
from .paths import abspath
from acq4.util.Mutex import Mutex
from coorx import Transform
from pyqtgraph import SignalProxy, BusyCursor
from pyqtgraph.configfile import readConfigFile, writeConfigFile, appendConfigFile

logger = get_logger(__name__)


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

        The directory need not exist. Raises TypeError if a FileHandle is already cached for the
        path, and NotADirectoryError if a file exists there.
        """
        with self.lock:
            handle = self._lookup(dirName, DirHandle)
            if handle is None:
                if os.path.isfile(dirName):
                    raise NotADirectoryError(f"Cannot open a DirHandle for file {dirName!r}.")
                handle = DirHandle(dirName, self, create=create)
                self._addHandle(dirName, handle)
            elif os.path.isfile(handle.path):
                raise NotADirectoryError(f"{handle.path!r} is cached as a directory but is now a file.")
            elif create:
                handle._create()
            return handle

    def getFileHandle(self, fileName) -> FileHandle:
        """Return the FileHandle for *fileName*, which need not exist yet.

        Raises TypeError if a DirHandle is already cached for the path, and IsADirectoryError if a
        directory exists there.
        """
        with self.lock:
            handle = self._lookup(fileName, FileHandle)
            if handle is None:
                if os.path.isdir(fileName):
                    raise IsADirectoryError(f"Cannot open a FileHandle for directory {fileName!r}.")
                handle = FileHandle(fileName, self)
                self._addHandle(fileName, handle)
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

    def _checkCanCreate(self, path, cls):
        """Raise before a *cls* (FileHandle or DirHandle) is created at *path* if that would conflict.

        Raises as `_lookup` does. Call before writing to disk, so a conflict leaves the disk untouched.
        """
        with self.lock:
            self._lookup(path, cls)

    def _lookup(self, name, cls):
        """Return the cached handle for *name*, or None; raise if it is not a *cls*.

        *cls* is FileHandle or DirHandle; a cached handle of the other type raises TypeError.
        Cache keys ignore case (Windows, macOS) and expand Windows short names, so a lookup can find
        a handle whose path is spelled differently from *name*. The two spellings must then refer to
        the same file on disk; otherwise raises FileExistsError (e.g. 'a.txt' and 'A.txt' in a
        case-sensitive directory). A handle created before its path existed takes the on-disk spelling.
        """
        handle = self.cache.get(abspath(name))
        if handle is None:
            return None
        if isinstance(handle, DirHandle) != issubclass(cls, DirHandle):
            raise TypeError(
                f"A {type(handle).__name__} is already cached for {handle.name()!r}; "
                f"cannot use it as a {cls.__name__}."
            )
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
        """Cache *handle* under the key for *fileName*."""
        self.cache[abspath(fileName)] = handle

    def _handleChanged(self, handle, change, *args):
        """Update cached handles after *handle* was 'renamed', 'moved' or 'deleted'.

        *args* is (oldPath, newPath) for a rename or move, (oldPath,) for a delete. Handles inside a
        renamed, moved or deleted directory are updated too.
        """
        with self.lock:
            if change in ['renamed', 'moved']:
                oldName = args[0]
                newName = args[1]
                oldKey = abspath(oldName)
                moves = []
                for key in self._getTree(oldName):
                    child = self.cache[key]
                    if key == oldKey:
                        moves.append((key, child, newName))  # rename()/move() already set this handle's path
                        continue
                    newPath = child._movedPath(oldName, newName)
                    if self._stillOutside(child.path, newPath):
                        continue
                    moves.append((key, child, newPath))
                for key, _, _ in moves:
                    del self.cache[key]
                for key, child, newPath in moves:
                    if key != oldKey:
                        child._parentMoved(newPath)
                    self._addHandle(newPath, child)

            elif change == 'deleted':
                oldName = args[0]

                oldKey = abspath(oldName)
                for key in self._getTree(oldName):
                    child = self.cache[key]
                    if key != oldKey and os.path.exists(child.path):
                        continue  # still exists: it is under a different directory whose name differs only in case
                    child._deleted()
                    del self.cache[key]

    @staticmethod
    def _stillOutside(oldPath, newPath):
        """Return True if a cached handle was not actually inside a directory that was just moved.

        Called after a directory is renamed or moved, for each cached handle whose path is under the
        directory's old path when case is ignored. *oldPath* is the handle's path; *newPath* is where
        it would now be if it was inside. It was inside if nothing exists at *oldPath* any more, or if
        *oldPath* and *newPath* are the same file (a rename that changed only case). Otherwise it is
        under a different directory whose name differs only in case, e.g. "A" when "a" was renamed.
        """
        if not os.path.exists(oldPath):
            return False
        return not (os.path.exists(newPath) and os.path.samefile(oldPath, newPath))

    def _getTree(self, parent):
        """Return cache keys for *parent* and every cached handle beneath it."""
        key = abspath(parent)
        prefix = os.path.join(key, '')
        tree = [key] if key in self.cache else []
        tree.extend(h for h in self.cache if h.startswith(prefix))
        return tree


__all__ = [
    "getDataManager",
    "getHandle",
    "getDirHandle",
    "getFileHandle",
    "FileHandle",
    "DirHandle",
]
