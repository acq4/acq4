# -*- coding: utf-8 -*-
from __future__ import print_function
from ctypes import *
import ctypes
import struct, os, threading, platform, atexit, inspect
from acq4.util.clibrary import *
from .MultiClampTelegraph import *
from acq4.util.debug import *

DEBUG=False ## Global flag for debugging hangups
if DEBUG:
    print("MultiClamp driver debug:", DEBUG)

__all__ = ['MultiClamp', 'axlib', 'getAxlib', 'wmlib']

## Load windows definitions
windowsDefs = winDefs()  #verbose=True)

# Load AxMultiClampMsg header
d = os.path.dirname(__file__)
axonDefs = CParser(
    copyFrom=windowsDefs,
    cache=os.path.join(d, 'AxMultiClampMsg.h.cache'),
    macros={'EXPORT':''}, ## needed for reading version 2.2.0.x headers (64bit)
    verbose=DEBUG
)

### the 700B software default location is C:/ProgramFiles or ProgramFiles(x86)/Molecular Devices
### the 700A software default location seems to be C:/Axon
searchPaths = [
    'C:\\Program Files\\Molecular Devices',
    'C:\\Program Files (x86)\\Molecular Devices',
    'C:\\Program Files\\Axon',
    'C:\\Program Files (x86)\\Axon',
    'C:\\Axon',
]


axlib = None
def getAxlib(libPath=None):
    """Return the handle to the axon library (CLibrary instance).

    If libPath is specified, then it must give the location of the AxMultiClampMsg.dll
    file that should be loaded. Otherwise, a predefined set of paths will be searched.

    Note: if you want to specify the DLL file using libPath, then this function must
    be called before MultiClamp.instance().
    """
    global axlib
    if axlib is None:
        if libPath is None:
            libPath = find_lib('AxMultiClampMsg.dll', paths=searchPaths)
        if not os.path.isfile(libPath):
            raise ValueError('MultiClamp DLL file "%s" does not exist' % libPath)
        print("Using MultiClamp DLL at ", libPath)

        axlib = CLibrary(windll.LoadLibrary(libPath), axonDefs, prefix='MCCMSG_')
        initializeGlobals()

    return axlib


