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
        self.dm.declareInterface(name, ['device'], self)
        #self.config = config
        self._name = name
    
    def name(self):
        return self._name
    
    def createTask(self, cmd):
        ### Read configuration, configure tasks
        ### Return a handle unique to this task
        pass
    
    #def __del__(self):
        #self.quit()
        
    def quit(self):
        pass
    
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return None
        
    def taskInterface(self, task):
        """Return a widget with a UI to put in the task rack"""
        return TaskGui(self, task)
        

    def reserve(self, block=True, timeout=20):
        #print "Device %s attempting lock.." % self.name()
        if block:
            l = self._lock_.tryLock(int(timeout*1000))
            if not l:
                print "Timeout waiting for device lock for %s" % self.name()
                print "  Device is currently locked from:"
                print self._lock_tb_
                raise Exception("Timed out waiting for device lock for %s" % self.name())
        else:
            l = self._lock_.tryLock()
            if not l:
                #print "Device %s lock failed." % self.name()
                return False
                #print "  Device is currently locked from:"
                #print self._lock_tb_
                #raise Exception("Could not acquire lock", 1)  ## 1 indicates failed non-blocking attempt
        self._lock_tb_ = ''.join(traceback.format_stack()[:-1])
        #print "Device %s lock ok" % self.name()
        return True
        
    def release(self):
        try:
            self._lock_.unlock()
            self._lock_tb_ = None
        except:
            printExc("WARNING: Failed to release device lock for %s" % self.name())
            
    def getTriggerChannel(self, daq):
        """Return the name of the channel on daq that this device raises when it starts.
        Allows the DAQ to trigger off of this device."""
        return None

class DeviceTask:
    def __init__(self, dev, cmd):
        self.dev = dev
        #self.cmd = cmd
    
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
                dirHandle.writeFile(result, self.dev.name()+'_'+str(k))
        else:
            dirHandle.writeFile(result, self.dev.name())
    
    def abort(self):
        self.stop(abort=True)
    
class TaskGui(QtGui.QWidget):
    
    sigSequenceChanged = QtCore.Signal(object)
    
    def __init__(self, dev, task):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.task = task
        self._PGConnected = False
        self.enable()
        
    def enable(self):
        if not self._PGConnected:
            #QtCore.QObject.connect(self.task, QtCore.SIGNAL('taskStarted'), self.taskStarted)        
            #QtCore.QObject.connect(self.task, QtCore.SIGNAL('taskStarted'), self.taskStarted)     
            #QtCore.QObject.connect(self.task, QtCore.SIGNAL('taskFinished'), self.taskFinished) 
            self.task.sigTaskStarted.connect(self.taskStarted) ## called at the beginning of a task/sequence
            self.task.sigTaskStarted.connect(self.taskStarted)## called at the beginning of all task runs
            self.task.sigTaskFinished.connect(self.taskFinished) ## called at the end of a task/sequence
            self._PGConnected = True
        
    def disable(self):
        if self._PGConnected:
            #QtCore.QObject.disconnect(self.task, QtCore.SIGNAL('taskStarted'), self.taskStarted)
            #QtCore.QObject.disconnect(self.task, QtCore.SIGNAL('taskStarted'), self.taskStarted)
            #QtCore.QObject.disconnect(self.task, QtCore.SIGNAL('taskFinished'), self.taskFinished)
            try:
                self.task.sigTaskStarted.disconnect(self.taskStarted)
            except TypeError:
                pass
            try:
                self.task.sigTaskStarted.disconnect(self.taskStarted)
            except TypeError:
                pass
            try:
                self.task.sigTaskFinished.disconnect(self.taskFinished)
            except TypeError:
                pass
            self._PGConnected = False
        
    def prepareTaskStart(self):
        """Called once before the start of each task or task sequence. Allows the device to execute any one-time preparations it needs."""
        pass
        
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        return {}
        
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        pass
        
    def describe(self, params=None):
        """Return a nested-dict structure that describes what the device will do during a task.
        This data will be stored along with results from a task run."""
        return self.saveState()  ## lazy; implement something nicer for your devices!
        
    def listSequence(self):
        """Return an OrderedDict of sequence parameter names and lengths {name: length}"""
        return {}
        
    def generateTask(self, params=None):
        if params is None:
            params = {}
        return {}
        
    def handleResult(self, result, params):
        """Display (or otherwise handle) the results of the task generated by this device.
        Does NOT handle file storage; this is handled by the device itself."""
        pass

    def taskStarted(self):
        """Automatically invoked before a task or sequence is started.
        Note: this signal is emitted AFTER generateTask() has been run for all devices,
        and before the task is started.
        """
        pass

    def taskStarted(self, params):
        """Automatically invoked before a single task task is started, including each task within a sequence."""
        pass
        
    def taskFinished(self):
        """Automatically invoked after a task or sequence has finished"""
        pass

    def quit(self):
        self.disable()





