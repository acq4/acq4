# -*- coding: utf-8 -*-
"""
Manager.py -  Defines main Manager class for ACQ4
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This class must be invoked once to initialize the ACQ4 core system.
The class is responsible for:
    - Configuring devices
    - Invoking/managing modules
    - Creating and executing acquisition tasks. 
"""


import os, sys, gc

## install global exception handler for others to hook into.
import acq4.pyqtgraph.exceptionHandling as exceptionHandling   
exceptionHandling.setTracebackClearing(True)

import time, atexit, weakref
from acq4.pyqtgraph.Qt import QtCore, QtGui
import acq4.util.reload as reload

from .util import DataManager, ptime, configfile
from .Interfaces import *
from .util.Mutex import Mutex
from .util.debug import *
import getopt, glob
from collections import OrderedDict
import acq4.pyqtgraph as pg
from .LogWindow import LogWindow
from .util.HelpfulException import HelpfulException




LOG = None

### All other modules can use this function to get the manager instance
def getManager():
    if Manager.single is None:
        raise Exception("No manager created yet")
    return Manager.single

def __reload__(old):
    Manager.CREATED = old['Manager'].CREATED
    Manager.single = old['Manager'].single
    
def logMsg(msg, **kwargs):
    """msg: the text of the log message
       msgTypes: user, status, error, warning (status is default)
       importance: 0-9 (0 is low importance, 9 is high, 5 is default)
       other supported keywords:
          exception: a tuple (type, exception, traceback) as returned by sys.exc_info()
          docs: a list of strings where documentation related to the message can be found
          reasons: a list of reasons (as strings) for the message
          traceback: a list of formatted callstack/trackback objects (formatting a traceback/callstack returns a list of strings), usually looks like [['line 1', 'line 2', 'line3'], ['line1', 'line2']]
       Feel free to add your own keyword arguments. These will be saved in the log.txt file, but will not affect the content or way that messages are displayed.
        """
    global LOG
    if LOG is not None:
        try:
            LOG.logMsg(msg, **kwargs)
        except:
            print "Error logging message:"
            print "    " + "\n    ".join(msg.split("\n"))
            print "    " + str(kwargs)
            sys.excepthook(*sys.exc_info())
    else:
        print "Can't log message; no log created yet."
        #print args
        print kwargs
        
    
def logExc(msg, *args, **kwargs):
    """Calls logMsg, but adds in the current exception and callstack. Must be called within an except block, and should only be called if the exception is not re-raised. Unhandled exceptions, or exceptions that reach the top of the callstack are automatically logged, so logging an exception that will be re-raised can cause the exception to be logged twice. Takes the same arguments as logMsg."""
    global LOG
    if LOG is not None:
        try:
            LOG.logExc(msg, *args, **kwargs)
        except:
            print "Error logging exception:"
            print "    " + "\n    ".join(msg.split("\n"))
            print "    " + str(kwargs)
            sys.excepthook(*sys.exc_info())
    else:
        print "Can't log error message; no log created yet."
        print args
        print kwargs

blockLogging = False
def exceptionCallback(*args):
    ## Called whenever there is an unhandled exception.
    
    ## unhandled exceptions generate an error message by default, but this
    ## can be overridden by raising HelpfulException(msgType='...')
    global blockLogging
    if not blockLogging:  ## if an error occurs *while* trying to log another exception, disable any further logging to prevent recursion.
        try:
            blockLogging = True
            logMsg("Unexpected error: ", exception=args, msgType='error')
        except:
            print "Error: Exception could no be logged."
            original_excepthook(*sys.exc_info())
        finally:
            blockLogging = False
exceptionHandling.register(exceptionCallback)        




