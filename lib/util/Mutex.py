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
        self.debug = False ## True to enable debugging functions

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




#class Mutex(QtCore
#class MutexLocker(QtCore.QMutexLocker):
    #pass
