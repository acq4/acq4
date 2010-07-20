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
        
def describeObj(__XX__Obj, depth=4, printResult=True, returnResult=False, ignoreNames=None, ignorePaths=None, start=True):
    """Return a string describing this object; attempt to find names that refer to it."""
    gc.collect()
    
    if ignoreNames is None:
        ignoreNames = ['_']
    if ignorePaths is None:
        ignorePaths = {}
    
    #typName = str(type(__XX__Obj))
    if depth == 0:
        return []
        #if printResult:
            #print "  "*depth + str(type(__XX__Obj))
        #return [__XX__Obj]
    
    #refStrs = []
    refs = []
    
    
    __XX__Refs = gc.get_referrers(__XX__Obj)
    for __XX__Ref in __XX__Refs:
        #if startObj is not None and startObj is not __XX__Ref:
            #continue
            
        ## First determine how to get from this reference to the object (key, index, or attribure)
        path = ('?',)*3
        if type(__XX__Ref).__name__ == 'frame':
            continue
        if hasattr(__XX__Ref, 'keys'):
            for k in __XX__Ref.keys():
                if isinstance(k, basestring) and k[:6] == '__XX__' or k in ignoreNames:
                    continue
                if __XX__Ref[k] is __XX__Obj:
                    path = ('key', k, hash(k))
                    break
        elif isinstance(__XX__Ref, list) or isinstance(__XX__Ref, tuple):
            junk = False
            for v in __XX__Ref[:10]:  ## lists containing frames are ubiquitous and unhelpful.
                if type(v) is types.FrameType:
                    junk = True
                    break
            if junk:
                continue
            
            try:
                i = __XX__Ref.index(__XX__Obj)
                path = ('index', i, '%d'%i)
            except:
                pass
        else:
            for k in dir(__XX__Ref):
                if k in ignoreNames:
                    continue
                if getattr(__XX__Ref, k) is __XX__Obj:
                    path = ('attr', k, k)
                    break
                    
        ## Make sure we haven't already been here
        #pathKey = (id(__XX__Ref), path[0], path[2])
        #if pathKey in ignorePaths:
            #continue
        #ignorePaths[pathKey] = None
        
        
        nextRefs = describeObj(__XX__Ref, depth=depth-1, printResult=printResult, ignoreNames=ignoreNames, ignorePaths=ignorePaths, start=False)
        
        
        desc = ''
        if path[0] == 'key':
            strPath = "[%s]" % repr(path[1])
            desc = str([type(v).__name__ for v in __XX__Ref.values()])[:80]
        elif path[0] == 'index':
            strPath = "[%d]" % path[1]
            desc = str([type(v).__name__ for v in __XX__Ref])[:80]
        elif path[0] == 'attr':
            strPath = '.%s' % path[1]
        else:
            strPath = path[0]
        refs.append((__XX__Ref, path[:2]+(strPath,), nextRefs))
        
        if printResult:
                
            objStr = str(__XX__Ref)
            if len(objStr) > 50:
                objStr = str(type(__XX__Ref).__name__)
            print "    "*(depth-1) + objStr, strPath, desc
    
    #refStrs = set(refStrs)
    
    #result = [s + ' ' + typName for s in refStrs]
    if start and printResult:
        print "    "*(depth) + str(type(__XX__Obj))
        
        print "-------------------"
        
        def printPaths(paths, suffix=''):
            for p in paths:
                suf = p[1][2]+suffix
                if len(p[2]) == 0:
                    line = str(type(p[0]))+suf
                    line = re.sub(r"\.__dict__\['([^\]]+)'\]", r'.\1', line)
                    print line
                else:
                    printPaths(p[2], suf)
        
        printPaths(refs)
        
        
    if not start or returnResult:
        return refs

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
        
    def add(self, obj, name):
        self.objs[name] = obj
        self.allNames.append(name)
        
    def __setitem__(self, name, obj):
        self.add(obj, name)
        
    def check(self):
        gc.collect()
        dead = self.allNames[:]
        alive = []
        for k in self.objs:
            dead.remove(k)
            alive.append(k)
        print "Deleted objects:", dead
        print "Live objects:", alive
        
    def __getitem__(self, item):
        return self.objs[item]

    
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
        
        
class ObjectWatcher:
    def __init__(self):
        self.objs = weakref.WeakKeyDictionary()
        self.ids = {}
        self.collect(self.objs, self.ids)
        self.newObjs = None
        
    def collect(self, objs, ids):
        for o in gc.get_objects():
            try:
                ids[id(o)] = type(o)
                objs[o] = type(o)
            except:
                pass
            
    def diff(self):
        gc.collect()
        objs = weakref.WeakKeyDictionary()
        ids = {}
        self.collect(objs, ids)
        newObjs = weakref.WeakKeyDictionary()
        self.delIDs = {}
        for o in objs:
            try:
                if o not in self.objs:
                    newObjs[o] = objs[o]
            except:
                pass
        for i in self.ids:
            try:
                if i not in ids:
                    self.delIDs[i] = self.ids[i]
            except:
                pass
                
        
        self.objs = objs
        self.ids = ids
        print "-----------  Deleted: ------------"
        self.report(self.delIDs)
        print "-----------  Created: ------------"
        self.report(newObjs)
        if self.newObjs is not None:
            print "----------- Persisted: -----------"
            self.report(self.newObjs)  ## if any objects are left from the last round of new objects, then they have persisted
            self.persistObjs = self.newObjs
        
        self.newObjs = newObjs
        
    def report(self, d):
        typs = d.values()
        typSet = list(set(typs))
        typSet.sort(lambda a,b: cmp(typs.count(a), typs.count(b)))
        
        for t in typSet:
            print "  ", typs.count(t), "\t", t
        
    def findTypes(self, d, regex):
        objs = weakref.WeakKeyDictionary()
        r = re.compile(regex)
        for k in d:
            if r.search(str(d[k])):
                objs[k] = d[k]
        return objs
        
    def findNew(self, regex):
        return self.findTypes(self.newObjs, regex)
    
    def findPersist(self, regex):
        return self.findTypes(self.persistObjs, regex)
    
    
    
        