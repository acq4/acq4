# -*- coding: utf-8 -*-
from __future__ import print_function

from .FileType import *
import numpy as np
from acq4.util.metaarray import MetaArray
from functools import reduce


class Analyze75(FileType):
    extensions = ['.nii', '.hdr']   ## list of extensions handled by this class
    dataTypes = []    ## list of python types handled by this class
    priority = 100      ## High priority; MetaArray is the preferred way to move data..
    
    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        """Write data to fileName.
        Return the file name written (this allows the function to modify the requested file name)
        """
        raise Exception('Writing NiFTI not implemented.')
        
    @classmethod
    def read(cls, fileHandle):
        if isinstance(fileHandle, six.string_types):
            fn = fileHandle
        else:
            fn = fileHandle.name()
        """Read a file, return a data object"""
        return readA75(fn)



## Function for reading NiFTI-1 and ANALYZE 7.5 image formats  (.nii and .hdr/.img files)
import numpy as np
import os
import six
from six.moves import range
from six.moves import reduce

dataTypes = {
    0: None,
    1: 'BINARY',
    2: np.ubyte,
    4: np.short,
    8: np.int,
    16: np.float32,
    32: np.complex,   ## two floats: (re, im)
    64: np.float64,
    128: [('R', np.ubyte), ('G', np.ubyte), ('B', np.ubyte)],
    256: 'ALL'
}

niiDataTypes = dataTypes.copy()
niiDataTypes.update({
    256: np.int8,
    512: np.uint16,
    768: np.uint32,
    1024: np.int64,
    1280: np.uint64,
    1536: "FLOAT128",
    1792: np.complex128,
    2048: "COMPLEX256",
    2304: [('R', np.ubyte), ('G', np.ubyte), ('B', np.ubyte), ('A', np.ubyte)],
})

units = {
    0: (None, 1.),
    1: ('m', 1.),
    2: ('m', 1e-3),
    3: ('m', 1e-6),
    8: ('s', 1.),
    16: ('s', 1e-3),
    24: ('s', 1e-6),
    32: ('Hz', 1.),
    40: ('ppm', 1.),
    48: ('rad/s', 1.),
}
    
    
class Obj(object):
    pass

#class Array(np.ndarray):  ## just allows us to add some dynamic attributes
    #def __new__(cls, arr):
        #return arr.view(cls)
    
import struct
def readA75(hdrFile):
    """Read ANALYZE or NiFTI format. 
      hdrFile: name of header file (.hdr, .ni1, or .nii) to read"""
    
    hdrFH = open(hdrFile, 'rb')
    
    ## determine if this is NiFTI or ANALYZE
    hdrFH.seek(344)
    nii = hdrFH.read(4)
    
    hdrFH = open(hdrFile, 'rb')
    
    if nii == 'n+1\0':
        print("n+1 format; loading data from", hdrFile)
        return parseNii(hdrFH, hdrFile)
    elif nii == 'ni1\0':
        imgFile = os.path.splitext(hdrFile)[0] + '.img'
        print("ni1 format; loading data from", imgFile)
        return parseNii(hdrFH, imgFile)
    else:  ## assume ANALYZE75 format
        imgFile = os.path.splitext(hdrFile)[0] + '.img'
        print("ANALYZE75 format; loading data from", imgFile)
        return parseA75(hdrFH, imgFile)


def parseA75(headerFH, imgFile):
    hdr = headerFH.read(348)
    if len(header) != 348:
        raise Exception("Header is wrong size! (expected 348, got %d" % len(header))

    order = getByteOrder(header[:4])

    ## break header into substructs
    hdr_key = struct.unpack(order+'i10s18sihcc', hdr[:40])
    img_dim = struct.unpack(order+'18h16f2i', hdr[40:148])
    data_history = struct.unpack(order+'80s24sc10s10s10s10s10s10s3s8i', hdr[148:348])
    
    ## pull variables from substructs
    (sizeof_hdr, data_type, db_name, extents, session_error, regular, hkey_un0) = hdr_key
    if regular != 'r':
        raise Exception("This function does not handle irregular arrays")
    
    (cal_max, cal_min, compressed, verified, glmax, glmin) = img_dim[30:]
    dim = img_dim[:8]
    (datatype, bitpix, dim_un0) = img_dim[15:18]
    #pixdim = img_dim[18:26]
    #vox_offset = img_dim[26]
    
    #print "dims:", dim
    #print "depth:", bitpix
    #print "type:", datatype
    
    ## read data
    fh = open(imgFile, 'rb')
    data = fh.read()
    fh.close()
    data = np.fromstring(data, dtype=dataTypes[datatype])
    data.shape = dim[1:dim[0]]
    
    return data
    