class MultiClampChannel:
    """Class used to run MultiClamp commander functions for a specific channel.
    Instances of this class are created via MultiClamp.getChannel"""
    def __init__(self, mc, desc, debug=DEBUG):
        self.debug = debug
        if debug:
            print("Creating MultiClampChannel")
        self.mc = mc
        self.desc = desc
        self.state = None
        self.callback = None
        self.lock = threading.RLock(verbose=debug)
        
        ## handle for axon mccmsg library 
        self.axonDesc = {
            'pszSerialNum': desc['sn'], 
            'uModel': desc['model'], 
            'uCOMPortID': desc['com'], 
            'uDeviceID': desc['dev'], 
            'uChannelID': desc['chan']
        }
        
    def setCallback(self, cb):
        if self.debug:
            print("MCChannel.setCallback called. callback:", cb)
        with self.lock:
            if self.debug:
                print("    lock acquired (setCallback)")
            self.callback = cb
        
    def getState(self):
        if self.debug:
            print("MCChannel.getState called. caller:", inspect.getouterframes(inspect.currentframe())[1][3])
        with self.lock:
            return self.state

    def getMode(self):
        if self.debug:
            print("MCChannel.getMode called.")
        with self.lock:
            return self.state['mode']

    def updateState(self, state):
        """Called by MultiClamp when changes have occurred in MCC."""
        if self.debug:
            print("MCChannel.updateState called.")
        with self.lock:
            self.state = state
            cb = self.callback
        if cb is not None:
            if self.debug:
                print("   calling callback:", cb)
            cb(state)

    def getParam(self, param):
        if self.debug:
            print("MCChannel.getParam called. param:", param)
        self.select()
        fn = 'Get' + param
        v = self.mc.call(fn)[1]
        
        ## perform return value mapping for a few specific functions
        if fn in INV_NAME_MAPS:
            if v not in INV_NAME_MAPS[fn]:
                raise Exception("Return from %s was %s; expected one of %s." % (fn, v, list(INV_NAME_MAPS[fn].keys())))
            v = INV_NAME_MAPS[fn][v]
            
        ## Silly workaround--MC700A likes to tell us that secondary signal gain is 0
        if fn == 'GetSecondarySignalGain' and self.desc['model'] == axlib.HW_TYPE_MC700A:
            return 1.0
            
        return v

    def setParam(self, param, value):

        if self.debug:
            print("MCChannel.setParam called. param: %s   value: %s" % (str(param), str(value)))
        self.select()
        fn = "Set" + param
        
        ## Perform value mapping for a few functions (SetMode, SetPrimarySignal, SetSecondarySignal)
        if fn in NAME_MAPS:
            if value not in NAME_MAPS[fn]:
                raise Exception("Argument to %s must be one of %s" % (fn, list(NAME_MAPS[fn].keys())))
            value = NAME_MAPS[fn][value]
        #print fn, value
        self.mc.call(fn, value)

    def getParams(self, params):
        """Reads multiple parameters from multiclamp.
        
        Arguments:
        chan -- Use the multiclamp device associated with this channel
        params -- List of parameters to request. 
                  Each parameter "SomeValue" must have a corresponding 
                  function "getSomeValue" in AxMultiClampMsg.h
        """
        res = {}
        for p in params:
            res[p] = self.getParam(p)
        return res

    def setParams(self, params):
        """Sets multiple parameters on multiclamp.
        
        Arguments:
        chan -- Use the multiclamp device associated with this channel
        params -- Dict of parameters to set. 
        """
        res = {}
        for p in params:
            #print "Setting", p, params[p]
            try:
                self.setParam(p, params[p])
                res[p] = True
            except:
                printExc("Error while setting parameter %s=%s" % (p, str(params[p])))
                res[p] = False
        return res
        
    def setMode(self, mode):
        return self.setParam('Mode', mode)

    def setSignal(self, signal, primary):
        """Set the signal of a MC primary/secondary channel by name. 
        
        Use this function instead of setParam('PrimarySignal', ...). Bugs in the axon driver
        prevent that call from working correctly."""

        if self.debug:
            print("MCChannel.setSignal called.")
        model = self.desc['model']
        priMap = ['PRI', 'SEC']
        
        mode = self.getMode()
        if mode == 'I=0':
            mode = 'IC'
            
        sigMap = SIGNAL_MAP[model][mode][priMap[primary]]
        if signal not in sigMap:
            raise Exception("Signal name '%s' not found. (Using map for model=%s, mode=%s, pri=%s)" % (signal, model, mode, priMap[primary]))
            
        sig = 'SIGNAL_' + sigMap[signal]
        if primary == 0:
            self.setParam('PrimarySignal', sig)
        elif primary == 1:
            self.setParam('SecondarySignal', sig)

    def setPrimarySignal(self, signal):
        return self.setSignal(signal, 0)

    def setSecondarySignal(self, signal):
        return self.setSignal(signal, 1)

    def listSignals(self, mode=None):
        """Return two lists of signal names that may be used for this channel:
           #( [primary signals], [secondary signals] )
        #If mode is omitted, then the current mode of the channel is used."""
        if mode is None:
            mode = self.getMode()
        if mode == 'I=0':
            mode = 'IC'
        model = self.desc['model']
        return (list(SIGNAL_MAP[model][mode]['PRI'].keys()), list(SIGNAL_MAP[model][mode]['SEC'].keys()))

    def select(self):
        """Select this channel for parameter get/set"""
        if self.debug:
            print("MCChannel.select called.")
        self.mc.call('SelectMultiClamp', **self.axonDesc)

    def autoPipetteOffset(self):
        self.select()
        self.mc.call('AutoPipetteOffset')


