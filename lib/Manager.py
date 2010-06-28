# -*- coding: utf-8 -*-
"""
Manager.py -  Defines main Manager class for ACQ4
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This class must be invoked once to initialize the ACQ4 core system.
The class is responsible for:
    - Configuring devices
    - Invoking/managing modules
    - Creating and executing protocol tasks. 
"""


## Path adjustments:
##   - make sure 'lib' path is available for module search
##   - add util to front of search path. This allows us to override some libs 
##     that may be installed globally with local versions.
import sys
import os.path as osp
d = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path = [osp.join(d, 'lib', 'util')] + sys.path + [d]



import time, atexit, weakref
from PyQt4 import QtCore, QtGui
from DataManager import *
import lib.util.ptime as ptime
from lib.util import configfile
from lib.util.Mutex import Mutex
from lib.util.debug import *
import getopt, glob
import ptime
#import pdb

### All other modules can use this function to get the manager instance
def getManager():
    if Manager.single is None:
        raise Exception("No manager created yet")
    return Manager.single



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
    
    def __init__(self, configFile=None, argv=None):
        if Manager.CREATED:
            raise Exception("Manager object already created!")
        
        if argv is not None:
            try:
                opts, args = getopt.getopt(argv, 'c:m:b:s:n', ['config=', 'module=', 'baseDir=', 'storageDir=', 'noManager'])
            except getopt.GetoptError, err:
                print str(err)
                print """
Valid options are:
    -c --config=     configuration file
    -m --module=     module name to load
    -b --baseDir=    base directory to use
    -s --storageDir= storage directory to use
    -n --noManager   Do not load manager module
"""
        QtCore.QObject.__init__(self)
        self.alreadyQuit = False
        self.taskLock = Mutex(QtCore.QMutex.Recursive)
        atexit.register(self.quit)
        self.devices = {}
        self.modules = {}
        self.config = {}
        self.definedModules = {}
        #self.devRack = None
        self.dataManager = DataManager()
        self.currentDir = None
        self.baseDir = None
        self.interface = None
        self.shortcuts = []
        
        ## Handle command line options
        loadModules = []
        setBaseDir = None
        setStorageDir = None
        loadManager = True
        for o, a in opts:
            if o in ['-c', '--config']:
                configFile = a
            elif o in ['-m', '--module']:
                loadModules.append(a)
            elif o in ['-b', '--baseDir']:
                setBaseDir = a
            elif o in ['-s', '--storageDir']:
                setStorageDir = a
            elif o in ['-n', '--noManager']:
                loadManager = False
            else:
                print "Unhandled option", o, a
        
        ## Read in configuration file
        if configFile is None:
            raise Exception("No configuration file specified!")
        self.configDir = os.path.dirname(configFile)
        self.readConfig(configFile)
        
        
        Manager.CREATED = True
        Manager.single = self
        
        ## Act on options if they were specified..
        try:
            if setBaseDir is not None:
                self.setBaseDir(setBaseDir)
            if setStorageDir is not None:
                self.setCurrentDir(setStorageDir)
            if loadManager:
                mm = self.loadModule(module='Manager', name='Manager', config={})
                self.createWindowShortcut('F1', mm.win)
            for m in loadModules:
                try:
                    self.loadDefinedModule(m)
                except:
                    if not loadManager:
                        self.loadModule(module='Manager', name='Manager', config={})
                    raise
                    
        except:
            printExc("\nError while acting on command line options: (but continuing on anyway..)")
            
            
        win = QtGui.QApplication.instance().activeWindow()
        #if win is None:   ## Breaks on some systems..
            #raise Exception("No GUI windows created during startup, exiting now.")
        #print "active window:", win
        self.quitShortcut = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+q'), win)
        self.quitShortcut.setContext(QtCore.Qt.ApplicationShortcut)
        QtCore.QObject.connect(self.quitShortcut, QtCore.SIGNAL('activated()'), self.quit)
        
        QtCore.QObject.connect(QtGui.QApplication.instance(), QtCore.SIGNAL('lastWindowClosed()'), self.lastWindowClosed)
            
            
            

    def readConfig(self, configFile):
        """Read configuration file, create device objects, add devices to list"""
        print "============= Starting Manager configuration from %s =================" % configFile
        cfg = configfile.readConfigFile(configFile)
        #self.config = cfg
        
        #if not cfg.has_key('devices'):
            #raise Exception('configuration file %s has no "devices" section.' % configFile)
            
        ## read modules, devices, and stylesheet out of config
        self.configure(cfg)
        
        #if 'configurations' in cfg:
            #self.setCurrentDir('')
        #else:
            #raise Exception("No configuration found for data management!")
        print "\n============= Manager configuration complete =================\n"
        
    def configure(self, cfg):
        """Load the devices, modules, stylesheet, and storageDir defined in cfg"""
        
        ## configure new devices
        for key in cfg:
            if key == 'devices':
                for k in cfg['devices']:
                    print "\n=== Configuring device '%s' ===" % k
                    try:
                        conf = None
                        if cfg['devices'][k].has_key('config'):
                            conf = cfg['devices'][k]['config']
                        driverName = cfg['devices'][k]['driver']
                        self.loadDevice(driverName, conf, k)
                    except:
                        printExc("Error configuring device %s:" % k)
                        
            ## Copy in new module definitions
            elif key == 'modules':
                for m in cfg['modules']:
                    self.definedModules[m] = cfg['modules'][m]
                    
            ## set new storage directory
            elif key == 'storageDir':
                self.setBaseDir(cfg['storageDir'])
            
            ## load stylesheet
            elif key == 'stylesheet':
                try:
                    css = open(os.path.join(self.configDir, cfg['stylesheet'])).read()
                    QtGui.QApplication.instance().setStyleSheet(css)
                except:
                    raise
                
            ## Copy in any other configurations.
            ## dicts are extended, all others are overwritten.
            else:
                if isinstance(cfg[key], dict):
                    if key not in self.config:
                        self.config[key] = {}
                    for key2 in cfg[key]:
                        self.config[key][key2] = cfg[key][key2]
                else:
                    self.config[key] = cfg[key]
            
            ### set new protocol directory
            #if 'protocolDir' in cfg:
                #self.config['protocolDir'] = cfg['protocolDir']
                
            ### copy in new folder type definitions
            #if 'folderTypes' in cfg:
                #if 'folderTypes' not in self.config:
                    #self.config['folderTypes'] = {}
                #for t in cfg['folderTypes']:
                    #self.config['folderTypes'][t] = cfg['folderTypes'][t]
            
        #print self.config
        self.emit(QtCore.SIGNAL('configChanged'))

    def listConfigurations(self):
        """Return a list of the named configurations available"""
        if 'configurations' in self.config:
            return self.config['configurations'].keys()
        else:
            return []

    def loadDefinedConfig(self, name):
        if name in self.config['configurations']:
            self.configure(self.config['configurations'][name])
        else:
            raise Exception("Could not find configuration named '%s'" % name)

    def __del__(self):
        self.quit()
    
    def readConfigFile(self, fileName, missingOk=True):
        fileName = os.path.join(self.configDir, fileName)
        if os.path.isfile(fileName):
            return configfile.readConfigFile(fileName)
        else:
            if missingOk: 
                return {}
            else:
                raise Exception('Config file "%s" not found.' % fileName)
            
    def writeConfigFile(self, data, fileName):
        fileName = os.path.join(self.configDir, fileName)
        return configfile.writeConfigFile(data, fileName)
        
    
    def loadDevice(self, driverName, conf, name):
        """Load the code for a device. For this to work properly, there must be 
        a python module called lib.devices.driverName which contains a class called driverName."""
        mod = __import__('lib.devices.%s' % driverName, fromlist=['*'])
        devclass = getattr(mod, driverName)
        self.devices[name] = devclass(self, conf, name)
        return self.devices[name]
    
    def getDevice(self, name):
        name = str(name)
        if name not in self.devices:
            #print self.devices
            raise Exception("No device named %s. Options are %s" % (name, str(self.devices.keys())))
        return self.devices[name]

    def listDevices(self):
        return self.devices.keys()

    def loadModule(self, module, name, config=None, forceReload=False):
        """Create a new instance of an acq4 module. For this to work properly, there must be 
        a python module called lib.modules.moduleName which contains a class called moduleName.
        Ugh. Sorry about the "python module" vs "acq4 module" name collision which I
        should have anticipated."""
        
        #print 'Loading module "%s" as "%s"...' % (module, name)
        if name in self.modules:
            raise Exception('Module already exists with name "%s"' % name)
        if config is None:
            config = {}
            
        mod = __import__('lib.modules.%s' % module, fromlist=['*'])
        if forceReload:
            ## Reload all .py files in module's directory
            modDir = os.path.join('lib', 'modules', module)
            files = glob.glob(os.path.join(modDir, '*.py'))
            files = [os.path.basename(f[:-3]) for f in files]
            if '__init__' in files:  ## Move __init__ to the very end
                files.remove('__init__')
                files.append('__init__')
            modName = 'lib.modules.' + module
            modNames = [modName + '.' + m for m in files] + [modName]
            print "RELOAD", modNames
            for m in modNames:
                if m in sys.modules:
                    reload(sys.modules[m])
            mod = __import__('lib.modules.%s' % module, fromlist=['*'])
            
        modclass = getattr(mod, module)
        self.modules[name] = modclass(self, name, config)
        self.emit(QtCore.SIGNAL('modulesChanged'))
        return self.modules[name]
        
        
    def listModules(self):
        """List currently loaded modules. """
        return self.modules.keys()[:]


    def getModule(self, name):
        """Return an already loaded module"""
        name = str(name)
        if name not in self.modules:
            raise Exception("No module named %s" % name)
        return self.modules[name]

        
    def listDefinedModules(self):
        """List module configurations defined in the config file"""
        return self.definedModules.keys()


    def loadDefinedModule(self, name, forceReload=False):
        """Load a module and configure as defined in the config file"""
        if name not in self.definedModules:
            print "Module '%s' is not defined. Options are: %s" % (name, str(self.definedModules.keys()))
            return
        conf = self.definedModules[name]
        
        mod = conf['module']
        if 'config' in conf:
            config = conf['config']
        else:
            config = {}
            
        ## Find an unused name for this module
        mName = name
        n = 0
        while mName in self.modules:
            mName = "%s_%d" % (name, n)
            n += 1
            
        mod = self.loadModule(mod, mName, config, forceReload=forceReload)
        win = mod.window()
        if 'shortcut' in conf and win is not None:
            self.createWindowShortcut(conf['shortcut'], win)
        print "Loaded module '%s'" % mName

    
    def moduleHasQuit(self, mod):
        if mod.name in self.modules:
            del self.modules[mod.name]
            self.emit(QtCore.SIGNAL('modulesChanged'))
            self.emit(QtCore.SIGNAL('moduleHasQuit'), mod.name)
            print "Module", mod.name, "has quit"


    def unloadModule(self, name):
        try:
            print "    request quit.."
            self.getModule(name).quit()
            print "    request quit done"
        except:
            printExc("Error while requesting module '%s' quit." % name)
            
        ## Module should have called moduleHasQuit already, but just in case:
        if name in self.modules:
            del self.modules[name]
            self.emit(QtCore.SIGNAL('modulesChanged'))
        #print "Unloaded module", name

    def createWindowShortcut(self, keys, win):
        try:
            sh = QtGui.QShortcut(QtGui.QKeySequence(keys), win)
            sh.setContext(QtCore.Qt.ApplicationShortcut)
            QtCore.QObject.connect(sh, QtCore.SIGNAL('activated()'), win.raise_)
        except:
            printExc("Error creating shortcut '%s':" % keys)
        
        self.shortcuts.append((sh, keys, weakref.ref(win)))
    
    def runProtocol(self, cmd):
        t = Task(self, cmd)
        t.execute()
        return t.getResult()

    def createTask(self, cmd):
        return Task(self, cmd)

    def showInterface(self):
        if self.interface is None:
            self.interface = self.loadModule('Manager', 'Manager', {})
        self.interface.show()
    
    
    def getCurrentDir(self):
        if self.currentDir is None:
            raise Exception("CurrentDir has not been set!")
        return self.currentDir

    def setCurrentDir(self, d):
        if self.currentDir is not None:
            QtCore.QObject.disconnect(self.currentDir, QtCore.SIGNAL('changed'), self.currentDirChanged)
            
            
        if isinstance(d, basestring):
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
        if isinstance(d, basestring):
            self.baseDir = self.dirHandle(d, create=False)
        elif isinstance(d, DirHandle):
            self.baseDir = d
        else:
            raise Exception("Invalid argument type: ", type(d), d)
        if not self.baseDir.isManaged():
            self.baseDir.createIndex()

        self.emit(QtCore.SIGNAL('baseDirChanged'))
        self.setCurrentDir(self.baseDir)

    def dirHandle(self, d, create=False):
        """Return a directory handle for d."""
        return self.dataManager.getDirHandle(d, create)

    def fileHandle(self, d):
        """Return a file or directory handle for d"""
        return self.dataManager.getHandle(d)
        
    def lockReserv(self):
        """Lock the reservation system so that only one task may reserve its set of devices at a time.
        This prevents deadlocks where two protocols use the same two devices but reserve them in opposite order."""
        if self.taskLock.tryLock(10e3):
            return True
        else:
            raise Exception("Times out waiting for task reservation system")
        
    def unlockReserv(self):
        """Unlock reservation system"""
        self.taskLock.unlock()
        
    def logMsg(self, msg, tags=None):
        if tags is None:
            tags = {}
        cd = self.getCurrentDir()
        cd.logMsg(msg, tags)

    def quit(self):
        """Nicely request that all devices and modules shut down"""
        #app = QtGui.QApplication.instance()
        #def q():
            #print "all windows closed"
        #QtCore.QObject.connect(app, QtCore.SIGNAL('lastWindowClosed()'), q)
        if not self.alreadyQuit:  ## Need this because multiple triggers can call this function during quit
            self.alreadyQuit = True
            
            print "Requesting all modules shut down.."
            while len(self.modules) > 0:  ## Modules may disappear from self.modules as we ask them to quit
                m = self.modules.keys()[0]
                print "    %s" % m
                
                self.unloadModule(m)
                print "Unloaded mod %s, modules left:" % m
                #try:
                    #self.modules[m].quit()
                #except:
                    #printExc("Error while requesting module '%s' quit." % m)
                #if m in self.modules:
                    #del self.modules[m]
            #pdb.set_trace()
                
            print "Requesting all devices shut down.."
            for d in self.devices:
                print "    %s" % d
                try:
                    self.devices[d].quit()
                except:
                    printExc("Error while requesting device '%s' quit." % d)
                #print "  done."
                
            print "Closing windows.."
            QtGui.QApplication.instance().closeAllWindows()
            QtGui.QApplication.instance().processEvents()
            #print "  done."
            print "\n    ciao."
        #app= QtGui.QApplication.instance()
        #print app.topLevelWidgets()
        #for w in app.topLevelWidgets():
        #    print w, w.isVisible()
        #print "Manager quits when last window closes:", QtGui.QApplication.instance().quitOnLastWindowClosed()
        QtGui.QApplication.quit()

    #def lastWindowClosed(self):
        #print "QApplication reports last window has closed."

