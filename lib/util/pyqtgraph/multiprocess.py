"""
Multiprocessing utility library
(parallelization done the way I like it)

Luke Campagnola
2012.06.10

This library provides:
  - simple mechanism for starting a new python interpreter process that can be controlled from the original process
  - proxy system that allows objects hosted in the remote process to be used as if they were local
  - Qt signal connection between processes

Example:
  
    ## start new process, start listening for events from remote
    proc = QtProcess('remote_plotter')
    proc.startEventTimer()

    ## import pyqtgraph on remote end, assign to local variable
    rpg = proc._import('pyqtgraph')
    
    ## use rpg exactly as if it were a local pyqtgraph module
    win = rpg.GraphicsWindow()
    plt1 = win.addPlot()
    p1 = plt.plot([1,5,2,4,3])
    p1.setPen('g')

    ## even connect signals from remote process to local functions
    def viewChanged(*args):
        print "Remote view changed:", args
    plt1.sigViewChanged.connect(viewChanged)

TODO:
    - don't rely on fixed port / authkey
    - deferred attribute lookup
    - custom pickler:
        - automatically decide which types to transfer by proxy or by value
            - selectable modes:
                proxy only mutable objects
                proxy only unpicklable objects
                proxy all
                custom list of classes
            - specific proxy objects may have default proxy mode, attributes inherit
                
        - allow LocalObjectProxy to be created without specifying event handler
        - allow LocalObjectProxy to be used multiple times
            (and be careful about reference counting!)
            Another approach: what if remote handler keeps track of the object IDs it still has references to?
            Then we don't need to worry about reuse of local proxies.. (actually, this might already be the case?)
    
    - attributes of proxy should inherit defaultReturnMode
    - additionally, proxies should inherit defaultReturnMode from the Process that generated them
        - and _import should obey defaultReturnMode ?
    - can we make process startup asynchronous since it takes so long?
        - Process can defer sending requests until remote process is ready
"""



import multiprocessing.connection
import subprocess
import os, __builtin__, time, sys, atexit, traceback, pickle, weakref
from pyqtgraph.Qt import QtCore, QtGui
import numpy

class ExitError(Exception):
    pass

class NoResultError(Exception):
    pass

    
