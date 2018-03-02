# -*- coding: utf-8 -*-
from __future__ import print_function
"""
Mutex.py -  Stand-in extension of Qt's QMutex class
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

import six

from acq4.util import Qt
import traceback
import acq4.pyqtgraph as pg
from acq4.pyqtgraph.util.mutex import Mutex, RecursiveMutex


class ThreadsafeWrapper(object):
    """Wrapper that makes access to any object thread-safe (within reasonable limits).
       Mostly tested for wrapping lists, dicts, etc.
       NOTE: Do not instantiate directly; use threadsafe(obj) instead.
    - all method calls and attribute/item accesses are protected by mutex
    - optionally, attribute/item accesses may return protected objects
    - can be manually locked for extended operations
    """
    def __init__(self, obj, recursive=False, reentrant=True):
        """
        If recursive is True, then sub-objects accessed from obj are wrapped threadsafe as well.
        If reentrant is True, then the object can be locked multiple times from the same thread."""

        self.__TSOwrapped_object__ = obj
            
        if reentrant:
            self.__TSOwrap_lock__ = Mutex(Qt.QMutex.Recursive)
        else:
            self.__TSOwrap_lock__ = Mutex()
        self.__TSOrecursive__ = recursive
        self.__TSOreentrant__ = reentrant
        self.__TSOwrapped_objs__ = {}

    def lock(self, id=None):
        self.__TSOwrap_lock__.lock(id=id)
        
    def tryLock(self, timeout=None, id=None):
        self.__TSOwrap_lock__.tryLock(timeout=timeout, id=id)
        
    def unlock(self):
        self.__TSOwrap_lock__.unlock()
        
    def unwrap(self):
        return self.__TSOwrapped_object__

    def __safe_call__(self, fn, *args, **kargs):
        obj = self.__wrapped_object__()
        ret = getattr(obj, fn)(*args, **kargs)
        return self.__wrap_object__(ret)

    def __getattr__(self, attr):
        #try:
            #return object.__getattribute__(self, attr)
        #except AttributeError:
        with self.__TSOwrap_lock__:
            val = getattr(self.__wrapped_object__(), attr)
            #if callable(val):
                #return self.__wrap_object__(val)
            return self.__wrap_object__(val)

    def __setattr__(self, attr, val):
        if attr[:5] == '__TSO':
            #return object.__setattr__(self, attr, val)
            self.__dict__[attr] = val
            return
        with self.__TSOwrap_lock__:
            return setattr(self.__wrapped_object__(), attr, val)
            
    def __wrap_object__(self, obj):
        if not self.__TSOrecursive__:
            return obj
        if obj.__class__ in [int, float, str, six.text_type, tuple]:
            return obj
        if id(obj) not in self.__TSOwrapped_objs__:
            self.__TSOwrapped_objs__[id(obj)] = threadsafe(obj, recursive=self.__TSOrecursive__, reentrant=self.__TSOreentrant__)
        return self.__TSOwrapped_objs__[id(obj)]
        
    def __wrapped_object__(self):
        #if isinstance(self.__TSOwrapped_object__, weakref.ref):
            #return self.__TSOwrapped_object__()
        #else:
        return self.__TSOwrapped_object__
    
def mkMethodWrapper(name):
    return lambda self, *args, **kargs: self.__safe_call__(name, *args, **kargs)    
    
def threadsafe(obj, *args, **kargs):
    """Return a thread-safe wrapper around obj. (see ThreadsafeWrapper)
    args and kargs are passed directly to ThreadsafeWrapper.__init__()
    This factory function is necessary for wrapping special methods (like __getitem__)"""
    if type(obj) in [int, float, str, six.text_type, tuple, type(None), bool]:
        return obj
    clsName = 'Threadsafe_' + obj.__class__.__name__
    attrs = {}
    ignore = set(['__new__', '__init__', '__class__', '__hash__', '__getattribute__', '__getattr__', '__setattr__'])
    for n in dir(obj):
        if not n.startswith('__') or n in ignore:
            continue
        v = getattr(obj, n)
        if callable(v):
            attrs[n] = mkMethodWrapper(n)
    typ = type(clsName, (ThreadsafeWrapper,), attrs)
    return typ(obj, *args, **kargs)
        
    
if __name__ == '__main__':
    d = {'x': 3, 'y': [1,2,3,4], 'z': {'a': 3}, 'w': (1,2,3,4)}
    t = threadsafe(d, recursive=True, reentrant=False)