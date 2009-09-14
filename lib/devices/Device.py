# -*- coding: utf-8 -*-
import time, traceback, sys
#import threading
from PyQt4 import QtCore, QtGui
import lib.util.ptime as ptime
from lib.util.Mutex import Mutex
#from lib.util.Mutex import Mutex

class Device(QtCore.QObject):
    """Abstract class defining the standard interface for Device subclasses."""
    def __init__(self, deviceManager, config, name):
        QtCore.QObject.__init__(self)
        #self._lock_ = threading.Lock()
        self._lock_ = Mutex(QtCore.QMutex.Recursive)
        self._lock_tb_ = None
        #self._lock_ = Mutex()
        self.dm = deviceManager
        self.config = config
        self.name = name
    
    def createTask(self, cmd):
        ### Read configuration, configure tasks
        ### Return a handle unique to this task
        pass
    
    def __del__(self):
        self.quit()
        
    def quit(self):
        pass
    
    def deviceInterface(self):
        """Return a widget with a UI to put in the device rack"""
        return QtGui.QWidget()
        
    def protocolInterface(self, prot):
        """Return a widget with a UI to put in the protocol rack"""
        return ProtocolGui(self, prot)
        

    def reserve(self, block=True, timeout=20):
        if block:
            l = self._lock_.tryLock(int(timeout*1000))
            if not l:
                print "Timeout waiting for device lock for %s" % self.name
                print "  Device is currently locked from:"
                print self._lock_tb_
                raise Exception("Timed out waiting for device lock for %s" % self.name)
        else:
            l = self._lock_.tryLock()
            if not l:
                raise Exception("Could not acquire lock")
        self._lock_tb_ = ''.join(traceback.format_stack()[:-1])
        return True
        
    def release(self):
        try:
            self._lock_.unlock()
            self._lock_tb_ = None
        except:
            print "WARNING: Failed to release device lock for %s" % self.name
            traceback.print_exception(*sys.exc_info())
            
    def getTriggerChannel(self, daq):
        """Return the name of the channel on daq that this device raises when it starts.
        Allows the DAQ to trigger off of this device."""
        return None

class DeviceTask:
    def __init__(self, dev, cmd):
        self.dev = dev
        self.cmd = cmd
    
    def configure(self, tasks, startOrder):
        pass
    
    def reserve(self, block=True, timeout=20):
        self.dev.reserve(block=block, timeout=timeout)
    
    def start(self):
        pass
    
    def isDone(self):
        return True
    
    def stop(self):
        pass
    
    def release(self):
        self.dev.release()
    
    def getResult(self):
        return None
    
    def storeResult(self, dirHandle):
        result = self.getResult()
        if result is None:
            return
        elif isinstance(result, dict):
            for k in result:
                dirHandle.writeFile(result, self.dev.name+'_'+str(k))
        else:
            dirHandle.writeFile(result, self.dev.name)
    
    
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
        
    def generateProtocol(self, params=None):
        if params is None:
            params = {}
        return {}
        
    def handleResult(self, result, params):
        pass