class MultiClamp:
    """Class used to interface with remote multiclamp server.
    Only one instance of this class should be created.
    
    Example usage:
        mc = MultiClamp.instance()
        devs = mc.listDevices()
        chan0 = mc.getChannel(devs[0])
        chan0.setMode('IC')
        signal, gain, units = chan0.getSignalInfo()
    """
    INSTANCE = None
    
    @classmethod
    def instance(cls):
        if cls.INSTANCE is None:
            # make sure dll has been initialized first
            getAxlib()
            cls.INSTANCE = cls()
        return cls.INSTANCE
    
    def __init__(self, debug=DEBUG):
        self.debug = debug
        if debug:
            print("Creating MultiClamp driver object")
        self.telegraph = None
        if MultiClamp.INSTANCE is not None:
            raise Exception("Already created MultiClamp driver object; use MultiClamp.INSTANCE")
        self.handle = None
        self.lock = threading.RLock(verbose=debug)
        
        self.channels = {} 
        self.chanDesc = {}  
        self.connect()
        
        self.telegraph = MultiClampTelegraph(self.chanDesc, self.telegraphMessage)
        MultiClamp.INSTANCE = self

        atexit.register(self.quit)
    
    def quit(self):
        ## do other things to shut down driver?
        self.disconnect()
        if self.telegraph is not None:
            self.telegraph.quit()
        MultiClamp.INSTANCE = None
    
    def getChannel(self, channel, callback=None):
        """Return a MultiClampChannel object for the specified device/channel. The
        channel argument should be the same as a single item from listDevices().
        The callback will be called when certain (but not any) changes are made
        to the multiclamp state."""

        if self.debug:
            print("MCDriver.getChannel called. Channel: %s    callback: %s" %(str(channel), str(callback)))
            caller = inspect.getouterframes(inspect.currentframe())[1][3]
            #caller = "nevermind"
            print("      caller:", caller)
        if channel not in self.channels:
            raise Exception("No channel with description '%s'. Options are %s" % (str(channel), str(self.listChannels())))
            
        ch = self.channels[channel]
        if callback is not None:
            if self.debug:
                print("   setting callback:", str(callback))
            ch.setCallback(callback)
        return ch
    
    def listChannels(self):
        """Return a list of strings used to identify all devices/channels.
        These strings should be used to identify the same channel across invocations."""
        if self.debug:
            print("MCDriver.listChannels called.")
        return list(self.channels.keys())
    
    def connect(self):
        """(re)create connection to commander."""
        #print "connect to commander.."
        if self.debug:
            print("MCDriver.connect called.")
        with self.lock:
            if self.handle is not None:
                #print "   disconnect first"
                self.disconnect()
            (self.handle, err) = axlib.CreateObject()
            if self.handle == 0:
                self.handle = None
                self.raiseError("Error while initializing Axon library:", err)
            self.findDevices()
            
            #print "    now connected:", self.chanDesc
            
    def disconnect(self):
        """Destroy connection to commander"""
        if self.debug:
            print("MCDriver.disconnect called.")
        with self.lock:
            if self.handle is not None and axlib is not None:
                axlib.DestroyObject(self.handle)
                self.handle = None
    
    def findDevices(self):
        if self.debug:
            print("MCDriver.findDevices called.")
        while True:
            ch = self.findMultiClamp()
            if ch is None:
                break
            else:
                ## Make sure the order of keys is well defined; string must be identical every time.
                ch1 = ch.copy()
                ch1['model'] = MODELS[ch1['model']]
                if ch1['model'] == 'MC700A':
                    strDesc = ",".join("%s:%s" % (k, ch1[k]) for k in ['model', 'com', 'dev', 'chan'])  
                elif ch1['model'] == 'MC700B':
                    strDesc = ",".join("%s:%s" % (k, ch1[k]) for k in ['model', 'sn', 'chan'])  
                if strDesc not in self.channels:
                    self.channels[strDesc] = MultiClampChannel(self, ch)
                self.chanDesc[strDesc] = ch

    def findMultiClamp(self):
        if self.debug:
            print("MCDriver.findMultiClamp called.")
        if len(self.channels) == 0:
            fn = 'FindFirstMultiClamp'
        else:
            fn = 'FindNextMultiClamp'
            
        try:
            serial = create_string_buffer(b'\0'*16)
            ret = self.call(fn, pszSerialNum=serial, uBufSize=16)
        except:
            if sys.exc_info()[1][0] == 6000:  ## We have reached the end of the device list
                return None
            raise
        
        desc = {'sn': ret['pszSerialNum'], 'model': ret['puModel'], 'com': ret['puCOMPortID'], 'dev': ret['puDeviceID'], 'chan': ret['puChannelID']}

        return desc

    def call(self, fName, *args, **kargs):   ## call is only used for functions that return a bool error status and have a pnError argument passed by reference.
        if self.debug:
            print("MC_driver.call called. fName:", fName)
        with self.lock:
            ret = axlib('functions', fName)(self.handle, *args, **kargs)
        if ret() == 0:
            funcStr = "%s(%s)" % (fName, ', '.join(list(map(str, args)) + ["%s=%s" % (k, str(kargs[k])) for k in kargs]))
            self.raiseError("Error while running function  %s\n      Error:" % funcStr, ret['pnError'])
        
        if self.debug:
            print("     %s returned." % fName)
        return ret
    
    def raiseError(self, msg, err):
        if self.debug:
            print("MCDriver.raiseError called:")
            print("    ", msg)
        raise Exception(err, msg + " " + self.errString(err))

    def errString(self, err):
        try:
            return axlib.BuildErrorText(self.handle, err, create_string_buffer(b'\0'*256), 256)['sTxtBuf'].decode()
        except:
            sys.excepthook(*sys.exc_info())
            return "<could not generate error message>"

    def telegraphMessage(self, msg, chID=None, state=None):
        if self.debug:
            print("MCDriver.telegraphMessage called. msg:", msg)
        if msg == 'update':
            self.channels[chID].updateState(state)
        elif msg == 'reconnect':
            self.connect()
        