class RemoteEventHandler(object):
    
    objProxies = {} ## id: object; cache of objects which are referenced by the remote process.
                    ## For each entry in this dict, there should exist an ObjectProxy on the remote
                    ## host which references the object. When the remote ObjectProxy is collected,
                    ## the reference in the dict will be removed, allowing the local object to
                    ## be collected as well.
                    ## We make this a class variable so the unpickler has an easier time tracking
                    ## down the objects.
                    
    handlers = {}   ## maps {process ID : handler}. This allows unpickler to determine which process
                    ## an object proxy belongs to
                         
    def __init__(self, connection, name, pid):
        self.conn = connection
        self.name = name
        self.results = {} ## reqId: (status, result); cache of request results received from the remote process
                          ## status is either 'result' or 'error'
                          ##   if 'error', then result will be (exception, formatted exceprion)
                          ##   where exception may be None if it could not be passed through the Connection.
        self.proxies = {} ## maps {weakref(proxy): objectId}; used to inform the remote process when a proxy has been deleted.                  
        self.nextRequestId = 0
        self.exited = False
        self.noProxyTypes = [ type(None), str, int, float, LocalObjectProxy, ObjectProxy ]
        
        RemoteEventHandler.handlers[pid] = self  ## register this handler as the one communicating with pid
    
    @classmethod
    def getHandler(cls, pid):
        return cls.handlers[pid]
    
    def processRequests(self):
        ## process all requests from the pipe. (non-blocking)
        if self.exited:
            raise ExitError()
        
        while self.conn.poll():
            try:
                self.handleRequest()
            except ExitError:
                self.exited = True
                raise
            except:
                print "Error in process %s" % self.name
                sys.excepthook(*sys.exc_info())
    
    def handleRequest(self):
        ## handle a single request from the pipe
        result = None
        try:
            cmd, reqId, optStr = self.conn.recv() ## args, kwds are double-pickled to ensure this recv() call never fails
        except EOFError:
            ## remote process has shut down; end event loop
            raise ExitError()
        except IOError:
            raise ExitError()
            
        
        #print "receive command:", cmd
        try:
            opts = pickle.loads(optStr)
            
            returnValue = opts.get('returnValue', 'auto')
            
            if cmd == 'result' or cmd == 'error':
                resultId = reqId
                reqId = None  ## prevents attempt to return information from this request
                              ## (this is already a return from a previous request)
                if cmd == 'result':
                    self.results[resultId] = ('result', opts['result'])
                else:
                    self.results[resultId] = ('error', (opts['exception'], opts['excString']))
            elif cmd == 'getObjAttr':
                result = getattr(opts['obj'], opts['attr'])
            elif cmd == 'callObj':
                obj = opts['obj']
                fnargs = opts['args']
                fnkwds = opts['kwds']
                if len(fnkwds) == 0:  ## need to do this because some functions do not allow keyword arguments.
                    #print obj, fnargs
                    result = obj(*fnargs)
                else:
                    result = obj(*fnargs, **fnkwds)
            elif cmd == 'getObjValue':
                result = opts['obj']  ## has already been unpickled into its local value
                returnValue = True
            elif cmd == 'transfer':
                result = opts['obj']
                returnValue = False
            elif cmd == 'import':
                name = opts['module']
                fromlist = opts.get('fromlist', [])
                mod = __builtin__.__import__(name, fromlist=fromlist)
                
                if len(fromlist) == 0:
                    parts = name.lstrip('.').split('.')
                    result = mod
                    for part in parts[1:]:
                        result = getattr(result, part)
                else:
                    result = map(mod.__getattr__, fromlist)
                
            elif cmd == 'del':
                del self.objProxies[opts['objId']]
                
            elif cmd == 'close':
                if reqId is not None:
                    result = True
                    returnValue = True
                    
            exc = None
        except:
            exc = sys.exc_info()

            
            
        if reqId is not None:
            if exc is None:
                #print "returnValue:", returnValue, result
                if returnValue == 'auto':
                    returnValue = False
                    for typ in self.noProxyTypes:
                        if isinstance(result, typ):
                            #print "return", result, "by value"
                            returnValue = True
                            break
                
                if returnValue is False:
                    proxy = LocalObjectProxy(result, self)
                    self.replyResult(reqId, proxy)
                else:
                    try:
                        self.replyResult(reqId, result)
                    except:
                        print "Error sending value for '%s':" % str(result)
                        sys.excepthook(*sys.exc_info())
                        self.replyError(reqId, *sys.exc_info())
            else:
                self.replyError(reqId, *exc)
                    
        elif exc is not None:
            sys.excepthook(*exc)
    
        if cmd == 'close':
            if opts.get('noCleanup', False) is True:
                os._exit(0)  ## exit immediately, do not pass GO, do not collect $200.
                             ## (more importantly, do not call any code that would
                             ## normally be invoked at exit)
            else:
                raise ExitError()
        
    
    
    def replyResult(self, reqId, result):
        self.send(request='result', reqId=reqId, returnMode='off', result=result)
    
    def replyError(self, reqId, *exc):
        excStr = traceback.format_exception(*exc)
        try:
            self.send(request='error', reqId=reqId, returnMode='off', exception=exc[1], excString=excStr)
        except:
            self.send(request='error', reqId=reqId, returnMode='off', exception=None, excString=excStr)
    
    def send(self, request, reqId=None, returnMode='sync', timeout=10, **opts):
        """Send a request or return packet to the remote process.
        Generally it is not necessary to call this method directly; it is for internal use.
        (The docstring has information that is nevertheless useful to the programmer
        as it describes the internal protocol used to communicate between processes)
        
        ==========  ====================================================================
        Arguments:  
        request     String describing the type of request being sent (see below)
        reqId       Integer uniquely linking a result back to the request that generated
                    it. (most requests leave this blank)
        returnMode  'sync':  return the actual result of the request
                    'async': return a Request object which can be uset to look up the 
                             result later
                    'off':   return no result
        timeout     Time in seconds to wait for a response when returnMode=='sync'
        **opts      Extra arguments sent to the remote process that determine the way
                    the request will be handled (see below)
        ==========  ====================================================================
        
        Description of request strings and options allowed for each:
        
        =============  =============  ========================================================
        request        option         description
        -------------  -------------  --------------------------------------------------------
        getObjAttr                    Request the remote process return (proxy to) an
                                      attribute of an object.
                       obj            reference to object whose attribute should be 
                                      returned
                       attr           string name of attribute to return
                       returnValue    bool or 'auto' indicating whether to return a proxy or
                                      the actual value. 
                       
        callObj                       Request the remote process call a function or 
                                      method. If a request ID is given, then the call's
                                      return value will be sent back (or information
                                      about the error that occurred while running the
                                      function)
                       obj            the (reference to) object to call
                       args           tuple of arguments to pass to callable
                       kwds           dict of keyword arguments to pass to callable
                       returnValue    bool or 'auto' indicating whether to return a proxy or
                                      the actual value. 
                       
        getObjValue                   Request the remote process return the value of
                                      a proxied object (must be picklable)
                       obj            reference to object whose value should be returned
                       
        transfer                      Copy an object to the remote process and request
                                      it return a proxy for the new object.
                       obj            The object to transfer.
                       
        import                        Request the remote process import new symbols
                                      and return proxy(ies) to the imported objects
                       module         the string name of the module to import
                       fromlist       optional list of string names to import from module
                       
        del                           Inform the remote process that a proxy has been 
                                      released (thus the remote process may be able to 
                                      release the original object)
                       objId          id of object which is no longer referenced by 
                                      remote host
                                      
        close                         Instruct the remote process to stop its event loop
                                      and exit. Optionally, this request may return a 
                                      confirmation.
            
        result                        Inform the remote process that its request has 
                                      been processed                        
                       result         return value of a request
                       
        error                         Inform the remote process that its request failed
                       exception      the Exception that was raised (or None if the 
                                      exception could not be pickled)
                       excString      string-formatted version of the exception and 
                                      traceback
        =============  =====================================================================
        """
        
        
        
        assert returnMode in ['off', 'sync', 'async'], 'returnMode must be one of "off", "sync", or "async"'
        if reqId is None:
            if returnMode != 'off': ## requested return value; use the next available request ID
                reqId = self.nextRequestId
                self.nextRequestId += 1
        else:
            ## If requestId is provided, this _must_ be a response to a previously received request.
            assert request in ['result', 'error']
        
        #if autoProxy:
            #for k, v in opts.iteritems():
                #proxy = True
                #for typ in self.noProxyTypes:
                    #if isinstance(v, typ):
                        #proxy = False
                        #break
                #if proxy:
                    #opts[k] = LocalObjectProxy(v, self)
        
        optStr = pickle.dumps(opts) ## double-pickle args to ensure that at least status and request ID get through
        request = (request, reqId, optStr)
        self.conn.send(request)  ## final request looks like (cmd, reqId, (args, kwds))
                                 ## where the format of (args, kwds) depends on the command value.
                                 ## for commands that invoke a remote method, the format is
                                 ##    (args, kwds) == ((method, call_args, call_kwds), {'returnProxy': bool})
        
        if returnMode == 'off':
            return
        
        req = Request(self, reqId, description=str(request))
        if returnMode == 'async':
            return req
            
        if returnMode == 'sync':
            try:
                return req.result(timeout=timeout)
            except NoResultError:
                return req
            
    
    def quitEventLoop(self, returnMode='off', **kwds):
        self.send(request='close', returnMode=returnMode, **kwds)
    
    def getResult(self, reqId):
        ## raises NoResultError if the result is not available yet
        if reqId not in self.results:
            #self.readPipe()
            try:
                self.processRequests()
            except ExitError:
                pass
        if reqId not in self.results:
            raise NoResultError()
        status, result = self.results.pop(reqId)
        if status == 'result': 
            return result
        elif status == 'error':
            #print ''.join(result)
            exc, excStr = result
            if exc is not None:
                print "===== Remote process raised exception on request: ====="
                print ''.join(excStr)
                print "===== Local Traceback to request follows: ====="
                raise exc
            else:
                print ''.join(excStr)
                raise Exception("Error getting result. See above for exception from remote process.")
                
        else:
            raise Exception("Internal error.")
    
    def _import(self, mod, **kwds):
        """
        Request the remote process import a module (or symbols from a module)
        and return the proxied results. Uses built-in __import__() function, but 
        adds a bit more processing:
        
            _import('module')  =>  returns module
            _import('module.submodule')  =>  returns submodule 
                                             (note this differs from behavior of __import__)
            _import('module', fromlist=[name1, name2, ...])  =>  returns [module.name1, module.name2, ...]
                                             (this also differs from behavior of __import__)
            
        """
        return self.send(request='import', returnMode='sync', module=mod, **kwds)
        
    def getObjAttr(self, obj, attr, **kwds):
        return self.send(request='getObjAttr', obj=obj, attr=attr, **kwds)
        
    def getObjValue(self, obj, **kwds):
        return self.send(request='getObjValue', obj=obj, **kwds)
        
    def callObj(self, obj, args, kwds, autoProxy=False, **opts):
        if autoProxy:
            args = tuple([self.autoProxy(v) for v in args])
            for k, v in kwds.iteritems():
                opts[k] = self.autoProxy(v)
        
        return self.send(request='callObj', obj=obj, args=args, kwds=kwds, **opts)

    def registerProxiedObject(self, obj):
        ## remember that this object has been sent by proxy to another process
        ## we keep a reference to the object until the remote tells us the proxy has been released.
        self.objProxies[id(obj)] = obj
            
    def registerProxy(self, proxy):
        ref = weakref.ref(proxy, self.deleteProxy)
        self.proxies[ref] = proxy._objectId
    
    def deleteProxy(self, ref):
        objId = self.proxies.pop(ref)
        try:
            self.send(request='del', objId=objId, returnMode='off')
        except IOError:  ## if remote process has closed down, there is no need to send delete requests anymore
            pass

    def transfer(self, obj, **kwds):
        """
        Transfer an object to the remote host (the object must be picklable) and return 
        a proxy for the new remote object.
        """
        return self.send(request='transfer', obj=obj, **kwds)
        
    def autoProxy(self, obj):
        ## Return object wrapped in LocalObjectProxy _unless_ its type is in self.noProxyTypes.
        for typ in self.noProxyTypes:
            if isinstance(obj, typ):
                return obj
        return LocalObjectProxy(obj, self)

