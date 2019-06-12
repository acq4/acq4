# -*- coding: utf-8 -*-
from __future__ import print_function

from PIL import Image

## Install support for 16-bit images in PIL

if hasattr(Image, 'VERSION') and  Image.VERSION == '1.1.7':
    Image._MODE_CONV["I;16"] = ('%su2' % Image._ENDIAN, None)
    Image._fromarray_typemap[((1, 1), "<u2")] = ("I", "I;16")
if hasattr(Image, 'VERSION') and  Image.VERSION == '1.1.6':
    Image._MODE_CONV["I;16"] = ('%su2' % Image._ENDIAN, None)
    ## just a copy of fromarray() from Image.py with I;16 added in
    def fromarray(obj, mode=None):
        arr = obj.__array_interface__
        shape = arr['shape']
        ndim = len(shape)
        try:
            strides = arr['strides']
        except KeyError:
            strides = None
        if mode is None:
            typestr = arr['typestr']
            if not (typestr[0] == '|' or typestr[0] == Image._ENDIAN or
                    typestr[1:] not in ['u1', 'b1', 'i4', 'f4']):
                raise TypeError("cannot handle data-type")
            if typestr[0] == Image._ENDIAN:
                typestr = typestr[1:3]
            else:
                typestr = typestr[:2]
            if typestr == 'i4':
                mode = 'I'
            if typestr == 'u2':
                mode = 'I;16'
            elif typestr == 'f4':
                mode = 'F'
            elif typestr == 'b1':
                mode = '1'
            elif ndim == 2:
                mode = 'L'
            elif ndim == 3:
                mode = 'RGB'
            elif ndim == 4:
                mode = 'RGBA'
            else:
                raise TypeError("Do not understand data.")
        ndmax = 4
        bad_dims=0
        if mode in ['1','L','I','P','F']:
            ndmax = 2
        elif mode == 'RGB':
            ndmax = 3
        if ndim > ndmax:
            raise ValueError("Too many dimensions.")

        size = shape[:2][::-1]
        if strides is not None:
            obj = obj.tostring()

        return frombuffer(mode, size, obj, "raw", mode, 0, 1)
        
    Image.fromarray=fromarray

#import png ## better png support than PIL

from numpy import array, ndarray
from acq4.util.metaarray import MetaArray as MA
from .FileType import *

#import libtiff
#from acq4.util import Qt

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
        try:
            img = Image.fromarray(data.transpose())
            img.save(os.path.join(dirHandle.name(), fileName))
        except TypeError:
            import tifffile
            name = os.path.join(dirHandle.name(), fileName)
            tifffile.imsave(name, data.transpose(), photometric='rgb')

        #if ext in ['tif', 'tiff']:
            #d = data.transpose()
            #tiff = libtiff.TIFFimage(d, description='')
            #tiff.write_file(os.path.join(dirHandle.name(), fileName), compression='none')
        #else:
            #ims = data.tostring()
            #img = Qt.QImage(buffer(ims), data.shape[1], data.shape[0], Qt.QImage.Format_ARGB32)
            #w = Qt.QImageWriter(os.path.join(dirHandle.name(), fileName), ext)
            #w.write(img)
        return fileName
        
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        try:
            img = Image.open(fileHandle.name())
        except IOError:
            import tifffile
            img = tifffile.imread(fileHandle.name())
            img = img.transpose()

        arr = array(img)
        if arr.ndim == 0:
            raise Exception("Image has no data. Either 1) this is not a valid image or 2) PIL does not support this image type.")
            
        #ext = os.path.splitext(fileHandle.name())[1].lower()[1:]
        #if ext in ['tif', 'tiff']:
            #tif = libtiff.TIFFfile(fileHandle.name())
            #samples, sample_names = tif.get_samples()
            #if len(samples) != 1:
                #arr = np.concatenate(samples)
            #else:
                #arr = samples[0]
        #else:
            #img = Qt.QImage()
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
            if not hasattr(img, 'getbands'): ## then we're dealing with a tifffile image instead of a PIL image
                #transp[0] = 1
                #transp[1] = 0
                axisHint = ['x', 'y', 'R', 'G', 'B']
            elif len(img.getbands()) > 1:
                transp[0] = 1
                transp[1] = 0
                axisHint = ['x', 'y']
            else:
                transp[1] = 2
                transp[2] = 1
                axisHint = ['t', 'x', 'y']
        elif arr.ndim == 4:
            transp[1] = 2
            transp[2] = 1
            axisHint = ['t', 'x', 'y']
        else:
            raise Exception("Bad image size: %s" % str(arr.ndim))
        #print arr.shape
        arr = arr.transpose(tuple(transp))
        if hasattr(img, 'getbands'):
            axisHint.append(img.getbands())
        
        arr = Array(arr) ## allow addition of new attributes
        arr.axisHint = arr
        #print arr.shape
        return arr
