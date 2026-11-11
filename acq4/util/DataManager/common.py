import ntpath
import os
import sys
import unicodedata


def isCaseFolding(platform=sys.platform):
    """Return True if *platform*'s default filesystems ignore case (Windows, macOS)."""
    return platform in ("win32", "darwin")


CASE_FOLDING = isCaseFolding()


def foldCase(name, platform=sys.platform):
    """Return *name* in the form the filesystem on *platform* treats as identical.

    Folds case on Windows and macOS, and also Unicode normalization on macOS. Use for
    comparison keys only, never for names written to disk or shown to the user.
    """
    if platform == "win32":
        return ntpath.normcase(name)
    if platform == "darwin":
        return unicodedata.normalize("NFC", name).lower()
    return name


def longPath(path):
    """Expand Windows 8.3 short names (``PROGRA~1``) in absolute *path* to their long form.

    Components that do not exist yet are kept as given. Returns *path* unchanged elsewhere.
    """
    if sys.platform != "win32" or "~" not in path:
        return path
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


def casedAbspath(fileName):
    """Return an absolute path for *fileName* that keeps the case it was given."""
    return longPath(os.path.abspath(fileName))


def abspath(fileName):
    """Return a normalized absolute path that uniquely identifies a file.

    This is an identity key only (case-folded where the filesystem ignores case). Never store
    it as a handle's path or use its basename as an index key; use `casedAbspath` for that.
    """
    return foldCase(casedAbspath(fileName))