class Manager(QtCore.QObject):
    """Manager class is responsible for:
      - Loading/configuring device modules and storing their handles
      - Managing the device rack GUI
      - Creating acquisition task handles
      - Loading gui modules and storing their handles
      - Creating and managing DirectoryHandle objects
      - Providing unified timestamps
      - Making sure all devices/modules are properly shut down at the end of the program"""
      
    sigConfigChanged = QtCore.Signal()
    sigModulesChanged = QtCore.Signal() 
    sigModuleHasQuit = QtCore.Signal(object) ## (module name)
    sigCurrentDirChanged = QtCore.Signal(object, object, object) # (file, change, args)
    sigBaseDirChanged = QtCore.Signal()
    sigLogDirChanged = QtCore.Signal(object) #dir
    sigTaskCreated = QtCore.Signal(object, object)  ## for debugger module
    
    CREATED = False
    single = None
    
    def __init__(self, configFile=None, argv=None):
        self.lock = Mutex(recursive=True)  ## used for keeping some basic methods thread-safe
        self.devices = OrderedDict()
        self.modules = OrderedDict()
        self.config = OrderedDict()
        self.definedModules = OrderedDict()
        self.currentDir = None
        self.baseDir = None
        self.gui = None
        self.shortcuts = []
        self.disableDevs = []
        self.disableAllDevs = False
        self.alreadyQuit = False
        self.taskLock = Mutex(QtCore.QMutex.Recursive)
        
        try:
            if Manager.CREATED:
                raise Exception("Manager object already created!")
            
            global LOG
            LOG = LogWindow(self)
            self.logWindow = LOG
            
            self.documentation = Documentation()
            
            if argv is not None:
                try:
                    opts, args = getopt.getopt(argv, 'c:a:m:b:s:d:nD', ['config=', 'config-name=', 'module=', 'base-dir=', 'storage-dir=', 'disable=', 'no-manager', 'disable-all'])
                except getopt.GetoptError, err:
                    print str(err)
                    print """
    Valid options are:
        -c --config=       Configuration file to load
        -a --config-name=  Named configuration to load
        -m --module=       Module name to load
        -b --base-dir=     Base directory to use
        -s --storage-dir=  Storage directory to use
        -n --no-manager    Do not load manager module
        -d --disable=      Disable the device specified
        -D --disable-all   Disable all devices
    """
                    raise
            
            
            QtCore.QObject.__init__(self)
            atexit.register(self.quit)
            self.interfaceDir = InterfaceDirectory()
    
            
            ## Handle command line options
            loadModules = []
            setBaseDir = None
            setStorageDir = None
            loadManager = True
            loadConfigs = []
            for o, a in opts:
                if o in ['-c', '--config']:
                    configFile = a
                elif o in ['-a', '--config-name']:
                    loadConfigs.append(a)
                elif o in ['-m', '--module']:
                    loadModules.append(a)
                elif o in ['-b', '--baseDir']:
                    setBaseDir = a
                elif o in ['-s', '--storageDir']:
                    setStorageDir = a
                elif o in ['-n', '--noManager']:
                    loadManager = False
                elif o in ['-d', '--disable']:
                    self.disableDevs.append(a)
                elif o in ['-D', '--disable-all']:
                    self.disableAllDevs = True
                else:
                    print "Unhandled option", o, a
            
            ## Read in configuration file
            if configFile is None:
                configFile = self._getConfigFile()
            
            self.configDir = os.path.dirname(configFile)
            self.readConfig(configFile)
            
            logMsg('ACQ4 started.', importance=9)
            
            Manager.CREATED = True
            Manager.single = self
            
            ## Act on options if they were specified..
            try:
                for name in loadConfigs:
                    self.loadDefinedConfig(name)
                        
                if setBaseDir is not None:
                    self.setBaseDir(setBaseDir)
                if setStorageDir is not None:
                    self.setCurrentDir(setStorageDir)
                if loadManager:
                    #mm = self.loadModule(module='Manager', name='Manager', config={})
                    self.showGUI()
                    self.createWindowShortcut('F1', self.gui.win)
                for m in loadModules:
                    try:
                        self.loadDefinedModule(m)
                    except:
                        if not loadManager:
                            self.showGUI()
                            #self.loadModule(module='Manager', name='Manager', config={})
                        raise
                        
            except:
                printExc("\nError while acting on command line options: (but continuing on anyway..)")
                
                
        except:
            printExc("Error while configuring Manager:")
        finally:
            if len(self.modules) == 0:
                self.quit()
                raise Exception("No modules loaded during startup, exiting now.")
            
        #win = QtGui.QApplication.instance().activeWindow()
        win = self.modules[self.modules.keys()[0]].window()
        #if win is None:   ## Breaks on some systems..
            #raise Exception("No GUI windows created during startup, exiting now.")
        #print "active window:", win
        self.quitShortcut = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+q'), win)
        self.quitShortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.reloadShortcut = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+r'), win)
        self.reloadShortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.quitShortcut.activated.connect(self.quit)
        self.reloadShortcut.activated.connect(self.reloadAll)
    
        
        #QtCore.QObject.connect(QtGui.QApplication.instance(), QtCore.SIGNAL('lastWindowClosed()'), self.lastWindowClosed)
            
    def _getConfigFile(self):
        ## search all the default locations to find a configuration file.
        from acq4 import CONFIGPATH
        for path in CONFIGPATH:
            cf = os.path.join(path, 'default.cfg')
            if os.path.isfile(cf):
                return cf
        raise Exception("Could not find config file in: %s" % CONFIGPATH)
    
    def _appDataDir(self):
        # return the user application data directory
        if sys.platform == 'win32':
            # resolves to "C:/Documents and Settings/User/Application Data/acq4" on XP
            # and "C:\User\Username\AppData\Roaming" on win7
            return os.path.join(os.environ['APPDATA'], 'acq4')
        elif sys.platform == 'darwin':
            return os.path.expanduser('~/Library/Preferences/acq4')
        else:
            return os.path.expanduser('~/.local/acq4')

            
    def readConfig(self, configFile):
        """Read configuration file, create device objects, add devices to list"""
        print "============= Starting Manager configuration from %s =================" % configFile
        logMsg("Starting Manager configuration from %s" % configFile)
        cfg = configfile.readConfigFile(configFile)
            
        ## read modules, devices, and stylesheet out of config
        self.configure(cfg)

        self.configFile = configFile
        print "\n============= Manager configuration complete =================\n"
        logMsg('Manager configuration complete.')
        
    def configure(self, cfg):
        """Load the devices, modules, stylesheet, and storageDir defined in cfg"""
        
        for key in cfg:
            try:
                ## configure new devices
                if key == 'devices':
                    for k in cfg['devices']:
                        if self.disableAllDevs or k in self.disableDevs:
                            print "    --> Ignoring device '%s' -- disabled by request" % k
                            logMsg("    --> Ignoring device '%s' -- disabled by request" % k)
                            continue
                        print "  === Configuring device '%s' ===" % k
                        logMsg("  === Configuring device '%s' ===" % k)
                        try:
                            conf = None
                            if cfg['devices'][k].has_key('config'):
                                conf = cfg['devices'][k]['config']
                            driverName = cfg['devices'][k]['driver']
                            self.loadDevice(driverName, conf, k)
                        except:
                            printExc("Error configuring device %s:" % k)
                    print "=== Device configuration complete ==="
                    logMsg("=== Device configuration complete ===")
                            
                ## Copy in new module definitions
                elif key == 'modules':
                    for m in cfg['modules']:
                        self.definedModules[m] = cfg['modules'][m]
                        
                ## set new storage directory
                elif key == 'storageDir':
                    print "=== Setting base directory: %s ===" % cfg['storageDir']
                    logMsg("=== Setting base directory: %s ===" % cfg['storageDir'])
                    self.setBaseDir(cfg['storageDir'])
                
                ## load stylesheet
                elif key == 'stylesheet':
                    try:
                        css = open(os.path.join(self.configDir, cfg['stylesheet'])).read()
                        QtGui.QApplication.instance().setStyleSheet(css)
                    except:
                        raise
                
                elif key == 'disableErrorPopups':
                    if cfg[key] is True:
                        self.logWindow.disablePopups(True)
                    elif cfg[key] is False:
                        self.logWindow.disablePopups(False)
                    else:
                        print "Warning: ignored config option 'disableErrorPopups'; value must be either True or False." 
                    
                elif key == 'defaultMouseMode':
                    mode = cfg[key].lower()
                    if mode == 'onebutton':
                        pg.setConfigOption('leftButtonPan', False)
                    elif mode == 'threebutton':
                        pg.setConfigOption('leftButtonPan', True)
                    else:
                        print "Warning: ignored config option 'defaultMouseMode'; value must be either 'oneButton' or 'threeButton'." 
                elif key == 'useOpenGL':
                    pg.setConfigOption('useOpenGL', cfg[key])
                    
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
                
            except:
                printExc("Error in ACQ4 configuration:")
        #print self.config
        self.sigConfigChanged.emit()

    def listConfigurations(self):
        """Return a list of the named configurations available"""
        with self.lock:
            if 'configurations' in self.config:
                return self.config['configurations'].keys()
            else:
                return []

    def loadDefinedConfig(self, name):
        with self.lock:
            if name not in self.config['configurations']:
                raise Exception("Could not find configuration named '%s'" % name)
            cfg = self.config['configurations'].get(name, )
        self.configure(cfg)

    #def __del__(self):
        #self.quit()
    
    def readConfigFile(self, fileName, missingOk=True):
        with self.lock:
            fileName = self.configFileName(fileName)
            if os.path.isfile(fileName):
                return configfile.readConfigFile(fileName)
            else:
                if missingOk: 
                    return {}
                else:
                    raise Exception('Config file "%s" not found.' % fileName)
            
    def writeConfigFile(self, data, fileName):
        """Write a file into the currently used config directory."""
        with self.lock:
            fileName = self.configFileName(fileName)
            dirName = os.path.dirname(fileName)
            if not os.path.exists(dirName):
                os.makedirs(dirName)
            return configfile.writeConfigFile(data, fileName)
    
    def appendConfigFile(self, data, fileName):
        with self.lock:
            fileName = self.configFileName(fileName)
            if os.path.exists(fileName):
                return configfile.appendConfigFile(data, fileName)
            else:
                raise Exception("Could not find file %s" % fileName)
        
        
    def configFileName(self, name):
        with self.lock:
            return os.path.join(self.configDir, name)
    
    def loadDevice(self, driverName, conf, name):
        """Load the code for a device. For this to work properly, there must be 
        a python module called acq4.devices.driverName which contains a class called driverName."""
        mod = __import__('acq4.devices.%s' % driverName, fromlist=['*'])
        devclass = getattr(mod, driverName)
        dev = devclass(self, conf, name)
        with self.lock:
            self.devices[name] = dev
        return dev
    
    def getDevice(self, name):
        with self.lock:
            name = str(name)
            if name not in self.devices:
                #print self.devices
                raise Exception("No device named %s. Options are %s" % (name, str(self.devices.keys())))
            return self.devices[name]

    def listDevices(self):
        with self.lock:
            return self.devices.keys()

    def loadModule(self, module, name, config=None, forceReload=False):
        """Create a new instance of an acq4 module. For this to work properly, there must be 
        a python module called acq4.modules.moduleName which contains a class called moduleName.
        Ugh. Sorry about the "python module" vs "acq4 module" name collision which I
        should have anticipated."""
        
        print 'Loading module "%s" as "%s"...' % (module, name)
        with self.lock:
            if name in self.modules:
                raise Exception('Module already exists with name "%s"' % name)
            if config is None:
                config = {}
        
        #print "  import"
        mod = __import__('acq4.modules.%s' % module, fromlist=['*'])
        #if forceReload:
            ### Reload all .py files in module's directory
            #modDir = os.path.join('lib', 'modules', module)
            #files = glob.glob(os.path.join(modDir, '*.py'))
            #files = [os.path.basename(f[:-3]) for f in files]
            #for f in [module, '__init__']:
                #if f in files:  ## try to rearrange so we load in correct order
                    #files.remove('__init__')
                    #files.append('__init__')
            #modName = 'acq4.modules.' + module
            #modNames = [modName + '.' + m for m in files] + [modName]
            #print "RELOAD", modNames
            #for m in modNames:
                #if m in sys.modules:
                    #reload(sys.modules[m])
            #mod = __import__('acq4.modules.%s' % module, fromlist=['*'])
            
        modclass = getattr(mod, module)
        #print "  create"
        mod = modclass(self, name, config)
        #print "  emit"
        with self.lock:
            self.modules[name] = mod
            
        self.sigModulesChanged.emit()
        #print "  return"
        return mod
        
        
    def listModules(self):
        """List names of currently loaded modules. """
        with self.lock:
            return self.modules.keys()[:]

    def getDirOfSelectedFile(self):
        """Returns the directory that is currently selected, or the directory of the file that is currently selected in Data Manager."""
        with self.lock:
            try:
                f = self.getModule("Data Manager").selectedFile()
                if not isinstance(f, DataManager.DirHandle):
                    f = f.parent()
            except Exception:
                f = False
                logMsg("Can't find currently selected directory, Data Manager has not been loaded.", msgType='warning')
            return f

    def getModule(self, name):
        """Return an already loaded module"""
        with self.lock:
            name = str(name)
            if name not in self.modules:
                raise Exception("No module named %s" % name)
            return self.modules[name]
        
    def getCurrentDatabase(self):
        """Return the database currently selected in the Data Manager"""
        return self.getModule("Data Manager").currentDatabase()

        
    def listDefinedModules(self):
        """List module configurations defined in the config file"""
        with self.lock:
            return self.definedModules.keys()


    def loadDefinedModule(self, name, forceReload=False):
        """Load a module and configure as defined in the config file"""
        with self.lock:
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
        
        with self.lock:
            if mod.name in self.modules:
                del self.modules[mod.name]
                self.interfaceDir.removeObject(mod)
            else:
                return
        self.removeWindowShortcut(mod.window())
        self.sigModulesChanged.emit()
        self.sigModuleHasQuit.emit(mod.name)
        #print "Module", mod.name, "has quit"



    def unloadModule(self, name):
        try:
            #print "    request quit.."
            self.getModule(name).quit()
            #print "    request quit done"
        except:
            printExc("Error while requesting module '%s' quit." % name)
            
        ## Module should have called moduleHasQuit already, but just in case:
        with self.lock:
            if name in self.modules:
                del self.modules[name]
            else:
                return
        self.sigModulesChanged.emit()
        #print "Unloaded module", name

    def reloadAll(self):
        """Reload all python code"""
        path = os.path.split(os.path.abspath(__file__))[0]
        path = os.path.abspath(os.path.join(path, '..'))
        print "\n---- Reloading all libraries under %s ----" % path
        reload.reloadAll(prefix=path, debug=True)
        print "Done reloading.\n"
        logMsg("Reloaded all libraries under %s." %path, msgType='status')
        

    def createWindowShortcut(self, keys, win):
        ## Note: this is probably not safe to call from other threads.
        try:
            sh = QtGui.QShortcut(QtGui.QKeySequence(keys), win)
            sh.setContext(QtCore.Qt.ApplicationShortcut)
            sh.activated.connect(lambda *args: win.raise_)
        except:
            printExc("Error creating shortcut '%s':" % keys)
        
        with self.lock:
            self.shortcuts.append((sh, keys, weakref.ref(win)))
            
    def removeWindowShortcut(self, win):
        ## Need to remove shortcuts after window is closed, because the shortcut is hanging on to all the widgets in the window
        ind = None
        for i, s in enumerate(self.shortcuts):
            if s[2]() == win:
                ind = i
                break
        
        if ind is not None:
            with self.lock:
                self.shortcuts.pop(ind)
    
    def runTask(self, cmd):
        """
        Convenience function that runs a task and returns its results.
        """
        t = Task(self, cmd)
        t.execute()
        return t.getResult()

    def createTask(self, cmd):
        """
        Creates a new Task instance from the specified command structure.
        """
        t = Task(self, cmd)
        self.sigTaskCreated.emit(cmd, t)
        return t

    def showGUI(self):
        """Show the Manager GUI"""
        if self.gui is None:
            self.gui = self.loadModule('Manager', 'Manager', {})
        self.gui.show()
    
    
    def getCurrentDir(self):
        """
        Return a directory handle to the currently-selected directory for data storage.
        """
        with self.lock:
            if self.currentDir is None:
                raise HelpfulException("Storage directory has not been set.", docs=["userGuide/modules/DataManager.html#acquired-data-storage"])
            return self.currentDir
    
    def setLogDir(self, d):
        """
        Set the directory to which log messages are stored.
        """
        self.logWindow.setLogDir(d)
        
    def setCurrentDir(self, d):
        """
        Set the currently-selected directory for data storage.
        """
        if self.currentDir is not None:
            try:
                self.currentDir.sigChanged.disconnect(self.currentDirChanged)
            except TypeError:
                pass
            
            
        if isinstance(d, basestring):
            self.currentDir = self.baseDir.getDir(d, create=True)
        elif isinstance(d, DataManager.DirHandle):
            self.currentDir = d
        else:
            raise Exception("Invalid argument type: ", type(d), d)
        
        p = d
        ## Storage directory is about to change; 
        logDir = self.logWindow.getLogDir()
        while not p.info().get('expUnit', False) and p != self.baseDir and p != logDir:
            p = p.parent()
        if p != self.baseDir and p != logDir:
            self.setLogDir(p)
        else:
            if logDir is None:
                logMsg("No log directory set. Log messages will not be stored.", msgType='warning', importance=8, docs=["userGuide/dataManagement.html#notes-and-logs"])
        #self.currentDir.sigChanged.connect(self.currentDirChanged)
        #self.sigCurrentDirChanged.emit()
        self.currentDir.sigChanged.connect(self.currentDirChanged)
        #self.emit(QtCore.SIGNAL('currentDirChanged'))
        self.sigCurrentDirChanged.emit(None, None, None)

    def currentDirChanged(self, fh, change=None, args=()):
        """Handle situation where currentDir is moved or renamed"""
        #self.sigCurrentDirChanged.emit(*args)
        #self.emit(QtCore.SIGNAL('currentDirChanged'), fh, change, args)
        self.sigCurrentDirChanged.emit(fh, change, args)
            
            
    def getBaseDir(self):
        """
        Return a directory handle to the base directory for data storage. 

        This is the highest-level directory where acquired data may be stored. If 
        the base directory has not been set, return None.
        """
        with self.lock:
            return self.baseDir

    def setBaseDir(self, d):
        """
        Set the base directory for data storage. 
        """
        with self.lock:
            if isinstance(d, basestring):
                self.baseDir = self.dirHandle(d, create=False)
            elif isinstance(d, DataManager.DirHandle):
                self.baseDir = d
            else:
                raise Exception("Invalid argument type: ", type(d), d)
            # Nah--only create the index if we really need it. Otherwise we get .index files left everywhere.
            # if not self.baseDir.isManaged():
            #     self.baseDir.createIndex()

        #self.emit(QtCore.SIGNAL('baseDirChanged'))
        self.sigBaseDirChanged.emit()
        self.setCurrentDir(self.baseDir)

    def dirHandle(self, d, create=False):
        """Return a directory handle for the specified directory string."""
        #return self.dataManager.getDirHandle(d, create)
        return DataManager.getDirHandle(d, create=create)

    def fileHandle(self, d):
        """Return a file or directory handle for d"""
        #return self.dataManager.getHandle(d)
        return DataManager.getFileHandle(d)
        
    def lockReserv(self):
        """Lock the reservation system so that only one task may reserve its set of devices at a time.
        This prevents deadlocks where two tasks use the same two devices but reserve them in opposite order."""
        if self.taskLock.tryLock(10e3):
            return True
        else:
            raise Exception("Times out waiting for task reservation system")
        
    def unlockReserv(self):
        """Unlock reservation system"""
        self.taskLock.unlock()
        
    #def logMsg(self, msg, tags=None):
        #if tags is None:
            #tags = {}
        #cd = self.getCurrentDir()
        #cd.logMsg(msg, tags)
        
    #def logMsg(self, *args, **kwargs):
        #self.logWindow.logMsg(*args, currentDir=self.currentDir, **kwargs)
        
    #def logExc(self, *args, **kwargs):
        #self.logWindow.logExc(*args, currentDir=self.currentDir, **kwargs)
        
    def showLogWindow(self):
        self.logWindow.show()
        
    ## These functions just wrap the functionality of an InterfaceDirectory
    def declareInterface(self, *args, **kargs):  ## args should be name, [types..], object  
        with self.lock:
            return self.interfaceDir.declareInterface(*args, **kargs)
        
    def removeInterface(self, *args, **kargs):
        with self.lock:
            return self.interfaceDir.removeInterface(*args, **kargs)
        
    def listInterfaces(self, *args, **kargs):
        with self.lock:
            return self.interfaceDir.listInterfaces(*args, **kargs)
        
    def getInterface(self, *args, **kargs):
        with self.lock:
            return self.interfaceDir.getInterface(*args, **kargs)
        
    
    def suggestedDirFields(self, file):
        """Given a DirHandle with a dirType, suggest a set of meta-info fields to use."""
        with self.lock:
            fields = OrderedDict()
            if isinstance(file, DataManager.DirHandle):
                info = file.info()
                if 'dirType' in info:
                    #infoKeys.remove('dirType')
                    dt = info['dirType']
                    if dt in self.config['folderTypes']:
                        fields = self.config['folderTypes'][dt]['info']
        
        if 'notes' not in fields:
            fields['notes'] = 'text', 5
        if 'important' not in fields:
            fields['important'] = 'bool'
        
        return fields
        
    def showDocumentation(self, label=None):
        self.documentation.show(label)
        
        
    def quit(self):
        """Nicely request that all devices and modules shut down"""
        #app = QtGui.QApplication.instance()
        #def q():
            #print "all windows closed"
        #QtCore.QObject.connect(app, QtCore.SIGNAL('lastWindowClosed()'), q)
        if not self.alreadyQuit:  ## Need this because multiple triggers can call this function during quit
            self.alreadyQuit = True
            lm = len(self.modules)
            ld = len(self.devices)
            with pg.ProgressDialog("Shutting down..", 0, lm+ld, cancelText=None, wait=0) as dlg:
                self.documentation.quit()
                print "Requesting all modules shut down.."
                logMsg("Shutting Down.", importance=9)
                while len(self.modules) > 0:  ## Modules may disappear from self.modules as we ask them to quit
                    m = self.modules.keys()[0]
                    print "    %s" % m
                    
                    self.unloadModule(m)
                    #print "Unloaded mod %s, modules left:" % m
                    #try:
                        #self.modules[m].quit()
                    #except:
                        #printExc("Error while requesting module '%s' quit." % m)
                    #if m in self.modules:
                        #del self.modules[m]
                    dlg.setValue(lm-len(self.modules))
                #pdb.set_trace()
                    
                print "Requesting all devices shut down.."
                for d in self.devices:
                    print "    %s" % d
                    try:
                        self.devices[d].quit()
                    except:
                        printExc("Error while requesting device '%s' quit." % d)
                    #print "  done."
                    dlg.setValue(lm+ld-len(self.devices))
                    
                    
                print "Closing windows.."
                QtGui.QApplication.instance().closeAllWindows()
                QtGui.QApplication.instance().processEvents()
            #print "  done."
            print "\n    ciao."
        QtGui.QApplication.quit()
        pg.exit()  # pg.exit() causes python to exit before Qt has a chance to clean up. 
                   # this avoids otherwise irritating exit crashes.

