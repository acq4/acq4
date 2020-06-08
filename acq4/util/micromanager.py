# -*- coding: utf-8 -*-
from __future__ import print_function
import os, sys
from acq4.util.Mutex import Mutex
from acq4 import CONFIGPATH
from acq4.util import configfile
# singleton MMCorePy instance



_mmc = None
global _mmc


DEFAULT_MM_PATH = "C:\\Program Files\\Micro-Manager-1.4"

def getMMConfig():
    """
        get the micromanager path and desired micromanager config file from acq4 config 
    """    
    for path in CONFIGPATH:
        cf = os.path.join(path, 'default.cfg')
        if os.path.isfile(cf):
            cfg = configfile.readConfigFile(cf)
            micromanager_dict = {'config_file' : os.path.join('config',cfg['micromanager_configfile']),
                                'micromanager_dir' : cfg['micromanager_directory']}
            return micromanager_dict
    raise Exception("Could not find config file in: %s" % CONFIGPATH)


try:
    micromanager_settings = getMMConfig()
    print(micromanager_settings)
    path = (micromanager_settings['micromanager_dir'])
except:
    print("failed to get micromanager settings")
    path = DEFAULT_MM_PATH
    micromanager_settings = {"config_file":None}


def getMMCorePy(path=path, mm_config_file = micromanager_settings['config_file']):
    """
    Return a singleton MMCorePy instance that is shared by all devices for accessing micromanager.
    mm_config_file not None will attempt to load that micromanager configuration file 

    """
    global _mmc
    if _mmc is None:
        try:
            global MMCorePy
            import MMCorePy
        except ImportError:
            if sys.platform != 'win32':
                raise
            # MM does not install itself to standard path. User should take care of this,
            # but we can make a guess..
            if path is None:
                path = microManagerPath
            sys.path.append(path)
            os.environ['PATH'] = os.environ['PATH'] + ';' + path
            try:
                import MMCorePy
            finally:
                sys.path.pop()
    
        _mmc = MMCorePy.CMMCore()


    if _mmc.getSystemState().size()<=12:  # hack to see if a real configuration is already loaded...

        if mm_config_file is not None:
            print("mm_config_file "+mm_config_file)
            try:
                _mmc.loadSystemConfiguration(mm_config_file)
                _mmc.getVersionInfo()
            except:
                print(_mmc.getDeviceAdapterSearchPaths())
                raise ValueError("micromanager loadSystemConfiguration failed!")
        else:
            print("no micromanager configuration defined or loaded")
    else:
        print("micromanager configuration already loaded")

    return _mmc


def unloadMMCore():
    print("attempting to unload Micro Manager Devices ... ")

    if "_mmc" in globals().keys():
        global _mmc
        print("Unloading All Micro Manager Devices")
        mmc = getMMCorePy()
        return mmc.unloadAllDevices()
    else:
        print("Nothing left to unload")
        return None
