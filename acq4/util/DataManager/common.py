import os


def abspath(fileName):
    """Return an absolute path string which is guaranteed to uniquely identify a file."""
    return os.path.normcase(os.path.abspath(fileName))