class Task:
    id = 0
    
    
    def __init__(self, dm, command):
        self.dm = dm
        self.command = command
        self.result = None
        
        self.lockedDevs = []
        self.startedDevs = []
        self.startTime = None
        self.stopTime = None
        
        #self.reserved = False
        try:
            self.cfg = command['protocol']
        except:
            print "================== Manager Task.__init__ command: ================="
            print command
            print "==========================================================="
            raise Exception("Command specified for task is invalid. (Must be dictionary with 'protocol' key)")
        self.id = Task.id
        Task.id += 1
        
        ## TODO:  set up data storage with cfg['storeData'] and ['writeLocation']
        #print "Task command", command
        self.devNames = command.keys()
        self.devNames.remove('protocol')
        self.devs = {devName: self.dm.getDevice(devName) for devName in self.devNames}
        
        #self.configDeps = {devName: set() for devName in self.devNames}
        #self.configCosts = {}
        #self.startDeps = {devName: set() for devName in self.devNames}
        #self.startCosts = {}
        
        ## Create task objects. Each task object is a handle to the device which is unique for this task run.
        self.tasks = {}
        #print "devNames: ", self.devNames
        
        for devName in self.devNames:
            task = self.devs[devName].createTask(self.command[devName], self)
            if task is None:
                printExc("Device '%s' does not have a task interface; ignoring." % devName)
                continue
            self.tasks[devName] = task

    #def addConfigDependency(self, task, before=None, after=None, cost=None):
        #"""
        #Declare that *task* must be configured before or after other devices.
        #Arguments *before* and *after* may be either Devices or their names.
        #"""
        #task = task.name() if isinstance(task, Device) else task
        #dep = [d.name() if isinstance(d, Device) else d for d in dep]
        #self.configDeps[task].extend(*dep)
        
    @staticmethod
    def getDevName(obj):
        if isinstance(obj, basestring):
            return obj
        elif isinstance(obj, Device):
            return obj.name()
        elif isinstance(obj, DeviceTask):
            return obj.dev.name()
            
    def getConfigOrder(self):
        ## determine the order in which tasks must be configured
        ## This is determined by tasks having called Task.addConfigDependency()
        ## when they were initialized.
            
        # request config order dependencies from devices
        deps = {devName: set() for devName in self.devNames}
        for devName, task in self.tasks.items():
            before, after = task.getConfigOrder()
            deps[devName] |= set(map(Task.getDevName, before))
            for t in map(self.getDevName, after):
                deps[t].add(devName)
                
        # request estimated configure time
        cost = {devName: self.tasks[devName].getPrepTimeEstimate() for devName in self.devNames}
        
        # convert sets to lists
        deps = dict([(k, list(deps[k])) for k in deps.keys()])
        
        # for testing, randomize the key order and ensure all devices are still started in the correct order
        #keys = deps.keys()
        #import random
        #random.shuffle(keys)
        #deps = OrderedDict([(k, deps[k]) for k in keys])
        
        #return sorted order
        order = self.toposort(deps, cost)
        #print "Config Order:"
        #print "    deps:", deps
        #print "    cost:", cost
        #print "    order:", order
        return order
        
    def getStartOrder(self):
        ## determine the order in which tasks must be started
        ## This is determined by tasks having called Task.addStartDependency()
        ## when they were initialized.
        deps = {devName: set() for devName in self.devNames}
        for devName, task in self.tasks.items():
            before, after = task.getStartOrder()
            deps[devName] |= set(map(Task.getDevName, before))
            for t in map(self.getDevName, after):
                deps[t].add(devName)
                
        deps = dict([(k, list(deps[k])) for k in deps.keys()])
        
        # for testing, randomize the key order and ensure all devices are still started in the correct order
        #keys = deps.keys()
        #import random
        #random.shuffle(keys)
        #deps = OrderedDict([(k, deps[k]) for k in keys])
        
        #return sorted order
        #print "Start Order:"
        #print "    deps:", deps
        order = self.toposort(deps)
        #print "    order:", order
        return order
        
    def execute(self, block=True, processEvents=True):
        """Start the task.
        If block is true, then the function blocks until the task is complete.
        if processEvents is true, then Qt events are processed while waiting for the task to complete."""
        self.lockedDevs = []
        self.startedDevs = []
        self.stopped = False
        self.abortRequested = False
        #print "======  Executing task %d:" % self.id
        #print self.cfg
        #print "======================="
        
        ## We need to make sure devices are stopped and unlocked properly if anything goes wrong..
        from acq4.util.debug import Profiler
        prof = Profiler('Manager.Task.execute', disabled=True)
        try:
        
            #print self.id, "Task.execute:", self.tasks
            ## Reserve all hardware
            self.dm.lockReserv()
            try:
                for devName in self.tasks:
                    #print "  %d Task.execute: Reserving hardware" % self.id, devName
                    res = self.tasks[devName].reserve(block=True)
                    #if not res:
                        #print "Locked from:"
                        #for tb in self.tasks[devName].dev._lock_.tb:
                            #print "====="
                            #print tb
                        #raise Exception('Damn')
                    self.lockedDevs.append(devName)
                    #print "  %d Task.execute: reserved" % self.id, devName
                #self.reserved = True
            except:
                #print "  %d Task.execute: problem reserving hardware; will unreserve these:"%self.id, self.lockedDevs
                raise
            finally:
                self.dm.unlockReserv()
                
            prof.mark('reserve')

            ## Determine order of device configuration.
            configOrder = self.getConfigOrder()
                

            ## Configure all subtasks. Some devices may need access to other tasks, so we make all available here.
            ## This is how we allow multiple devices to communicate and decide how to operate together.
            ## Each task may modify the startOrder list to suit its needs.
            #print "Configuring subtasks.."
            for devName in configOrder:
                self.tasks[devName].configure()
                prof.mark('configure %s' % devName)
                
            startOrder = self.getStartOrder()
            #print "done"

            if 'leadTime' in self.cfg:
                time.sleep(self.cfg['leadTime'])
                
            prof.mark('leadSleep')

            self.result = None
            
            
            
            ## Start tasks in specific order
            #print "Starting tasks.."
            for devName in startOrder:
                #print "  ", devName
                try:
                    self.startedDevs.append(devName)
                    self.tasks[devName].start()
                except:
                    self.startedDevs.remove(devName)
                    raise HelpfulException("Error starting device '%s'; aborting task." % devName)
                prof.mark('start %s' % devName)
            self.startTime = ptime.time()
            
                    
            
            #print "  %d Task started" % self.id
                
            if not block:
                prof.finish()
                #print "  %d Not blocking; execute complete" % self.id
                return
            
            ## Wait until all tasks are done
            #print "Waiting for all tasks to finish.."
            timeout = self.cfg.get('timeout', None)
            
            lastProcess = ptime.time()
            isGuiThread = QtCore.QThread.currentThread() == QtCore.QCoreApplication.instance().thread()
            #print "isGuiThread:", isGuiThread
            while not self.isDone():
                now = ptime.time()
                elapsed = now - self.startTime
                if timeout is not None and elapsed > timeout:
                    raise Exception("Task timed out (>%0.2fs); aborting." % timeout)
                if isGuiThread:
                    if processEvents and now-lastProcess > 20e-3:  ## only process Qt events every 20ms
                        QtGui.QApplication.processEvents()
                        lastProcess = ptime.time()
                    
                if elapsed < self.cfg['duration']-10e-3:  ## If the task duration has not elapsed yet, only wake up every 10ms, and attempt to wake up 5ms before the end
                    sleep = min(10e-3, self.cfg['duration']-elapsed-5e-3)
                else:
                    sleep = 1.0e-3  ## afterward, wake up more quickly so we can respond as soon as the task finishes
                #print "sleep for", sleep
                time.sleep(sleep)
            #print "all tasks finshed."
            
            self.stop()
            #print "  %d execute complete" % self.id
        except: 
            #printExc("==========  Error in task execution:  ==============")
            self.abort()
            self.releaseAll()
            raise
        finally:
            prof.finish()
        
        
    def isDone(self):
        #print "Manager.Task.isDone"
        if not self.abortRequested:
            t = ptime.time()
            if t - self.startTime < self.cfg['duration']:
                #print "  not done yet"
                return False
            #else:
                #print "  duration elapsed; start:", self.startTime, "now:", t, "diff:", t-self.startTime, 'duration:', self.cfg['duration']
        #else:
            #print "  aborted, checking tasks.."
        d = self.tasksDone()
        #print "  tasks say:", d
        return d
        
    def tasksDone(self):
        for t in self.tasks:
            if not self.tasks[t].isDone():
                #print "Task %s not finished" % t
                return False
        if self.stopTime is None:
            self.stopTime = ptime.time()
        return True
    
    def duration(self):
        """Return the requested task duration, or None if it was not given."""
        return self.command.get('protocol', {}).get('duration', None)
    
    def runTime(self):
        """Return the length of time since this task has been running.
        If the task has already finished, return the length of time the task ran for.
        If the task has not started yet, return None.
        """
        if self.startTime is None:
            return None
        if self.stopTime is None:
            return ptime.time() - self.startTime
        return self.stopTime - self.startTime
        
    def stop(self, abort=False):
        """Stop all tasks and read data. If abort is True, does not attempt to collect data from the run."""
        prof = Profiler("Manager.Task.stop", disabled=True)
        self.abortRequested = abort
        try:
            if not self.stopped:
                #print "stopping tasks.."
                ## Stop all tasks
                for t in self.startedDevs[:]:
                    #print "  stopping", t
                    ## Force all tasks to stop immediately.
                    #print "Stopping task", t, "..."
                    try:
                        self.tasks[t].stop(abort=abort)
                        self.startedDevs.remove(t)
                    except:
                        printExc("Error while stopping task %s:" % t)
                    #print "   ..task", t, "stopped"
                    prof.mark("   ..task "+ t+ " stopped")
                self.stopped = True
            
            if not abort and not self.tasksDone():
                raise Exception("Cannot get result; task is still running.")
            
            if not abort and self.result is None:
                #print "Get results.."
                ## Let each device generate its own output structure.
                result = {'protocol': {'startTime': self.startTime}}
                for devName in self.tasks:
                    try:
                        result[devName] = self.tasks[devName].getResult()
                    except:
                        printExc( "Error getting result for task %s (will set result=None for this task):" % devName)
                        result[devName] = None
                    prof.mark("get result: "+devName)
                self.result = result
                #print "RESULT 1:", self.result
                
                ## Store data if requested
                if 'storeData' in self.cfg and self.cfg['storeData'] is True:
                    self.cfg['storageDir'].setInfo(result['protocol'])
                    for t in self.tasks:
                        self.tasks[t].storeResult(self.cfg['storageDir'])
                prof.mark("store data")
        finally:   ## Regardless of any other problems, at least make sure we release hardware for future use
            ## Release all hardware for use elsewhere
            if self.stopTime is None:
                self.stopTime = ptime.time()
            
            self.releaseAll()
            prof.mark("release all")
            prof.finish()
            
        if abort:
            gc.collect()  ## it is often the case that now is a good time to garbage-collect.
        #print "tasks:", self.tasks
        #print "RESULT:", self.result        
        
    def getResult(self):
        self.stop()
        return self.result

    def releaseAll(self):
        #if self.reserved:
        #print self.id,"Task.releaseAll:"
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

    @staticmethod
    def toposort(deps, cost=None):
        """Topological sort. Arguments are:
        deps       Dictionary describing dependencies where a:[b,c] means "a 
                    depends on b and c"
        cost       Optional dictionary of per-node cost values. This will be used
                    to sort independent graph branches by total cost. 
                
        Examples::

            # Sort the following graph:
            # 
            #   B ──┬─────> C <── D
            #       │       │       
            #   E <─┴─> A <─┘
            #     
            deps = {'a': ['b', 'c'], 'c': ['b', 'd'], 'e': ['b']}
            toposort(deps)
            => ['b', 'e', 'd', 'c', 'a']
            
            # This example is underspecified; there are several orders
            # that correctly satisfy the graph. However, we may use the
            # 'cost' argument to impose more constraints on the sort order.
            
            # Let each node have the following cost:
            cost = {'a': 0, 'b': 0, 'c': 1, 'e': 1, 'd': 3}
            
            # Then the total cost of following any node is its own cost plus
            # the cost of all nodes that follow it:
            #   A = cost[a]
            #   B = cost[b] + cost[c] + cost[e] + cost[a]
            #   C = cost[c] + cost[a]
            #   D = cost[d] + cost[c] + cost[a]
            #   E = cost[e]
            # If we sort independent branches such that the highest cost comes 
            # first, the output is:
            toposort(deps, cost=cost)
            => ['d', 'b', 'c', 'e', 'a']
        """
        # copy deps and make sure all nodes have a key in deps
        deps0 = deps
        deps = {}
        for k,v in deps0.items():
            deps[k] = v[:]
            for k2 in v:
                if k2 not in deps:
                    deps[k2] = []

        # Compute total branch cost for each node
        key = None
        if cost is not None:
            order = Task.toposort(deps)
            allDeps = {n: set(n) for n in order}
            for n in order[::-1]:
                for n2 in deps.get(n, []):
                    allDeps[n2] |= allDeps.get(n, set())
                    
            totalCost = {n: sum([cost.get(x, 0) for x in allDeps[n]]) for n in allDeps}
            key = lambda x: totalCost.get(x, 0)

        # compute weighted order
        order = []
        while len(deps) > 0:
            # find all nodes with no remaining dependencies
            ready = [k for k in deps if len(deps[k]) == 0]
            
            # If no nodes are ready, then there must be a cycle in the graph
            if len(ready) == 0:
                print deps
                raise Exception("Cannot resolve requested device configure/start order.")
            
            # sort by branch cost
            if key is not None:
                ready.sort(key=key, reverse=True)
            
            # add the highest-cost node to the order, then remove it from the
            # entire set of dependencies
            order.append(ready[0])
            del deps[ready[0]]
            for v in deps.values():
                try:
                    v.remove(ready[0])
                except ValueError:
                    pass
        
        return order
        

