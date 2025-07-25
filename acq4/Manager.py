import atexit
import gc
import getopt
import os
import sys
import time
import argparse
import weakref
import socket
import getpass
import threading
from collections import OrderedDict

import pyqtgraph as pg
import pyqtgraph.reload as reload
from pyqtgraph import configfile
from pyqtgraph.debug import printExc, Profiler
from pyqtgraph.util.mutex import Mutex
from . import __version__
from . import devices, modules
from .Interfaces import InterfaceDirectory
from .devices.Device import Device, DeviceTask
from .util import DataManager, ptime, Qt
from .util.DataManager import DirHandle
from .util.HelpfulException import HelpfulException
from .util.debug import logExc, logMsg, createLogWindow

_ = logExc  # prevent cleanup of logExc; needed by debug


def __reload__(old):
    Manager.CREATED = old['Manager'].CREATED
    Manager.single = old['Manager'].single


class Manager(Qt.QObject):
    """Manager class is responsible for:
      - Loading/configuring device modules and storing their handles
      - Managing the device rack GUI
      - Creating acquisition task handles
      - Loading gui modules and storing their handles
      - Creating and managing DirectoryHandle objects
      - Providing unified timestamps
      - Making sure all devices/modules are properly shut down at the end of the program"""

    sigConfigChanged = Qt.Signal()
    sigModulesChanged = Qt.Signal()
    sigModuleHasQuit = Qt.Signal(object)  ## (module name)
    sigCurrentDirChanged = Qt.Signal(object, object, object)  # (file, change, args)
    sigBaseDirChanged = Qt.Signal()
    sigLogDirChanged = Qt.Signal(object)  # dir
    sigTaskCreated = Qt.Signal(object, object)  ## for debugger module
    sigAbortAll = Qt.Signal()  # User requested abort all tasks via ESC key

    CREATED = False
    single = None

    @classmethod
    def makeArgParser(cls):
        parser = argparse.ArgumentParser(description="CQ4 control script")
        parser.add_argument("--config", "-c", help="Configuration file to load", default=cls._getConfigFile())
        parser.add_argument("--config-name", "-a", help="Named configuration to load", action="append")
        parser.add_argument("--module", "-m", help="Module name to load", action="append")
        parser.add_argument("--base-dir", "-b", help="Base directory to use")
        parser.add_argument("--storage-dir", "-s", help="Storage directory to use")
        parser.add_argument("--debug-logging", action="store_true", help="Whether to be extra noisy in printing")
        parser.add_argument("--disable", "-d", help="Disable the device specified", action="append")
        parser.add_argument("--disable-all", "-D", help="Disable all devices", action="store_true")
        parser.add_argument("--exit-on-error", "-x", help="Whether to exit immidiately on the first exception during initial Manager setup", action="store_true")
        parser.add_argument("--no-manager", "-n", help="Do not load manager module", action="store_true")
        return parser

    @classmethod
    def runFromCommandLine(self, args):
        """Run the Manager from the command line."""
        m = Manager()
        m.initFromCommandLine(args)
        return m

    def __init__(self, configFile=None):
        self.moduleLock = Mutex(recursive=True)  ## used for keeping some basic methods thread-safe
        # self.devices = OrderedDict()  # all currently loaded devices
        self.isReady = threading.Event()
        self.modules = OrderedDict()  # all currently running modules
        self.devices = OrderedDict()  # all devices loaded via Manager
        self.definedModules = OrderedDict()  # all custom-defined module configurations
        self.config = OrderedDict()
        self.currentDir = None
        self.baseDir = None
        self.exitOnError = False
        self.gui = None
        self.shortcuts = []
        self.disableDevs = []
        self.disableAllDevs = False
        self._debug = False
        self.alreadyQuit = False
        self.taskLock = Mutex(Qt.QMutex.Recursive)
        self._folderTypes = None

        try:
            if Manager.CREATED:
                raise Exception("Manager object already created!")

            Manager.CREATED = True
            Manager.single = self
            self.logWindow = createLogWindow(self)
            self.documentation = Documentation()

            Qt.QObject.__init__(self)
            atexit.register(self.quit)
            self.interfaceDir = InterfaceDirectory()

            # Import all built-in module classes
            modules.importBuiltinClasses()

            logMsg('ACQ4 version %s started.' % __version__, importance=9)

        except:
            Manager.CREATED = False
            Manager.single = None
            if self.exitOnError:
                raise
            else:
                printExc("Error while configuring Manager:")

    def initFromCommandLine(self, args: argparse.Namespace):
        self.exitOnError = args.exit_on_error
        self.disableDevs = args.disable or []
        self.disableAllDevs = args.disable_all
        self._debug = args.debug_logging

        self.configDir = os.path.dirname(args.config)
        self.readConfig(args.config)

        ## Act on options if they were specified..
        try:
            for name in (args.config_name or []):
                self.loadDefinedConfig(name)

            if args.base_dir is not None:
                self.setBaseDir(args.base_dir)
            if args.storage_dir is not None:
                self.setCurrentDir(args.storage_dir)
            if not args.no_manager:
                self.showGUI()
                self.createWindowShortcut('F1', self.gui.win)
            for m in (args.module or []):
                try:
                    if m in self.definedModules:
                        self.loadDefinedModule(m)
                    else:
                        self.loadModule(m)
                except:
                    if not not args.no_manager:
                        self.showGUI()
                    raise

        except:
            if self.exitOnError:
                raise
            else:
                printExc("\nError while acting on command line options: (but continuing on anyway..)")
        finally:
            self.isReady.set()
            if len(self.modules) == 0:
                self.quit()
                raise Exception("No modules loaded during startup, exiting now.")

    @staticmethod
    def _getConfigFile():
        ## search all the default locations to find a configuration file.
        from acq4 import CONFIGPATH
        for path in CONFIGPATH:
            cf = os.path.join(path, 'default.cfg')
            if os.path.isfile(cf):
                return cf
        raise FileNotFoundError(f"Could not find default.cfg file in any of: {CONFIGPATH}")

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
        print("============= Starting Manager configuration from %s =================" % configFile)
        logMsg("Starting Manager configuration from %s" % configFile)
        ns = {
            'hostname': socket.gethostname(),
            'username': getpass.getuser(),
            'environ': os.environ,
        }
        cfg = configfile.readConfigFile(configFile, **ns)
        self.config.update(cfg)

        ## read modules, devices, and stylesheet out of config
        self.configure(self.config)

        self.configFile = configFile
        print("\n============= Manager configuration complete =================\n")
        logMsg('Manager configuration complete.')

    def exec_(self, pyfile):
        """Execute a Python file.

        This is used to enable easy loading of customizations from an externally defined file.
        Note that sys.path is temporarily modified to allow the external file to import from
        scripts in its own path.

        For more complex customizations, it is recommended to build an importable
        module instead.

        Parameters
        ----------
        pyfile : str
            The full path to the python file to be exec'd

        Returns
        -------
        globs : dict
            global namespace defined by the exec
        """
        modDir = os.path.dirname(pyfile)
        sys.path.insert(0, modDir)
        try:
            globs = {}
            with open(pyfile, 'rb') as fh:
                exec(fh.read(), globs)
        finally:
            sys.path.pop(0)
        return globs

    def configure(self, cfg):
        """Load the devices, modules, stylesheet, and storageDir defined in cfg"""

        self._loadConfig(cfg)

        self.sigConfigChanged.emit()

    def _loadConfig(self, cfg):
        # Handle custom import prior to loading devices
        if 'imports' in cfg:
            try:
                if isinstance(cfg["imports"], str):
                    cfg["imports"] = [cfg["imports"]]
                for mod in cfg["imports"]:
                    __import__(mod)
            except:
                if self.exitOnError:
                    raise
                else:
                    printExc("Error in ACQ4 configuration:")

        for key, val in cfg.items():
            try:
                # Hand custom exec
                if key == 'execFiles':
                    if isinstance(val, str):
                        val = [val]
                    for pyfile in val:
                        self.exec_(pyfile)

                ## configure new devices
                elif key == 'devices':
                    for k in cfg['devices']:
                        if self.disableAllDevs or k in self.disableDevs:
                            print(f"    --> Ignoring device '{k}' -- disabled by request")
                            logMsg(f"    --> Ignoring device '{k}' -- disabled by request")
                            continue
                        print(f"  === Configuring device '{k}' ===")
                        logMsg(f"  === Configuring device '{k}' ===")
                        try:
                            conf = cfg['devices'][k]
                            try:
                                driverName = conf['driver']
                            except KeyError as exc:
                                raise KeyError(f"No driver specified for device {k}") from exc
                            if 'config' in conf:  # for backward compatibility
                                conf = conf['config']
                            self.loadDevice(driverName, conf, k)
                        except:
                            print(f"Error configuring device {k}:")
                            if self.exitOnError:
                                raise
                            else:
                                printExc()
                    print("=== Device configuration complete ===")
                    logMsg("=== Device configuration complete ===")

                ## Copy in new module definitions
                elif key == 'modules':
                    for m in cfg['modules']:
                        self.definedModules[m] = cfg['modules'][m]

                ## set new storage directory
                elif key == 'storageDir':
                    print(f"=== Setting base directory: {cfg['storageDir']} ===")
                    logMsg(f"=== Setting base directory: {cfg['storageDir']} ===")
                    self.setBaseDir(cfg['storageDir'])

                elif key == 'defaultCompression':
                    comp = cfg['defaultCompression']
                    try:
                        if isinstance(comp, tuple):
                            cstr = comp[0]
                            assert isinstance(comp[1], int)
                        else:
                            cstr = comp
                        assert cstr in [None, 'gzip', 'szip', 'lzf']
                    except Exception:
                        raise Exception(
                            f"'defaultCompression' option must be one of: None, 'gzip', 'szip', 'lzf', ('gzip', 0-9), or ('szip', opts). Got: '{comp}'")

                    print(f"=== Setting default HDF5 compression: {comp} ===")
                    from MetaArray import MetaArray
                    MetaArray.defaultCompression = comp

                elif key == 'folderTypes':
                    self._folderTypes = val

                ## load stylesheet
                elif key == 'stylesheet':
                    css = open(os.path.join(self.configDir, cfg['stylesheet'])).read()
                    Qt.QApplication.instance().setStyleSheet(css)

                elif key == 'disableErrorPopups':
                    if cfg[key] is True:
                        self.logWindow.disablePopups(True)
                    elif cfg[key] is False:
                        self.logWindow.disablePopups(False)
                    else:
                        print(
                            "Warning: ignored config option 'disableErrorPopups'; value must be either True or False.")

                elif key == 'defaultMouseMode':
                    mode = cfg[key].lower()
                    if mode == 'onebutton':
                        pg.setConfigOption('leftButtonPan', False)
                    elif mode == 'threebutton':
                        pg.setConfigOption('leftButtonPan', True)
                    else:
                        print(
                            "Warning: ignored config option 'defaultMouseMode'; value must be either 'oneButton' or 'threeButton'.")
                elif key == 'useOpenGL':
                    pg.setConfigOption('useOpenGL', cfg[key])

                elif key == 'misc':
                    # Let's start moving things out of the top level, but stay backwards compatible
                    self._loadConfig(cfg[key])

            except:
                if self.exitOnError:
                    raise
                else:
                    printExc("Error in ACQ4 configuration:")

    def listConfigurations(self):
        """Return a list of the named configurations available"""
        return list(self.config.get('configurations', {}).keys())

    def loadDefinedConfig(self, name):
        try:
            cfg = self.config['configurations'][name]
        except KeyError:
            raise KeyError(f"Could not find configuration named '{name}'")
        self.configure(cfg)

    def readConfigFile(self, fileName, missingOk=True):
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
        fileName = self.configFileName(fileName)
        dirName = os.path.dirname(fileName)
        if not os.path.exists(dirName):
            os.makedirs(dirName)
        return configfile.writeConfigFile(data, fileName)

    def appendConfigFile(self, data, fileName):
        fileName = self.configFileName(fileName)
        if os.path.exists(fileName):
            return configfile.appendConfigFile(data, fileName)
        else:
            raise Exception("Could not find file %s" % fileName)

    def updateConfig(self, config: dict):
        self.config.update(config)

    def configFileName(self, name):
        return os.path.join(self.configDir, name)

    def loadDevice(self, devClassName, conf, name):
        """Create a new instance of a device.
        
        Parameters
        ----------
        devClassName : str
            The name of a device class that was registered using acq4.devices.registerDeviceClass().
            See acq4.devices.DEVICE_CLASSES for access to all available device classes.
        conf : dict
            A structure passed to the device providing configuration options
        name : str
            The name of this device. The instantiated device object will be retrievable using
            ``Manager.getDevice(name)``

        Returns
        -------
        device : Device instance
            The instantiated device object
        """
        devclass = devices.getDeviceClass(devClassName)
        dev = devclass(self, conf, name)
        self.devices[name] = dev  # just to prevent device being collected
        return dev

    def getDevice(self, name):
        """Return a device instance given its name.
        """
        name = str(name)
        try:
            return self.getInterface('device', name)
        except KeyError:
            raise Exception("No device named %s. Options are %s" % (name, ','.join(self.listDevices())))

    def listDevices(self):
        """Return a list of the names of available devices.
        """
        return self.listInterfaces('device')

    def reserveDevices(self, devices, timeout=10.0):
        """Return a DeviceLocker that can be used to reserve multiple devices simultaneously::

            with manager.reserveDevices(['Camera', 'Clamp1', 'Stage']):
                # .. do stuff

        """
        devices = [self.getDevice(d) if isinstance(d, str) else d for d in devices]
        return DeviceLocker(self, devices, timeout=timeout)

    def loadModule(self, moduleClassName, name=None, config=None, forceReload=False, importMod=None, execPath=None):
        """Create a new instance of an user interface module. 

        Parameters
        ----------
        moduleClassName : str
            The name of the module *class* to instantiate. The class must have been
            registered by calling acq4.modules.registerModuleClass(). See
            acq4.modules.MODULE_CLASSES for access to all available module classes.
        name : str or None
            The name to assign to the newly instantiated module. If None, then the class
            name is used instead. Module names are automatically modified to avoid name
            collision with previously loaded modules.
        config : dict | None
            Configuration options to pass to the module constructor
        """
        if name is None:
            name = moduleClassName

        ## Find an unused name for this module
        baseName = name
        n = 0
        with self.moduleLock:
            while name in self.listInterfaces().get("module", []):
                name = "%s_%d" % (baseName, n)
                n += 1
            if name in self.modules:
                raise NameError(f"Module name '{name}' is already in use.")
            self.modules[name] = None  # reserve this spot

        if config is None:
            config = {}

        print('Loading module "%s" as "%s"...' % (moduleClassName, name))

        # deprecated args
        if importMod is not None:
            __import__(importMod)
        elif execPath is not None:
            self.exec_(execPath)

        modclass = modules.getModuleClass(moduleClassName)

        mod = modclass(self, name, config)
        self.modules[name] = mod

        self.sigModulesChanged.emit()
        return mod

    def listModules(self):
        """List names of currently loaded modules. """
        return list(self.modules.keys())

    def getDirOfSelectedFile(self):
        """Returns the directory that is currently selected, or the directory of the file that is currently selected in Data Manager."""
        try:
            f = self.getModule("Data Manager").selectedFile()
            if not isinstance(f, DirHandle):
                f = f.parent()
        except Exception:
            f = False
            logMsg("Can't find currently selected directory, Data Manager has not been loaded.", msgType='warning')
            if self.exitOnError:
                raise
        return f

    def getModule(self, name: str):
        """Return a module"""
        with self.moduleLock:
            if name not in self.modules:
                self.loadDefinedModule(name)
        return self.modules[name]

    def getCurrentDatabase(self):
        """Return the database currently selected in the Data Manager"""
        return self.getModule("Data Manager").currentDatabase()

    def listDefinedModules(self):
        """List module configurations defined in the config file"""
        return self.definedModules.copy()

    def loadDefinedModule(self, name, forceReload=False):
        """Load a module and configure as defined in the config file"""
        if name not in self.definedModules:
            print("Module '%s' is not defined. Options are: %s" % (name, str(list(self.definedModules.keys()))))
            return
        conf = self.definedModules[name]

        mod = conf['module']
        config = conf.get('config', {})

        # Allow mechanisms for importing custom modules
        execPath = conf.get('exec', None)
        importMod = conf.get('import', None)

        mod = self.loadModule(mod, name, config, forceReload=forceReload, execPath=execPath, importMod=importMod)
        win = mod.window()
        if 'shortcut' in conf and win is not None:
            self.createWindowShortcut(conf['shortcut'], win)
        print("Loaded module '%s'" % mod.name)

    def moduleHasQuit(self, mod):
        with self.moduleLock:
            if mod.name in self.modules:
                del self.modules[mod.name]
                self.interfaceDir.removeObject(mod)
            else:
                return
        self.removeWindowShortcut(mod.window())
        self.sigModulesChanged.emit()
        self.sigModuleHasQuit.emit(mod.name)

    def unloadModule(self, name):
        try:
            mod = self.getModule(name)
            if mod is not None:
                mod.quit()
        except:
            print(f"Error while requesting module '{name}' quit.")
            if self.exitOnError:
                raise
            else:
                printExc()

        ## Module should have called moduleHasQuit already, but just in case:
        mod = self.modules.pop(name, None)
        if mod is not None:
            self.sigModulesChanged.emit()

    def reloadAll(self):
        """Reload all python code"""
        # path = os.path.split(os.path.abspath(__file__))[0]
        # path = os.path.abspath(os.path.join(path, '..'))
        path = 'acq4'
        print("\n---- Reloading all libraries under %s ----" % path)
        reload.reloadAll(debug=True)
        print("Done reloading.\n")
        logMsg("Reloaded all libraries under %s." % path, msgType='status')

    def createWindowShortcut(self, keys, win):
        ## Note: this is probably not safe to call from other threads.
        try:
            sh = Qt.QShortcut(Qt.QKeySequence(keys), win)
            sh.setContext(Qt.Qt.ApplicationShortcut)
            sh.activated.connect(lambda *args: win.raise_())
        except:
            print(f"Error creating shortcut '{keys}':")
            if self.exitOnError:
                raise
            else:
                printExc()

        self.shortcuts.append((sh, keys, weakref.ref(win)))

    def removeWindowShortcut(self, win):
        ## Need to remove shortcuts after window is closed, because the shortcut is hanging on to all the widgets in the window
        s = None
        for i, s in enumerate(self.shortcuts):
            if s[2]() == win:
                break

        if s is not None:
            self.shortcuts.remove(s)

    def runTask(self, cmd):
        """
        Convenience function that runs a task and returns its results.
        """
        t = Task(self, cmd)
        t.execute()
        return t.getResult()

    def createTask(self, cmd) -> "Task":
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
            # win = self.modules[list(self.modules.keys())[0]].window() ?
            win = self.gui.window()
            self.quitShortcut = Qt.QShortcut(Qt.QKeySequence('Ctrl+q'), win)
            self.quitShortcut.setContext(Qt.Qt.ApplicationShortcut)
            self.abortShortcut = Qt.QShortcut(Qt.QKeySequence('Esc'), win)
            self.abortShortcut.setContext(Qt.Qt.ApplicationShortcut)
            self.reloadShortcut = Qt.QShortcut(Qt.QKeySequence('Ctrl+r'), win)
            self.reloadShortcut.setContext(Qt.Qt.ApplicationShortcut)
            self.quitShortcut.activated.connect(self.quit)
            self.abortShortcut.activated.connect(self.sigAbortAll)
            self.reloadShortcut.activated.connect(self.reloadAll)

        self.gui.show()

    def getCurrentDir(self):
        """
        Return a directory handle to the currently-selected directory for data storage.
        """
        if self.currentDir is None:
            raise HelpfulException("Storage directory has not been set.",
                                    docs=["userGuide/modules/DataManager.html#acquired-data-storage"])
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

        if isinstance(d, str):
            self.currentDir = self.baseDir.getDir(d, create=True)
        elif isinstance(d, DirHandle):
            self.currentDir = d
        else:
            raise Exception("Invalid argument type: ", type(d), d)

        p = self.currentDir

        ## Storage directory is about to change; 
        logDir = self.logWindow.getLogDir()
        while not p.info().get('expUnit', False) and p != self.baseDir and p != logDir:
            p = p.parent()
        if p != self.baseDir and p != logDir:
            self.setLogDir(p)
        else:
            if logDir is None:
                logMsg("No log directory set. Log messages will not be stored.", msgType='warning', importance=8,
                       docs=["userGuide/dataManagement.html#notes-and-logs"])

        self.currentDir.sigChanged.connect(self.currentDirChanged)
        self.sigCurrentDirChanged.emit(None, None, None)

    def currentDirChanged(self, fh, change=None, args=()):
        """Handle situation where currentDir is moved or renamed"""
        self.sigCurrentDirChanged.emit(fh, change, args)

    def getBaseDir(self):
        """
        Return a directory handle to the base directory for data storage. 

        This is the highest-level directory where acquired data may be stored. If 
        the base directory has not been set, return None.
        """
        return self.baseDir

    def setBaseDir(self, d):
        """
        Set the base directory for data storage. 
        """
        if isinstance(d, str):
            dh = self.dirHandle(d, create=False)
        elif isinstance(d, DirHandle):
            dh = d
        else:
            raise Exception("Invalid argument type: ", type(d), d)

        changed = False
        if self.baseDir is not dh:
            self.baseDir = dh
            changed = True

        if changed:
            self.sigBaseDirChanged.emit()
            self.setCurrentDir(self.baseDir)

    def dirHandle(self, d, create=False) -> DirHandle:
        """Return a directory handle for the specified directory string."""
        # return self.dataManager.getDirHandle(d, create)
        return DataManager.getDirHandle(d, create=create)

    def fileHandle(self, d):
        """Return a file or directory handle for d"""
        # return self.dataManager.getHandle(d)
        return DataManager.getFileHandle(d)

    def showLogWindow(self):
        self.logWindow.show()

    ## These functions just wrap the functionality of an InterfaceDirectory
    def declareInterface(self, *args, **kargs):  ## args should be name, [types..], object  
        return self.interfaceDir.declareInterface(*args, **kargs)

    def removeInterface(self, *args, **kargs):
        return self.interfaceDir.removeInterface(*args, **kargs)

    def listInterfaces(self, *args, **kargs):
        return self.interfaceDir.listInterfaces(*args, **kargs)

    def getInterface(self, *args, **kargs):
        """Return the object that was previously declared with *name* and interface *type*.
        """
        return self.interfaceDir.getInterface(*args, **kargs)

    def suggestedDirFields(self, file):
        """Given a DirHandle with a dirType, suggest a set of meta-info fields to use."""
        fields = OrderedDict()
        if isinstance(file, DirHandle):
            info = file.info()
            if 'dirType' in info:
                # infoKeys.remove('dirType')
                dt = info['dirType']
                folderTypesConfig = self._folderTypesConfig()
                if dt in folderTypesConfig:
                    fields = folderTypesConfig[dt]['info']

        if 'notes' not in fields:
            fields['notes'] = 'text', 5
        if 'important' not in fields:
            fields['important'] = 'bool'

        return fields

    def _folderTypesConfig(self):
        return self._folderTypes

    def showDocumentation(self, label=None):
        self.documentation.show(label)

    def printIfDebug(self, s):
        if self._debug:
            print(s)

    def quit(self):
        """Nicely request that all devices and modules shut down"""
        if not self.alreadyQuit:  ## Need this because multiple triggers can call this function during quit
            self.alreadyQuit = True
            lm = len(self.modules)
            ld = len(self.listDevices())
            with pg.ProgressDialog("Shutting down..", 0, lm + ld, cancelText=None, wait=0) as dlg:
                self.documentation.quit()

                self.printIfDebug("Requesting all modules shut down..")
                logMsg("Shutting Down.", importance=9)
                while len(self.modules) > 0:  ## Modules may disappear from self.modules as we ask them to quit
                    m = list(self.modules.keys())[0]
                    self.printIfDebug(f"    {m}")

                    self.unloadModule(m)
                    dlg.setValue(lm - len(self.modules))

                self.printIfDebug("Requesting all devices shut down..")
                devs = Device._deviceCreationOrder[::-1]
                for d in devs:  # shut down in reverse order
                    d = d()
                    if d is None:
                        # device was already deleted
                        continue
                    self.printIfDebug(f"    {d}")
                    try:
                        d.quit()
                    except:
                        self.printIfDebug(f"Error while requesting device '{d.name()}' quit.")
                        if self.exitOnError:
                            raise
                        else:
                            printExc()

                    dlg.setValue(lm + ld - len(devs))

                self.printIfDebug("Closing windows..")
                Qt.QApplication.instance().closeAllWindows()
                Qt.QApplication.instance().processEvents()
            self.printIfDebug("\n    ciao.")
        Qt.QApplication.quit()


