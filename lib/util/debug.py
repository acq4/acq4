# -*- coding: utf-8 -*-
"""
debug.py - Functions to aid in debugging 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

import sys, traceback, time, gc, re


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
        
def describeObj(funnyNamedObj, depth=4, printResult=True, ignoreNames=None):
    """Return a string describing this object; attempt to find names that refer to it."""
    
    if ignoreNames is None:
        ignoreNames = []
    
    typName = str(type(funnyNamedObj))
    if depth == 0:
        return [typName]
    
    refStrs = []
    funnyNamedRefs = gc.get_referrers(funnyNamedObj)
    for funnyNamedRef in funnyNamedRefs:
        if hasattr(funnyNamedRef, 'keys'):
            for k in funnyNamedRef.keys():
                if k in ['funnyNamedObj', 'funnyNamedRef', 'funnyNamedRefs', '__dict__']:
                    continue
                if k in ignoreNames:
                    continue
                if funnyNamedRef[k] is funnyNamedObj:
                    rs = describeObj(funnyNamedRef, depth=depth-1, printResult=False, ignoreNames=ignoreNames)
                    refStrs.extend(["%s ['%s']" % (s, k) for s in rs])
                    break
        elif isinstance(funnyNamedRef, list) or isinstance(funnyNamedRef, tuple):
            for k in range(len(funnyNamedRef)):
                if funnyNamedRef[k] is funnyNamedObj:
                    rs = describeObj(funnyNamedRef, depth=depth-1, printResult=False, ignoreNames=ignoreNames)
                    refStrs.extend(["%s [%d]" % (s, k) for s in rs])
                    break
        else:
            for k in dir(funnyNamedRef):
                if k in ignoreNames:
                    continue
                if getattr(funnyNamedRef, k) is funnyNamedObj:
                    rs = describeObj(funnyNamedRef, depth=depth-1, printResult=False, ignoreNames=ignoreNames)
                    refStrs.extend(["%s .%s" % (s, k) for s in rs])
                    break
                    
    refStrs = set(refStrs)
    result = [s + ' ' + typName for s in refStrs]
    if printResult:
        for r in result:
            print r
    else:
        return result
                    
    
    
    
    
    