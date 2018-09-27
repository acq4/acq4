# -*- coding: utf-8 -*-
from __future__ import print_function
from .FileType import *
    
class FlatDict(FileType):
    
    extensions = ['.dict']   ## list of extensions handled by this class
    dataTypes = [dict]    ## list of python types handled by this class
    priority = 50      
    
    
    ##not implemented yet.
    
    #@classmethod
    #def write(cls, data, dirHandle, fileName, **args):
        #"""Write data to fileName.
        #Return the file name written (this allows the function to modify the requested file name)
        #"""
        #fileName = cls.addExtension(fileName)
        #return fileName
        
    #@classmethod
    #def read(cls, fileHandle):
        #"""Read a file, return a data object"""
        #return MA(file=fileHandle.name())
    
    