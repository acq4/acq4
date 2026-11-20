"""The .index metadata file: one per managed directory, holding an info dict for the directory
itself (key '.') and for each file or subdirectory in it (keyed by name as spelled on disk).
"""
import os
from collections import OrderedDict

import numpy as np

from acq4.logging_config import get_logger
from coorx import Transform
from pyqtgraph.configfile import readConfigFile, writeConfigFile, appendConfigFile
from .paths import foldName

logger = get_logger(__name__)


def _serializer(obj):
    if isinstance(obj, Transform):
        return obj.save_state()
    return obj


def _deserializer(obj):
    if isinstance(obj, dict) and 'type' in obj and obj['type'] == 'Transform':
        return Transform.from_state(obj)
    return obj


def _signature(indexFile):
    """Return (mtime, size) of *indexFile*, compared to detect writes from another handle or process."""
    st = os.stat(indexFile)
    return st.st_mtime_ns, st.st_size


def _valuesEqual(a, b):
    """Return True if two .index values are equal; arrays compare element-wise, incomparable values are unequal."""
    try:
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            return bool(np.array_equal(a, b))
        return bool(a == b)
    except Exception:
        return False


class DotIndex:
    """The .index file of the directory that *dirHandle* refers to.

    Shares *dirHandle*'s lock, and follows its path through renames and moves. The parsed file is
    cached and re-read when another handle or process changes it.
    """

    FILE_NAME = '.index'

    def __init__(self, dirHandle):
        self._dir = dirHandle
        self._index = None
        self._signature = None
        self._foldedKeys = None  # maps foldName(key) to the keys with that form; None until built
        self._exists = os.path.isfile(self.path)  # last known; read() and writes keep it current

    @property
    def path(self):
        return os.path.join(self._dir.path, self.FILE_NAME)

    def exists(self):
        """Return True if the directory had an index file when it was last checked."""
        return self._exists

    def create(self):
        """Write an index holding only an empty entry for the directory. Raises if one exists."""
        with self._dir.lock:
            if self._exists or os.path.exists(self.path):
                raise Exception(f"Directory {self._dir.name()!r} is already managed.")
            self._write(OrderedDict([('.', {})]))

    def read(self, missingOk=False):
        """Return the parsed index, an OrderedDict of {name: info}.

        If there is no index file, returns None when *missingOk* is True and raises otherwise.
        Raises FileNotFoundError if the file was present before and has since disappeared.
        """
        with self._dir.lock:
            try:
                signature = _signature(self.path)
            except (FileNotFoundError, NotADirectoryError):
                if self._exists:
                    raise FileNotFoundError(
                        f"Index file {self.path!r} has disappeared; this directory was managed when last read."
                    ) from None
                self._index = None
                self._foldedKeys = None
                if missingOk:
                    return None
                raise Exception(f"Directory {self._dir.name()!r} is not managed.") from None
            if self._index is None or signature != self._signature:
                try:
                    self._index = readConfigFile(self.path, deserializer=_deserializer, np=np)
                except Exception:
                    logger.exception(f"Error while reading index file {self.path!r}")
                    raise
                self._foldedKeys = None
                self._signature = signature
                self._exists = True
            return self._index

    def keys(self, fileName):
        """Return the keys that refer to *fileName*, in index order; [] if there is no index.

        In a directory that ignores case this is every key equal to *fileName* ignoring case; older
        versions could store one file's info under several spellings.
        """
        with self._dir.lock:
            index = self.read(missingOk=True)
            if index is None:
                return []
            if not self._dir._isCaseInsensitive():
                return [fileName] if fileName in index else []
            if self._foldedKeys is None:
                self._foldedKeys = {}
                for k in index:
                    self._foldedKeys.setdefault(foldName(k), []).append(k)
            return list(self._foldedKeys.get(foldName(fileName), []))

    def contains(self, fileName):
        return len(self.keys(fileName)) > 0

    def info(self, fileName):
        """Return a copy of the info stored for *fileName* ('.' for the directory); {} if none."""
        with self._dir.lock:
            keys = self.keys(fileName)
            if len(keys) == 0:
                return {}
            if len(keys) == 1:
                return dict(self._index[keys[0]])
            return self._merge(fileName, keys)

    def update(self, fileName, info):
        """Merge *info* into the entry for *fileName* ('.' for the directory), creating the index if needed.

        *fileName* must be spelled as on disk: a new entry is stored under it. Entries stored under
        other spellings of the same name are merged into it and removed.
        """
        with self._dir.lock:
            index = self.read(missingOk=True)
            if index is None:
                self.create()
                index = self._index
            keys = self.keys(fileName)
            append = len(keys) == 0
            if append:
                index[fileName] = {}
            elif keys != [fileName]:
                merged = self._merge(fileName, keys)
                for k in keys:
                    del index[k]
                index[fileName] = merged
            index[fileName].update(info)
            if append:
                self._append({fileName: index[fileName]})
            else:
                self._write(index)

    def forget(self, fileName):
        """Remove every entry for *fileName*. Return False if it had none."""
        with self._dir.lock:
            keys = self.keys(fileName)
            if not keys:
                return False
            index = self.read()
            for k in keys:
                del index[k]
            self._write(index)
            return True

    def prune(self, exists):
        """Remove entries whose name fails *exists(name)*, logging each; the '.' entry is kept."""
        with self._dir.lock:
            index = self.read(missingOk=True)
            if index is None:
                return
            gone = [name for name in index if name != '.' and not exists(name)]
            for name in gone:
                logger.info(f"File {os.path.join(self._dir.name(), name)!r} is no more, removing from index.")
                del index[name]
            if gone:
                self._write(index)

    def _merge(self, fileName, keys):
        """Return one info dict combining the entries under *keys*.

        *keys* are spellings of *fileName* that differ only in case; older versions could store a
        file's info under several. Later keys win, and a warning names any field whose values differ.
        """
        merged = {}
        conflicts = set()
        for k in keys:
            for field, value in self._index[k].items():
                if field in merged and not _valuesEqual(merged[field], value):
                    conflicts.add(field)
                merged[field] = value
        if conflicts:
            logger.warning(
                f"Index for {self._dir.name()!r} stores {fileName!r} under {keys}, with conflicting values "
                f"for {sorted(map(str, conflicts))}; using the values from {keys[-1]!r}."
            )
        return merged

    def _write(self, index):
        writeConfigFile(index, self.path, serializer=_serializer)
        self._index = index
        self._foldedKeys = None
        self._signature = _signature(self.path)
        self._exists = True

    def _append(self, entries):
        appendConfigFile(entries, self.path, serializer=_serializer)
        for k, v in entries.items():
            self._index[k] = v
            if self._foldedKeys is not None:
                spellings = self._foldedKeys.setdefault(foldName(k), [])
                if k not in spellings:
                    spellings.append(k)
        self._signature = _signature(self.path)
        self._exists = True