DOC_ROOT = 'http://acq4.org/documentation/'

class Documentation(QtCore.QObject):
    def __init__(self):
        QtCore.QObject.__init__(self)

    def show(self, label=None):
        if label is None:
            url = DOC_ROOT
        else:
            url = DOC_ROOT + label
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


    def quit(self):
        pass


class QtDocumentation(QtCore.QObject):
    """Encapsulates documentation functionality.

    Note: this class is currently out of service in favor of 
    referencing online documentation instead.
    """
    def __init__(self):
        QtCore.QObject.__init__(self)
        path = os.path.abspath(os.path.dirname(__file__))
        self.docFile = os.path.normpath(os.path.join(path, '..', 'documentation', 'build', 'qthelp', 'ACQ4.qhc'))

        self.process = QtCore.QProcess()
        self.process.finished.connect(self.processFinished)
        

    def show(self, label=None):
        if self.process.state() == self.process.NotRunning:
            self.startProcess()
            if label is not None:
                QtCore.QTimer.singleShot(2000, lambda: self.activateId(label))
                return
        if label is not None:
            self.activateId(label)
                

    def expandToc(self, n=2):
        self.write('expandToc %d\n' % n)
        
    def startProcess(self):
        self.process.start('assistant', ['-collectionFile', self.docFile, '-enableRemoteControl'])
        if not self.process.waitForStarted():
            output = str(self.process.readAllStandardError())
            raise Exception("Error starting documentation viewer:  " +output)
        QtCore.QTimer.singleShot(1000, self.expandToc)
        
    def activateId(self, id):
        print "activate:", id
        self.show()
        self.write('activateIdentifier %s\n' % id)
        
    def activateKeyword(self, kwd):
        self.show()
        self.write('activateKeyword %s\n' % kwd)
        
    def write(self, data):
        ba = QtCore.QByteArray(data)
        return self.process.write(ba)
        
    def quit(self):
        self.process.close()

    def processFinished(self):
        print "Doc viewer exited:", self.process.exitCode()
        print str(self.process.readAllStandardError())    
    
    
    