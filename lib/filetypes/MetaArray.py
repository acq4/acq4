# -*- coding: utf-8 -*-

from lib.util.MetaArray import MetaArray as MA
from FileType import *

class MetaArray(FileType):
    def __init__(self, data):
        self.data = data
        
    def write(self, dirHandle, fileName, **args):
        if fileName[-3:] != '.ma':
            fileName = fileName + '.ma'
        self.data.write(os.path.join(dirHandle.name(), fileName), **args)
        return fileName
        
def fromFile(fileName, info=None):
    return MA(file=fileName)
    