
import inspect, os, sys, __builtin__, gc, traceback

def reloadAll(prefix=None, debug=False):
    """
    Automatically reload everything whose __file__ begins with prefix.
    Skips reload if the file has not been updated
    """
    
    for mod in sys.modules.itervalues():
        if not inspect.ismodule(mod):
            continue
        
        ## Ignore if the file name does not start with prefix
        if not hasattr(mod, '__file__') or os.path.splitext(mod.__file__)[1] not in ['.py', '.pyc']:
            continue
        if prefix is not None and mod.__file__[:len(prefix)] != prefix:
            continue
        
        ## ignore if the .pyc is newer than the .py (or if there is no pyc or py)
        py = os.path.splitext(mod.__file__)[0] + '.py'
        pyc = py + 'c'
        if os.path.isfile(pyc) and os.path.isfile(py) and os.stat(pyc).st_mtime >= os.stat(py).st_mtime:
            #if debug:
                #print "Ignoring module %s; unchanged" % str(mod)
            continue
        
        try:
            reload(mod, debug=debug)
        except:
            print traceback.format_exc().strip()
            print "Error while reloading module %s, skipping\n" % mod


def reload(module, debug=False):
    """Replacement for the builtin reload function:
    - Reloads the module as usual
    - Updates all old functions and class methods to use the new code
    - Updates all instances of each modified class to use the new class

    - Requires that class and function names have not changed
    """
    if debug:
        print "Reloading module", module
        
    ## make a copy of the old module dictionary, reload, then grab the new module dictionary for comparison
    oldDict = module.__dict__.copy()
    __builtin__.reload(module)
    newDict = module.__dict__
    
    for k in oldDict:
        old = oldDict[k]
        new = newDict.get(k, None)
        if old is new or new is None:
            continue
        
        if inspect.isclass(old):
            if debug:
                print "  Updating class %s.%s (0x%x -> 0x%x)" % (module.__name__, k, id(old), id(new))
            updateClass(old, new, debug)
            #new.__previous_reload_version__ = old
                    
        elif inspect.isfunction(old):
            if debug:
                print "  Updating function %s.%s" % (module.__name__, k)
            updateFunction(old, new, debug)
            #new.__previous_reload_version__ = old



## For functions:
##  1) update the code and defaults to new versions.
##  2) keep a reference to the previous version so ALL versions get updated for every reload
def updateFunction(old, new, debug, depth=0):
    if debug and depth > 0:
        print "    -> also updating previous version", old, " -> ", new
    old.__code__ = new.__code__
    #old.__dict__ = new.__dict__  ## is this necessary?
    old.__defaults__ = new.__defaults__
    
    ## finally, update any previous versions still hanging around..
    if hasattr(old, '__previous_reload_version__'):
        updateFunction(old.__previous_reload_version__, new, debug, depth=depth+1)
    #elif debug: 
        #print "    old function", old, "has no previous version."
        
    ## We need to keep a pointer to the previous version so we remember to update BOTH
    ## when the next reload comes around.
    if depth == 0:
        #if debug:
            #print "    Setting previous version link", new, " -> ", old
        new.__previous_reload_version__ = old
    
## For classes:
##  1) find all instances of the old class and set instance.__class__ to the new class
##  2) update all old class methods to use code from the new class methods
def updateClass(old, new, debug):
    ## Track town all instances of old and any subclasses of old
    refs = gc.get_referrers(old)
    #if debug:
        #print "\n    REFERRERS:"
        #for r in refs:
            #print '      ' + str(r)[:100]
    for ref in refs:
        try:
            if isinstance(ref, old) and ref.__class__ is old:
                ref.__class__ = new
                if debug:
                    print "    Changed class for", ref
            elif inspect.isclass(ref) and issubclass(ref, old) and old in ref.__bases__:
                ind = ref.__bases__.index(old)
                ref.__bases__ = ref.__bases__[:ind] + (new,) + ref.__bases__[ind+1:]
                if debug:
                    print "    Changed superclass for", ref
            else:
                if debug:
                    print "    Ignoring reference", type(ref)
        except:
            print "Error updating reference (%s) for class change (%s -> %s)" % (str(ref), str(old), str(new))
            raise
        
    ## update all class methods to use new code.
    ## Generally this is not needed since instances already know about the new class, 
    ## but it fixes a few specific cases (pyqt signals, for one)
    for attr in dir(old):
        oa = getattr(old, attr)
        if inspect.ismethod(oa):
            if debug:
                print "    Updating method", attr
            try:
                na = getattr(new, attr)
            except AttributeError:
                if debug:
                    print "    Skipping method update for %s; new class does not have this attribute" % attr
                
            if oa.im_func is not na.im_func:
                updateFunction(oa.im_func, na.im_func, debug)
            #oa.im_func.__code__ = na.im_func.__code__
            #oa.im_func.__dict__ = na.im_func.__dict__
            #oa.im_func.__defaults__ = na.im_func.__defaults__
            
    ## finally, update any previous versions still hanging around..
    if hasattr(old, '__previous_reload_version__'):
        updateClass(old.__previous_reload_version__, new, debug)