class Process(RemoteEventHandler):
    def __init__(self, name=None, target=None):
        if target is None:
            target = startEventLoop
        if name is None:
            name = str(self)
            
        port = 50000
        authkey = 'a8hfu23p9rapm9fw'
        
        ## start remote process, instruct it to run target function
        self.proc = subprocess.Popen((sys.executable, __file__, 'remote'), stdin=subprocess.PIPE)
        pickle.dump((name+'_child', port, authkey, target), self.proc.stdin)
        self.proc.stdin.close()
        
        ## open connection to remote process
        conn = multiprocessing.connection.Client(('localhost', port), authkey=authkey)
        RemoteEventHandler.__init__(self, conn, name+'_parent', pid=self.proc.pid)
        
        atexit.register(self.join)
        
    def join(self, timeout=10):
        if self.proc.poll() is None:
            self.quitEventLoop()
            start = time.time()
            while self.proc.poll() is None:
                if timeout is not None and time.time() - start > timeout:
                    raise Exception('Timed out waiting for remote process to end.')
                time.sleep(0.05)
        
        
def startEventLoop(name, port, authkey):
    l = multiprocessing.connection.Listener(('localhost', int(port)), authkey=authkey)
    conn = l.accept()
    global HANDLER
    HANDLER = RemoteEventHandler(conn, name, os.getppid())
    while True:
        try:
            HANDLER.processRequests()  # exception raised when the loop should exit
            time.sleep(0.01)
        except ExitError:
            break


