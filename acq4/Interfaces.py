# -*- coding: utf-8 -*-
from __future__ import print_function

import weakref

import six


from pyqtgraph.util.mutex import Mutex
from acq4.util import Qt


class InterfaceMixin(object):
    """Mixin class used to allow objects to declare which APIs they implement.

    Use addInterface() to declare a supported API::

        class MyObject(InterfaceMixin):
            def __init__(self):
                self.addInterface("my_api")

    Use implements() to determine whether an object supports an API:

        if hasattr(obj, 'implements') and obj.implements('my_api'):
            # safe to call methods defined by my_api
    
    """
    def implements(self, interface=None):
        """Return True if this device implements the specified API.

        If no API name is given, then return the list of APIs implemented by this device.
        """
        ints = getattr(self, '_InterfaceMixin__interfaces', [])
        if interface is None:
            return ints
        return interface in ints

    def addInterface(self, name):
        """Declare that this device implements a particular API.
        """
        if not hasattr(self, '_InterfaceMixin__interfaces'):
            self.__interfaces = []
        if name not in self.__interfaces:
            self.__interfaces.append(name)
    

class InterfaceDirectory(Qt.QObject):
    """Class for managing a directory of interfaces, through which objects may advertise their services.
    """
    sigInterfaceListChanged = Qt.Signal(object)
    
    def __init__(self):
        Qt.QObject.__init__(self)
        self.lock = Mutex(Mutex.Recursive)
        self.nameList = {}                           # maps objName:typeName:None
        self.typeList = {}                           # maps typeName:objName:object
        
    def declareInterface(self, name, types, obj):
        """Declare a new interface. Types may be either a single string type or 
        a list of types.
        
        Raises NameError if the name is already in use."""
        with self.lock:
            if isinstance(types, six.string_types):
                types = [types]
            for t in types:
                if t in self.typeList and name in self.typeList[t] and obj is not self.typeList[t][name]:
                    raise NameError("Interface type %r name %r is already used." % (t, name))
                
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
            if types is None:
                types = self.nameList[name]
                
            for t in types:
                del self.typeList[t][name]
                del self.nameList[name][t]
                
            if len(self.nameList[name]) == 0:
                del self.nameList[name]
                
            self.sigInterfaceListChanged.emit(types)
        
    def removeObject(self, obj):
        """Remove all occurrences of object from the interface directory"""
        changedTypes = set()
        
        for typeName, objList in self.typeList.items():
            rem = []
            for objName, obj2 in objList.items():
                if obj is obj2:
                    rem.append(objName)
                    changedTypes.add(typeName)
            for objName in rem:
                del objList[objName]
                del self.nameList[objName][typeName]
                if len(self.nameList[objName]) == 0:
                    del self.nameList[objName]
        self.sigInterfaceListChanged.emit(list(changedTypes))
        
    def listInterfaces(self, types=None):
        """
        Return a list or dictionary of interface names for specific types.
        If *types* is a single string, return a list of interfaces for that type
        If *types* is a list, return a dictionary {type: [interfaces...], ...} 
        If *types* is None, return a dict tree of all interfaces.
        """
        with self.lock:
            if types is None:
                types = self.typeList.keys()
            
            elif isinstance(types, six.string_types):
                return list(self.typeList.get(types, {}).keys())
                
            ints = {}
            for t in types:
                ints[t] = list(self.typeList.get(t, {}).keys())
            return ints
            
    def getInterface(self, type, name):
        """Return the object that was previously declared with *name* and interface *type*.
        """
        with self.lock:
            return self.typeList[type][name]