## Tests:
#  write modules to disk, import, then re-write and run again
if __name__ == '__main__':
    doQtTest = True
    try:
        from PySide import QtCore, QtGui
        app = QtGui.QApplication([])
        class Btn(QtCore.QObject):
            sig = QtCore.Signal()
            def emit(self):
                QtCore.QObject.emit(self, QtCore.SIGNAL('signal'))
        btn = Btn()
    except:
        doQtTest = False



    import os
    if not os.path.isdir('test1'):
        os.mkdir('test1')
    open('test1/__init__.py', 'w')
    modFile1 = "test1/test1.py"
    modCode1 = """
import sys
class A(object):
    def __init__(self, msg):
        object.__init__(self)
        self.msg = msg
    def fn(self, pfx = ""):
        print pfx+"A class:", self.__class__, id(self.__class__)
        print pfx+"  %%s: %d" %% self.msg

class B(A):
    def fn(self, pfx=""):
        print pfx+"B class:", self.__class__, id(self.__class__)
        print pfx+"  %%s: %d" %% self.msg
        print pfx+"  calling superclass.. (%%s)" %% id(A) 
        A.fn(self, "  ")
"""

    modFile2 = "test2.py"
    modCode2 = """
import test1.test1 as C
a1 = C.A("ax1")
b1 = C.B("bx1")

def fn():
  print "fn: %s"
""" 

    open(modFile1, 'w').write(modCode1%(1,1))
    open(modFile2, 'w').write(modCode2%"message 1")
    import test1.test1 as C
    import test2
    print "Test 1 originals:"
    A1 = C.A
    B1 = C.B
    a1 = C.A("a1")
    b1 = C.B("b1")
    a1.fn()
    b1.fn()
    #print "function IDs  a1 bound method: %d a1 func: %d  a1 class: %d  b1 func: %d  b1 class: %d" % (id(a1.fn), id(a1.fn.im_func), id(a1.fn.im_class), id(b1.fn.im_func), id(b1.fn.im_class))


    from test2 import fn
    
    if doQtTest:
        print "Button test before:"
        QtCore.QObject.connect(btn, QtCore.SIGNAL('signal'), fn)
        QtCore.QObject.connect(btn, QtCore.SIGNAL('signal'), a1.fn)
        btn.sig.connect(a1.fn)
        btn.emit()
        #btn.sig.emit()
    
    #print "a1.fn referrers:", sys.getrefcount(a1.fn.im_func), gc.get_referrers(a1.fn.im_func)
    
    
    print "Test2 before reload:"
    
    fn()
    oldfn = fn
    test2.a1.fn()
    test2.b1.fn()
    
    os.remove(modFile1+'c')
    os.remove(modFile2+'c')
    open(modFile1, 'w').write(modCode1%(2,2))
    open(modFile2, 'w').write(modCode2%"message 2")
    
    print "\n----RELOAD-----\n"
    reloadAll(os.path.abspath(__file__)[:10], debug=True)

    if doQtTest:
        print "Button test after:"
        btn.emit()
        #btn.sig.emit()

    #print "a1.fn referrers:", sys.getrefcount(a1.fn.im_func), gc.get_referrers(a1.fn.im_func)

    print "Test2 after reload:"
    fn()
    test2.a1.fn()
    test2.b1.fn()
    
    print "\n==> Test 1 Old instances:"
    a1.fn()
    b1.fn()
    #print "function IDs  a1 bound method: %d a1 func: %d  a1 class: %d  b1 func: %d  b1 class: %d" % (id(a1.fn), id(a1.fn.im_func), id(a1.fn.im_class), id(b1.fn.im_func), id(b1.fn.im_class))

    print "\n==> Test 1 New instances:"
    a2 = C.A("a2")
    b2 = C.B("b2")
    a2.fn()
    b2.fn()
    #print "function IDs  a1 bound method: %d a1 func: %d  a1 class: %d  b1 func: %d  b1 class: %d" % (id(a1.fn), id(a1.fn.im_func), id(a1.fn.im_class), id(b1.fn.im_func), id(b1.fn.im_class))




    os.remove(modFile1+'c')
    os.remove(modFile2+'c')
    open(modFile1, 'w').write(modCode1%(3,3))
    open(modFile2, 'w').write(modCode2%"message 3")
    
    print "\n----RELOAD-----\n"
    reloadAll(os.path.abspath(__file__)[:10], debug=True)

    if doQtTest:
        print "Button test after:"
        btn.emit()
        #btn.sig.emit()

    #print "a1.fn referrers:", sys.getrefcount(a1.fn.im_func), gc.get_referrers(a1.fn.im_func)

    print "Test2 after reload:"
    fn()
    test2.a1.fn()
    test2.b1.fn()
    
    print "\n==> Test 1 Old instances:"
    a1.fn()
    b1.fn()
    print "function IDs  a1 bound method: %d a1 func: %d  a1 class: %d  b1 func: %d  b1 class: %d" % (id(a1.fn), id(a1.fn.im_func), id(a1.fn.im_class), id(b1.fn.im_func), id(b1.fn.im_class))

    print "\n==> Test 1 New instances:"
    a2 = C.A("a2")
    b2 = C.B("b2")
    a2.fn()
    b2.fn()
    print "function IDs  a1 bound method: %d a1 func: %d  a1 class: %d  b1 func: %d  b1 class: %d" % (id(a1.fn), id(a1.fn.im_func), id(a1.fn.im_class), id(b1.fn.im_func), id(b1.fn.im_class))


    os.remove(modFile1)
    os.remove(modFile2)
    os.remove(modFile1+'c')
    os.remove(modFile2+'c')
    os.system('rm -r test1')








