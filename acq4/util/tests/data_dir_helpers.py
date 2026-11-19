"""Test helpers for shaping DataManager directories, e.g. into ones made before directories had uuids."""


def strip_uuid(dirHandle):
    index = dirHandle._readIndex()
    del index["."]["__uuid__"]
    dirHandle._writeIndex(index)
