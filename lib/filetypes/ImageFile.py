# -*- coding: utf-8 -*-

import Image
from numpy import array
from FileType import *

class ImageFile(FileType):
    def __init__(self, data):
        self.data = data
        
    def write(self, dirHandle, fileName):
        img = Image.fromarray(self.data.transpose())
        img.save(os.path.join(dirHandle.name(), fileName))
        
def fromFile(fileName, info=None):
    img = Image.open(fileName)
    return array(img).transpose()

