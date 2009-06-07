# -*- coding: utf-8 -*-
from util import configfile
import time, sys, atexit
from PyQt4 import QtCore, QtGui
from DataManager import *
import lib.util.ptime as ptime

class Manager(QtCore.QObject):
    """Manager class is responsible for:
      - Loading/configuring device modules and storing their handles
      - Managing the device rack GUI
      - Creating protocol task handles
      - Loading interface modules and storing their handles
      - Creating and managing DirectoryHandle objects
      - Providing unified timestamps
      - Making sure all devices/modules are properly shut down at the end of the program"""
    CREATED = False
    single = None
    
    def __init__(self, configFile=None):
        if Manager.CREATED:
            raise Exception("Manager object already created!")
        
        QtCore.QObject.__init__(self)
        self.alreadyQuit = False
        self.taskLock = QtCore.QMutex(QtCore.QMutex.Recursive)
        atexit.register(self.quit)
        self.devices = {}
        self.modules = {}
        self.devRack = None
        self.dataManager = DataManager()
        self.currentDir = None
        self.baseDir = None
        self.readConfig(configFile)
        Manager.CREATED = True
        Manager.single = self

    def readConfig(self, configFile):
        """Read configuration file, create device objects, add devices to list"""
        print "============= Starting Manager configuration from %s =================" % configFile
        cfg = configfile.readConfigFile(configFile)
        if not cfg.has_key('devices'):
            raise Exception('configuration file %s has no "devices" section.' % configFile)
        for k in cfg['devices']:
            print "\n=== Configuring device %s ===" % k
            conf = None
            if cfg['devices'][k].has_key('config'):
                conf = cfg['devices'][k]['config']
            modName = cfg['devices'][k]['module']
            self.loadDevice(modName, conf, k)
        if 'users' in cfg:
            user = 'Luke'
            self.conf = cfg['users'][user]
            baseDir = self.conf['storageDir']
            self.setBaseDir(baseDir)
            self.setCurrentDir('')
        else:
            raise Exception("No configuration found for data management!")
        print "\n============= Manager configuration complete =================\n"



    def __del__(self):
        self.quit()
    
    def loadDevice(self, modName, conf, name):
        mod = __import__('lib.devices.%s.interface' % modName, fromlist=['*'])
        devclass = getattr(mod, modName)
        self.devices[name] = devclass(self, conf, name)
        return self.devices[name]
    
    def getDevice(self, name):
        name = str(name)
        if name not in self.devices:
            print self.devices
            raise Exception("No device named %s. Options are %s" % (name, str(self.devices.keys())))
        return self.devices[name]

    def listDevices(self):
        return self.devices.keys()

    def loadModule(self, module, name, config=None):
        if config is None:
            config = {}
        mod = __import__('lib.modules.%s.interface' % module, fromlist=['*'])
        modclass = getattr(mod, module)
        self.modules[name] = modclass(self, name, config)
        return self.modules[name]
        
    def getModule(self, name):
        if name not in self.modules:
            raise Exception("No module named %s" % name)
        return self.modules[name]
        
    
    def runProtocol(self, cmd):
        t = Task(self, cmd)
        t.execute()
        return t.getResult()

    def createTask(self, cmd):
        return Task(self, cmd)

    
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
    
    def getCurrentDir(self):
        if self.currentDir is None:
            raise Exception("CurrentDir has not been set!")
        return self.currentDir

    def setCurrentDir(self, d):
        if self.currentDir is not None:
            QtCore.QObject.disconnect(self.currentDir, QtCore.SIGNAL('changed'), self.currentDirChanged)
            
            
        if type(d) is str:
            self.currentDir = self.baseDir.getDir(d, create=True)
        elif isinstance(d, DirHandle):
            self.currentDir = d
        else:
            raise Exception("Invalid argument type: ", type(d), d)
        QtCore.QObject.connect(self.currentDir, QtCore.SIGNAL('changed'), self.currentDirChanged)
        self.emit(QtCore.SIGNAL('currentDirChanged'))

    def currentDirChanged(self, *args):
        """Handle situation where currentDir is moved or renamed"""
        #print "Changed:", args
        self.emit(QtCore.SIGNAL('currentDirChanged'), *args)
            
            
    def getBaseDir(self):
        if self.baseDir is None:
            raise Exception("BaseDir has not been set!")
        return self.baseDir

    def setBaseDir(self, d):
        if type(d) is str:
            self.baseDir = self.dirHandle(d, create=False)
        elif isinstance(d, DirHandle):
            self.baseDir = d
        else:
            raise Exception("Invalid argument type: ", type(d), d)
        if not self.baseDir.isManaged():
            self.baseDir.createIndex()
        self.emit(QtCore.SIGNAL('baseDirChanged'))

    def dirHandle(self, d, create=False):
        """Return a directory handle for d."""
        return self.dataManager.getDirHandle(d, create)

    def fileHandle(self, d):
        """Return a file or directory handle for d"""
        return self.dataManager.getHandle(d)
        
    def lockReserv(self):
        """Lock the reservation system so that only one task may reserve its set of devices at a time"""
        if self.taskLock.tryLock(10e3):
            return True
        else:
            raise Exception("Times out waiting for task reservation system")
        
    def unlockReserv(self):
        self.taskLock.unlock()
        
    def logMsg(self, msg, tags=None):
        if tags is None:
            tags = {}
        cd = self.getCurrentDir()
        cd.logMsg(msg, tags)

    def quit(self):
        """Nicely request that all devices shut down"""
        if not self.alreadyQuit:
            for d in self.devices:
                print "Requesting %s quit.." % d
                self.devices[d].quit()
            self.alreadyQuit = True


