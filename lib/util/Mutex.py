# -*- coding: utf-8 -*-
"""
Mutex.py -  Stand-in extension of Qt's QMutex class
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

from PyQt4 import QtCore
import traceback

class Mutex(QtCore.QMutex):
    """Extends QMutex to provide warning messages when a mutex stays locked for a long time.
    Mostly just useful for debugging purposes. Should only be used with MutexLocker, not
    QMutexLocker.
    """
    
    def __init__(self, *args):
        QtCore.QMutex.__init__(self, *args)
        self.l = QtCore.QMutex()  ## for serializing access to self.tb
        self.tb = []
        self.debug = True ## True to enable debugging functions

    def tryLock(self, timeout=None, id=None):
        if timeout is None:
            l = QtCore.QMutex.tryLock(self)
        else:
            l = QtCore.QMutex.tryLock(self, timeout)

        if self.debug and l:
            self.l.lock()
            try:
                if id is None:
                    self.tb.append(''.join(traceback.format_stack()[:-1]))
                else:
                    self.tb.append("  " + str(id))
                #print 'trylock', self, len(self.tb)
            finally:
                self.l.unlock()
        return l
        
    def lock(self, id=None):
        c = 0
        waitTime = 5000  # in ms
        while True:
            if self.tryLock(waitTime, id):
                break
            c += 1
            self.l.lock()
            try:
                print "Waiting for mutex lock (%0.1f sec). Traceback follows:" % (c*waitTime/1000.)
                traceback.print_stack()
                if len(self.tb) > 0:
                    print "Mutex is currently locked from:\n", self.tb[-1]
                else:
                    print "Mutex is currently locked from [???]"
            finally:
                self.l.unlock()
        #print 'lock', self, len(self.tb)

    def unlock(self):
        QtCore.QMutex.unlock(self)
        if self.debug:
            self.l.lock()
            try:
                #print 'unlock', self, len(self.tb)
                if len(self.tb) > 0:
                    self.tb.pop()
                else:
                    raise Exception("Attempt to unlock mutex before it has been locked")
            finally:
                self.l.unlock()

    def depth(self):
        self.l.lock()
        n = len(self.tb)
        self.l.unlock()
        return n

    def traceback(self):
        self.l.lock()
        try:
            ret = self.tb[:]
        finally:
            self.l.unlock()
        return ret

    def __exit__(self, *args):
        self.unlock()

    def __enter__(self):
        self.lock()
        return self
        

class MutexLocker:
    def __init__(self, lock):
        #print self, "lock on init",lock, lock.depth()
        self.lock = lock
        self.lock.lock()
        self.unlockOnDel = True

    def unlock(self):
        #print self, "unlock by req",self.lock, self.lock.depth()
        self.lock.unlock()
        self.unlockOnDel = False


    def relock(self):
        #print self, "relock by req",self.lock, self.lock.depth()
        self.lock.lock()
        self.unlockOnDel = True

    def __del__(self):
        if self.unlockOnDel:
            #print self, "Unlock by delete:", self.lock, self.lock.depth()
            self.lock.unlock()
        #else:
            #print self, "Skip unlock by delete", self.lock, self.lock.depth()

    def __exit__(self, *args):
        if self.unlockOnDel:
            self.unlock()

    def __enter__(self):
        return self

    def mutex(self):
        return self.lock

import functools, weakref

class ThreadsafeObject:
    """Wrapper that makes access to any object thread-safe (within reasonable limits).
    - all method calls and attribute/item accesses are protected by mutex
    - optionally, attribute/item accesses may return protected objects
    - can be manually locked for extended operations
    """
    def __init__(self, obj, recursive=False, reentrant=True):
        """
        If recursive is True, then sub-objects accessed from obj are wrapped threadsafe as well.
        If reentrant is True, then the object can be locked multiple times from the same thread."""

        try:
            self.__TSOwrapped_object__ = weakref.ref(obj)
        except:
            self.__TSOwrapped_object__ = obj
            
        if reentrant:
            self.__TSOwrap_lock__ = Mutex(QtCore.QMutex.Recursive)
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


    def __getattr__(self, attr):
        #try:
            #return object.__getattribute__(self, attr)
        #except AttributeError:
        with self.__TSOwrap_lock__:
            val = getattr(self.__wrapped_object__(), attr)
            if callable(val):
                return self.__wrap_object__(val)
            if self.__TSOrecursive__:
                return self.__wrap_object__(val)
            return val

    def __setattr__(self, attr, val):
        if attr[:5] == '__TSO':
            #return object.__setattr__(self, attr, val)
            self.__dict__[attr] = val
            return
        with self.__TSOwrap_lock__:
            return setattr(self.__wrapped_object__(), attr, val)
            
    #def __getitem__(self, item):
        #with self.__TSOwrap_lock__:
            #val = self.__wrapped_object__()[item]
            #if self.__TSOrecursive__:
                #return self.__wrap_object__(val)
                ##return ThreadsafeObject(val, recursive=self.__TSOrecursive__, reentrant=self.__TSOreentrant__)
            #else:
                #return val

    #def __setitem__(self, item, val):
        #with self.__TSOwrap_lock__:
            #self.__wrapped_object__()[item] = val
            
    #def __call__(self, *args, **kargs):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__()(*args, **kargs)
            
    #def __repr__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().__repr__()

    #def __str__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().__str__()

    #def __eq__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().__eq__()

    #def __ne__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().__ne__()

    #def __lt__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __gt__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __le__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __ge__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __add__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __sub__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __mul__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __div__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __iadd__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __isub__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __imul__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __idiv__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __radd__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __rsub__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __rmul__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __rdiv__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __pow__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __ipow__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __rpow__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __len__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def __abs__(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()

    #def ____(self):
        #with self.__TSOwrap_lock__:
            #return self.__wrapped_object__().____()



    def __wrap_object__(self, obj):
        if obj.__class__ in [int, float, str, unicode, tuple]:
            return obj
        if id(obj) not in self.__TSOwrapped_objs__:
            self.__TSOwrapped_objs__[id(obj)] = ThreadsafeObject(obj, recursive=self.__TSOrecursive__, reentrant=self.__TSOreentrant__)
        return self.__TSOwrapped_objs__[id(obj)]
        
    def __wrapped_object__(self):
        if isinstance(self.__TSOwrapped_object__, weakref.ref):
            return self.__TSOwrapped_object__()
        else:
            return self.__TSOwrapped_object__



#class Mutex(QtCore
#class MutexLocker(QtCore.QMutexLocker):
    #pass


if __name__ == '__main__':
    d = {'x': 1, 'y': [1,2,3,4,5]}
    t = ThreadsafeObject(d, recursive=False, reentrant=False)