def initializeGlobals():
    global MODELS, MODE_LIST, MODE_LIST_INV, PRI_OUT_MODE_LIST, SEC_OUT_MODE_LIST
    global PRI_OUT_MODE_LIST_INV, SEC_OUT_MODE_LIST_INV, NAME_MAPS, INV_NAME_MAPS
    global SIGNAL_MAP

    ## Crapton of stuff to remember that is not provided by header files

    def invertDict(d):
        return dict([(x[1], x[0]) for x in d.items()])

    MODELS = {
        axlib.HW_TYPE_MC700A: 'MC700A',
        axlib.HW_TYPE_MC700B: 'MC700B'
    }

    MODE_LIST = {
        "VC": axlib.MODE_VCLAMP,
        "IC": axlib.MODE_ICLAMP,
        "I=0": axlib.MODE_ICLAMPZERO,
    }
    MODE_LIST_INV = invertDict(MODE_LIST) 

    ## Extract all signal names from library
    PRI_OUT_MODE_LIST = {}
    SEC_OUT_MODE_LIST = {}
    for k in axlib['values']:
        if k[:18] == 'MCCMSG_PRI_SIGNAL_':
            PRI_OUT_MODE_LIST[k[11:]] = axlib('values', k)
        elif k[:18] == 'MCCMSG_SEC_SIGNAL_':
            SEC_OUT_MODE_LIST[k[11:]] = axlib('values', k)
    PRI_OUT_MODE_LIST_INV = invertDict(PRI_OUT_MODE_LIST)
    SEC_OUT_MODE_LIST_INV = invertDict(SEC_OUT_MODE_LIST)


    NAME_MAPS = {
        'SetMode': MODE_LIST,
        'SetPrimarySignal': PRI_OUT_MODE_LIST,
        'SetSecondarySignal': SEC_OUT_MODE_LIST
    }
    INV_NAME_MAPS = {
        'GetMode': MODE_LIST_INV,
        'GetPrimarySignal': PRI_OUT_MODE_LIST_INV,
        'GetSecondarySignal': SEC_OUT_MODE_LIST_INV
    }

    ## Build a map for connecting signal strings from telegraph headers to signal values from axon headers.
    ##  Note: Completely retarded.

    SIGNAL_MAP = {
        axlib.HW_TYPE_MC700A: {
            'VC': {
                'PRI': {
                    "Membrane Potential": "VC_MEMBPOTENTIAL",
                    "Membrane Current": "VC_MEMBCURRENT",
                    "Pipette Potential": "VC_PIPPOTENTIAL",
                    "100 x AC Pipette Potential": "VC_100XACMEMBPOTENTIAL",
                    "Bath Potential": "VC_AUXILIARY1"
                },
                'SEC': {
                    "Membrane plus Offset Potential": "VC_MEMBPOTENTIAL",
                    "Membrane Current": "VC_MEMBCURRENT",
                    "Pipette Potential": "VC_PIPPOTENTIAL",
                    "100 x AC Pipette Potential": "VC_100XACMEMBPOTENTIAL",
                    "Bath Potential": "VC_AUXILIARY1"
                }   
            },
            'IC': {
                'PRI': {   ## Driver bug? Primary IC signals use VC values. Bah.
                    "Command Current": "VC_MEMBPOTENTIAL",
                    "Membrane Current": "VC_MEMBCURRENT",
                    "Membrane Potential": "VC_PIPPOTENTIAL",
                    "100 x AC Membrane Potential": "VC_100XACMEMBPOTENTIAL",
                    "Bath Potential": "VC_AUXILIARY1"
                    #"Command Current": "IC_CMDCURRENT",
                    #"Membrane Current": "IC_MEMBCURRENT",
                    #"Membrane Potential": "IC_MEMBPOTENTIAL",
                    #"100 x AC Membrane Potential": "IC_100XACMEMBPOTENTIAL",
                    #"Bath Potential": "IC_AUXILIARY1"
                },
                'SEC': {
                    "Command Current": "IC_CMDCURRENT",
                    "Membrane Current": "IC_MEMBCURRENT",
                    "Membrane plus Offset Potential": "IC_MEMBPOTENTIAL",
                    "100 x AC Membrane Potential": "IC_100XACMEMBPOTENTIAL",
                    "Bath Potential": "IC_AUXILIARY1"
                }
            }
        },
            
        axlib.HW_TYPE_MC700B: {
            'VC': {
                'PRI': {
                    "Membrane Current": "VC_MEMBCURRENT",
                    "Membrane Potential": "VC_MEMBPOTENTIAL",
                    "Pipette Potential": "VC_PIPPOTENTIAL",
                    "100x AC Membrane Potential": "VC_100XACMEMBPOTENTIAL",
                    "External Command Potential": "VC_EXTCMDPOTENTIAL",
                    "Auxiliaryl": "VC_AUXILIARY1",
                    "Auxiliary2": "VC_AUXILIARY2",
                },
                'SEC': {
                    "Membrane Current":"VC_MEMBCURRENT" ,
                    "Membrane Potential": "VC_MEMBPOTENTIAL",
                    "Pipette Potential": "VC_PIPPOTENTIAL",
                    "100x AC Membrane Potential": "VC_100XACMEMBPOTENTIAL",
                    "External Command Potential": "VC_EXTCMDPOTENTIAL",
                    "Auxiliaryl": "VC_AUXILIARY1",
                    "Auxiliary2": "VC_AUXILIARY2",
                }
            },
            'IC': {
                'PRI': {
                    "Membrane Potential": "IC_MEMBPOTENTIAL",
                    "Membrane Current": "IC_MEMBCURRENT",
                    "Command Current": "IC_CMDCURRENT",
                    "100x AC Membrane Potential": "IC_100XACMEMBPOTENTIAL",
                    "External Command Current": "IC_EXTCMDCURRENT",
                    "Auxiliary1": "IC_AUXILIARY1",
                    "Auxiliary2": "IC_AUXILIARY2",
                },
                'SEC': {
                    "Membrane Potential": "IC_MEMBPOTENTIAL",
                    "Membrane Current": "IC_MEMBCURRENT",
                    "Pipette Potential": "IC_PIPPOTENTIAL",
                    "100x AC Membrane Potential": "IC_100XACMEMBPOTENTIAL",
                    "External Command Current": "IC_EXTCMDCURRENT",
                    "Auxiliary1": "IC_AUXILIARY1",
                    "Auxiliary2": "IC_AUXILIARY2",
                }
            }
        }
    }
    
