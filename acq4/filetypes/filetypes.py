# -*- coding: utf-8 -*-
from __future__ import print_function
"""
fileio.py -  FileType helper functions
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

Functions for accessing available fileTypes. Generally these are used by DataManager
and should not be accessed directly.
"""
import os
import acq4.util.debug as debug

KNOWN_FILE_TYPES = None
    
def suggestReadType(fileHandle):
    """Guess which fileType class should be used to read fileName.
    Return the name of the class."""
    maxVal = None
    maxType = None
    for typ in listFileTypes():
        try:
            cls = getFileType(typ)
        except:
            continue
        priority = cls.acceptsFile(fileHandle)
        if priority is False:
            continue
        else:
            if maxVal is None or priority > maxVal:
                maxVal = priority
                maxType = typ
    return maxType

def suggestWriteType(data, fileName=None):
    """Guess which fileType class should be used to write data.
    If fileName is specified, this may influence the guess.
    Return the name of the class."""
    maxVal = None
    maxType = None
    #print "Suggest for type %s, name %s" % (type(data), str(fileName))
    for typ in listFileTypes():
        try:
            cls = getFileType(typ)
        except:
            debug.printExc("ignoring filetype %s" % typ)
            continue
        priority = cls.acceptsData(data, fileName)
        #print "filetype %s has priority %d" %(typ, int(priority))
        if priority is False:
            continue
        else:
            if maxVal is None or priority > maxVal:
                maxVal = priority
                maxType = typ
    #print "Suggesting", maxType
    return maxType


def listReadTypes(fileHandle):
    """List all fileType classes that can read the file indicated."""
    return [typ for typ in listFileTypes() if typ.acceptsFile(fileHandle) is not False]


def listWriteTypes(data, fileName=None):
    """List all fileType classes that can write the data to file."""
    return [typ for typ in listFileTypes() if typ.acceptsData(data, fileName) is not False]


def registerFileType(name, cls):
    """Register a new file type.

    This adds support for automatic reading / writing of a file type.

    Parameters
    ----------
    name : str
        Name of the type to be registered
    cls : FileType subclass
        FileType subclass to register
    """
    global KNOWN_FILE_TYPES
    KNOWN_FILE_TYPES[name] = cls


def getFileType(typName):
    """Return the fileType class for the given name.
    (this is generally only for internal use)"""
    global KNOWN_FILE_TYPES
    if typName not in KNOWN_FILE_TYPES:
        mod = __import__('acq4.filetypes.' + typName, fromlist=['*'])
        cls = getattr(mod, typName)
        registerFileType(typName, cls)
        
    return KNOWN_FILE_TYPES[typName]
    
    
def listFileTypes():
    """Return a list of the names of all available fileType subclasses."""
    global KNOWN_FILE_TYPES
    if KNOWN_FILE_TYPES is None:
        KNOWN_FILE_TYPES = {}
        files = os.listdir(os.path.dirname(__file__))
        for f in ['filetypes.py', '__init__.py', 'FileType.py']:
            if f in files:
                files.remove(f)
        typs = [os.path.splitext(f)[0] for f in files if f[-3:] == '.py']
        for typ in typs:
            try:
                getFileType(typ)
            except:
                debug.printExc("Error loading file type library '%s':" % typ)
    return list(KNOWN_FILE_TYPES.keys())

## initialize:
listFileTypes()