import sys

class Parallelize:
    """
    Class for ultra-simple inline parallelization on multi-core CPUs
    
    Example::
    
        ## Here is the serial (single-process) task:
        
        tasks = [1, 2, 4, 8]
        results = []
        for task in tasks:
            result = processTask(task)
            results.append(result)
        print results
        
        
        ## Here is the parallelized version:
        
        tasks = [1, 2, 4, 8]
        results = []
        with Parallelize(tasks, results, workers=4) as tasker:
            for task in tasker:
                result = processTask(task)
                tasker.results.append(result)
        print results
        
        
    The only major caveat is that *result* in the example above must be picklable.
    """

    def __init__(self, tasks, workers=None, **kwds):
        if workers is None:
            workers = multiprocessing.cpu_count()
        if not hasattr(os, 'fork'):
            workers = 1
        self.workers = workers
        self.tasks = tasks
        self.kwds = kwds
        
    def __enter__(self):
        if workers == 1: 
            return Tasker(self, self.tasks, self.kwds)
            
        childs = []
        for i in range(workers):
            proc = ForkedProcess(target=None)
            if not proc.isParent():
                return Tasker(proc, self.tasks, self.kwds)
            else:
                childs.append(proc)
        
    def __exit__(self, *exc_info):
        if exc_info[0] is not None:
            sys.excepthook(*exc_info)
    
    
class Tasker:
    def __init__(self, proc, tasks, kwds):
        self.proc = proc
        self.tasks = tasks
        for k, v in kwds.iteritems():
            setattr(self, k, v)
        
    def __iter__(self):
        ## we could fix this up such that tasks are retrieved from the parent process one at a time..
        for task in self.tasks:
            yield task
    
    
    
class Parallelizer:
    """
    Use::
    
        p = Parallelizer()
        with p(4) as i:
            p.finish(do_work(i))
        print p.results()
    
    """
    def __init__(self):
        pass

    def __call__(self, tasks, workers=None):
        if workers is None:
            workers = multiprocessing.cpu_count()
        
        self.replies = []
        self.conn = None  ## indicates this is the parent process
        return Session(self, tasks, workers)
            
    def finish(self, data):
        if self.conn is None:
            self.replies.append((self.i, data))
        else:
            self.conn.send((self.i, data))
            os._exit(0)
            
    def result(self):
        print self.replies
        
class Session:
    def __init__(self, par, tasks, workers):
        self.par = par
        self.tasks = tasks
        self.workers = workers
        
    def __enter__(self):
        self.childs = []
        for i in range(1, self.n):
            c1, c2 = multiprocessing.Pipe()
            pid = os.fork()
            if pid == 0:  ## child
                self.par.i = i
                self.par.conn = c2
                self.childs = None
                c1.close()
                return i+1
            else:
                self.childs.append(c1)
                c2.close()
        self.par.i = 0
        return 0
            
        
        
    def __exit__(self, *exc_info):
        if exc_info[0] is not None:
            sys.excepthook(*exc_info)
        if self.childs is not None:
            self.par.replies.extend([conn.recv() for conn in self.childs])
        else:
            self.par.finish(None)
        
