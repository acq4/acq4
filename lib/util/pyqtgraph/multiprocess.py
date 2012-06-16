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
        
    - ForkedProcess using pipe for faster parallelization
"""



import multiprocessing.connection as connection
import subprocess
import os, __builtin__, time, sys, atexit, traceback, pickle, weakref
from pyqtgraph.Qt import QtCore, QtGui

class ExitError(Exception):
    pass

class NoResultError(Exception):
    pass

    
class RemoteEventHandler(object):
    ## reads commands from Connection, executes them and returns results.
    ## one RemoteEventHandler is set up at either end of a bidirectional pipe
    ## so that communication between two processes is (optionally) symmetrical.
    
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
        RemoteEventHandler.handlers[pid] = self  ## register this handler as the one communicating with pid
    
    @classmethod
    def getHandler(cls, pid):
        return cls.handlers[pid]
    
    def processRequests(self):
        ## process all requests from the pipe. (non-blocking)
        while self.conn.poll():
            try:
                self.handleRequest()
            except ExitError:
                raise
            except:
                print "Error in process %s" % self.name
                sys.excepthook(*sys.exc_info())
    
    def handleRequest(self):
        ## handle a single request from the pipe
        result = None
        returnProxy = True
        try:
            cmd, reqId, argStr = self.conn.recv() ## args, kargs are double-pickled to ensure this recv() call never fails
        except EOFError:
            ## remote process has shut down; end event loop
            raise ExitError()
        #print "receive command:", cmd
        try:
            args, kargs = pickle.loads(argStr)
            
            if cmd == 'getObjAttr':
                obj, attr = args
                result = getattr(obj, attr)
            elif cmd == 'callObj':
                obj, fnargs, fnkargs = args
                returnProxy = kargs.get('returnProxy', returnProxy)
                if len(fnkargs) == 0:  ## need to do this because some functions do not allow keyword arguments.
                    #print obj, fnargs
                    result = obj(*fnargs)
                else:
                    result = obj(*fnargs, **fnkargs)
            elif cmd == 'getObjValue':
                result = self.objProxies[args[0]]
                returnProxy = False
            #elif cmd == 'get':
                #try:
                    #result = ns[args[0]]
                #except KeyError as err:
                    #result = err
            elif cmd == 'import':
                name = args[0]
                fromlist = kargs.get('fromlist', [])
                mod = __builtin__.__import__(name, fromlist=fromlist)
                
                if len(fromlist) == 0:
                    parts = name.lstrip('.').split('.')
                    result = mod
                    for part in parts[1:]:
                        result = getattr(result, part)
                else:
                    result = map(mod.__getattr__, fromlist)
                
            elif cmd == 'del':
                del self.objProxies[args[0]]
            exc = None
        except:
            exc = sys.exc_info()

        if cmd == 'close':
            raise ExitError()
            
            
        if reqId is not None:
            if exc is None:
                if returnProxy:
                    #oid = id(result)
                    #self.objProxies[oid] = result
                    proxy = LocalObjectProxy(result, self)
                    self.sendReply("result", reqId, proxy)
                else:
                    try:
                        self.sendReply("result", reqId, result)
                    except:
                        print "Error sending value for '%s':" % str(result)
                        sys.excepthook(*sys.exc_info())
                        exc = traceback.format_exception(*sys.exc_info())
                        #print "Sending back error text instead:"
                        #print exc
                        #print "----"
                        self.sendReply('error', reqId, exc)
            else:
                #print "Error processing request:"
                #sys.excepthook(*exc)
                excStr = traceback.format_exception(*exc)
                try:
                    self.sendReply("error", reqId, (exc[1], excStr))
                except:
                    self.sendReply("error", reqId, (None, excStr))
                    
        elif exc is not None:
            sys.excepthook(*exc)
    
    
    #def __getattr__(self, attr):
        #return self.sendSync('get', attr)
    def sendReply(self, status, reqId, *args, **kargs):
        argStr = pickle.dumps((args, kargs)) ## double-pickle args to ensure that at least status and request ID get through
        self.conn.send((status, reqId, argStr))
    
    def sendNoReturn(self, cmd, *args, **kargs):
        argStr = pickle.dumps((args, kargs)) ## double-pickle args to ensure that at least status and request ID get through
        self.conn.send((cmd, None, argStr))
    
    def sendAsync(self, cmd, *args, **kargs):
        reqId = self.nextRequestId
        self.nextRequestId += 1
        argStr = pickle.dumps((args, kargs)) ## double-pickle args to ensure that at least status and request ID get through
        request = (cmd, reqId, argStr)
        self.conn.send(request)
        return Request(self, reqId, description=str(request))
        
    def sendSync(self, cmd, *args, **kargs):
        req = self.sendAsync(cmd, *args, **kargs)
        try:
            return req.result()
        except NoResultError:
            return req
    
    def quitEventLoop(self):
        self.sendNoReturn('close')
    
    def getResult(self, reqId):
        ## raises NoResultError if the result is not available yet
        if reqId not in self.results:
            self.readPipe()
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
    
    def readPipe(self):
        #print "read pipe"
        while self.conn.poll():
            status, reqId, argStr = self.conn.recv()
            args, kargs = pickle.loads(argStr)
            result = args[0]
            self.results[reqId] = (status, result)

    def _import(self, *args, **kargs):
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
        return self.sendSync('import', *args, **kargs)
        
    def getObjAttr(self, obj, attr):
        return self.sendSync('getObjAttr', obj, attr)
        
    def getObjValue(self, objId):
        return self.sendSync('getObjValue', objId)
        
    def callObj(self, obj, *args, **kargs):
        mode = kargs.pop('returnMode', 'sync')
        if mode == 'sync':
            return self.sendSync('callObj', obj, args, kargs)
        elif mode == 'async':
            return self.sendAsync('callObj', obj, args, kargs)
        elif mode == 'off' or mode is None:
            return self.sendNoReturn('callObj', obj, args, kargs)
        elif mode == 'value':
            return self.sendSync('callObj', obj, args, kargs, returnProxy=False)
        elif mode == 'async_value':
            return self.sendAsync('callObj', obj, args, kargs, returnProxy=False)

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
            self.sendNoReturn('del', objId)
        except IOError:  ## if remote process has closed down, there is no need to send delete requests anymore
            pass

    
#class Process(mp.Process, RemoteEventHandler):
    
    #processes = {}  ## child PID: Process; used when unpickling object proxies
                    ### to determine which Process the proxy belongs to.
    
    #def __init__(self, name, eventLoop=None):
        #conn, self._remote = mp.Pipe()
        #RemoteEventHandler.__init__(self, conn, name+'_parent')
        
        #if eventLoop is None:
            #eventLoop = startEventLoop
        #mp.Process.__init__(self, target=eventLoop, args=(self._remote, name+'_child'))
        #self.start()
        #while self.pid is None:
            #time.sleep(0.005)
        #Process.processes[self.pid] = self
        #atexit.register(self.join)

    #def join(self, timeout=None):
        #if self.is_alive():
            #self.quitEventLoop()
            #mp.Process.join(self, timeout)
        
        
class Process(RemoteEventHandler):
    def __init__(self, name=None, target=None):
        if target is None:
            target = startEventLoop
        if name is None:
            name = ''
            
        port = 50000
        authkey = 'a8hfu23p9rapm9fw'
        
        ## start remote process, instruct it to run target function
        self.proc = subprocess.Popen((sys.executable, __file__, 'remote'), stdin=subprocess.PIPE)
        pickle.dump((name+'_child', port, authkey, target), self.proc.stdin)
        self.proc.stdin.close()
        
        ## open connection to remote process
        conn = connection.Client(('localhost', port), authkey=authkey)
        RemoteEventHandler.__init__(self, conn, name+'_parent', pid=self.proc.pid)
        
        #self.start()
        #while self.pid is None:  need to set self.pid
            #time.sleep(0.005)
        #Process.processes[self.proc.pid] = self
        atexit.register(self.join)
        
        #print "parent received:", conn.recv()
        
    def join(self, timeout=10):
        if self.proc.poll() is None:
            self.quitEventLoop()
            start = time.time()
            while self.proc.poll() is None:
                if timeout is not None and time.time() - start > timeout:
                    raise Exception('Timed out waiting for remote process to end.')
                time.sleep(0.05)
        
        
def startEventLoop(name, port, authkey):
    l = connection.Listener(('localhost', int(port)), authkey=authkey)
    conn = l.accept()
    global HANDLER
    HANDLER = RemoteEventHandler(conn, name, os.getppid())
    while True:
        try:
            HANDLER.processRequests()  # exception raised when the loop should exit
            time.sleep(0.01)
        except ExitError:
            print "Event loop exited normally"
            break


##Special set of subclasses that implement a Qt event loop instead.
        
class RemoteQtEventHandler(RemoteEventHandler):
    def __init__(self, *args, **kargs):
        RemoteEventHandler.__init__(self, *args, **kargs)
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
    l = connection.Listener(('localhost', int(port)), authkey=authkey)
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
        self.typeStr = str(obj)
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
        
    def __call__(self, *args, **kargs):
        if 'returnMode' not in kargs and self._defaultReturnMode is not None:
            kargs['returnMode'] = self._defaultReturnMode
        #proc = Process._processes[self._processId]
        return self._handler.callObj(self, *args, **kargs)
    
    def __getitem__(self, *args):
        return self.__getattr__('__getitem__')(*args)
    
    def __setitem__(self, *args):
        return self.__getattr__('__setitem__')(*args)
        
    def __str__(self, *args):
        return self.__getattr__('__str__')(*args, returnMode='value')
        
    # handled by weakref instead
    #def __del__(self):
        #if Process is None:
            #return
        #self._handler.deleteProxy(self._objectId)
    
    def _getValue(self):
        #proc = Process._processes[self._processId]
        return self._handler.getObjValue(self._objectId)
        
    
    ## Explicitly proxy special methods. Is there a better way to do this??
    
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

        
    else:
        ## testing code goes here
        
        import pyqtgraph as pg
        p2 = pg.plot([1,4,2,3])
        
        #print "parent:", os.getpid()
        from PyQt4 import QtGui, QtCore
        proc = QtProcess('test')
        
        #app = QtGui.QApplication([])
        
        proc.startEventTimer()
        
        rnp = proc._import('numpy')
        arr = rnp.array([1,4,2,3,5])
        arr2 = arr+arr
        
        rpg = proc._import('pyqtgraph')
        plt = rpg.plot()
        p1 = plt.plot(arr2)
        p1.setPen('g')
        
        print plt.viewRect(returnMode='value')
        req = plt.viewRect(returnMode='async')
        while not req.hasResult():
            time.sleep(0.01)
        print req.result()._getValue()
        
        b = rpg.QtGui.QPushButton("PRESS ME")
        b.show()
        
        def fn(b):
            print "got remote click"
        fnProx = LocalObjectProxy(fn, proc)
        b.clicked.connect(fnProx)
        
        







