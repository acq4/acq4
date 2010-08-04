# -*- coding: utf-8 -*-
"""
debug.py - Functions to aid in debugging 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

import sys, traceback, time, gc, re, types, weakref
import ptime
from numpy import ndarray
#from PyQt4 import QtCore, QtGui

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
        

    
def findRefPath(startObj, endObj, maxLen=8, restart=True, seen={}, path=None):
    """Determine all paths of object references from startObj to endObj"""
    refs = []
    if path is None:
        path = [endObj]
    prefix = " "*(8-maxLen)
    #print prefix + str(map(type, path))
    prefix += " "
    if restart:
        #gc.collect()
        seen.clear()
    gc.collect()
    newRefs = gc.get_referrers(endObj)
    for r in newRefs:
        #print prefix+"->"+str(type(r))
        if type(r).__name__ in ['frame', 'function', 'listiterator']:
            #print prefix+"  FRAME"
            continue
        try:
            if any([r is x for x in  path]):
                #print prefix+"  LOOP", objChainString([r]+path)
                continue
        except:
            print r
            print path
            raise
        if r is startObj:
            refs.append([r])
            print refPathString([startObj]+path)
            continue
        if maxLen == 0:
            #print prefix+"  END:", objChainString([r]+path)
            continue
        
        ## See if we have already searched this node.
        ## If not, recurse.
        tree = None
        try:
            cache = seen[id(r)]
            if cache[0] >= maxLen:
                tree = cache[1]
                for p in tree:
                    print refPathString(p+path)
        except KeyError:
            pass
        if tree is None:
            tree = findRefPath(startObj, r, maxLen-1, restart=False, path=[r]+path)
            seen[id(r)] = [maxLen, tree]
            
        ## integrate any returned results
        if len(tree) == 0:
            #print prefix+"  EMPTY TREE"
            continue
        else:
            for p in tree:
                refs.append(p+[r])
        #seen[id(r)] = [maxLen, refs]
    return refs

def objString(obj):
    """Return a short but descriptive string for any object"""
    try:
        if isinstance(obj, dict):
            if len(obj) > 5:
                return "<dict {%s,...}>" % (",".join(obj.keys()[:5]))
            else:
                return "<dict {%s}>" % (",".join(obj.keys()))
        elif isinstance(obj, basestring):
            return '"%s"' % obj[:50]
        elif isinstance(obj, ndarray):
            return "<ndarray %s %s>" % (str(obj.dtype), str(obj.shape))
        elif hasattr(obj, '__len__'):
            if len(obj) > 5:
                return "<%s [%s,...]>" % (type(obj).__name__, ",".join([type(o).__name__ for o in obj[:5]]))
            else:
                return "<%s [%s]>" % (type(obj).__name__, ",".join([type(o).__name__ for o in obj]))
        else:
            return "<%s %s>" % (type(obj).__name__, obj.__class__.__name__)
    except:
        return str(type(obj))

def refPathString(chain):
    """Given a list of adjacent objects in a reference path, print the 'natural' path
    names (ie, attribute names, keys, and indexes) that follow from one object to the next ."""
    s = objString(chain[0])
    i = 0
    while i < len(chain)-1:
        #print " -> ", i
        i += 1
        o1 = chain[i-1]
        o2 = chain[i]
        cont = False
        if isinstance(o1, list) or isinstance(o1, tuple):
            if o2 in o1:
                s += "[%d]" % o1.index(o2)
                continue
        #print "  not list"
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
        #print "  not __dict__"
        if isinstance(o1, dict):
            try:
                if o2 in o1:
                    s += "[key:%s]" % objString(o2)
                    continue
            except TypeError:
                pass
            for k in o1:
                if o1[k] is o2:
                    s += "[%s]" % objString(k)
                    cont = True
                    continue
        #print "  not dict"
        for k in dir(o1):
            if getattr(o1, k) is o2:
                s += ".%s" % k
                cont = True
                continue
        #print "  not attr"
        if cont:
            continue
        s += " ? "
        sys.stdout.flush()
    return s

    
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
        #elif isinstance(obj, QtCore.QObject):
            #try:
                #childs = obj.children()
                #if verbose:
                    #print indent+"Qt children:"
                #for ch in childs:
                    #s = objectSize(obj, ignore=ignore, verbose=verbose, depth=depth+1)
                    #size += s
                    #if verbose:
                        #print indent + '  +', ch.objectName(), s
                    
            #except:
                #pass
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
def _getr(slist, olist, first=True):
    #global ALL_OBJS_CACHE
    i = 0 
    for e in slist:
        
        oid = id(e)
        typ = type(e)
        if oid in olist or typ is int or typ is long:    ## or e in olist:     ## since we're excluding all ints, there is no longer a need to check for olist keys
            continue
        #seen[oid] = None
        #olist.append(e)
        olist[oid] = e
        if first and (i%100) == 0:
            gc.collect()
        tl = gc.get_referents(e)
        if tl:
            _getr(tl, olist, first=False)
        i += 1
# The public function.
#ALL_OBJS_CACHE = {}
def get_all_objects():
    """Return a list of all live Python objects (excluding int and long), not including the list itself."""
    #global ALL_OBJS_CACHE
    #if useCache and len(ALL_OBJS_CACHE) > 0:
        #return ALL_OBJS_CACHE
    gc.collect()
    gcl = gc.get_objects()
    olist = {}
    #seen = {}
    # Just in case:
    #seen[id(gcl)] = None
    #seen[id(olist)] = None
    #seen[id(seen)] = None
    # _getr does the real work.
    _getr(gcl, olist)
    
    del olist[id(olist)]
    del olist[id(gcl)]
    #del olist[id(ALL_OBJS_CACHE)]
    #ALL_OBJS_CACHE = olist
    return olist
    #d = {}
    #for o in olist:
        #d[id(o)] = o
    #return d    
        
def lookup(oid, objects=None):
    """Return an object given its ID, if it exists."""
    if objects is None:
        objects = get_all_objects()
    return objects[oid]
        
        
#class ObjRef:
    #"""Attempts to be a weak reference even for objects which can't be weakref'd. 
    #Keeps track of all objects created within the instances so they can be ignored."""
    #allObjs = {}
    #allObjs[id(allObjs)] = None
    
    #def __init__(self, obj):
        #try:
            #self.ref = weakref.ref(obj) 
        #except:
            #self.ref = None
        #self.id = id(obj)
        ##self.type = type(obj)
        ##self.size = objectSize(obj)
        ##self.uid = "%d %s" % (self.id, str(self.type))
        ##self.objs = [self.__dict__, self.ref, self.id]
        ##self.objs.append(self.objs)
        #ObjRef.allObjs[id(self)] = None
        #for v in [self.__dict__, self.ref, self.id]:
            #ObjRef.allObjs[id(v)] = None
            
    #def __del__(self):
        #try:
            #del ObjRef.allObjs[id(self)]
        #except KeyError:
            #pass
        #for v in [self.__dict__, self.ref, self.id]:
            #try:
                #del ObjRef.allObjs[id(v)]
            #except KeyError:
                #pass
            
    #@classmethod
    #def isObjVar(cls, o):
        #return type(o) is cls or id(o) in cls.allObjs
    
    #def refIsAlive(self):
        #if self.ref is None:
            #return True
        #else:
            #return self.ref() is not None
        
    #def __call__(self, allObjs=None):
        #if self.ref is not None:
            #return self.ref()
        #else:
            #if allObjs is None:
                #objs = get_all_objects()
            #else:
                #objs = allObjs
            #obj = objs.get(self.id, None)
            #if type(obj) is self.type:
                #return obj
            #return None
                    
        
