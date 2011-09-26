# -*- coding: utf-8 -*-
import time, traceback, sys
from PyQt4 import QtCore, QtGui
from Mutex import Mutex
from debug import *

class Device(QtCore.QObject):
    """Abstract class defining the standard interface for Device subclasses."""
    def __init__(self, deviceManager, config, name):
        QtCore.QObject.__init__(self)
        #self._lock_ = threading.Lock()
        #self._lock_ = Mutex(QtCore.QMutex.Recursive)  ## bad idea.
        self._lock_ = Mutex(QtCore.QMutex.Recursive)  ## no, good idea
        self._lock_tb_ = None
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
    
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return None
        
    def protocolInterface(self, prot):
        """Return a widget with a UI to put in the protocol rack"""
        return ProtocolGui(self, prot)
        

    def reserve(self, block=True, timeout=20):
        #print "Device %s attempting lock.." % self.name
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
                #print "Device %s lock failed." % self.name
                return False
                #print "  Device is currently locked from:"
                #print self._lock_tb_
                #raise Exception("Could not acquire lock", 1)  ## 1 indicates failed non-blocking attempt
        self._lock_tb_ = ''.join(traceback.format_stack()[:-1])
        #print "Device %s lock ok" % self.name
        return True
        
    def release(self):
        try:
            self._lock_.unlock()
            self._lock_tb_ = None
        except:
            printExc("WARNING: Failed to release device lock for %s" % self.name)
            
    def getTriggerChannel(self, daq):
        """Return the name of the channel on daq that this device raises when it starts.
        Allows the DAQ to trigger off of this device."""
        return None

class DeviceTask:
    def __init__(self, dev, cmd):
        self.dev = dev
        self.cmd = cmd
    
    def getConfigOrder(self):
        """return lists of devices that should be configured (before, after) this device"""
        return ([], [])
    
    def configure(self, tasks, startOrder):
        pass
    
    def reserve(self, block=True, timeout=20):
        return self.dev.reserve(block=block, timeout=timeout)
    
    def start(self):
        pass
    
    def isDone(self):
        return True
    
    def stop(self, abort=False):
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
    
    def abort(self):
        self.stop(abort=True)
    
class ProtocolGui(QtGui.QWidget):
    
    sigSequenceChanged = QtCore.Signal(object)
    
    def __init__(self, dev, prot):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.prot = prot
        self._PGConnected = False
        self.enable()
        
    def enable(self):
        if not self._PGConnected:
            #QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolStarted'), self.protocolStarted)        
            #QtCore.QObject.connect(self.prot, QtCore.SIGNAL('taskStarted'), self.taskStarted)     
            #QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolFinished'), self.protocolFinished) 
            self.prot.sigProtocolStarted.connect(self.protocolStarted) ## called at the beginning of a protocol/sequence
            self.prot.sigTaskStarted.connect(self.taskStarted)## called at the beginning of all protocol runs
            self.prot.sigProtocolFinished.connect(self.protocolFinished) ## called at the end of a protocol/sequence
            self._PGConnected = True
        
    def disable(self):
        if self._PGConnected:
            #QtCore.QObject.disconnect(self.prot, QtCore.SIGNAL('protocolStarted'), self.protocolStarted)
            #QtCore.QObject.disconnect(self.prot, QtCore.SIGNAL('taskStarted'), self.taskStarted)
            #QtCore.QObject.disconnect(self.prot, QtCore.SIGNAL('protocolFinished'), self.protocolFinished)
            self.prot.sigProtocolStarted.disconnect(self.protocolStarted)
            self.prot.sigTaskStarted.disconnect(self.taskStarted)
            self.prot.sigProtocolFinished.disconnect(self.protocolFinished)
            self._PGConnected = False
        
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        return {}
        
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        pass
        
    def listSequence(self):
        """Return an OrderedDict of sequence parameter names and lengths {name: length}"""
        return {}
        
    def generateProtocol(self, params=None):
        if params is None:
            params = {}
        return {}
        
    def handleResult(self, result, params):
        """Display (or otherwise handle) the results of the protocol generated by this device.
        Does NOT handle file storage; this is handled by the device itself."""
        pass

    def protocolStarted(self):
        """Automatically invoked before a protocol or sequence is started"""
        pass

    def taskStarted(self, params):
        """Automatically invoked before a single protocol task is started"""
        pass
        
    def protocolFinished(self):
        """Automatically invoked after a protocol or sequence has finished"""
        pass

    def quit(self):
        self.disable()





