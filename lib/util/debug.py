# -*- coding: utf-8 -*-
"""
debug.py - Functions to aid in debugging 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

import sys, traceback, time, gc, re
import ptime

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
                if k[:6] == '__XX__' or k in ignoreNames:
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
                    
    
    
class Profiler:
    def __init__(self, msg="Profiler"):
        self.t0 = ptime.time()
        self.msg = msg
        self.mark("start")
    
    def mark(self, msg=''):
        t1 = ptime.time()
        print self.msg, msg, "%gms" % ((t1-self.t0)*1000)
        self.t0 = t1