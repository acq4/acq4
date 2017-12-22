# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.util.metaarray import MetaArray as MA
from numpy import ndarray
from .FileType import *

#class MetaArray(FileType):
    #@staticmethod
    #def write(self, dirHandle, fileName, **args):
        #self.data.write(os.path.join(dirHandle.name(), fileName), **args)
        
    #@staticmethod
    #def extension(self, **args):
        #return ".ma"
        
#def fromFile(fileName, info=None):
    #return MA(file=fileName)



class MetaArray(FileType):
    
    extensions = ['.ma']   ## list of extensions handled by this class
    dataTypes = [MA, ndarray]    ## list of python types handled by this class
    priority = 100      ## High priority; MetaArray is the preferred way to move data..
    
    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        """Write data to fileName.
        Return the file name written (this allows the function to modify the requested file name)
        """
        ext = cls.extensions[0]
        if fileName[-len(ext):] != ext:
            fileName = fileName + ext
            
        if not isinstance(data, MA):
            data = MA(data)
        data.write(os.path.join(dirHandle.name(), fileName), **args)
        return fileName
        
    @classmethod
    def read(cls, fileHandle, *args, **kargs):
        """Read a file, return a data object"""
        return MA(file=fileHandle.name(), *args, **kargs)
