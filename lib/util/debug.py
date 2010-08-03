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

    
def findObjChains(startObj, endObj, maxLen=8, restart=True, seen={}, path=None):
    """Determine all paths of object references from startObj to endObj"""
    refs = []
    if path is None:
        path = [endObj]
    if restart:
        seen.clear()
    newRefs = gc.get_referrers(endObj)
    for r in newRefs:
        if r is startObj:
            refs.append([r])
            print "FOUND:", objChainString(path)
            continue
        if seen.get(id(r), 0) >= maxLen:   ## Skip this object if it has already been searched in greater-or-equal detail than we will
            #print "SKIP FRAME"
            #print "SKIP :", objChainString(path)
            continue
        elif maxLen == 0:
            print "END  :", objChainString(path)
            continue
        if type(r).__name__ == 'frame':
            continue
        seen[id(r)] = maxLen
        tree = findObjChains(startObj, r, maxLen-1, restart=False, path=[r]+path)
        if len(tree) == 0:
            continue
        else:
            for p in tree:
                refs.append([r] + p)
    return refs



def objChainString(chain):
    s = str(chain[0])
    if len(s) > 50:
        s = s[:50]+"(...)"
    i = 0
    while i < len(chain)-1:
        i += 1
        o1 = chain[i-1]
        o2 = chain[i]
        cont = False
        if isinstance(o2, dict) and hasattr(o1, '__dict__') and o2 == o1.__dict__:
            i += 1
            if i >= len(chain):
                s += ".__dict__"
                continue
            o3 = chain[i]
            for k in o2:
                if o2[k] is o3:
                    s += '.%s' % k
                    cont = True
                    continue
        if isinstance(o1, dict):
            try:
                if o2 in o1:
                    s += "[key:%s]" % str(o2)[:30]
                    continue
            except TypeError:
                pass
            for k in o1:
                if o1[k] is o2:
                    s += "[%s]" % str(k)[:30]
                    cont = True
                    continue
        if isinstance(o1, list) or isinstance(o1, tuple):
            if o2 in o1:
                s += "[%d]" % o1.index(o2)
                continue
        for k in dir(o1):
            if getattr(o1, k) is o2:
                s += ".%s" % k
                cont = True
                continue
        if cont:
            continue
        s += " ? "
    return s

findObjChains(a,c,4)

    
def objectSize(obj, ignore=None, verbose=False, depth=0, recursive=False):
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
    
    try:
        size = sys.getsizeof(obj)
    except TypeError:
        size = 0
        
    if isinstance(obj, ndarray):
        try:
            size += len(obj.data)
        except:
            pass
            
        
    if recursive:
        if type(obj) in [list, tuple]:
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
        
        
        
        
  
#### Code for listing (nearly) all objects in the known universe
#### http://utcc.utoronto.ca/~cks/space/blog/python/GetAllObjects
# Recursively expand slist's objects
# into olist, using seen to track
# already processed objects.
def _getr(slist, olist, seen):
    for e in slist:
        if id(e) in seen:
            continue
        seen[id(e)] = None
        olist.append(e)
        tl = gc.get_referents(e)
        if tl:
            _getr(tl, olist, seen)
# The public function.
def get_all_objects():
    """Return a list of all live Python  objects, not including the list itself."""
    gcl = gc.get_objects()
    olist = []
    seen = {}
    # Just in case:
    seen[id(gcl)] = None
    seen[id(olist)] = None
    seen[id(seen)] = None
    # _getr does the real work.
    _getr(gcl, olist, seen)
    d = {}
    for o in olist:
        d[id(o)] = o
    return d    
        
        
        
        