class Task:
    id = 0
    
    
    def __init__(self, dm, command):
        self.dm = dm
        self.command = command
        self.result = None
        self.reserved = False
        self.cfg = command['protocol']
        self.id = Task.id
        Task.id += 1
        
        ## TODO:  set up data storage with cfg['storeData'] and ['writeLocation']
        
        self.devNames = command.keys()
        self.devNames.remove('protocol')
        self.devs = {}
        
        ## Create task objects. Each task object is a handle to the device which is unique for this protocol run.
        self.tasks = {}
        for devName in self.devNames:
            self.devs[devName] = self.dm.getDevice(devName)
            self.tasks[devName] = self.devs[devName].createTask(self.command[devName])
        
        
    def execute(self, block=True):
        self.stopped = False
        #print "======  Executing task %d:" % self.id
        #print self.cfg
        #print "======================="
        
        
        
        ## Reserve all hardware before starting any
        self.dm.lockReserv()
        try:
            for devName in self.tasks:
                #print "  %d Reserving hardware" % self.id, devName
                self.tasks[devName].reserve()
                #print "  %d reserved" % self.id, devName
            self.reserved = True
        finally:
            self.dm.unlockReserv()


        ## Configure all subtasks. Some devices may need access to other tasks, so we make all available here.
        ## This is how we allow multiple devices to communicate and decide how to operate together.
        ## Each task may modify the startOrder array to suit its needs.
        self.startOrder = self.devs.keys()
        for devName in self.tasks:
            self.tasks[devName].configure(self.tasks, self.startOrder)

        if 'leadTime' in self.cfg:
            time.sleep(self.cfg['leadTime'])

        self.result = None
        
        ## Start tasks in specific order
        for devName in self.startOrder:
            self.tasks[devName].start()
        self.startTime = ptime.time()
        #print "  %d Task started" % self.id
            
        if not block:
            #print "  %d Not blocking; execute complete" % self.id
            return
        
        ## Wait until all tasks are done
        while not self.isDone():
            time.sleep(10e-6)
        
        self.stop()
        #print "  %d execute complete" % self.id
        ## Store data if requested
        #if 'storeData' in self.cfg and self.cfg['storeData'] is True:
            #for t in self.tasks:
                #self.tasks[t].storeResult(self.cfg['storageDir'])
        
        
    def isDone(self):
        t = ptime.time()
        if t - self.startTime < self.cfg['duration']:
            return False
        for t in self.tasks:
            if not self.tasks[t].isDone():
                return False
        return True
        
    def stop(self):
        self.getResult()
        return
        
    #def stop(self):
        #if self.stopped:
            #return
        ### Stop all tasks
        #for t in self.tasks:
            #self.tasks[t].stop()
        #self.stopped = True
            
        #self.getResult()
            
        ### Release all hardware for use elsewhere
        #for t in self.tasks:
            #self.tasks[t].release()
            #print "  %d released" % self.id, t
        
    def getResult(self):
        if not self.isDone():
            raise Exception("Cannot get result; task is still running.")
        
        if not self.stopped:
            ## Stop all tasks
            for t in self.tasks:
                self.tasks[t].stop()
            self.stopped = True
        
        if self.result is None:
            ## Let each device generate its own output structure.
            result = {}
            for devName in self.tasks:
                result[devName] = self.tasks[devName].getResult()
            self.result = result
            
        ## Release all hardware for use elsewhere
        if self.reserved:
            for t in self.tasks:
                #print "  %d releasing" % self.id, t
                self.tasks[t].release()
                #print "  %d released" % self.id, t
        self.reserved = False
            
        return self.result


def getManager():
    if Manager.single is None:
        raise Exception("No manager created yet")
    return Manager.single