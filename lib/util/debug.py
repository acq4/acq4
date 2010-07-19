# -*- coding: utf-8 -*-
"""
debug.py - Functions to aid in debugging 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

import sys, traceback, time, gc, re, types, weakref
import ptime
from numpy import ndarray
from PyQt4 import QtCore, QtGui

def ftrace(func):
    ## Use as decorator to mark beginning and end of functions
    def w(*args, **kargs):
        print func.__name__ + " start"
        rv = func(*args, **kargs)
        print func.__name__ + " done"
        return rv
    return w

def getExc(indent=4, prefix='|  '):
    tb = traceback.format_exc()
    lines = []
    for l in tb.split('\n'):        
        lines.append(" "*indent + prefix + l)
    return '\n'.join(lines)

def printExc(msg='', indent=4, prefix='|'):
    exc = getExc(indent, prefix + '  ')
    print "[%s]  %s\n" % (time.strftime("%H:%M:%S"), msg)
    print " "*indent + prefix + '='*30 + '>>'
    print exc
    print " "*indent + prefix + '='*30 + '<<'
    

def backtrace(skip=0):
    return ''.join(traceback.format_stack()[:-(skip+1)])    
    
    
def listObjs(regex='Q', typ=None):
    """List all objects managed by python with class name matching regex.
    Finds 'Q...' classes by default."""
    if typ is not None:
        return [x for x in gc.get_objects() if isinstance(x, typ)]
    else:
        return [x for x in gc.get_objects() if re.match(regex, type(x).__name__)]
        
def describeObj(__XX__Obj, depth=4, printResult=True, ignoreNames=None):
    """Return a string describing this object; attempt to find names that refer to it."""
    gc.collect()
    
    if ignoreNames is None:
        ignoreNames = []
    
    typName = str(type(__XX__Obj))
    if depth == 0:
        return [typName]
    
    refStrs = []
    
    
    __XX__Refs = gc.get_referrers(__XX__Obj)
    for __XX__Ref in __XX__Refs:
        if type(__XX__Ref).__name__ == 'frame':
            continue
        if hasattr(__XX__Ref, 'keys'):
            for k in __XX__Ref.keys():
                if isinstance(k, basestring) and k[:6] == '__XX__' or k in ignoreNames:
                    continue
                if __XX__Ref[k] is __XX__Obj:
                    rs = describeObj(__XX__Ref, depth=depth-1, printResult=False, ignoreNames=ignoreNames)
                    refStrs.extend(["%s ['%s']" % (s, k) for s in rs])
                    break
        elif isinstance(__XX__Ref, list) or isinstance(__XX__Ref, tuple):
            for k in range(len(__XX__Ref)):
                if __XX__Ref[k] is __XX__Obj:
                    rs = describeObj(__XX__Ref, depth=depth-1, printResult=False, ignoreNames=ignoreNames)
                    refStrs.extend(["%s [%d]" % (s, k) for s in rs])
                    break
        else:
            for k in dir(__XX__Ref):
                if k in ignoreNames:
                    continue
                if getattr(__XX__Ref, k) is __XX__Obj:
                    rs = describeObj(__XX__Ref, depth=depth-1, printResult=False, ignoreNames=ignoreNames)
                    refStrs.extend(["%s .%s" % (s, k) for s in rs])
                    break
    
    refStrs = set(refStrs)
    result = [s + ' ' + typName for s in refStrs]
    if printResult:
        for r in result:
            print r
    else:
        return result
                    

def objectSize(obj, ignore=None, verbose=False, depth=0):
    """Guess how much memory an object is using"""
    ignoreTypes = [types.MethodType, types.UnboundMethodType, types.BuiltinMethodType, types.FunctionType, types.BuiltinFunctionType]
    ignoreRegex = re.compile('(method-wrapper|Flag|ItemChange|Option|Mode)')
    
    
    if ignore is None:
        ignore = {}
        
    indent = '  '*depth
    
    try:
        hash(obj)
        hsh = obj
    except:
        hsh = "%s:%d" % (str(type(obj)), id(obj))
        
    if hsh in ignore:
        return 0
    ignore[hsh] = 1
    
    size = sys.getsizeof(obj)
    if isinstance(obj, ndarray):
        size += len(obj.data)
    elif type(obj) in [list, tuple]:
        if verbose:
            print indent+"list:"
        for o in obj:
            s = objectSize(o, ignore=ignore, verbose=verbose, depth=depth+1)
            if verbose:
                print indent+'  +', s
            size += s
    elif isinstance(obj, dict):
        if verbose:
            print indent+"list:"
        for k in obj:
            s = objectSize(obj[k], ignore=ignore, verbose=verbose, depth=depth+1)
            if verbose:
                print indent+'  +', k, s
            size += s
    elif isinstance(obj, QtCore.QObject):
        try:
            childs = obj.children()
            if verbose:
                print indent+"Qt children:"
            for ch in childs:
                s = objectSize(obj, ignore=ignore, verbose=verbose, depth=depth+1)
                size += s
                if verbose:
                    print indent + '  +', ch.objectName(), s
                
        except:
            pass
    #if isinstance(obj, types.InstanceType):
    gc.collect()
    if verbose:
        print indent+'attrs:'
    for k in dir(obj):
        if k in ['__dict__']:
            continue
        o = getattr(obj, k)
        if type(o) in ignoreTypes:
            continue
        strtyp = str(type(o))
        if ignoreRegex.search(strtyp):
            continue
        #if isinstance(o, types.ObjectType) and strtyp == "<type 'method-wrapper'>":
            #continue
        
        #if verbose:
            #print indent, k, '?'
        refs = [r for r in gc.get_referrers(o) if type(r) != types.FrameType]
        if len(refs) == 1:
            s = objectSize(o, ignore=ignore, verbose=verbose, depth=depth+1)
            size += s
            if verbose:
                print indent + "  +", k, s
        #else:
            #if verbose:
                #print indent + '  -', k, len(refs)
    return size

class GarbageWatcher:
    def __init__(self):
        self.objs = weakref.WeakValueDictionary()
        self.allNames = []
        
    def addObj(self, obj, name):
        self.objs[name] = obj
        self.allNames.append(name)
        
    def check(self):
        gc.collect()
        dead = self.allNames[:]
        alive = []
        for k in self.objs:
            dead.remove(k)
            alive.append(k)
        print "Deleted objects:", dead
        print "Live objects:", alive
        


    
class Profiler:
    depth = 0
    
    def __init__(self, msg="Profiler", disabled=False):
        self.depth = Profiler.depth 
        Profiler.depth += 1
        
        self.disabled = disabled
        if disabled: 
            return
        self.t0 = ptime.time()
        self.t1 = self.t0
        self.msg = "  "*self.depth + msg
        print self.msg, ">>> Started"
    
    def mark(self, msg=''):
        if self.disabled: 
            return
        t1 = ptime.time()
        print "  "+self.msg, msg, "%gms" % ((t1-self.t1)*1000)
        self.t1 = t1
        
    def finish(self):
        if self.disabled: 
            return
        t1 = ptime.time()
        print self.msg, '<<< Finished, total time:', "%gms" % ((t1-self.t0)*1000)
        
    def __del__(self):
        Profiler.depth -= 1
        