class ObjRef:
    """Attempts to be a weak reference even for objects which can't be weakref'd. 
    Keeps track of all objects created within the instances so they can be ignored."""
    allObjs = {}
    allObjs[id(allObjs)] = None
    
    def __init__(self, obj):
        try:
            self.ref = weakref.ref(obj) 
        except:
            self.ref = None
        self.id = id(obj)
        self.type = type(obj)
        #self.size = objectSize(obj)
        self.uid = "%d %s" % (self.id, str(self.type))
        self.objs = [self, self.__dict__, self.ref, self.id, self.type, self.uid]
        self.objs.append(self.objs)
        for v in self.objs:
            ObjRef.allObjs[id(v)] = None
            
    def __del__(self):
        for v in self.objs:
            del ObjRef.allObjs[id(v)]
        
    @classmethod
    def isObjVar(cls, o):
        return type(o) is cls or id(o) in cls.allObjs
    
    def refIsAlive(self):
        if self.ref is None:
            return True
        else:
            return self.ref() is not None
        
    def __call__(self, allObjs=None):
        if self.ref is not None:
            return self.ref()
        else:
            if allObjs is None:
                objs = get_all_objects()
            else:
                objs = allObjs
            obj = objs.get(self.id, None)
            if type(obj) is self.type:
                return obj
            return None
                    
        
