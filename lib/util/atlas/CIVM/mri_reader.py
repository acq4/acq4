# -*- coding: utf-8 -*-

## Function for reading NiFTI-1 and ANALYZE 7.5 image formats  (.nii and .hdr/.img files)
import numpy as np
import os

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
        print "n+1 format; loading data from", hdrFile
        return parseNii(hdrFH, hdrFile)
    elif nii == 'ni1\0':
        imgFile = os.path.splitext(hdrFile)[0] + '.img'
        print "ni1 format; loading data from", imgFile
        return parseNii(hdrFH, imgFile)
    else:  ## assume ANALYZE75 format
        imgFile = os.path.splitext(hdrFile)[0] + '.img'
        print "ANALYZE75 format; loading data from", imgFile
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
    
    print "dims:", dim
    print "depth:", bitpix
    print "type:", datatype
    
    ## read data
    fh = open(imgFile, 'rb')
    data = fh.read()
    fh.close()
    data = np.fromstring(data, dtype=dataTypes[datatype])
    data.shape = dim[1:dim[0]]
    
    return data
    

def parseNii(headerFH, imgFile):
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
    
    dim = image_dim[:8]
    intent = image_dim[8:11]
    intent_code, datatype, bitpix, slice_start = image_dim[11:15]
    pixdim = image_dim[15:23]
    vox_offset, scl_slope, scl_inter, slice_end, slice_code = image_dim[23:28]
    xyzt_units, cal_max, cal_min, slice_duration, toffset, glmax, glmin = image_dim[28:35]
    
    descrip, aux_file, qform_code, sform_code = data_history[:4]
    quatern = data_history[4:7]
    qoffset = data_history[7:10]
    srow_x = data_history[10:14]
    srow_y = data_history[14:18]
    srow_z = data_history[18:22]
    intent_name, magic = data_history[22:]
    
    print "Description:", descrip[:descrip.index('\0')]

    ## sanity checks
    if magic not in ['nii\0', 'n+1\0']:
        raise Exception('Unsupported NiFTI version: "%s"' % magic)
    if dim[0] > 7:
        print header_key
        print dim
        ## If dim[0] > 7, then somehow this changes the byte ordering of the 
        ## header/data, but I can't find any info on this.
        raise Exception('Dim > 7 not supported. (got %d)' % dim[0])
    vox_offset = int(vox_offset)


    ## read extended data (nothing done here yet, we just let the user know that the data is there.)
    if extension[0] != '\0':
        ext = headerFH.read(8)
        esize, ecode = struct.unpack('2i', ext)
        #edata = headerFH.read(esize-8)
        
        if ecode == 2:
            print "Header has extended data in DICOM format (ignored)"
        elif ecode == 4: 
            print "Header has extended data in AFNI format (ignored)"
        else:
            print "Header has extended data in unknown format (code=%d; ignored)" % ecode
    
    ## do a little parsing
    shape = dim[1:dim[0]+1]
    size = (bitpix / 8) * reduce(lambda a,b: a*b, shape)
    dtype = niiDataTypes[datatype]
    if isinstance(dtype, basestring):
        raise Exception("Data type not supported: %s"% dtype)
    print "Dimensions:", dim[0]
    print "Data shape:", shape
    print "Data type: %s  (%dbpp)" % (str(dtype), bitpix)
    
    ## read image data. Anything more than 200MB, use memmap.
    if size < 200e6:
        if magic == 'n+1\0':  ## data is in the same file as the header
            vox_offset = max(352, vox_offset)
            headerFH.seek(int(vox_offset))
            data = headerFH.read(size)
        elif magic == 'nii\0':               ## data is in a separate .img file
            imgFile = os.path.splitext(hdrFile)[0] + '.img'
            fh = open(imgFile, 'rb')
            fh.seek(vox_offset)
            data = fh.read(size)
        headerFH.close()
        
        if len(data) != size:
            raise Exception("Data size is incorrect. Expected %d, got %d" % (size, len(data)))
            
        data = np.fromstring(data, dtype=dtype)
        data.shape = dim[1:dim[0]+1]
    else:
        print "Large file; loading by memmap"
        if magic == 'n+1\0':  ## data is in the same file as the header
            vox_offset = max(352, vox_offset)
            fh = headerFH
        elif magic == 'nii\0':               ## data is in a separate .img file
            imgFile = os.path.splitext(hdrFile)[0] + '.img'
            fh = open(imgFile, 'rb')
            headerFH.close()
        data = np.memmap(fh, offset=vox_offset, dtype=dtype, shape=shape, mode='r')
    
    ## apply scaling
    if scl_slope == 0.0:
        scl_slope = 1.0
    
    if (scl_slope != 1.0 or scl_inter != 0.0) and datatype != 128: ## scaling not allowed for RGB24
        print "Applying scale and offset"
        data = (data.astype(np.float32) * scl_slope) + scl_inter

    xUnits = units[xyzt_units & 0x07]
    tUnits = units[xyzt_units & 0x38]

    ## determine coordinate system
    if sform_code > 0:
        print "affine transform:"
        print srow_x
        print srow_y
        print srow_z
    else:
        pixdim = list(pixdim)
        pixdim[1] *= xUnits[1]
        pixdim[2] *= xUnits[1]
        pixdim[3] *= xUnits[1]
        pixdim[4] *= tUnits[1]
        print "Voxel dimensions:", pixdim
        ## try just using pixdim
    
    print "Voxel units:", xUnits[0]
    
    ## In NiFTI, dimensions MUST represent (x, y, z, t, v, ...)
    ## pixdim[1:] specifies voxel length along each axis
    ## intent_code
    ## orientation
    ## bitpix
    ## cal_min, cal_max are calibrated display black and white levels
    
    return data

def getByteOrder(hLen):
    order = '<'
    hLen1 = struct.unpack('<i', hLen)[0]
    if hLen1 == 348:
        print "Byte order is LE"
    else:
        order = '>'
        hLen2 = struct.unpack('>i', hLen)[0]
        if hLen2 == 348:
            print "Byte order is BE"
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
    for i in xrange(data.shape[0]):
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

if __name__ == '__main__':
    import sys
    import pyqtgraph as pg
    w = pg.ImageWindow()
    header = sys.argv[1]
    data = readA75(header)
    while data.ndim > 3:
        data = data[..., 0]
    
    ## load labels, recolor data
    if len(sys.argv) > 2:
        labels, num = sys.argv[2:]
        #dMax = data.max()
        #dMin = data.min()
        #scale = 255./(dMax-dMin)
        #print "Generating LUT"
        #lut = np.empty(2**16, dtype=np.ubyte)
        #diff = (dMax-dMin)/256.
        #for i in range(256):
            #lut[int(diff*i):int(diff*(i+1))] = i
        #lut[diff*255:] = 255
        #print "Processing data.."
        #data = lut[data]
        #data = data*scale
        #data -= data.min()
        #data = data.astype(np.byte)
        data = shortToByte(data)
        data = np.concatenate([data[..., np.newaxis]]*3, axis=3)
        
        lData = readA75(labels)
        while lData.ndim > 3:
            lData = lData[..., 0]
        mask = lData == int(num)
        data[...,0][mask] = 0
    
        
    w.setImage(data, autoLevels=False, levels=[0, 255])