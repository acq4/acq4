# -*- coding: utf-8 -*-
class CLibrary:
    def __init__(self, lib, headers):
        self.lib = lib
        self.headers = headers
        self.objs = {}

    def __getattr__(self, name):
        if name not in self.objs:
            if name in self.lib.values:
                self.objs['name'] = self.getVal(name)
            elif name in self.lib.structs:
                self.objs['name'] = self.getStruct(name)
            elif name in self.lib.functions:
                self.objs['name'] = self.getFunction(name)
            else:
                raise NameError(name)
        return self.objs['name']
        
    def getVal(self, name):
        pass
    
    def getStruct(self, name):
        pass
    
    def getFunction(self, func):
        return CFunction(self, getattr(self.lib, func), self.headers.functions[name])
        
    def __getitem__(self, item):
        return self.getVal(item)
        
class CFunction:
    def __init__(self, func, sig):
        self.func = func
        self.sig = sig
        
    def __call__(self, *args, **kwargs):
        pass
    
    
    
    
    
    