class ForkedProcess(RemoteEventHandler):
    """
    ForkedProcess is a substitute for Process that uses os.fork() to generate a new process.
    This is much faster than starting a completely new interpreter, but carries some caveats
    and limitations:
      - open file handles are shared with the parent process, which is potentially dangerous
      - it is not possible to have a QApplication in both parent and child process
        (unless both QApplications are created _after_ the call to fork())
      - generally not thread-safe.
      - forked processes are unceremoniously terminated when join() is called; they are not 
        given any opportunity to clean up. (This prevents them calling any cleanup code that
        was only intended to be used by the parent process)
    """
    
    def __init__(self, name=None, target=None):
        self.hasJoined = False
        if target is None:
            target = self.eventLoop
        if name is None:
            name = str(self)
        
        conn, remoteConn = multiprocessing.Pipe()
        
        pid = os.fork()
        if pid == 0:
            conn.close()
            sys.stdin.close()  ## otherwise we screw with interactive prompts.
            RemoteEventHandler.__init__(self, remoteConn, name+'_child', pid=os.getppid())
            target()
        else:
            self.childPid = pid
            remoteConn.close()
            RemoteEventHandler.objProxies = {}  ## don't want to inherit any of this from the parent.
            RemoteEventHandler.handlers = {}
            
            RemoteEventHandler.__init__(self, conn, name+'_parent', pid=pid)
            atexit.register(self.join)
        
        
    def eventLoop(self):
        while True:
            try:
                self.processRequests()  # exception raised when the loop should exit
                time.sleep(0.01)
            except ExitError:
                sys.exit(0)
        
    def join(self, timeout=10):
        if self.hasJoined:
            return
        #os.kill(pid, 9)  
        self.quitEventLoop(returnMode='sync', timeout=timeout, noCleanup=True)  ## ask the child process to exit and require that it return a confirmation.
        self.hasJoined = True


