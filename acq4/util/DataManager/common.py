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
    """Return *name* in the form the filesystem on *platform* treats as identical by default.

    Folds case on Windows and macOS, and also Unicode normalization on macOS. Use for
    comparison keys only, never for names written to disk or shown to the user.
    """
    if platform == "win32":
        return ntpath.normcase(name)
    if platform == "darwin":
        return unicodedata.normalize("NFC", name).lower()
    return name


def _sameEntry(a, b):
    return os.path.exists(b) and os.path.samefile(a, b)


def isCaseInsensitiveDir(path):
    """Return whether names inside directory *path* are looked up case-insensitively.

    Probes an entry of *path* itself (its .index file if present). Returns None if that is
    impossible: the directory is missing or unreadable, or no entry has a name with letters.
    """
    index = os.path.join(path, ".index")
    if os.path.exists(index):
        return _sameEntry(index, os.path.join(path, ".INDEX"))
    try:
        entries = os.listdir(path)
    except OSError:
        return None
    for name in entries:
        if name.swapcase() != name:
            return _sameEntry(os.path.join(path, name), os.path.join(path, name.swapcase()))
    return None


def _getLongPathName(path):
    """Return absolute *path* with its existing prefix as the Windows long, on-disk-case form."""
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
    """Return absolute *path* with each existing component named as Windows stores it."""
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
    """Return a normalized absolute path that uniquely identifies a file.

    This is an identity key only (case-folded where the platform ignores case by default). Never
    store it as a handle's path or use its basename as an index key; use `casedAbspath` for that.
    """
    return foldCase(longPath(os.path.abspath(fileName)))