# All other modules can use this function to get the manager instance
def getManager() -> Manager:
    if Manager.single is None:
        raise Exception("No manager created yet")
    return Manager.single


class DeviceLocker(object):
    def __init__(self, manager, devices, timeout=10.0):
        # make sure we lock devices in a predictable order; this is what prevents deadlocks
        self.devices = sorted(devices, key=lambda d: d.name())
        self.locked = []
        self.timeout = timeout
        self.lockErr = None

    def tryLock(self, timeout=None):
        try:
            for device in self.devices:
                devLocked = device.reserve(block=True, timeout=timeout)
                if not devLocked:
                    self.lockErr = "Timed out waiting for %s" % device.name()
                    self.unlock()
                    return False
                self.locked.append(device)

            return True
        except Exception:
            self.unlock()
            raise

    def lock(self):
        locked = self.tryLock(timeout=self.timeout)
        if not locked:
            self.unlock()
            raise RuntimeError("Failed to lock devices: %s" % self.lockErr)

    def unlock(self):
        for device in self.locked:
            try:
                device.release()
            except:
                pass
        self.locked = []

    def __enter__(self):
        self.lock()
        return self

    def __exit__(self, *args):
        self.unlock()


class Task:
    id = 0

    def __init__(self, dm, command):
        self.dm = dm
        self.command = command
        self.result = None

        self.taskLock = Mutex(recursive=True)
        self.deviceLock = None

        self.startedDevs = []
        self.startTime = None
        self.stopTime = None
        self.stopped = False
        self.abortRequested = False
        self._done = False

        # self.reserved = False
        try:
            self.cfg = command['protocol']
        except:
            print("================== Manager Task.__init__ command: =================")
            print(command)
            print("===========================================================")
            raise TypeError("Command specified for task is invalid. (Must be dictionary with 'protocol' key)")
        self.id = Task.id
        Task.id += 1

        ## TODO:  set up data storage with cfg['storeData'] and ['writeLocation']
        self.devNames = list(command.keys())
        self.devNames.remove('protocol')
        self.devs = {devName: self.dm.getDevice(devName) for devName in self.devNames}

        ## Create task objects. Each task object is a handle to the device which is unique for this task run.
        self.tasks = {}

        for devName in self.devNames:
            task = self.devs[devName].createTask(self.command[devName], self)
            if task is None:
                printExc("Device '%s' does not have a task interface; ignoring." % devName)
                continue
            self.tasks[devName] = task

    @staticmethod
    def getDevName(obj):
        if isinstance(obj, str):
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
                if t in deps:
                    deps[t].add(devName)

        # request estimated configure time
        cost = {devName: self.tasks[devName].getPrepTimeEstimate() for devName in self.devNames}

        # convert sets to lists
        deps = dict([(k, list(deps[k])) for k in deps.keys()])

        # return sorted order
        order = self.toposort(deps, cost)
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
                if t not in deps:
                    # device is not in task; don't worry about its start order
                    # (this happens, for example, with Trigger devices that do not need to be started by acq4)
                    continue
                deps[t].add(devName)

        deps = dict([(k, list(deps[k])) for k in deps.keys()])

        # return sorted order
        order = self.toposort(deps)
        return order

    def execute(self, block=True, processEvents=True):
        """Start the task.

        If block is true, then the function blocks until the task is complete.
        if processEvents is true, then Qt events are processed while waiting for the task to complete.
        """
        with self.taskLock:
            self.startedDevs = []
            self.stopped = False  # whether sub-tasks have been stopped yet
            self.abortRequested = False
            self._done = False  # cached output of isDone()


            ## We need to make sure devices are stopped and unlocked properly if anything goes wrong..
            from acq4.util.debug import Profiler
            prof = Profiler('Manager.Task.execute', disabled=True)
            try:

                ## Reserve all hardware
                self.reserveDevices()

                prof.mark('reserve')

                ## Determine order of device configuration.
                configOrder = self.getConfigOrder()

                ## Configure all subtasks. Some devices may need access to other tasks, so we make all available here.
                ## This is how we allow multiple devices to communicate and decide how to operate together.
                ## Each task may modify the startOrder list to suit its needs.
                for devName in configOrder:
                    self.tasks[devName].configure()
                    prof.mark(f'configure {devName}')

                startOrder = self.getStartOrder()

                if 'leadTime' in self.cfg:
                    time.sleep(self.cfg['leadTime'])

                prof.mark('leadSleep')

                self.result = None

                ## Start tasks in specific order
                for devName in startOrder:
                    try:
                        self.startedDevs.append(devName)
                        self.tasks[devName].start()
                    except:
                        self.startedDevs.remove(devName)
                        print(f"Error starting device '{devName}'; aborting task.")
                        raise
                    prof.mark(f'start {devName}')
                self.startTime = ptime.time()

                if not block:
                    prof.finish()
                    return

                ## Wait until all tasks are done
                lastProcess = ptime.time()
                isGuiThread = Qt.QThread.currentThread() == Qt.QCoreApplication.instance().thread()
                while not self.isDone():
                    now = ptime.time()
                    elapsed = now - self.startTime
                    if isGuiThread:
                        if processEvents and now - lastProcess > 20e-3:  ## only process Qt events every 20ms
                            Qt.QApplication.processEvents()
                            lastProcess = ptime.time()

                    ## If the task duration has not elapsed yet, only wake up every 10ms, and attempt to wake up 5ms before the end
                    if elapsed < self.cfg['duration'] - 10e-3:
                        sleep = min(10e-3, self.cfg['duration'] - elapsed - 5e-3)
                    else:
                        sleep = 1.0e-3  ## afterward, wake up more quickly so we can respond as soon as the task finishes
                    time.sleep(sleep)

                self.stop()
            except:
                printExc("==========  Error in task execution:  ==============")
                self.abort()
                self.releaseDevices()
                raise
            finally:
                prof.finish()

    def isDone(self):
        """Return True if all tasks are completed and ready to return results.

        If the task run time exceeds the timeout duration, then raise RuntimeError.
        """
        with self.taskLock:
            # If we previously returned True or raised an exception, then
            # just repeat that result.
            if self._done is True:
                return True
            elif self._done is not False:
                raise self._done

            # Check for timeout
            if self.startTime is not None:
                # By default, timeout occurs 10 sec after requested duration is elapsed.
                # Set timeout=None to disable the check.
                timeout = self.cfg.get('timeout', self.cfg['duration'] + 10.0)

                now = ptime.time()
                elapsed = now - self.startTime
                if timeout is not None and elapsed > timeout:
                    self.stop(abort=True)
                    self._done = RuntimeError("Task timed out (>%0.2fs)." % timeout)
                    raise self._done

            # For testing tasks that fail to complete
            if getattr(self, 'test_endless', False):
                return False

            if not self.abortRequested:
                t = ptime.time()
                if self.startTime is None or t - self.startTime < self.cfg['duration']:
                    return False
            d = self._tasksDone()
            self._done = d
            return d

    def _tasksDone(self):
        for t in self.tasks:
            if not self.tasks[t].isDone():
                return False
        if self.stopTime is None:
            self.stopTime = ptime.time()
        return True

    def duration(self):
        """Return the requested task duration, or None if it was not given."""
        return self.command.get('protocol', {}).get('duration', None)

    def runTime(self):
        """Return the length of time since this task began running.
        If the task has already finished, return the length of time the task ran for.
        If the task has not started yet, return None.
        """
        if self.startTime is None:
            return None
        if self.stopTime is None:
            return ptime.time() - self.startTime
        return self.stopTime - self.startTime

    def stop(self, abort=False):
        """Stop all tasks and read data. If abort is True, do not attempt to collect results from the task.
        """
        with self.taskLock:

            prof = Profiler("Manager.Task.stop", disabled=True)
            self.abortRequested = abort
            try:
                if not self.stopped:
                    ## Stop all device tasks
                    while len(self.startedDevs) > 0:
                        t = self.startedDevs.pop()
                        try:
                            self.tasks[t].stop(abort=abort)
                        except:
                            printExc("Error while stopping task %s:" % t)
                        prof.mark("   ..task " + t + " stopped")
                    self.stopped = True

                if not abort and not self._tasksDone():
                    raise Exception("Cannot get result; task is still running.")

                if not abort and self.result is None:
                    ## Let each device generate its own output structure.
                    result = {'protocol': {'startTime': self.startTime}}
                    for devName in self.tasks:
                        try:
                            result[devName] = self.tasks[devName].getResult()
                        except:
                            printExc(f"Error getting result for task {devName} (will set result=None for this task):")
                            result[devName] = None
                        prof.mark("get result: " + devName)
                    self.result = result

                    ## Store data if requested
                    if 'storeData' in self.cfg and self.cfg['storeData'] is True:
                        self.cfg['storageDir'].setInfo(result['protocol'])
                        for t in self.tasks:
                            self.tasks[t].storeResult(self.cfg['storageDir'])
                    prof.mark("store data")
            finally:
                ## Regardless of any other problems, at least make sure we
                ## release hardware for future use
                if self.stopTime is None:
                    self.stopTime = ptime.time()

                self.releaseDevices()
                prof.mark("release all")
                prof.finish()

            if abort:
                gc.collect()  ## it is often the case that now is a good time to garbage-collect.

    def getResult(self):
        with self.taskLock:
            self.stop()
            return self.result

    def reserveDevices(self):
        if self.deviceLock is None:
            try:
                self.deviceLock = self.dm.reserveDevices(list(self.tasks.keys()))
                self.deviceLock.lock()
            except Exception:
                self.deviceLock = None
                raise

    def releaseDevices(self):
        if self.deviceLock is None:
            return
        self.deviceLock.unlock()
        self.deviceLock = None

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
        for k, v in deps0.items():
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
                print(deps)
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


