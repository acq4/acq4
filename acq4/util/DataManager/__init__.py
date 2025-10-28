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
from acq4.util.DataManager.dot_index import FileHandle, DirHandle
from acq4.util.Mutex import Mutex

logger = get_logger(__name__)


def abspath(fileName):
    """Return an absolute path string which is guaranteed to uniquely identify a file."""
    return os.path.normcase(os.path.abspath(fileName))


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
            dirName = os.path.abspath(dirName)
            if not self._cacheHasName(dirName):
                self._addHandle(dirName, DirHandle(dirName, self, create=create))
            return self._getCache(dirName)

    def getFileHandle(self, fileName):
        with self.lock:
            fileName = os.path.abspath(fileName)
            if not self._cacheHasName(fileName):
                self._addHandle(fileName, FileHandle(fileName, self))
            return self._getCache(fileName)

    def getHandle(self, fileName):
        """Return a FileHandle or DirHandle for the given fileName.
        If the file does not exist, a handle will still be returned, but is not guaranteed to have the correct type.
        """
        fn = os.path.abspath(fileName)
        if os.path.isdir(fn) or (not os.path.exists(fn) and fn.endswith(os.path.sep)):
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
                for h in tree:
                    ## Update key to cached handle
                    newh = os.path.abspath(os.path.join(newName, h[len(oldName+os.path.sep):]))
                    self._setCache(newh, self._getCache(h))

                    ## If the change originated from h's parent, inform it that this change has occurred.
                    if h != oldName:
                        self._getCache(h)._parentMoved(oldName, newName)
                    self._delCache(h)

            elif change == 'deleted':
                oldName = args[0]

                ## Inform all children that they have been deleted and remove from cache
                tree = self._getTree(oldName)
                for path in tree:
                    self._getCache(path)._deleted()
                    self._delCache(path)

    def _getTree(self, parent):
        """Return the entire list of cached handles that are children or grandchildren of this handle"""

        ## If handle has no children, then there is no need to search for its tree.
        tree = [parent]
        ph = self._getCache(parent)
        prefix = os.path.normcase(os.path.join(parent, ''))

        for h in self.cache:
            if h[:len(prefix)] == prefix:
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


dm = DataManager()

__all__ = [
    "dm",
    "getDataManager",
    "getHandle",
    "getDirHandle",
    "getFileHandle",
    "FileHandle",
    "DirHandle",
]
