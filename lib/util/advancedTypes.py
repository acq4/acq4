# -*- coding: utf-8 -*-
"""
advancedTypes.py - Basic data structures not included with python 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

Includes:
  - OrderedDict - Dictionary which preserves the order of its elements
  - BiDict, ReverseDict - Bi-directional dictionaries
  - ThreadsafeDict, ThreadsafeList - Self-mutexed data structures
"""

import threading, sys
from debug import *

class OrderedDict(dict):
    """extends dict so that elements are iterated in the order that they were added.
    Since this class can not be instantiated with regular dict notation, it instead uses
    a list of tuples: 
      od = OrderedDict([(key1, value1), (key2, value2), ...])
    items set using __setattr__ are added to the end of the key list.
    """
    
    def __init__(self, data=None):
        self.order = []
        if data is not None:
            for i in data:
                self[i[0]] = i[1]
    
    def __setitem__(self, k, v):
        if not self.has_key(k):
            self.order.append(k)
        dict.__setitem__(self, k, v)
    
    def __delitem__(self, k):
        self.order.remove(k)
        dict.__delitem__(self, k)

    def keys(self):
        return self.order[:]
    
    def items(self):
        it = []
        for k in self.keys():
            it.append((k, self[k]))
        return it
    
    def values(self):
        return [self[k] for k in self.order]
    
    def remove(self, key):
        del self[key]
        #self.order.remove(key)
    
    def __iter__(self):
        for k in self.order:
            yield k
            
    def update(self, data):
        """Works like dict.update, but accepts list-of-tuples as well as dict."""
        if isinstance(data, dict):
            for k in data.keys():
                self[k] = data[k]
        else:
            for k,v in data:
                self[k] = v

    def copy(self):
        return OrderedDict(self.items())
        
    def itervalues(self):
        for k in self.order:
            yield self[k]
            
    def iteritems(self):
        for k in self.order:
            yield (k, self[k])
            
    
        

class ReverseDict(dict):
    """extends dict so that reverse lookups are possible by requesting the key as a list of length 1:
       d = BiDict({'x': 1, 'y': 2})
       d['x']
         1
       d[[2]]
         'y'
    """
    def __init__(self, data=None):
        if data is None:
            data = {}
        self.reverse = {}
        for k in data:
            self.reverse[data[k]] = k
        dict.__init__(self, data)
        
    def __getitem__(self, item):
        if type(item) is list:
            return self.reverse[item[0]]
        else:
            return dict.__getitem__(self, item)

    def __setitem__(self, item, value):
        self.reverse[value] = item
        dict.__setitem__(self, item, value)

class BiDict(dict):
    """extends dict so that reverse lookups are possible by adding each reverse combination to the dict.
    This only works if all values and keys are unique."""
    def __init__(self, data=None):
        if data is None:
            data = {}
        dict.__init__(self)
        for k in data:
            self[data[k]] = k
        
    def __setitem__(self, item, value):
        dict.__setitem__(self, item, value)
        dict.__setitem__(self, value, item)
    

class ThreadsafeDict(dict):
    """Extends dict so that getitem, setitem, and contains are all thread-safe.
    Also adds lock/unlock functions for extended exclusive operations
    Converts all sub-dicts and lists to threadsafe as well.
    """
    
    def __init__(self, *args, **kwargs):
        self.mutex = threading.RLock()
        dict.__init__(self, *args, **kwargs)
        for k in self:
            if type(self[k]) is dict:
                self[k] = ThreadsafeDict(self[k])

    def __getitem__(self, attr):
        self.lock()
        try:
            val = dict.__getitem__(self, attr)
        finally:
            self.unlock()
        return val

    def __setitem__(self, attr, val):
        if type(val) is dict:
            val = ThreadsafeDict(val)
        self.lock()
        try:
            dict.__setitem__(self, attr, val)
        finally:
            self.unlock()
        
    def __contains__(self, attr):
        self.lock()
        try:
            val = dict.__contains__(self, attr)
        finally:
            self.unlock()
        return val

    def __len__(self):
        self.lock()
        try:
            val = dict.__len__(self)
        finally:
            self.unlock()
        return val
        
    def lock(self):
        self.mutex.acquire()
        
    def unlock(self):
        self.mutex.release()
        
class ThreadsafeList(list):
    """Extends list so that getitem, setitem, and contains are all thread-safe.
    Also adds lock/unlock functions for extended exclusive operations
    Converts all sub-lists and dicts to threadsafe as well.
    """
    
    def __init__(self, *args, **kwargs):
        self.mutex = threading.RLock()
        list.__init__(self, *args, **kwargs)
        for k in self:
            self[k] = mkThreadsafe(self[k])

    def __getitem__(self, attr):
        self.lock()
        try:
            val = list.__getitem__(self, attr)
        finally:
            self.unlock()
        return val

    def __setitem__(self, attr, val):
        val = makeThreadsafe(val)
        self.lock()
        try:
            list.__setitem__(self, attr, val)
        finally:
            self.unlock()
        
    def __contains__(self, attr):
        self.lock()
        try:
            val = list.__contains__(self, attr)
        finally:
            self.unlock()
        return val

    def __len__(self):
        self.lock()
        try:
            val = list.__len__(self)
        finally:
            self.unlock()
        return val
    
    def lock(self):
        self.mutex.acquire()
        
    def unlock(self):
        self.mutex.release()
        
def makeThreadsafe(obj):
    if type(obj) is dict:
        return ThreadsafeDict(obj)
    elif type(obj) is list:
        return ThreadsafeList(obj)
    elif type(obj) in [str, int, float, bool, tuple]:
        return obj
    else:
        raise Exception("Not sure how to make object of type %s thread-safe" % str(type(obj)))
        
        
class Locker:
    def __init__(self, lock):
        self.lock = lock
        self.lock.acquire()
    def __del__(self):
        try:
            self.lock.release()
        except:
            pass

