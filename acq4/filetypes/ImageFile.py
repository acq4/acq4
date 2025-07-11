import os

from MetaArray import MetaArray as MA
from PIL import Image
from numpy import array, ndarray

from .FileType import FileType


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
            #img = Qt.QImage(buffer(ims), data.shape[1], data.shape[0], Qt.QImage.Format_ARGB32)
            #w = Qt.QImageWriter(os.path.join(dirHandle.name(), fileName), ext)
            #w.write(img)
        return fileName
        
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        img = Image.open(fileHandle.name())
        arr = array(img)
        if arr.ndim == 0:
            raise ValueError("Image has no data. Either 1) this is not a valid image or 2) PIL does not support this image type.")

        transp = list(range(arr.ndim))    ## switch axis order y,x to x,y
        if arr.ndim == 2:
            transp[0] = 1
            transp[1] = 0
            axisHint = ['x', 'y']
        elif arr.ndim == 3:
            if len(img.getbands()) > 1:
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
            raise ValueError(f"Bad image size: {arr.ndim}")
        arr = arr.transpose(tuple(transp))
        axisHint.append(img.getbands())

        arr = Array(arr) ## allow addition of new attributes
        arr.axisHint = arr
        return arr
