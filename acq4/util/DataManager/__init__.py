"""
DataManager.py - DataManager, FileHandle, and DirHandle classes
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

These classes implement a data management system that allows modules
to easily store and retrieve data files along with metadata. The objects
probably only need to be created via functions in the Manager class.
"""
import os
import pathlib
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

    def getDirHandle(self, dirName, create=False):
        with self.lock:
            handle = self._getCache(dirName) if self._cacheHasName(dirName) else None
            if handle is not None and not isinstance(handle, DirHandle) and not os.path.isfile(handle.name()):
                handle = None  # cached as a file before anything existed at this path
            if handle is None:
                handle = DirHandle(dirName, self, create=create)
                self._addHandle(dirName, handle)
            elif create and isinstance(handle, DirHandle):
                handle._create()
            return handle

    def getFileHandle(self, fileName):
        with self.lock:
            handle = self._getCache(fileName) if self._cacheHasName(fileName) else None
            if isinstance(handle, DirHandle) and not os.path.isdir(handle.name()):
                handle = None  # cached as a directory before anything existed at this path
            if handle is None:
                handle = FileHandle(fileName, self)
                self._addHandle(fileName, handle)
            return handle

    def getHandle(self, fileName):
        """Return a FileHandle or DirHandle for the given fileName.
        If the file does not exist, a handle will still be returned, but is not guaranteed to have the correct type.
        """
        fn = abspath(fileName)
        if os.path.isdir(fn) or (not os.path.exists(fn) and fileName.endswith(('/', os.path.sep))):
            return self.getDirHandle(fileName)
        else:
            return self.getFileHandle(fileName)

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
                ## Inform all children that they have been moved and update cache
                tree = self._getTree(oldName)
                handles = [(h, self._getCache(h)) for h in tree]
                for h, _ in handles:
                    self._delCache(h)
                for h, handle in handles:
                    if h == abspath(oldName):
                        newKey = newName
                    else:
                        ## h is a (grand)child of the changed handle; tell it about the move.
                        depth = len(pathlib.PurePath(abspath(oldName)).parts)
                        newKey = os.path.join(newName, *pathlib.PurePath(h).parts[depth:])
                        handle._parentMoved(oldName, newName)
                    self._setCache(newKey, handle)

            elif change == 'deleted':
                oldName = args[0]

                ## Inform all children that they have been deleted and remove from cache
                tree = self._getTree(oldName)
                for path in tree:
                    self._getCache(path)._deleted()
                    self._delCache(path)

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