class ObjTracker:
    allObjs = {} ## keep track of all objects created and stored within class instances
    allObjs[id(allObjs)] = None
    
    def __init__(self):
        self.startRefs = {}
        self.startCount = {}
        self.newRefs = {}
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
            
        ObjTracker.allObjs[id(self)] = None
        self.objs = [self.__dict__, self.startRefs, self.startCount, self.newRefs]
        self.objs.append(self.objs)
        for v in self.objs:
            ObjTracker.allObjs[id(v)] = None
            
        self.start()
            
    def __del__(self):
        self.startRefs.clear()
        self.startCount.clear()
        self.newRefs.clear()
        del ObjTracker.allObjs[id(self)]
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
        print "Collecting list of all objects..."
        gc.collect()
        objs = get_all_objects()
        ignoreTypes = [int, long]
        refs = {}
        count = {}
        for k in objs:
            o = objs[k]
            typ = type(o)
            oid = id(o)
            if ObjTracker.isObjVar(o) or typ in ignoreTypes:
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
            
            try:
                ref = weakref.ref(obj)
            except:
                ref = None
            refs[oid] = ref
            typ = type(o)
            count[typ] = count.get(typ, 0) + 1
            
        print "All objects: %d   Tracked objects: %d" % (len(objs), len(refs))
        #for o in [ids, ignore, count, self.objs, self.newObjs, self.persistObjs, self.ignore]:
            #ignore[self.objId(o)] = None
        #self.ignore = ignore
        return refs, count, objs
    
    def start(self):
        """Remember the current set of objects as the comparison for all future calls to diff()"""
        refs, count, objs = self.collect()
        for r in self.startRefs:
            self.forgetRef(self.startRefs[r])
        self.startRefs.clear()
        self.startRefs.update(refs)
        for r in refs:
            self.rememberRef(r)
        self.startCount = count
        #self.newRefs.clear()
        #self.newRefs.update(refs)
    
    def forgetRef(self, ref):
        if ref is not None:
            del ObjTracker.allObjs[id(ref)]
        
    def rememberRef(self, ref):
        """Record the address of the weakref object so it is not included in future object counts."""
        if ref is not None:
            ObjTracker.allObjs[id(ref)] = None
            
    def diff(self):
        """Compute all differences between the current object set and the reference set."""
        refs, count, objs = self.collect()
        #objs, allIds, onlyIds = self.collect()
        #print "got %d refs" % (len(refs))
        ## Which refs have disappeared since call to start()  (these are only displayed once, then forgotten.)
        delRefs = {}
        for i in self.startRefs.keys():
            if i not in refs:
                delRefs[i] = self.startRefs[i]
                del self.startRefs[i]
                self.forgetRef(delRefs[i])
        for i in self.newRefs.keys():
            if i not in refs:
                delRefs[i] = self.newRefs[i]
                del self.newRefs[i]
                self.forgetRef(delRefs[i])
        #print "deleted:", len(delRefs)
                
        ## Also check for expired weakrefs (?)
        #for k in self.startRefs:
            #if not self.startRefs[k].refIsAlive():
                #delRefs[k] = self.startRefs[k]
                #del self.startRefs[k]
        
        ## Which refs have appeared since call to start() or diff()
        newRefs = {}
        createRefs = {}
        for o in refs:
            if o not in self.startRefs:
                if o not in self.newRefs:
                    createRefs[o] = refs[o]
                else:
                    newRefs[o] = refs[o]
        #print "new:", len(newRefs)
                
        ## newRefs holds the entire set of objects created since start()
        for r in self.newRefs:
            self.forgetRef(self.newRefs[r])
        self.newRefs.clear()
        self.newRefs.update(newRefs)
        self.newRefs.update(createRefs)
        for r in self.newRefs:
            self.rememberRef(self.newRefs[r])
        #print "created:", len(createRefs)
        
        ## See if any of the newly created refs collide with previous ones
        #collidedRefs = {}
        #ids = {}
        #for k in self.startRefs:
            #ids[self.startRefs[k].id] = k
        #for k in createRefs:
            #if createRefs[k].id in ids:  ## two objects with same ID but different UID
                #k2 = ids[k]
                #delRefs[k2] = self.startRefs[k2]
                #collidedRefs[k2] = self.startRefs[k2]
                #del self.startRefs[k2]
        #print "collided:", len(collidedRefs)
                
                
        #self.objs = objs
        print "----------- Count changes since start: ----------"
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
            
        print "-----------  %d Deleted since last diff: ------------" % len(delRefs)
        self.report(delRefs, objs)
        print "-----------  %d Created since last diff: ------------" % len(createRefs)
        self.report(createRefs, objs)
        print "-----------  %d Created since start (persistent): ------------" % len(newRefs)
        self.report(newRefs, objs)
        
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
        
    #def lookup(self, oid):
        #if oid in self.objs:
            #ref = self.objs[oid][2]
            #if ref is None:
                #return None
            #else:
                #return ref()
        #else:
            #objs = gc.get_objects()
            #for o in objs:
                #if self.objId(o) == oid:
                    #return o
    def lookup(self, oid, ref, objs=None):
        if ref is None or ref() is None:
            try:
                obj = lookup(oid, objects=objs)
            except:
                obj = None
        else:
            obj = ref()
        return obj
                    
                    
    def report(self, refs, allobjs=None):
        if allobjs is None:
            allobjs = get_all_objects()
        
        #typs = d.values()
        #typSet = list(set(typs))
        #typSet.sort(lambda a,b: cmp(typs.count(a), typs.count(b)))
        #print len(refs)
        count = {}
        for oid in refs:
            obj = self.lookup(oid, refs[oid], allobjs)
            typ = type(obj)
            c = count.get(typ, [0,0])
            count[typ] =  [c[0]+1, c[1]+objectSize(obj)]
        typs = count.keys()
        typs.sort(lambda a,b: cmp(count[a][1], count[b][1]))
        
        for t in typs:
            print "  ", count[t][0], "\t", count[t][1], "\t", t
        
    def findTypes(self, refs, regex):
        allObjs = get_all_objects()
        ids = {}
        objs = []
        r = re.compile(regex)
        for k in refs:
            obj = self.lookup(k, refs[k], allObjs)
            if r.search(str(type(obj))):
                objs.append(obj)
        return objs
        
    def findNew(self, regex):
        return self.findTypes(self.newRefs, regex)
    
    
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

    
def searchRefs(obj, *args):
    for a in args:
        gc.collect()
        refs = gc.get_referrers(obj)
        if type(a) is int:
            obj = refs[a]
        elif a == 't':
            print map(type, refs)
        elif a == 'o':
            print obj
    
    
    