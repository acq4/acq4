# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.util.metaarray import MetaArray as MA
from numpy import ndarray, loadtxt
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
            
        #if not (hasattr(data, 'implements') and data.implements('MetaArray')):
            #data = MetaArray(data)
        #data.write(os.path.join(dirHandle.name(), fileName), **args)
        #return fileName
        
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        fn = fileHandle.name()
        with open(fn) as fd:
        
            header = fd.readline().split(',')
            n = len(header)
           
            if header[-1] == '\n' or header[-1] == ' \n':
                header.pop(-1)
                dontUse = n-1
            elif header[-1][-1:] == '\n':
                header[-1] = header[-1][:-1]             
            
            try:
                [int(float(header[i])) for i in range(len(header))] ## if the first row of the file is not convertible to numbers, then this will raise a ValueError, and we use the first row as a header
                cols = range(n)
                cols.remove(dontUse)
                return loadtxt(fn, delimiter=',', usecols=cols)
            
            except ValueError:
                return loadtxt(fn, delimiter=',', skiprows=1, dtype=[(f, float) for f in header])
        
        #if type(header[0]) == type('str'):
        #    return loadtxt(fn, delimiter=',', skiprows=1, dtype=[(f, float) for f in header])

        #return loadtxt(fn, delimiter=',')