#
#        Failure graveyard ahead:
#


"""Reload Importer:
Hooks into import system to 
1) keep a record of module dependencies as they are imported
2) make sure modules are always reloaded in correct order
3) update old classes and functions to use reloaded code"""

#import imp, sys

## python's import hook mechanism doesn't work since we need to be 
## informed every time there is an import statement, not just for new imports
#class ReloadImporter:
    #def __init__(self):
        #self.depth = 0
        
    #def find_module(self, name, path):
        #print "  "*self.depth + "find: ", name, path
        ##if name == 'PyQt4' and path is None:
            ##print "PyQt4 -> PySide"
            ##self.modData = imp.find_module('PySide')
            ##return self
        ##return None ## return none to allow the import to proceed normally; return self to intercept with load_module
        #self.modData = imp.find_module(name, path)
        #self.depth += 1
        ##sys.path_importer_cache = {}
        #return self
        
    #def load_module(self, name):
        #mod =  imp.load_module(name, *self.modData)
        #self.depth -= 1
        #print "  "*self.depth + "load: ", name
        #return mod

#def pathHook(path):
    #print "path hook:", path
    #raise ImportError
#sys.path_hooks.append(pathHook)

#sys.meta_path.append(ReloadImporter())


### replace __import__ with a wrapper that tracks module dependencies
#modDeps = {}
#reloadModule = None
#origImport = __builtins__.__import__
#def _import(name, globals=None, locals=None, fromlist=None, level=-1, stack=[]):
    ### Note that stack behaves as a static variable.
    ##print "  "*len(importStack) + "import %s" % args[0]
    #stack.append(set())
    #mod = origImport(name, globals, locals, fromlist, level)
    #deps = stack.pop()
    #if len(stack) > 0:
        #stack[-1].add(mod)
    #elif reloadModule is not None:     ## If this is the top level import AND we're inside a module reload
        #modDeps[reloadModule].add(mod)
            
    #if mod in modDeps:
        #modDeps[mod] |= deps
    #else:
        #modDeps[mod] = deps
        
    
    #return mod
    
#__builtins__.__import__ = _import

### replace 
#origReload = __builtins__.reload
#def _reload(mod):
    #reloadModule = mod
    #ret = origReload(mod)
    #reloadModule = None
    #return ret
#__builtins__.reload = _reload


#def reload(mod, visited=None):
    #if visited is None:
        #visited = set()
    #if mod in visited:
        #return
    #visited.add(mod)
    #for dep in modDeps.get(mod, []):
        #reload(dep, visited)
    #__builtins__.reload(mod)