class Documentation(Qt.QObject):
    def __init__(self):
        Qt.QObject.__init__(self)

    def show(self, label=None):
        if label is None:
            url = DOC_ROOT
        else:
            url = DOC_ROOT + label
        Qt.QDesktopServices.openUrl(Qt.QUrl(url))

    def quit(self):
        pass


class QtDocumentation(Qt.QObject):
    """Encapsulates documentation functionality.

    Note: this class is currently out of service in favor of 
    referencing online documentation instead.
    """

    def __init__(self):
        Qt.QObject.__init__(self)
        path = os.path.abspath(os.path.dirname(__file__))
        self.docFile = os.path.normpath(os.path.join(path, '..', 'documentation', 'build', 'qthelp', 'ACQ4.qhc'))

        self.process = Qt.QProcess()
        self.process.finished.connect(self.processFinished)

    def show(self, label=None):
        if self.process.state() == self.process.NotRunning:
            self.startProcess()
            if label is not None:
                Qt.QTimer.singleShot(2000, lambda: self.activateId(label))
                return
        if label is not None:
            self.activateId(label)

    def expandToc(self, n=2):
        self.write('expandToc %d\n' % n)

    def startProcess(self):
        self.process.start('assistant', ['-collectionFile', self.docFile, '-enableRemoteControl'])
        if not self.process.waitForStarted():
            output = str(self.process.readAllStandardError())
            raise Exception("Error starting documentation viewer:  " + output)
        Qt.QTimer.singleShot(1000, self.expandToc)

    def activateId(self, id):
        print("activate:", id)
        self.show()
        self.write('activateIdentifier %s\n' % id)

    def activateKeyword(self, kwd):
        self.show()
        self.write('activateKeyword %s\n' % kwd)

    def write(self, data):
        ba = Qt.QByteArray(data)
        return self.process.write(ba)

    def quit(self):
        self.process.close()

    def processFinished(self):
        print("Doc viewer exited:", self.process.exitCode())
        print(str(self.process.readAllStandardError()))