##Special set of subclasses that implement a Qt event loop instead.
        
class RemoteQtEventHandler(RemoteEventHandler):
    def __init__(self, *args, **kwds):
        RemoteEventHandler.__init__(self, *args, **kwds)
        self.timer = QtCore.QTimer()
        
    def startEventTimer(self):
        self.timer.timeout.connect(self.processRequests)
        self.timer.start(10)
    
    def processRequests(self):
        try:
            RemoteEventHandler.processRequests(self)
        except ExitError:
            QtGui.QApplication.instance().quit()
            self.timer.stop()
            #raise

class QtProcess(Process):
    def __init__(self, name=None):
        Process.__init__(self, name, target=startQtEventLoop)
        
        self.timer = QtCore.QTimer()
        self.startEventTimer()
        
    def startEventTimer(self):
        app = QtGui.QApplication.instance()
        if app is None:
            raise Exception("Must create QApplication before starting QtProcess")
        self.timer.timeout.connect(self.processRequests)
        self.timer.start(10)
        
    def processRequests(self):
        try:
            Process.processRequests(self)
        except ExitError:
            self.timer.stop()
    
def startQtEventLoop(name, port, authkey):
    l = multiprocessing.connection.Listener(('localhost', int(port)), authkey=authkey)
    conn = l.accept()
    from pyqtgraph.Qt import QtGui, QtCore
    #from PyQt4 import QtGui, QtCore
    app = QtGui.QApplication.instance()
    #print app
    if app is None:
        app = QtGui.QApplication([])
        app.setQuitOnLastWindowClosed(False)  ## generally we want the event loop to stay open 
                                              ## until it is explicitly closed by the parent process.
    
    global HANDLER
    HANDLER = RemoteQtEventHandler(conn, name, os.getppid())
    HANDLER.startEventTimer()
    app.exec_()


class Request:
    ## used internally for tracking asynchronous requests and returning results
    def __init__(self, process, reqId, description=None):
        self.proc = process
        self.description = description
        self.reqId = reqId
        self.gotResult = False
        self._result = None
        
    def result(self, block=True, timeout=10):
        """Return the result for this request. 
        If block is True, wait until the result has arrived or *timeout* seconds passes.
        If the timeout is reached, raise an exception. (use timeout=None to disable)
        If block is False, raises an exception if the result has not arrived yet."""
        if self.gotResult:
            return self._result
        
        if block:
            start = time.time()
            while not self.hasResult():
                time.sleep(0.005)
                if timeout is not None and time.time() - start > timeout:
                    print "Request timed out:", self.description
                    import traceback
                    traceback.print_stack()
                    raise NoResultError()
            return self._result
        else:
            self._result = self.proc.getResult(self.reqId)  ## raises NoResultError if result is not available yet
            self.gotResult = True
            return self._result
        
    def hasResult(self):
        """Returns True if the result for this request has arrived."""
        try:
            #print "check result", self.description
            self.result(block=False)
        except NoResultError:
            #print "  -> not yet"
            pass
        
        return self.gotResult

