# -*- coding: utf-8 -*-

from metaarray import MetaArray as MA
from numpy import ndarray, loadtxt
from FileType import *

#class MetaArray(FileType):
    #@staticmethod
    #def write(self, dirHandle, fileName, **args):
        #self.data.write(os.path.join(dirHandle.name(), fileName), **args)
        
    #@staticmethod
    #def extension(self, **args):
        #return ".ma"
        
#def fromFile(fileName, info=None):
    #return MA(file=fileName)



class CSVFile(FileType):
    
    extensions = ['.csv']   ## list of extensions handled by this class
    dataTypes = [MA, ndarray]    ## list of python types handled by this class
    priority = 10      ## low priority; MetaArray is the preferred way to move data..
    
    #@classmethod
    #def write(cls, data, dirHandle, fileName, **args):
        #"""Write data to fileName.
        #Return the file name written (this allows the function to modify the requested file name)
        #"""
        #ext = cls.extensions[0]
        #if fileName[-len(ext):] != ext:
            #fileName = fileName + ext
            
        #if not isinstance(data, MetaArray):
            #data = MetaArray(data)
        #data.write(os.path.join(dirHandle.name(), fileName), **args)
        #return fileName
        
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        #fn = fileHandle.name()
        #fd = open(fn)
        #header = fd.readline().split(',')
        
        
        return loadtxt(fn, delimiter=',')