def parseNii(headerFH, imgFile):
    m = Obj()
    
    ## see nifti1.h
    header = headerFH.read(348)
    if len(header) != 348:
        raise Exception("Header is wrong size! (expected 348, got %d" % len(header))
    
    order = getByteOrder(header[:4])
    
    ## break up into substructs
    header_key = struct.unpack(order+'i10s18sihcc', header[:40])
    image_dim = struct.unpack(order+'8h3f4h11fhcB4f2i', header[40:148])
    data_history = struct.unpack(order+'80s24s2h18f16s4s', header[148:348])
    
    extension = headerFH.read(4)
    if len(extension) < 4:
        extension = '\0\0\0\0'
    
    ## pull variables from substructs
    dim_info = header_key[-1]  ## all others are unused in NiFTI
    
    m.dim = image_dim[:8]
    m.intent = image_dim[8:11]
    m.intent_code, m.datatype, m.bitpix, m.slice_start = image_dim[11:15]
    m.pixdim = image_dim[15:23]
    m.qfac = m.pixdim[0]
    if m.qfac == 0.0:
        m.qfac = 1.0
    m.vox_offset, m.scl_slope, m.scl_inter, m.slice_end, m.slice_code = image_dim[23:28]
    m.xyzt_units, m.cal_max, m.cal_min, m.slice_duration, m.toffset, m.glmax, m.glmin = image_dim[28:35]
    
    m.descrip, m.aux_file, m.qform_code, m.sform_code = data_history[:4]
    m.quatern = data_history[4:7]
    m.qoffset = data_history[7:10]
    m.srow_x = data_history[10:14]
    m.srow_y = data_history[14:18]
    m.srow_z = data_history[18:22]
    m.intent_name, m.magic = data_history[22:]
    
    try:
        m.descrip = m.descrip[:m.descrip.index('\0')]
    except ValueError:
        pass
    
    #print "Description:", descrip[:descrip.index('\0')]

    ## sanity checks
    if m.magic not in ['nii\0', 'n+1\0']:
        raise Exception('Unsupported NiFTI version: "%s"' % m.magic)
    if m.dim[0] > 7:
        raise Exception('Dim > 7 not supported. (got %d)' % m.dim[0])
    m.vox_offset = int(m.vox_offset)


    ## read extended data (nothing done here yet, we just let the user know that the data is there.)
    if extension[0] != '\0':
        ext = headerFH.read(8)
        esize, ecode = struct.unpack('2i', ext)
        #edata = headerFH.read(esize-8)
        
        if ecode == 2:
            print("Header has extended data in DICOM format (ignored)")
        elif ecode == 4: 
            print("Header has extended data in AFNI format (ignored)")
        else:
            print("Header has extended data in unknown format (code=%d; ignored)" % ecode)
    
    ## do a little parsing
    shape = m.dim[1:m.dim[0]+1]
    size = (m.bitpix / 8) * reduce(lambda a,b: a*b, shape)
    dtype = niiDataTypes[m.datatype]
    if isinstance(dtype, six.string_types):
        raise Exception("Data type not supported: %s"% dtype)
    #print "Dimensions:", dim[0]
    #print "Data shape:", shape
    #print "Data type: %s  (%dbpp)" % (str(dtype), bitpix)
    
    ## read image data. Anything more than 200MB, use memmap.
    if size < 200e6:
        if m.magic == 'n+1\0':  ## data is in the same file as the header
            m.vox_offset = max(352, m.vox_offset)
            headerFH.seek(int(m.vox_offset))
            data = headerFH.read(size)
        elif m.magic == 'nii\0':               ## data is in a separate .img file
            imgFile = os.path.splitext(hdrFile)[0] + '.img'
            fh = open(imgFile, 'rb')
            fh.seek(m.vox_offset)
            data = fh.read(size)
        headerFH.close()
        
        if len(data) != size:
            raise Exception("Data size is incorrect. Expected %d, got %d" % (size, len(data)))
            
        data = np.fromstring(data, dtype=dtype)
        data.shape = m.dim[1:m.dim[0]+1]
    else:
        #print "Large file; loading by memmap"
        if m.magic == 'n+1\0':  ## data is in the same file as the header
            m.vox_offset = max(352, m.vox_offset)
            fh = headerFH
        elif m.magic == 'nii\0':               ## data is in a separate .img file
            imgFile = os.path.splitext(hdrFile)[0] + '.img'
            fh = open(imgFile, 'rb')
            headerFH.close()
        data = np.memmap(fh, offset=m.vox_offset, dtype=dtype, shape=shape, mode='r')
    
    ## apply scaling
    if m.scl_slope == 0.0:
        m.scl_slope = 1.0
    
    if (m.scl_slope != 1.0 or m.scl_inter != 0.0) and m.datatype != 128: ## scaling not allowed for RGB24
        #print "Applying scale and offset"
        data = (data.astype(np.float32) * m.scl_slope) + m.scl_inter

    m.xUnits = units[m.xyzt_units & 0x07]
    m.tUnits = units[m.xyzt_units & 0x38]

    info = []
    for x in shape:
        info.append({})
    
    
    ## determine coordinate system
    if m.qform_code > 0:  ## coordinate method 2  (currently rotation matrix is not implemented, only offset.)
        m.xVals = []
        for i in range(min(3, m.dim[0])):
            offset = m.qoffset[i] * m.xUnits[1]
            width = (m.pixdim[i+1] * m.xUnits[1] * (m.dim[i+1]-1))
            info[i]['values'] = np.linspace(offset, offset + width, m.dim[i+1])
    
    if m.sform_code > 0:  ## coordinate method 3
        print("Warning: This data (%s) has an unsupported affine transform." % headerFH.name)
        #print "affine transform:"
        #print srow_x
        #print srow_y
        #print srow_z
    else:  ## coordinate method 1
        m.pixdim = list(m.pixdim)
        m.pixdim[1] *= m.xUnits[1]
        m.pixdim[2] *= m.xUnits[1]
        m.pixdim[3] *= m.xUnits[1]
        m.pixdim[4] *= m.tUnits[1]
        #print "Voxel dimensions:", pixdim
        ## try just using pixdim
    
    #print "Voxel units:", xUnits[0]
    
    ## In NiFTI, dimensions MUST represent (x, y, z, t, v, ...)
    ## x = right, y = anterior, z = superior
    names = ['right', 'anterior', 'dorsal', 'time']
    for i in range(min(4, m.dim[0])):
        info[i]['name'] = names[i]
        
    
    ## pixdim[1:] specifies voxel length along each axis
    ## intent_code
    ## orientation
    ## bitpix
    ## cal_min, cal_max are calibrated display black and white levels
    
    info.append(m.__dict__)
    
    #print "dims:", m.dim
    #print info
    data = MetaArray(data, info=info)
    return data