class LocalObjectProxy(object):
    """Used for wrapping local objects to ensure that they are send by proxy to a remote host.
    A LocalObjectProxy may only be used for a single RemoteEventHandler and may only be used once.
    """
    def __init__(self, obj, handler):
        self.processId = os.getpid()
        self.objectId = id(obj)
        self.typeStr = repr(obj)
        self.handler = handler
        self.obj = obj
        self.pickled = False
        
    def __reduce__(self):
        ## this proxy is being pickled; most likely it is being sent to another process.
        if self.pickled:
            raise Exception("It is not safe to re-use LocalObjectProxy")
        self.pickled = True
        self.handler.registerProxiedObject(self.obj)
        return (unpickleObjectProxy, (self.processId, self.objectId, self.typeStr))
        
## alias
proxy = LocalObjectProxy

def unpickleObjectProxy(processId, objectId, typeStr):
    if processId == os.getpid():
        return RemoteEventHandler.objProxies[objectId]
    else:
        return ObjectProxy(processId, objId=objectId, typeStr=typeStr)
    
class ObjectProxy(object):
    ## Represents an object stored by the remote process.
    ## when passed through the pipe, it is unpickled as the referenced object.
    def __init__(self, processId, objId, typeStr=''):
        object.__init__(self)
        self._processId = processId
        self._typeStr = typeStr
        self._objectId = objId
        self._defaultReturnMode = None
        self._defaultReturnValue = None
        self._handler = RemoteEventHandler.getHandler(processId)
        self._handler.registerProxy(self)  ## handler will watch proxy; inform remote process when the proxy is deleted.
    
    def _setReturnMode(self, mode):
        """See Process.callObj for list of accepted return modes"""
        self._defaultReturnMode = mode
    
    def __reduce__(self):
        return (unpickleObjectProxy, (self._processId, self._objectId, self._typeStr))
    
    def __repr__(self):
        #objRepr = self.__getattr__('__repr__')(returnMode='value')
        return "<ObjectProxy for process %d, object 0x%x: %s >" % (self._processId, self._objectId, self._typeStr)
        
        
    def __getattr__(self, attr):
        #if '_processId' not in self.__dict__:
            #raise Exception("ObjectProxy has no processId")
        #proc = Process._processes[self._processId]
        return self._handler.getObjAttr(self, attr)
        
    def __call__(self, *args, **kwds):
        """
        Attempts to call the proxied object from the remote process.
        Accepts extra keyword arguments:
        
            _returnMode    'off', 'sync', or 'async'
            _returnValue   bool or 'auto'
        
        """
        opts = {}
        returnMode = kwds.pop('_returnMode', self._defaultReturnMode)
        if returnMode is not None:
            opts['returnMode'] = returnMode
        returnValue = kwds.pop('_returnValue', self._defaultReturnValue)
        if returnValue is not None:
            opts['returnValue'] = returnValue
        return self._handler.callObj(obj=self, args=args, kwds=kwds, **opts)
    
    def __getitem__(self, *args):
        return self.__getattr__('__getitem__')(*args)
    
    def __setitem__(self, *args):
        return self.__getattr__('__setitem__')(*args)
        
    def __str__(self, *args):
        return self.__getattr__('__str__')(*args, _returnValue=True)
        
    def _getValue(self):
        #proc = Process._processes[self._processId]
        return self._handler.getObjValue(self)
        
    
    ## Explicitly proxy special methods. Is there a better way to do this??
    
    def __len__(self, *args):
        return self.__getattr__('__len__')(*args)
    
    def __add__(self, *args):
        return self.__getattr__('__add__')(*args)
    
    def __sub__(self, *args):
        return self.__getattr__('__sub__')(*args)
        
    def __div__(self, *args):
        return self.__getattr__('__div__')(*args)
        
    def __mul__(self, *args):
        return self.__getattr__('__mul__')(*args)
        
    def __pow__(self, *args):
        return self.__getattr__('__pow__')(*args)
        
    def __rshift__(self, *args):
        return self.__getattr__('__rshift__')(*args)
        
    def __lshift__(self, *args):
        return self.__getattr__('__lshift__')(*args)
        
    def __floordiv__(self, *args):
        return self.__getattr__('__pow__')(*args)
        
    def __eq__(self, *args):
        return self.__getattr__('__eq__')(*args)
    
    def __ne__(self, *args):
        return self.__getattr__('__ne__')(*args)
        
    def __lt__(self, *args):
        return self.__getattr__('__lt__')(*args)
    
    def __gt__(self, *args):
        return self.__getattr__('__gt__')(*args)
        
    def __le__(self, *args):
        return self.__getattr__('__le__')(*args)
    
    def __ge__(self, *args):
        return self.__getattr__('__ge__')(*args)
        
    def __and__(self, *args):
        return self.__getattr__('__and__')(*args)
        
    def __or__(self, *args):
        return self.__getattr__('__or__')(*args)
        
    def __xor__(self, *args):
        return self.__getattr__('__or__')(*args)
        
    def __mod__(self, *args):
        return self.__getattr__('__mod__')(*args)
        
    def __radd__(self, *args):
        return self.__getattr__('__radd__')(*args)
    
    def __rsub__(self, *args):
        return self.__getattr__('__rsub__')(*args)
        
    def __rdiv__(self, *args):
        return self.__getattr__('__rdiv__')(*args)
        
    def __rmul__(self, *args):
        return self.__getattr__('__rmul__')(*args)
        
    def __rpow__(self, *args):
        return self.__getattr__('__rpow__')(*args)
        
    def __rrshift__(self, *args):
        return self.__getattr__('__rrshift__')(*args)
        
    def __rlshift__(self, *args):
        return self.__getattr__('__rlshift__')(*args)
        
    def __rfloordiv__(self, *args):
        return self.__getattr__('__rpow__')(*args)
        
    def __rand__(self, *args):
        return self.__getattr__('__rand__')(*args)
        
    def __ror__(self, *args):
        return self.__getattr__('__ror__')(*args)
        
    def __rxor__(self, *args):
        return self.__getattr__('__ror__')(*args)
        
    def __rmod__(self, *args):
        return self.__getattr__('__rmod__')(*args)
        
        
        
    
