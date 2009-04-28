# -*- coding: utf-8 -*-
import time, traceback, sys
#import threading
from PyQt4 import QtCore, QtGui

class Device:
    """Abstract class defining the standard interface for Device subclasses."""
    def __init__(self, deviceManager, config, name):
        #self._lock_ = threading.Lock()
        self._lock_ = QtCore.QMutex()
        self.dm = deviceManager
        self.config = config
        self.name = name
    
    def createTask(self):
        pass
    
    def __del__(self):
        self.quit()
        
    def quit(self):
        pass
    
    def prepareProtocol(cmd):
        ## Read configuration, configure tasks
        ## Return a handle unique to this task
        raise Exception("Function prepareProtocol() not defined in this subclass!")
        
    ## This should not be needed.
    #def setHolding(self):
        #"""set all channels for this device to their configured holding level"""
        #raise Exception("Function setHolding() not defined in this subclass!")

    def deviceInterface(self):
        """Return a widget with a UI to put in the device rack"""
        return QtGui.QLabel(self.name)
        
    def protocolInterface(self, prot):
        """Return a widget with a UI to put in the protocol rack"""
        return ProtocolGui(self, prot)
        

    def reserve(self, block=True, timeout=20):
        #lock = False
        #count = 0
        #interval = 1e-3
        #lock = self._lock_.acquire(False)  ## We'll do our own blocking
        #if not lock and not block:
            #raise Exception("Could not acquire lock")
        #while not lock:
            #if timeout is not None and (count*interval > timeout):
                #raise Exception("Timed out waiting for device lock for %s" % self.name)
            #time.sleep(interval)
            #lock = self._lock_.acquire(False)  ## We'll do our own blocking
            #count += 1
        #return True
        
        if block:
            l = self._lock_.tryLock(int(timeout*1000))
            if not l:
                raise Exception("Timed out waiting for device lock for %s" % self.name)
        else:
            l = self._lock_.tryLock()
            if not l:
                raise Exception("Could not acquire lock")
        return True
        
    def release(self):
        try:
            #self.lock.release()
            self._lock_.unlock()
        except:
            print "WARNING: Failed to release device lock for %s" % self.name
            traceback.print_exception(sys.exc_info())


class DeviceTask:
    def __init__(self, dev, cmd):
        self.dev = dev
        self.cmd = cmd
    
    def configure(self, tasks):
        pass
    
    def reserve(self, block=True, timeout=20):
        self.dev.reserve(block=block, timeout=timeout)
    
    def start(self):
        pass
    
    def isDone(self):
        pass
    
    def stop(self):
        pass
    
    def release(self):
        self.dev.release()
    
    def getResult(self):
        pass
    
    
class ProtocolGui(QtGui.QWidget):
    def __init__(self, dev, prot):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.prot = prot
        
    def saveState(self):
        return {}
        
        
    def restoreState(self, state):
        pass
        
    def listSequence(self):
        ## returns sequence parameter names and lengths
        return []
        
    def generateProtocol(self):
        return {}