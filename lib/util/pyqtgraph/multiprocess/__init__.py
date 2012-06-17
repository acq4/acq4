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
    
    - attributes of proxy should inherit defaultReturnMode
    - additionally, proxies should inherit defaultReturnMode from the Process that generated them
        - and _import should obey defaultReturnMode ?
    - can we make process startup asynchronous since it takes so long?
        - Process can defer sending requests until remote process is ready
        
        
        
"""


from remoteproxy import RemoteEventHandler, ExitError, NoResultError
import subprocess, atexit, os, sys, time
import cPickle as pickle
import multiprocessing.connection

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
    
    def __init__(self, name=None, target=0):
        """
        When initializing, an optional target may be given. 
        If no target is specified, self.eventLoop will be used.
        If None is given, no target will be called (and it will be up 
        to the caller to properly shut down the forked process)
        """
        self.hasJoined = False
        if target == 0:
            target = self.eventLoop
        if name is None:
            name = str(self)
        
        conn, remoteConn = multiprocessing.Pipe()
        
        pid = os.fork()
        if pid == 0:
            self.isParent = False
            conn.close()
            sys.stdin.close()  ## otherwise we screw with interactive prompts.
            RemoteEventHandler.__init__(self, remoteConn, name+'_child', pid=os.getppid())
            if target is not None:
                target()
        else:
            self.isParent = True
            self.childPid = pid
            remoteConn.close()
            RemoteEventHandler.handlers = {}  ## don't want to inherit any of this from the parent.
            
            RemoteEventHandler.__init__(self, conn, name+'_parent', pid=pid)
            atexit.register(self.join)
        
        
    def eventLoop(self):
        while True:
            try:
                self.processRequests()  # exception raised when the loop should exit
                time.sleep(0.01)
            except ExitError:
                sys.exit(0)
            except:
                print "Error occurred in forked event loop:"
                sys.excepthook(*sys.exc_info())
        
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
        
    def startEventTimer(self):
        from pyqtgraph.Qt import QtGui, QtCore
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.processRequests)
        self.timer.start(10)
    
    def processRequests(self):
        try:
            RemoteEventHandler.processRequests(self)
        except ExitError:
            from pyqtgraph.Qt import QtGui, QtCore
            QtGui.QApplication.instance().quit()
            self.timer.stop()
            #raise

class QtProcess(Process):
    def __init__(self, name=None):
        Process.__init__(self, name, target=startQtEventLoop)
        self.startEventTimer()
        
    def startEventTimer(self):
        from pyqtgraph.Qt import QtGui, QtCore  ## avoid module-level import to keep bootstrap snappy.
        self.timer = QtCore.QTimer()
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


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'remote':  ## module has been invoked as script in new python interpreter.
        name, port, authkey, target = pickle.load(sys.stdin)
        target(name, port, authkey)
        sys.exit(0)
