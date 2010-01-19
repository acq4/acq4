# -*- coding: utf-8 -*-

from metaarray import MetaArray as MA
from FileType import *

class MetaArray(FileType):
    def __init__(self, data):
        self.data = data
        
    def write(self, dirHandle, fileName, **args):
        self.data.write(os.path.join(dirHandle.name(), fileName), **args)
        
    def extension(self, **args):
        return ".ma"
        
def fromFile(fileName, info=None):
    return MA(file=fileName)
    