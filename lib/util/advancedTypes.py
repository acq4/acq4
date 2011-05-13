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

import threading, sys, copy
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
            for k, v in data.iteritems():
                self[k] = v
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
            
    def __deepcopy__(self, memo):
        return OrderedDict([(k, copy.deepcopy(v, memo)) for k, v in self.iteritems()])
        
        

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

    def __deepcopy__(self, memo):
        raise Exception("deepcopy not implemented")
        
        
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
    
    def __deepcopy__(self, memo):
        raise Exception("deepcopy not implemented")

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

    def __deepcopy__(self, memo):
        raise Exception("deepcopy not implemented")
        
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

    def __deepcopy__(self, memo):
        raise Exception("deepcopy not implemented")
        
        
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

class CaselessDict(dict):
    """Case-insensitive dict. Values can be set and retrieved using keys of any case.
    Note that when iterating, the original case is returned for each key."""
    def __init__(self, *args):
        dict.__init__(self, *args)
        self.keyMap = dict([(k.lower(), k) for k in self.keys()])
    
    def __setitem__(self, key, val):
        kl = key.lower()
        if kl in self.keyMap:
            dict.__setitem__(self, kl, val)
        else:
            dict.__setitem__(self, key, val)
            self.keyMap[kl] = key
            
    def __getitem__(self, key):
        kl = key.lower()
        if kl not in self.keyMap:
            raise KeyError(key)
        return dict.__getitem__(self, self.keyMap[kl])
        
    def __contains__(self, key):
        return key.lower() in self.keyMap
    
    def update(self, d):
        for k, v in d.iteritems():
            self[k] = v
            
    def copy(self):
        return CaselessDict(dict.copy(self))
        
    def __delitem__(self, key):
        kl = key.lower()
        if kl not in self.keyMap:
            raise KeyError(key)
        dict.__delitem__(self, self.keyMap[kl])
        del self.keyMap[kl]
            
    def __deepcopy__(self, memo):
        raise Exception("deepcopy not implemented")

class ProtectedDict(dict):
    """
    A class allowing read-only 'view' of a dict. 
    The object can be treated like a normal dict, but will never modify the original dict it points to.
    If any values in the dict are either list or dict, they will be returned as protected objects when accessed.
    """
    def __init__(self, data):
        self._data_ = data
        #for fn in ['keys', 'items', 'values', '__iter__', 'copy', 'itervalues', 'iteritems']:
            #setattr(self, fn, getattr(self._data_, fn))
                   
    #def keys(self):
        #return _data_.keys()
    
            
    def items(self):
        return ProtectedList(self._data_.items())
    
    def values(self):
        return ProtectedList(self._data_.values())
    
    def __getattribute__(self, attr):
        """We need inherit functions from self._data_, but we have already inherited them from dict, so we need to
        check if the attr is explicitly defined in ProtectedDict, and if it's not then we request the attribute
        from self._data_ (Why do we inherit from dict? So glad you asked. Because we need isinstance(ProtectedDict(), dict) 
        to return True)"""
        if attr in ProtectedDict.__dict__ or attr == '_data_':
            return object.__getattribute__(self, attr)
        else:
            return self._data_.__getattribute__(attr)
        
    def __getitem__(self, ind):
        val = self._data_.__getitem__(ind)
        return protect(val)
    
    #def __iter__(self):
        #return self._data_.__iter__()
    
    def copy(self):
        raise Exception("It is not safe to copy protected dicts! (instead try deepcopy, but be careful.)")
    
    def deepcopy(self):
        return copy.deepcopy(self._data_)
    
    def __deepcopy__(self, memo):
        return copy.deepcopy(self._data_, memo)
        
    def itervalues(self):
        for v in self._data_.itervalues():
            yield protect(v)
        
    def iteritems(self):
        for k, v in self._data_.iteritems():
            yield (k, protect(v))
            
    
    def error(self, *args, **kargs):
        raise Exception("Can not modify read-only dict.")
            
    __setitem__ = error
    __delitem__ = error
    remove = error
    update = error
    clear = error
    pop = error
    popitem = error
    setdefault = error
    
    ### These methods all use the same template (as in ProtectedList)
    def __repr__(self):
        return self._data_.__repr__()
        
    def __len__(self):
        return len(self._data_)
    
    def __contains__(self, arg):
        return self._data_.__contains__(arg)
    
    def __eq__(self, arg):
        return self._data_.__eq__(arg)
    
            
class ProtectedList(list):
    """
    A class allowing read-only 'view' of a list or dict. 
    The object can be treated like a normal list, but will never modify the original list it points to.
    """
    def __init__(self, data):
        self._data_ = data
    
    def __getattribute__(self, attr):
        """We need to inherit functions from self._data_, but we have already inherited them from list, so we need to
        check if the attr is explicitly defined in ProtectedList, and if it's not then we request the attribute
        from self._data_ (Why do we inherit from list? So glad you asked. Because we need isinstance(ProtectedList(), list) 
        to return True)"""
        if attr in ProtectedList.__dict__ or attr == '_data_':
            return object.__getattribute__(self, attr)
        else:
            return self._data_.__getattribute__(attr)
        
    
    
    def __getitem__(self, ind):
        val = self._data_.__getitem__(ind)
        return protect(val)
    
    def __getslice__(self, *args):
        return ProtectedList(self._data_.__getslice__(*args))
    
    def __iter__(self):
        for i in self._data_:
            yield protect(i)
            
    @staticmethod
    def makeProxyMethod(methodName):
        return lambda self, *args: getattr(self._data_, methodName)
    

    def error(self, *args, **kargs):
        raise Exception("Can not modify read-only list.")
            
    __setitem__ = error
    __setslice__ = error
    __delitem__ = error
    __delslice__ = error
    remove = error
    append = error
    extend = error
    pop = error
    insert = error
    reverse = error
    sort = error
    
    def poop(self):
        raise Exception("This is a list. It does not poop.")

    def copy(self):
        raise Exception("It is not safe to copy protected lists! (instead try deepcopy, but be careful.)")
    
    def deepcopy(self):
        return copy.deepcopy(self._data_)
    
    def __deepcopy__(self, memo):
        return copy.deepcopy(self._data_, memo)
    
    #### Unpacking doesn't work yet either
    
    #### The following methods use the same template
    def __repr__(self):
        return self._data_.__repr__()
    
    def __len__(self):
        return len(self._data_)
    
    def __contains__(self, arg):
        return self._data_.__contains__(arg)
    
    def __eq__(self, arg):
        return self._data_.__eq__(arg)
    
#for methodName in ['__len__']:
    ##locals()[methodName] = makeProxyMethod(methodName)
    #setattr(ProtectedList, methodName, ProtectedList.makeProxyMethod(methodName))
    
def protect(obj):
    if isinstance(obj, dict):
        return ProtectedDict(obj)
    elif isinstance(obj, list) or isinstance(obj, tuple):
        return ProtectedList(obj)
    else:
        return obj
    
    
if __name__ == '__main__':
    d1 = {'x': 1, 'y': [1,2], 'z': ({'a': 2, 'b': [3,4], 'c': (5,6)}, 1, 2)}
    d1p = protect(d1)
    
    l = [1,2,3,4,5]
    lp = protect(l)