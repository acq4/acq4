# -*- coding: utf-8 -*-
import weakref
from Mutex import *









class InterfaceDirectory(QtCore.QObject):
    """Class for managing a phonebook of interfaces.
    Any object in the program may advertise its services via this directory"""
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.lock = Mutex(Mutex.Recursive)
        self.objList = weakref.WeakValueDictionary()
        self.nameList = {}
        self.typeList = {}
        
    def declareInterface(self, name, types, obj):
        """Declare a new interface. Types may be either a single string type or 
        a list of types. Returns False if the name is already in use."""
        with self.lock:
            if name in self.objList and obj is not self.objList[name]:
                return False
            self.objList[name] = obj
        
            if isinstance(types, basestring):
                types = [types]
                
            if name not in self.nameList:
                self.nameList[name] = {}
                
            for t in types:
                if t not in self.typeList:
                    self.typeList[t] = {}
                self.typeList[t][name] = None
                self.nameList[name][t] = None
            
            self.emit(QtCore.SIGNAL('interfaceListChanged'), types)
            return True

    def removeInterface(self, name, types=None):
        """Remove an interface. A list of types (or a single type) may be specified. 
        Otherwise, all types are removed for the name provided."""
        with self.lock:
            if name not in self.objList:
                raise Exception("Interface %s does not exist." % name)
            
            if types is None:
                types = self.nameList[name]
                
            for t in types:
                del self.typeList[t][name]
                del self.nameList[name][t]
                
            if len(self.nameList[name]) == 0:
                del self.nameList[name]
                del self.objList[name]
                
            self.emit(QtCore.SIGNAL('interfaceListChanged'), types)
        
    def listInterfaces(self, types):
        with self.lock:
            if isinstance(types, basestring):
                types = [types]
            ints = []
            for t in types:
                for n in self.typeList.get(t, []):
                    ints.append(n)
            return ints
            
    def getInterface(self, name):
        with self.lock:
            return self.objList[name]
