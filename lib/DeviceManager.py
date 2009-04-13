# -*- coding: utf-8 -*-
from util import configfile
import time, sys, atexit
from PyQt4 import QtCore, QtGui

class DeviceManager():
    """DeviceManager class is responsible for loading device modules and instantiating device
    objects as they are needed. This class is the global repository for device handles."""
    
    def __init__(self, configFile=None):
        self.alreadyQuit = False
        atexit.register(self.quit)
        self.devices = {}
        self.modules = {}
        self.devRack = None
        self.readConfig(configFile)
        if 'win' in sys.platform:
            time.clock()  ### Required to start the clock in windows
            self.startTime = time.time()
            self.time = self.winTime
        else:
            self.time = self.unixTime
    
    def __del__(self):
        self.quit()
    
    def getDevice(self, name):
        if name not in self.devices:
            raise Exception("No device named %s" % name)
        return self.devices[name]

    def loadModule(self, module, name, config={}):
        mod = __import__('lib.modules.%s.interface' % module, fromlist=['*'])
        modclass = getattr(mod, module)
        self.modules[name] = modclass(self, name, config)
        return self.modules[name]
        
    def getModule(self, name):
        if name not in self.modules:
            raise Exception("No module named %s" % name)
        return self.modules[name]
        
    
        
    def winTime(self):
        """Return the current time in seconds with high precision (windows version)."""
        return time.clock() + self.startTime
    
    def unixTime(self):
        """Return the current time in seconds with high precision (unix version)."""
        return time.time()
    
    def readConfig(self, configFile):
        """Read configuration file, create device objects, add devices to list"""
        print "============= Starting DeviceManager configuration from %s =================" % configFile
        cfg = configfile.readConfigFile(configFile)
        if not cfg.has_key('devices'):
            raise Exception('configuration file %s has no "devices" section.' % configFile)
        for k in cfg['devices']:
            print "\n=== Configuring device %s ===" % k
            modName = cfg['devices'][k]['module']
            mod = __import__('lib.devices.%s.interface' % modName, fromlist=['*'])
            conf = None
            if cfg['devices'][k].has_key('config'):
                conf = cfg['devices'][k]['config']
            devclass = getattr(mod, modName)
            self.devices[k] = devclass(self, conf, k)
        print "\n============= DeviceManager configuration complete =================\n"

    def runProtocol(self, cmd):
        t = Task(self, cmd)
        t.execute()
        return t.getResult()

    def createTask(self, cmd):
        return Task(self, cmd)

    def quit(self):
        """Nicely request that all devices shut down"""
        if not self.alreadyQuit:
            for d in self.devices:
                print "Requesting %s quit.." % d
                self.devices[d].quit()
            self.alreadyQuit = True
            
    def showDeviceRack(self):
        if self.devRack is None:
            self.devRackDocks = {}
            self.devRack = QtGui.QMainWindow()
            for d in self.devices:
                dw = self.devices[d].deviceInterface()
                dock = QtGui.QDockWidget(d)
                dock.setFeatures(dock.AllDockWidgetFeatures)
                dock.setWidget(dw)
                
                self.devRackDocks[d] = dock
                self.devRack.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        self.devRack.show()
            
class Task:
    def __init__(self, dm, command):
        self.dm = dm
        self.command = command
        self.result = None
        
        self.cfg = command['protocol']

        ## TODO:  set up data storage with cfg['storeData'] and ['writeLocation']
        
        self.devNames = command.keys()
        self.devNames.remove('protocol')
        self.devs = {}
        
        ## Create task objects. Each task object is a handle to the device which is unique for this protocol run.
        self.tasks = {}
        for devName in self.devNames:
            self.devs[devName] = self.dm.getDevice(devName)
            self.tasks[devName] = self.devs[devName].createTask(self.command[devName])
        
    def execute(self):
        ## Configure all subtasks. Some devices may need access to other tasks, so we make all available here.
        ## This is how we allow multiple devices to communicate and decide how to operate together.
        ## Each task may modify the startOrder array to suit its needs.
        self.startOrder = self.devs.keys()
        for devName in self.tasks:
            self.tasks[devName].configure(self.tasks, self.startOrder)
        
        ## Reserve all hardware before starting any
        for devName in self.tasks:
            self.tasks[devName].reserve()
        
        self.result = None
        
        ## Start tasks in specific order
        for devName in self.startOrder:
            self.tasks[devName].start()
            
        ## Wait until all tasks are done
        for t in self.tasks:
            while not self.tasks[t].isDone():
                time.sleep(10e-6)
        
        ## Stop all tasks
        for t in self.tasks:
            self.tasks[t].stop()
        
        ## Release all hardware for use elsewhere
        for t in self.tasks:
            self.tasks[t].release()
        
    def getResult(self):
        if self.result is None:
            ## Let each device generate its own output structure.
            result = {}
            for devName in self.tasks:
                result[devName] = self.tasks[devName].getResult()
            
            return result
        return self.result
