# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import traceback
from contextlib import contextmanager
from typing import Optional

import acq4
from acq4.Interfaces import InterfaceMixin
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.debug import printExc
from acq4.util.optional_weakref import Weakref


class Device(InterfaceMixin, Qt.QObject):  # QObject calls super, which is disastrous if not last in the MRO
    """Abstract class defining the standard interface for Device subclasses."""

    sigGeometryChanged = Qt.Signal(object)  # self

    # used to ensure devices are shut down in the correct order
    _deviceCreationOrder = []

    def __init__(self, deviceManager: acq4.Manager.Manager, config: dict, name: str):
        Qt.QObject.__init__(self)

        # task reservation lock -- this is a recursive lock to allow a task to run its own subtasks
        # (for example, setting a holding value before exiting a task).
        # However, under some circumstances we might try to run two concurrent tasks from the same 
        # thread (eg, due to calling processEvents() while waiting for the task to complete). We
        # don't have a good solution for this problem at present..
        self._lock_ = Mutex(Qt.QMutex.Recursive)
        self._lock_tb_ = None
        self.dm = deviceManager
        self.dm.declareInterface(name, ['device'], self)
        Device._deviceCreationOrder.append(Weakref(self))
        self._name = name
        self._geometry = config.get('geometry', {})

    def name(self):
        """Return the string name of this device.
        """
        return self._name
    
    def createTask(self, cmd: dict, task: acq4.Manager.Task):
        # Read configuration, configure tasks
        # Return a handle unique to this task
        # See TaskGUI.listSequences and TaskGUI.generateTask for more info on usage.
        pass
    
    def quit(self):
        pass
    
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return None
        
    def taskInterface(self, task):
        """Return a widget with a UI to put in the task rack"""
        return TaskGui(self, task)

    def defaultGeometryArgs(self):
        """Return a dictionary of default arguments to be used when creating a 3D model for this device.
        """
        return {}

    def getGeometries(self) -> list:
        """Return a 3D model to be displayed in the 3D visualization window.
        """
        from acq4.modules.Visualize3D import create_geometry

        defaults = self.defaultGeometryArgs()
        if self._geometry:
            args = {**self._geometry}
            return create_geometry(defaults=defaults, **args)
        return []

    def configPath(self):
        """Return the path used for storing configuration data for this device.

        This path should resolve to `acq4/config/devices/DeviceName_config`.
        """
        return os.path.join('devices', self.name() + '_config')

    def configFileName(self, filename):
        """Return the full path to a config file for this device.
        """
        filename = os.path.join(self.configPath(), filename)
        return self.dm.configFileName(filename)

    def readConfigFile(self, filename):
        """Read a config file from this device's configuration directory.
        """
        fileName = os.path.join(self.configPath(), filename)
        return self.dm.readConfigFile(fileName)

    def writeConfigFile(self, data, filename):
        """Write data to a config file in this device's configuration directory.
        """
        fileName = os.path.join(self.configPath(), filename)
        return self.dm.writeConfigFile(data, fileName)

    def appendConfigFile(self, data, filename):
        """Append data to a config file in this device's configuration directory.
        """
        fileName = os.path.join(self.configPath(), filename)
        return self.dm.appendConfigFile(data, fileName)

    @contextmanager
    def reserved(self):
        self.reserve()
        try:
            yield
        finally:
            self.release()

    def reserve(self, block=True, timeout=20):
        """Reserve this device globally.

        This lock allows subsystems to request exclusive access to the device. If
        mutiple devices need to be locked simultaneously, then it is strongly
        recommended to use Manager.reserveDevices() instead in order to avoid deadlocks.
        """
        # print("Device %s attempting lock.." % self.name())
        if block:
            l = self._lock_.tryLock(int(timeout*1000))
            if not l:
                print("Timeout waiting for device lock for %s" % self.name())
                print("  Device is currently locked from:")
                print(self._lock_tb_)
                raise Exception("Timed out waiting for device lock for %s\n  Locking traceback:\n%s" % (self.name(), self._lock_tb_))
        else:
            l = self._lock_.tryLock()
            if not l:
                # print("Device %s lock failed." % self.name())
                return False
                #print "  Device is currently locked from:"
                #print self._lock_tb_
                #raise Exception("Could not acquire lock", 1)  ## 1 indicates failed non-blocking attempt
        self._lock_tb_ = ''.join(traceback.format_stack()[:-1])
        # print("Device %s lock ok" % self.name())
        return True
        
    def release(self):
        try:
            self._lock_.unlock()
            # print("Device %s unlocked" % self.name())
            self._lock_tb_ = None
        except:
            printExc("WARNING: Failed to release device lock for %s" % self.name())

    def getTriggerChannels(self, daq: str) -> dict:
        """Return the name of the channel(s) on *daq* can be used to synchronize between this device and a DAQ.

        Parameters
        ----------
        daq : str
            The name of the DAQ device to be synchronized with.

        Returns
        -------
        channels : dict
            Dictionary containing keys "input" (the name of a digital input on the DAQ that we can use to trigger the
            DAQ) and "output" (the name of a digital output that can be used to trigger this device). Either value may
            be None.
        """
        return {'input': None, 'output': None}
    
    def __repr__(self):
        return f'<{self.__class__.__name__} "{self.name()}">'
    

