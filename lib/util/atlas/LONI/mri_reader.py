# -*- coding: utf-8 -*-

## Function for reading NiFTI-1 and ANALYZE 7.5 image formats  (.nii and .hdr/.img files)
import numpy as np

dataTypes = {
    0: None,
    1: 'BINARY',
    2: np.ubyte,
    4: np.short,
    8: np.int,
    16: np.float,
    32: np.complex,   ## two floats: (re, im)
    64: np.double,
    128: 'RGB',
    256: 'ALL'
}
    
        

import struct
def readA75(hdrFile, imgFile=None):
    hdr = open(hdrFile, 'rb').read()
    hdr_key = struct.unpack('i10s18sihcc', hdr[:40])
    (sizeof_hdr, data_type, db_name, extents, session_error, regular, hkey_un0) = hdr_key
    if regular != 'r':
        raise Exception("This function does not handle irregular arrays")
    
    img_dim = struct.unpack('18h16f2i', hdr[40:148])
    dim = img_dim[:8]
    (datatype, bitpix, dim_un0) = img_dim[15:18]
    pixdim = img_dim[18:26]
    vox_offset = img_dim[26]
    (cal_max, cal_min, compressed, verified, glmax, glmin) = img_dim[30:]
    
    print "dims:", dim
    print "depth:", bitpix
    print "type:", datatype
    
    if imgFile is None:
        imgFile = os.path.splitext(hdrFile)[0] + '.img'
    
    data = open(imgFile, 'rb').read()
    data = np.fromstring(data, dtype=dataTypes[datatype])
    data.shape = dim[1:dim[0]]
    return data
    
if __name__ == '__main__':
    import sys
    header = sys.argv[1]
    
    data = readA75(header)
    from pyqtgraph.graphicsWindows import *
    w = ImageWindow()
    w.setImage(data)