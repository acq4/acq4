# -*- coding: utf-8 -*-
import os

class FileType:
    def typeName(self):
        """Return the type name to be used when loading this file from disk."""
        return self.__class__.__name__
        
    def write(self, dirHandle, fileName, **args):
        """Write this object to fileName within dirHandle.
        Optionally return a string representing the file name written (this allows the function to modify the requested file name)
        """
        raise Exception("Function must be implemented in subclass")
        
    def extension(self, **args):
        return ''

        