class DeviceTask(object):
    """
    DeviceTask handles all behavior of a single device during 
    execution of a task, including configuring the device based on the 
    contents of its command, starting the device, and collecting results.    
    
    DeviceTask instances are usually created by calling Device.createTask().
    """
    def __init__(self, dev, cmd, parentTask):
        """
        Initialization is provided 3 arguments: *dev* is the Device for which
        this DeviceTask is responsible for controlling. *cmd* is the command
        structure which describes the requested behavior of the device during 
        execution of the task. *parentTask* is the Manager-created Task object
        which coordinates action between multiple DeviceTasks that will be 
        operating synchronously.
        """
        self.dev = dev
        self.__parentTask = Weakref(parentTask)
        
    def parentTask(self):
        return self.__parentTask()
    
    def getConfigOrder(self):
        """
        This method is called by the parent task before configuration and allows 
        the DeviceTask to declare any configuration dependencies. Must return
        two lists that contain the devices (or names of devices) that
        must be configured before / after this device.
        
        By default, this method returns empty lists. The final configuration
        order is determined by topologically sorting all of the declared
        dependencies, with a weighting based on the expected preparation time
        for each device (see getPrepTimeEstimate).
        
        """
        return [], []

    def getPrepTimeEstimate(self):
        """
        Return an estimate of the amount of time this device will require 
        between returning from its configure() method and returning from its
        start() method. 
        
        This method is called by the parent task before configuration as a means
        of allowing devices with a known, long preparation time to be 
        configured as early as possible (while still satisfying the dependencies
        declared by getConfigureOrder). This allows the parent task to optimize
        the order in which devices are configured for minimum latency to start.
        
        By default, this method returns 0.
        """
        return 0
        
    def configure(self):
        """
        This method prepares the device to begin protocol execution by 
        uploading waveform data, arming triggers, and setting any device
        parameters needed.
        
        The parent Task will call this method on each DeviceTask in an order
        determined by the configuration dependencies declared in 
        DeviceTask.__init__. 
        
        This method is responsible for indicating to the parent Task any 
        start-order dependencies. For example:
        
            # 'device' must be started before self
            parentTask.addStartDependency(self, 'device')
        """
        pass

    def getStartOrder(self):
        """
        This method is called by the parent task before starting any devices.
        It allows the DeviceTask to declare any starting dependencies. Must 
        return two lists that contain the devices (or names of devices) that
        must be started before / after this device.
        
        By default, this method returns empty lists. The final start
        order is determined by topologically sorting all of the declared
        dependencies.
        """
        return [], []

    def start(self):
        """
        This method instructs the device to begin execution of the task.
        In many cases, this method will do nothing because the device has
        already been configured to start on an external trigger signal.         
        """
        pass
    
    def isDone(self):
        """
        Return true if this DeviceTask has completed.
        
        The default implementation returns True.
        """
        return True
    
    def stop(self, abort=False):
        """
        Stop this DeviceTask. If abort is True, then the task should stop as
        soon as possible. 
        
        The default implementation does nothing.
        """
        pass
    
    def getResult(self):
        """
        Return any data acquired by the device during the most recent task.
        """
        return None
    
    def storeResult(self, dirHandle):
        """
        Store the most recent set of results inside the specified dirHandle. 
        Although each device may determine the best data structure and formats
        to write, a few conventions are recommended: 
        
        * Create either a single file or a single directory inside dirHandle,
          and name it beginning with the name of this device in order to avoid
          name collisions with other devices.
        * If a directory is created, any file structure may be placed inside it.
        * When appropriate, store data using MetaArray.
        * To store very small amounts of data, it is acceptable to simply call
          `dirHandle.setInfo(...)`. As in the case of files, only a single key
          should be added to the directory meta-info, and it should begin with
          the name of the device.
        """
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

    
class TaskGui(Qt.QWidget):
    
    sigSequenceChanged = Qt.Signal(object)
    
    def __init__(self, dev, taskRunner):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.taskRunner = taskRunner
        self._PGConnected = False
        self.enable()
        
    def enable(self):
        if not self._PGConnected:
            self.taskRunner.sigTaskSequenceStarted.connect(self.taskSequenceStarted) ## called at the beginning of a task/sequence
            self.taskRunner.sigTaskStarted.connect(self.taskStarted)## called at the beginning of all task runs
            self.taskRunner.sigTaskFinished.connect(self.taskFinished) ## called at the end of a task/sequence
            self._PGConnected = True
        
    def disable(self):
        if self._PGConnected:
            try:
                self.taskRunner.sigTaskSequenceStarted.disconnect(self.taskSequenceStarted)
            except TypeError:
                pass
            try:
                self.taskRunner.sigTaskStarted.disconnect(self.taskStarted)
            except TypeError:
                pass
            try:
                self.taskRunner.sigTaskFinished.disconnect(self.taskFinished)
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
        """
        Return an OrderedDict of sequence parameter names and values {name: list_of_values}. See generateTask for more
        details on usage.
        """
        return {}
        
    def generateTask(self, params: Optional[dict] = None) -> dict:
        """
        This method should convert params' index-values back into task-values, along with any default work non-sequenced
        tasks need. WARNING! Long sequences will not automatically lock the UI or preserve the state of your parameter
        sequences. The example code below will break if a user messes with anything while the task sequence is running.

        :param params:
            This dictionary will have the same top-level shape as the return value of listSequence, but instead of a
            list, its values will be the indexes of the values currently being run. E.g.::

                listSequence() -> {'a': [10, 100, 1000], 'b': [20, 40]}
                generateTask({'a': 0, 'b': 0})
                generateTask({'a': 1, 'b': 0})
                ...

        :return:
            Valid command structure for your devices' task.
        """
        if params is None:
            params = {}
        paramSpace = self.listSequence()  # WARNING! This is not reliable!
        params = {k: paramSpace[k][v] for k, v in params.items()}
        return params
        
    def handleResult(self, result, params):
        """Display (or otherwise handle) the results of the task generated by this device.
        Does NOT handle file storage; this is handled by the device itself."""
        pass

    def taskSequenceStarted(self):
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
