from PyQt4 import QtCore
import traceback

class Mutex(QtCore.QMutex):
    """Extends QMutex to provide warning messages when a mutex stays locked for a long time.
    Mostly just useful for debugging purposes.
    """
    
    def __init__(self, *args):
        QtCore.QMutex.__init__(self, *args)
        self.tb = None
        self.waitTime = 2000

    def lock(self):
        c = 0
        while True:
            if self.tryLock(self.waitTime):
                self.tb = ''.join(traceback.format_stack())
                break
            c += 1
            print "Waiting for mutex lock (%d sec). Traceback follows:" % (c*self.waitTime/1000.)
            traceback.print_stack()
            print "Mutex is currently locked from:\n", self.tb

