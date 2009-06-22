# -*- coding: utf-8 -*-

from lib.util.MetaArray import MetaArray

#class MetaArray:
    #def __init__(self, data):
        #self.data = data
        
    #def typeName(self):
        #return 'MetaArray'
        
    #def write(self, fileName, *args):
        #self.data.write(fileName, *args)
        
def fromFile(fileName, info=None):
    return MetaArray(file=fileName)
    