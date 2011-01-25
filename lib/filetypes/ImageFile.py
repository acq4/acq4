# -*- coding: utf-8 -*-

import Image
from numpy import array, ndarray
from metaarray import MetaArray as MA
from FileType import *

#class ImageFile(FileType):
    #def __init__(self, data):
        #self.data = data
        
    #def write(self, dirHandle, fileName):
        #img = Image.fromarray(self.data.transpose())
        #img.save(os.path.join(dirHandle.name(), fileName))
        
#def fromFile(fileName, info=None):
    #img = Image.open(fileName)
    #return array(img).transpose()


class ImageFile(FileType):
    
    extensions = ['.png', '.tif']   ## list of extensions handled by this class
    dataTypes = [MA, ndarray]    ## list of python types handled by this class
    priority = 50      ## medium priority; MetaArray should be used for writing arrays if possible;
    
    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        """Write data to fileName.
        Return the file name written (this allows the function to modify the requested file name)
        """
        fileName = cls.addExtension(fileName)
        img = Image.fromarray(data.transpose())
        img.save(os.path.join(dirHandle.name(), fileName))
        return fileName
        
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        img = Image.open(fileHandle.name())
        arr = array(img)
        if arr.ndim == 0:
            raise Exception("Image has no data. Either 1) this is not a valid image or 2) the PIL script is not correctly installed.")
        transp = range(arr.ndim)    ## switch axis order y,x to x,y
        if len(img.size) == 2:
            transp[0] = 1
            transp[1] = 0
        elif len(img.size) == 3:
            transp[1] = 2
            transp[2] = 1
        #print arr.shape
        arr = arr.transpose(tuple(transp))
        #print arr.shape
        return arr
