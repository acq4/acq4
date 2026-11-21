"""Path helpers for the DataManager.

A path has two forms here: a cache key (`abspath`), which treats spellings of the same file as
equal, and an on-disk spelling (`casedAbspath`), used for handle names and .index keys.
"""
import ntpath
import os
import pathlib
import sys
import unicodedata


def isCaseFolding(platform=sys.platform):
    """Return True if *platform*'s filesystems ignore case by default (Windows, macOS)."""
    return platform in ("win32", "darwin")


CASE_FOLDING = isCaseFolding()


def foldCase(name, platform=sys.platform):
    """Return a comparison key for *name*: names with equal keys are the same file by default on *platform*.

    Ignores case on Windows and macOS, and Unicode normalization (NFC vs NFD) on macOS. The key
    is not a usable spelling; never write it to disk or show it.
    """
    if platform == "win32":
        return ntpath.normcase(name)
    if platform == "darwin":
        return unicodedata.normalize("NFC", name).lower()
    return name


def _sameEntry(a, b):
    """Return True if *b* exists and is the same file or directory as *a*."""
    return os.path.exists(b) and os.path.samefile(a, b)


def foldName(name):
    """Return a key that matches *name* to its other spellings in a directory that ignores case."""
    return foldCase(name) if CASE_FOLDING else name.lower()


def pathParts(path):
    """Split an absolute path into its components, drive and root first."""
    return pathlib.PurePath(path).parts


def isCaseInsensitiveDir(path, probe=None):
    """Return True if directory *path* finds its entries regardless of case, False if not.

    Tests one entry of *path*: *probe* if given and present, else any entry whose name has
    letters. The directory ignores case if the name with its case swapped finds the same entry.
    Returns None if there is no such entry, or *path* is missing or unreadable.
    """
    if probe is not None and probe.swapcase() != probe and os.path.exists(os.path.join(path, probe)):
        return _sameEntry(os.path.join(path, probe), os.path.join(path, probe.swapcase()))
    try:
        entries = os.listdir(path)
    except OSError:
        return None
    for name in entries:
        if name.swapcase() != name:
            return _sameEntry(os.path.join(path, name), os.path.join(path, name.swapcase()))
    return None


def _getLongPathName(path):
    """Return absolute *path* with Windows 8.3 short names expanded in the part that exists.

    Does not correct the case of components that are not short names.
    """
    import ctypes

    getLongPathName = ctypes.windll.kernel32.GetLongPathNameW
    head, tail = path, []
    while True:
        buf = ctypes.create_unicode_buffer(32768)
        n = getLongPathName(head, buf, len(buf))
        if 0 < n < len(buf):
            return os.path.join(buf.value, *reversed(tail))
        newHead, name = os.path.split(head)
        if newHead == head or not name:
            return path
        tail.append(name)
        head = newHead


def longPath(path):
    """Expand Windows 8.3 short names (``PROGRA~1``) in absolute *path* to their long form.

    Components that do not exist yet are kept as given. Returns *path* unchanged elsewhere.
    """
    if sys.platform != "win32" or "~" not in path:
        return path
    return _getLongPathName(path)


def _windowsRealCase(path):
    """Return absolute *path* with each existing component spelled as stored on disk (case, long name)."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.FindFirstFileW.restype = wintypes.HANDLE
    kernel32.FindFirstFileW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)]
    kernel32.FindClose.argtypes = [wintypes.HANDLE]
    invalid = wintypes.HANDLE(-1).value

    parts = pathlib.PureWindowsPath(path).parts
    anchor = parts[0]
    if len(anchor) >= 2 and anchor[1] == ":":
        anchor = anchor[0].upper() + anchor[1:]
    result = anchor
    data = wintypes.WIN32_FIND_DATAW()
    for i, name in enumerate(parts[1:], start=1):
        handle = kernel32.FindFirstFileW(os.path.join(result, name), ctypes.byref(data))
        if handle == invalid or handle is None:
            return os.path.join(result, *parts[i:])
        kernel32.FindClose(handle)
        result = os.path.join(result, data.cFileName)
    return result


def realCase(path):
    """Return absolute *path* spelled as it is on disk.

    On Windows every existing component is corrected (and short names expanded); on macOS only
    the final component. Components that do not exist are kept as given.
    """
    if sys.platform == "win32":
        return _windowsRealCase(path)
    if sys.platform == "darwin" and os.path.exists(path):
        parent, name = os.path.split(path)
        if not name:
            return path
        try:
            entries = os.listdir(parent)
        except OSError:
            return path
        if name in entries:
            return path
        matches = [e for e in entries if foldCase(e) == foldCase(name) and _sameEntry(path, os.path.join(parent, e))]
        if len(matches) == 1:
            return os.path.join(parent, matches[0])
    return path


def casedAbspath(fileName):
    """Return an absolute path for *fileName*, spelled as on disk where it exists."""
    return realCase(os.path.abspath(fileName))


def abspath(fileName):
    """Return the DataManager's cache key for *fileName*.

    The key is the absolute path with Windows short names expanded and case ignored on Windows
    and macOS, so different spellings of one file share a key. It is not a usable spelling: handle
    paths and .index keys use `casedAbspath`.
    """
    return foldCase(longPath(os.path.abspath(fileName)))
