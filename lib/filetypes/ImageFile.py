# -*- coding: utf-8 -*-

import Image

## Install support for 16-bit images in PIL
Image._MODE_CONV["I;16"] = ('%su2' % Image._ENDIAN, None)
Image._fromarray_typemap[((1, 1), "<u2")] = ("I", "I;16")

#import png ## better png support than PIL

from numpy import array, ndarray
from metaarray import MetaArray as MA
from FileType import *

#import libtiff
#from PyQt4 import QtCore, QtGui

class Array(ndarray):  ## just allows us to add some dynamic attributes
    def __new__(cls, arr):
        return arr.view(cls)

class ImageFile(FileType):
    
    extensions = ['.png', '.tif', '.jpg']   ## list of extensions handled by this class
    dataTypes = [MA, ndarray]    ## list of python types handled by this class
    priority = 50      ## medium priority; MetaArray should be used for writing arrays if possible;
    
    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        """Write data to fileName.
        Return the file name written (this allows the function to modify the requested file name)
        """
        fileName = cls.addExtension(fileName)
        ext = os.path.splitext(fileName)[1].lower()[1:]
        
        img = Image.fromarray(data.transpose())
        img.save(os.path.join(dirHandle.name(), fileName))
        
        #if ext in ['tif', 'tiff']:
            #d = data.transpose()
            #tiff = libtiff.TIFFimage(d, description='')
            #tiff.write_file(os.path.join(dirHandle.name(), fileName), compression='none')
        #else:
            #ims = data.tostring()
            #img = QtGui.QImage(buffer(ims), data.shape[1], data.shape[0], QtGui.QImage.Format_ARGB32)
            #w = QtGui.QImageWriter(os.path.join(dirHandle.name(), fileName), ext)
            #w.write(img)
        return fileName
        
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        img = Image.open(fileHandle.name())
        arr = array(img)
        if arr.ndim == 0:
            raise Exception("Image has no data. Either 1) this is not a valid image or 2) the PIL script is not correctly installed.")
            
        #ext = os.path.splitext(fileHandle.name())[1].lower()[1:]
        #if ext in ['tif', 'tiff']:
            #tif = libtiff.TIFFfile(fileHandle.name())
            #samples, sample_names = tif.get_samples()
            #if len(samples) != 1:
                #arr = np.concatenate(samples)
            #else:
                #arr = samples[0]
        #else:
            #img = QtGui.QImage()
            #img.load(fileHandle.name())
            #ptr = img.bits()
            #ptr.setsize(img.byteCount())
            #buf = buffer(ptr, 0, img.byteCount())
            #arr = np.frombuffer(buf, dtype=np.ubyte)
            #arr.shape = (img.height(), img.width(), img.depth() / 8)
            
            
        transp = range(arr.ndim)    ## switch axis order y,x to x,y
        if arr.ndim == 2:
            transp[0] = 1
            transp[1] = 0
            axisHint = ['x', 'y']
        elif arr.ndim == 3:
            transp[1] = 2
            transp[2] = 1
            axisHint = ['t', 'x', 'y']
        else:
            raise Exception("Bad image size: %s" % str(arr.ndim))
        #print arr.shape
        arr = arr.transpose(tuple(transp))
        axisHint.append(img.mode)
        
        arr = Array(arr) ## allow addition of new attributes
        arr.axisHint = arr
        #print arr.shape
        return arr