def getByteOrder(hLen):
    order = '<'
    hLen1 = struct.unpack('<i', hLen)[0]
    if hLen1 == 348:
        pass
        #print "Byte order is LE"
    else:
        order = '>'
        hLen2 = struct.unpack('>i', hLen)[0]
        if hLen2 == 348:
            pass
            #print "Byte order is BE"
        else:
            raise Exception('Header length must be 348 (got %d (LE) or %d (BE))' % (hLen1, hLen2))
    return order
    
def shortToByte(data, dMin=None, dMax=None):
    if dMax is None:
        dMax = data.max()
    if dMin is None:
        dMin = data.min()
    lut = np.empty(2**16, dtype=np.ubyte)
    diff = (dMax-dMin)/256.
    for i in range(256):
        lut[int(diff*i):int(diff*(i+1))] = i
    lut[diff*255:] = 255
    d2 = np.empty(data.shape, dtype=np.ubyte)
    for i in range(data.shape[0]):
        d2[i] = lut[data[i]]
    return d2

def loadMulti(*files):
    d1 = shortToByte(readA75(files[0]))    
    data = np.empty(d1.shape + (len(files),), dtype=np.ubyte)
    data[..., 0] = d1
    del d1
    for i in range(1, len(files)):
        data[..., i] = shortToByte(readA75(files[i]))
    return data
