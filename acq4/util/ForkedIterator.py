from __future__ import print_function
import multiprocessing as m
import time
import numpy

class StopRemoteIteration:
    pass

class ForkedIterator(m.Process):
    def __init__(self, fn, *args, **kargs):
        self.fn = fn
        self.p1, self.p2 = m.Pipe()
        self.args = args
        self.kargs = kargs
        m.Process.__init__(self)
        self.daemon = True
        self.start()
        self.p2.close()  ## we will never use this end of the pipe from here; close it locally so we can detect when the pipe is fully closed
        
    def send(self, obj):
        self.p1.send(obj)
        
    def run(self):
        self.p1.close()  ## we will never use this end of the pipe from here; close it locally so we can detect when the pipe is fully closed
        #print "args", self.args, "kargs", self.kargs
        #print "fn", self.fn
        for x in self.fn(*self.args, **self.kargs):
            self.p2.send(x)
        self.p2.send(StopRemoteIteration())
        self.p2.close()
        
    def __iter__(self):
        return self
        
    def __next__(self):
        try:
            x = self.p1.recv()
            #print "recv:", x
        except EOFError:  ## nothing left in pipe
            if self.is_alive():
                raise Exception("Remote process has already closed pipe (but is still alive)")
            else: 
                raise Exception("Remote process has ended (and pipe is empty). (exit code %d)" % self.exitcode)
        except IOError as (errno, strerror):
            if errno == 4:   ## blocking read was interrupted; try again.
                return next(self)
            else:
                raise
        if isinstance(x, StopRemoteIteration):
            #print "iteration done"
            raise StopIteration
        else:
            return x
            

        
#val = {'a': ['complex', 'object']}
#v = m.Value(dict, val)
if __name__ == '__main__':
    
    def gen(nMax):
        for i in range(nMax):
            r = numpy.random.random()
            #if r < 0.05:
                #print "Fatal error in process"
                #import os
                #os.kill(os.getpid(), 9)
            #elif r < 0.1:
                #raise Exception("Error in process")
            yield i, nMax
        yield 3.1415, None
    
    fg = ForkedIterator(gen, 10)
    for x in fg:
        print(x)
    