class ObjTracker:
    allObjs = {} ## keep track of all objects created and stored within class instances
    allObjs[id(allObjs)] = None
    
    def __init__(self):
        self.startRefs = {}
        self.startCount = {}
        self.lastRefs = {}
        #self.objs = self.newObjs = self.persistObjs = None
        #self.typeCount = None
        #self.ignoreObjs = {}
        #self.ignore(self.ignoreObjs)
        #self.ignore(self.refs)
        #self.ignore(self.count)
        #self.ignore(self.__dict__)
        
        #self.objs, self.typeCount = self.collect()
        #ObjTracker.allObjs[id(self)] = None
        #ObjTracker.allObjs[id(self.__dict__)] = None
        #for v in self.__dict__.values():
            #ObjTracker.allObjs[id(v)] = None
            
        self.objs = [self, self.__dict__, self.startRefs, self.startCount, self.lastRefs]
        self.objs.append(self.objs)
        for v in self.objs:
            ObjRef.allObjs[id(v)] = None
            
        self.start()
            
    def __del__(self):
        for v in self.objs:
            del ObjTracker.allObjs[id(v)]
    #def objId(self, obj):
        #return (id(obj), str(type(obj)))
            
    @classmethod
    def isObjVar(cls, o):
        return type(o) is cls or id(o) in cls.allObjs
    
    #def ignore(self, obj):
        #"""Note: ignore keeps strong references to ignored objects; only for internal use."""
        #self.ignoreObjs[id(obj)] = obj
        
    #def unignore(self, obj):
        #if self.isIgnored(obj):
            #del self.ignoreObjs[id(obj)]
            
    #def isIgnored(self, obj):
        #return id(obj) in self.ignoreObjs and self.ignoreObjs[id(obj)] is obj
        
            
    def collect(self):
        #ids = {}
        #ignore = {}
        #count = {}
        #self.ignore[self.objId(ids)] = None
        #self.ignore[self.objId(count)] = None
        #self.ignore[self.objId(ignore)] = None
        gc.collect()
        objs = get_all_objects()
        print "got all objects"
        refs = {}
        count = {}
        for k in objs:
            o = objs[k]
            if ObjTracker.isObjVar(o) or ObjRef.isObjVar(o) or type(o) is int:
                continue
            #s = objectSize(o)
            #ref = None
            #try:
                #ref = weakref.ref(o)
                #ignore[self.objId(ref)] = None
            #except:
                #pass
            #desc = (type(o), s, ref)
            #oid = self.objId(o)
            #ids[oid] = desc
            #ignore[self.objId(desc)] = None
            
            ref = ObjRef(o)
            refs[ref.uid] = ref
            count[ref.type] = count.get(ref.type, 0) + 1
            
        #for o in [ids, ignore, count, self.objs, self.newObjs, self.persistObjs, self.ignore]:
            #ignore[self.objId(o)] = None
        #self.ignore = ignore
        return refs, count, objs
            
    
    def start(self):
        """Remember the current set of objects as the comparison for all future calls to diff()"""
        refs, count, objs = self.collect()
        self.startRefs.clear()
        self.startRefs.update(refs)
        #self.lastRefs.clear()
        #self.lastRefs.update(refs)
    
    def diff(self):
        """Compute all differences between the current object set and the reference set."""
        refs, count, allObjs = self.collect()
        #objs, allIds, onlyIds = self.collect()
        print "got %d refs from %d objs" % (len(refs), len(allObjs))
        ## Which refs have disappeared since call to start()  (these are only displayed once, then forgotten.)
        delRefs = {}
        for i in self.startRefs.keys():
            if i not in refs:
                delRefs[i] = self.startRefs[i]
                del self.startRefs[i]
        print "deleted:", len(delRefs)
                
        ## Also check for expired weakrefs (?)
        #for k in self.startRefs:
            #if not self.startRefs[k].refIsAlive():
                #delRefs[k] = self.startRefs[k]
                #del self.startRefs[k]
        
        ## Which refs have appeared since call to start()
        newRefs = {}
        for o in refs:
            if o not in self.startRefs:
                newRefs[o] = refs[o]
        print "new:", len(newRefs)
                
        ## Which of the new refs have appeared since the last call to diff()
        createRefs = {}  
        for o in newRefs.keys():
            if o not in self.lastRefs:
                createRefs[o] = newRefs[o]
                del newRefs[o]
        self.lastRefs.clear()
        self.lastRefs.update(newRefs)
        self.lastRefs.update(createRefs)
        print "created:", len(createRefs)
        
        ## See if any of the newly created refs collide with previous ones
        collidedRefs = {}
        ids = {}
        for k in self.startRefs:
            ids[self.startRefs[k].id] = k
        for k in createRefs:
            if createRefs[k].id in ids:  ## two objects with same ID but different UID
                k2 = ids[k]
                delRefs[k2] = self.startRefs[k2]
                collidedRefs[k2] = self.startRefs[k2]
                del self.startRefs[k2]
        print "collided:", len(collidedRefs)
                
                
        #self.objs = objs
        print "----------- Count Changes: ----------"
        c1 = count.copy()
        for k in self.startCount:
            c1[k] = c1.get(k, 0) - self.startCount[k]
        typs = c1.keys()
        typs.sort(lambda a,b: cmp(c1[a], c1[b]))
        for t in typs:
            if c1[t] == 0:
                continue
            num = "%d" % c1[t]
            print "  " + num + " "*(10-len(num)) + str(t)
            
        print "-----------  Deleted since start: ------------"
        self.report(delRefs, allObjs)
        print "-----------  Created since last diff: ------------"
        self.report(createRefs, allObjs)
        print "-----------  Created since start (persistent): ------------"
        self.report(newRefs, allObjs)
        
        #if self.newObjs is not None:
            #perObjs = {}
            #for o in self.newObjs:  ## if any objects are left from the last round of new objects, then they have persisted
                #if o in self.objs:
                    #perObjs[o] = self.objs[o]
            #print "----------- Persisted: -----------"
            #self.report(perObjs)  
            #self.persistObjs = perObjs
        #self.newObjs = newObjs
        
        
        #self.startCount.clear()
        #self.count.update(count)
        
    def lookup(self, oid):
        if oid in self.objs:
            ref = self.objs[oid][2]
            if ref is None:
                return None
            else:
                return ref()
        else:
            objs = gc.get_objects()
            for o in objs:
                if self.objId(o) == oid:
                    return o
        
    def report(self, refs, allobjs=None):
        if allobjs is None:
            allobjs = get_all_objects()
        #typs = d.values()
        #typSet = list(set(typs))
        #typSet.sort(lambda a,b: cmp(typs.count(a), typs.count(b)))
        print len(refs)
        count = {}
        for uid in refs:
            ref = refs[uid]
            c = count.get(ref.type, [0,0])
            count[ref.type] =  [c[0]+1, c[1]+objectSize(ref(allobjs))]
                
        typs = count.keys()
        typs.sort(lambda a,b: cmp(count[a][1], count[b][1]))
        
        for t in typs:
            print "  ", count[t][0], "\t", count[t][1], "\t", t
        
    def findTypes(self, refs, regex):
        #allObjs = gc.get_objects()
        ids = {}
        objs = []
        r = re.compile(regex)
        for k in refs:
            if r.search(str(refs[k].type)):
                objs.append(refs[k]())
        return objs
        
    def findNew(self, regex):
        return self.findTypes(self.lastRefs, regex)
    
    
