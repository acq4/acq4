# -*- coding: utf-8 -*-
import weakref
from Mutex import *


class InterfaceDirectory(QtCore.QObject):
    """Class for managing a phonebook of interfaces.
    Any object in the program may advertise its services via this directory"""
    sigInterfaceListChanged = QtCore.Signal(object)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.lock = Mutex(Mutex.Recursive)
        #self.objList = weakref.WeakValueDictionary() # maps objName:object
        self.nameList = {}                           # maps objName:typeName:None
        self.typeList = {}                           # maps typeName:objName:object
        
    def declareInterface(self, name, types, obj):
        """Declare a new interface. Types may be either a single string type or 
        a list of types. Returns False if the name is already in use."""
        with self.lock:
            #self.objList[name] = obj
        
            if isinstance(types, basestring):
                types = [types]
            for t in types:
                if t in self.typeList and name in self.typeList[t] and obj is not self.typeList[t][name]:
                    return False
                
            if name not in self.nameList:
                self.nameList[name] = {}
                
            for t in types:
                if t not in self.typeList:
                    self.typeList[t] = weakref.WeakValueDictionary()
                self.typeList[t][name] = obj
                self.nameList[name][t] = None
            
            self.sigInterfaceListChanged.emit(types)
            return True

    def removeInterface(self, name, types=None):
        """Remove an interface. A list of types (or a single type) may be specified. 
        Otherwise, all types are removed for the name provided."""
        with self.lock:
            #if name not in self.objList:
                #raise Exception("Interface %s does not exist." % name)
            
            if types is None:
                types = self.nameList[name]
                
            for t in types:
                del self.typeList[t][name]
                del self.nameList[name][t]
                
            if len(self.nameList[name]) == 0:
                del self.nameList[name]
                #del self.objList[name]
                
            self.sigInterfaceListChanged.emit(types)
        
    def listInterfaces(self, types=None):
        """Return a list of the names of interfaces with a given type.
        if type is None, instead return a dict tree of all interfaces.
        """
        with self.lock:
            if types is None:
                return dict([(k, dict(v)) for k,v in self.typeList.iteritems()])
                
            if isinstance(types, basestring):
                types = [types]
            ints = []
            for t in types:
                ints.extend(self.typeList.get(t, {}).keys())
                #for n in self.typeList.get(t, []):
                    #ints.append(n)
            return ints
            
    def getInterface(self, type, name):
        with self.lock:
            return self.typeList[type][name]