if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'remote':  ## module has been invoked as script in new python interpreter.
        name, port, authkey, target = pickle.load(sys.stdin)
        #print "remote process %s starting.." % name
        target(name, port, authkey)
        #time.sleep(5)
        sys.exit(0)
        #import atexit
        #def done():
            #print "remote propcess done"
        #atexit.register(done)

        
    #else:
        ### testing code goes here
        
        #import pyqtgraph as pg
        #p2 = pg.plot([1,4,2,3])
        
        ##print "parent:", os.getpid()
        #from PyQt4 import QtGui, QtCore
        #proc = QtProcess('test')
        
        ##app = QtGui.QApplication([])
        
        #proc.startEventTimer()
        
        #rnp = proc._import('numpy')
        #arr = rnp.array([1,4,2,3,5])
        #arr2 = arr+arr
        
        #rpg = proc._import('pyqtgraph')
        #plt = rpg.plot()
        #p1 = plt.plot(arr2)
        #p1.setPen('g')
        
        #print plt.viewRect(returnValue=True)
        #req = plt.viewRect(returnMode='async')
        #while not req.hasResult():
            #time.sleep(0.01)
        #print req.result()._getValue()
        
        #b = rpg.QtGui.QPushButton("PRESS ME")
        #b.show()
        
        #def fn(b):
            #print "got remote click"
        #fnProx = LocalObjectProxy(fn, proc)
        #b.clicked.connect(fnProx)
        
        







