# -*- coding: utf-8 -*-

from ctypes import *

class CLibrary:
    """The CLibrary class is intended to automate much of the work in using ctypes by integrating
    header file definitions from CParser. Ths class serves as a proxy to a ctypes, adding
    a few features:
      - allows easy access to values defined via CParser
      - automatic type conversions for function calls using CParser function signatures
      - creates ctype classes based on type definitions from CParser
    """
    
    cTypes = {
        'char': c_char,
        'wchar': c_wchar,
        'unsigned char': c_ubyte,
        'short': c_short,
        'short int': c_short,
        'int': c_int,
        'unsigned int': c_uint,
        'long': c_long,
        'unsigned long': c_ulong,
        'unsigned long int': c_ulong,
        '__int64': c_longlong,
        'long long': c_longlong,
        'long long int': c_longlong,
        'unsigned __int64': c_ulonglong,
        'unsigned long long': c_ulonglong,
        'unsigned long long int': c_ulonglong,
        'float': c_float,
        'double': c_double,
        'long double': c_longdouble
    }
    cPtrTypes = {
        'char': c_char_p,
        'wchar': c_wchar_p,
        'void': c_void_p
    }
        
        
    
    def __init__(self, lib, headers):
        ## name everything using underscores to avoid name collisions with library
        
        self._lib_ = lib
        self._headers_ = headers
        self._defs_ = headers.defs
        self._objs_ = {}
        self._structs_ = {}
        self._unions_ = {}

    def __getattr__(self, name):
        if name not in self._objs_:
            if name in self._defs_['values']:
                self._objs_[name] = self._getVal(name)
            elif name in self._defs_['functions']:
                self._objs_[name] = self._getFunction(name)
            elif name in self._defs_['structs']:
                self._objs_[name] = self._cstruct(name)
            elif name in self._defs_['types']:
                self._objs_[name] = self._ctype(name)
            elif name in self._defs_['enums']:
                self._objs_[name] = self._defs_['enums'][name]
            else:
                raise NameError(name)
        return self._objs_[name]
        
    def _getVal(self, name):
        return self._defs_['values'][name]
    
    def _getFunction(self, funcName):
        try:
            func = getattr(self._lib_, funcName)
        except:
            raise Exception("Function name '%s' appears in headers but not in library!" % func)
            
        return CFunction(self, func, self._defs_['functions'][funcName])
        
    def _ctype(self, typ):
        """return a ctype object representing the named type"""
        # Is this a struct / union / enum?
        
        
        # Create the initial type
        mods = typ[1:]
        if typ[1] == '*' and typ[0] in CLibrary.cPtrTypes:
            cls = CLibrary.cPtrTypes[typ[0]]
            mods = typ[2:]
        elif typ[0] in CLibrary.cTypes:
            cls = CLibrary.cTypes[typ[0]]
        elif typ[0][:7] == 'struct ':
            cls = self._cstruct(self._defs_['types'][typ[0]])
        elif typ[0][:6] == 'union ':
            cls = self._cunion(self._defs_['types'][typ[0]])
        elif typ[0][:5] == 'enum ':
            cls = c_int
        else:
            raise Exception("Can't find base type for %s" % str(typ))
            
        # apply pointers and arrays
        for p in mods:
            if isinstance(p, basestring):  ## pointer or reference
                if p[0] in ['*', '&']:
                    for i in p:
                        cls = POINTER(cls)
            elif type(p) is list:          ## array
                for i in p:
                    cls = cls * i
            elif type(p) is tuple:
                raise Exception("Haven't implemented function types yet..")
            else:
                raise Exception("Not sure what to do with this type modifier: '%s'" % str(p))
        return cls
        
    def _cstruct(self, strName):
        if strName not in self._structs_:
            defs = self._defs_['structs'][strName]
            class s(Structure):
                pass
            ## must register struct here to allow recursive definitions.
            self._structs_[strName] = s
            #s._anonymous_ =
            s._fields_ = [(m[0], self._ctype(m[1])) for m in defs]
            s._defaults_ = [m[2] for m in defs]
        return self._structs_[strName]
        
    def _cunion(self, unionName):
        if unionName not in self._unions_:
            defs = self._defs_['unions'][unionName]
            class s(Union):
                pass
            ## must register struct here to allow recursive definitions.
            self._unions_[unionName] = s
            #s._anonymous_ =
            s._fields_ = [(m[0], self._ctype(m[1])) for m in defs]
            s._defaults_ = [m[2] for m in defs]
        return self._unions_[unionName]
        
    def __getitem__(self, item):
        return self.getVal(item)
        
class CFunction:
    def __init__(self, lib, func, sig):
        self._lib_ = lib
        self.func = func
        self.sig = sig
        func.restype = lib._ctype(sig[0])
        func.argtypes = map(lib._ctype, sig[1])
        
    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)
    
    
    
    
    
    

