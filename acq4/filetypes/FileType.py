# -*- coding: utf-8 -*-
from __future__ import print_function
"""
FileType.py -  Base class for all file types
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This abstract class defines the interface that must be used to extend acq4 to support
more file types. The classes are not meant to be instantiated, but instead are just used
to encapsulate a set of static methods.
"""

import os

class FileType:
    
    extensions = []   ## list of extensions handled by this class
    dataTypes = []    ## list of python types handled by this class
    priority = 0      ## priority for this class when multiple classes support the same file types
    
    @classmethod
    def typeName(cls):
        """Return a string representing the file type for this class.
        The default implementation just returns the name of the class."""
        return cls.__name__
        
    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        """Write data to fileName.
        Return the file name written (this allows the function to modify the requested file name)
        """
        raise Exception("Function must be implemented in subclass")
        
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        raise Exception("Function must be implemented in subclass")
        
    @classmethod
    def acceptsFile(cls, fileHandle):
        """Return priority value if the file can be read by this class.
        Otherwise return False.
        The default implementation just checks for the correct name extensions."""
        name = fileHandle.name()
        for ext in cls.extensions:
            if name[-len(ext):].lower() == ext.lower():
                return cls.priority
        return False
        
    @classmethod
    def acceptsData(cls, data, fileName):
        """Return priority value if the data can be written by this class.
        Otherwise return False."""
        for typ in cls.dataTypes:
            if isinstance(data, typ):
                return cls.priority
        return False
        
    @classmethod
    def addExtension(cls, fileName):
        """Return a file name with extension added if it did not already have one."""
        for ext in cls.extensions:
            if fileName[-len(ext):].lower() == ext.lower():
                return fileName
        return fileName + cls.extensions[0]