class Task:
    id = 0
    
    
    def __init__(self, dm, command):
        self.dm = dm
        self.command = command
        self.result = None
        
        self.lockedDevs = []
        self.startedDevs = []
        
        
        #self.reserved = False
        try:
            self.cfg = command['protocol']
        except:
            print "================== Manager Task.__init__ command: ================="
            print command
            print "==========================================================="
            raise Exception("Command specified for protocol is invalid. (Must be dictionary with 'protocol' key)")
        self.id = Task.id
        Task.id += 1
        
        ## TODO:  set up data storage with cfg['storeData'] and ['writeLocation']
        #print "Task command", command
        self.devNames = command.keys()
        self.devNames.remove('protocol')
        self.devs = {}
        
        ## Create task objects. Each task object is a handle to the device which is unique for this protocol run.
        self.tasks = {}
        for devName in self.devNames:
            dev = self.dm.getDevice(devName)
            task = dev.createTask(self.command[devName])
            if task is None:
                printExc("Device '%s' does not have a protocol interface; ignoring." % devName)
                continue
            self.devs[devName] = dev
            self.tasks[devName] = task
        
        
    def execute(self, block=True):
        self.lockedDevs = []
        self.startedDevs = []
        self.stopped = False
        #print "======  Executing task %d:" % self.id
        #print self.cfg
        #print "======================="
        
        ## We need to make sure devices are stopped and unlocked properly if anything goes wrong..
        #from debug import Profiler
        #prof = Profiler()
        
        try:
        
            #print "execute:", self.tasks
            ## Reserve all hardware
            self.dm.lockReserv()
            try:
                for devName in self.tasks:
                    #print "  %d Reserving hardware" % self.id, devName
                    self.tasks[devName].reserve()
                    self.lockedDevs.append(devName)
                    #print "  %d reserved" % self.id, devName
                #self.reserved = True
            finally:
                self.dm.unlockReserv()
                
            #prof.mark('reserve')

            ## Configure all subtasks. Some devices may need access to other tasks, so we make all available here.
            ## This is how we allow multiple devices to communicate and decide how to operate together.
            ## Each task may modify the startOrder list to suit its needs.
            #print "Configuring subtasks.."
            self.startOrder = self.devs.keys()
            for devName in self.tasks:
                self.tasks[devName].configure(self.tasks, self.startOrder)
                #prof.mark('configure %s' % devName)
            #print "done"

            if 'leadTime' in self.cfg:
                time.sleep(self.cfg['leadTime'])
                
            #prof.mark('leadSleep')

            self.result = None
            
            
            
            ## Start tasks in specific order
            #print "Starting tasks.."
            for devName in self.startOrder:
                #print "  ", devName
                self.tasks[devName].start()
                self.startedDevs.append(devName)
                #prof.mark('start %s' % devName)
            self.startTime = ptime.time()
            #print "  %d Task started" % self.id
                
            if not block:
                #print "  %d Not blocking; execute complete" % self.id
                return
            
            ## Wait until all tasks are done
            #print "Waiting for all tasks to finish.."
            while not self.isDone():
                time.sleep(1e-3)
            #print "all tasks finshed."
            
            self.stop()
            #print "  %d execute complete" % self.id
        except: 
            #printExc("==========  Error in protocol execution:  ==============")
            self.abort()
            self.releaseAll()
            raise
        
        
    def isDone(self):
        t = ptime.time()
        if t - self.startTime < self.cfg['duration']:
            return False
        d = self.tasksDone()
        #print "Is done:", d
        return d
        
    def tasksDone(self):
        for t in self.tasks:
            if not self.tasks[t].isDone():
                #print "Task %s not finished" % t
                return False
        return True
        
    def stop(self, abort=False):
        """Stop all tasks and read data. If abort is True, does not attempt to collect data from the run."""
        #prof = Profiler("Stop Task")
        try:
            if not self.stopped:
                #print "stopping tasks.."
                ## Stop all tasks
                for t in self.startedDevs[:]:
                    #print "  stopping", t
                    ## Force all tasks to stop immediately.
                    #print "Stopping task", t, "..."
                    try:
                        self.tasks[t].stop()
                        self.startedDevs.remove(t)
                    except:
                        printExc("Error while stopping task %s:" % t)
                    #print "   ..task", t, "stopped"
                    #prof.mark("   ..task "+ t+ " stopped")
                self.stopped = True
            
            if not abort and not self.tasksDone():
                raise Exception("Cannot get result; task is still running.")
            
            if not abort and self.result is None:
                #print "Get results.."
                ## Let each device generate its own output structure.
                result = {}
                for devName in self.tasks:
                    try:
                        result[devName] = self.tasks[devName].getResult()
                    except:
                        printExc( "Error getting result for task %s (will set result=None for this task):" % devName)
                        result[devName] = None
                    #prof.mark("get result: "+devName)
                self.result = result
                #print "RESULT 1:", self.result
                
                ## Store data if requested
                if 'storeData' in self.cfg and self.cfg['storeData'] is True:
                    for t in self.tasks:
                        self.tasks[t].storeResult(self.cfg['storageDir'])
                #prof.mark("store data")
        finally:   ## Regardless of any other problems, at least make sure we release hardware for future use
            ## Release all hardware for use elsewhere
            self.releaseAll()
            #prof.mark("release all")
            
        #print "tasks:", self.tasks
        #print "RESULT:", self.result        
        
    def getResult(self):
        self.stop()
        return self.result

    def releaseAll(self):
        #if self.reserved:
        #print "release hardware.."
        for t in self.lockedDevs[:]:
            #print "  %d releasing" % self.id, t
            try:
                self.tasks[t].release()
                self.lockedDevs.remove(t)
            except:
                printExc("Error while releasing hardware for task %s:" % t)
                
                #print "  %d released" % self.id, t
        #self.reserved = False

    def abort(self):
        """Stop all tasks, to not attempt to get data."""
        self.stop(abort=True)
        