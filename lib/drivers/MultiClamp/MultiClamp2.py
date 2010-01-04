# -*- coding: utf-8 -*-
from ctypes import *
import ctypes
import struct, os, threading
from lib.util.clibrary import *
import weakref
#from lib.util.CLibrary import *
#from PyQt4 import QtCore, QtGui

__all__ = ['MultiClamp']

## Load windows definitions
windowsDefs = winDefs(verbose=True)

# Load AxMultiClampMsg header
d = os.path.dirname(__file__)
axonDefs = CParser(
    os.path.join(d, 'AxMultiClampMsg.h'), 
    copyFrom=windowsDefs,
    cache=os.path.join(d, 'AxMultiClampMsg.h.cache'),
    verbose=True
)



class MultiClampChannel:
    """Class used to run MultiClamp commander functions for a specific channel.
    Uses most of the same functions as MultiClamp, but does not require the channel argument.
    Instances of this class are created via MultiClamp.getChannel"""
    def __init__(self, mc, chan):
        self.mc = mc
        self.chan = chan
        
        ## Proxy functions back to MC object with channel argument automatically supplied
        for fn in ['getParam', 'setParam', 'getParams', 'setParams', 'getMode', 'setMode', 'setPrimarySignalByName', 'setSecondarySignalByName', 'setSignalByName', 'getPrimarySignalInfo', 'getSecondarySignalInfo', 'getSignalInfo', 'listSignals']:
            self.mkProxy(fn)

    def mkProxy(self, fn):
        setattr(self, fn, lambda *a, **k: self.proxy(fn, *a, **k))

    def proxy(self, fn, *args, **kwargs):
        if self.chan is None:
            raise Exception("MultiClamp channel does not exist in system!")
        return getattr(self.mc, fn)(self.chan, *args, **kwargs)
        
    def setChan(self, ch):
        self.chan = ch
        
        

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
    
    def __init__(self):
        if MultiClamp.INSTANCE is not None:
            raise Exception("Already created MultiClamp driver object; use MultiClamp.INSTANCE")
        self.handle = None
        self.telegraphLock = threading.Lock()
        self.devStates = []  ## Stores basic state of devices reported by telegraph
        
        self.chanHandles = weakref.WeakValueDictionary()  
        self.connect()
        
        self.telegraph = MultiClampTelegraph(self.devices, self.telegraphMessage)
        MultiClamp.INSTANCE = self
    
    def __del__(self):
        ## do other things to shut down driver?
        self.disconnect()
        MultiClamp.INSTANCE = None
    
    @staticmethod
    def instance():
        return MultiClamp.INSTANCE
    
        

    ### High-level driver calls
    
    def getChannel(self, channel):
        """Return a MultiClampChannel object for the specified device/channel. The
        argument should be the same as a single item from listDevices()"""
        chInd = self.channelIndex(channel)
            
        h = MultiClampChannel(self, chInd)
        self.chanHandles[channel] = h
        return h
    
    
    def getParam(self, chan, param):
        self.selectDev(chan)
        fn = 'Get' + param
        v = self.call(fn)[1]
        
        ## perform return value mapping for a few specific functions
        if fn in INV_NAME_MAPS:
            if v not in INV_NAME_MAPS[fn]:
                raise Exception("Return from %s was %s; expected one of %s." % (fn, v, INV_NAME_MAPS[fn].keys()))
            v = INV_NAME_MAPS[fn][v]
            
        ## Silly workaround--MC700A likes to tell us that secondary signal gain is 0
        if fn == 'GetSecondarySignalGain' and self.devices[chan]['model'] == axlib.HW_TYPE_MC700A:
            return 1.0
            
        return v


    def setParam(self, chan, param, value):
        self.selectDev(chan)
        fn = "Set" + param
        
        ## Perform value mapping for a few functions (SetMode, SetPrimarySignal, SetSecondarySignal)
        if fn in NAME_MAPS:
            if value not in NAME_MAPS[fn]:
                raise Exception("Argument to %s must be one of %s" % (fn, NAME_MAPS[fn].keys()))
            value = NAME_MAPS[fn][value]
        
        self.call(fn, value)


    def getParams(self, chan, params):
        """Reads multiple parameters from multiclamp.
        
        Arguments:
        chan -- Use the multiclamp device associated with this channel
        params -- List of parameters to request. 
                  Each parameter "SomeValue" must have a corresponding 
                  function "getSomeValue" in AxMultiClampMsg.h
        """
        res = {}
        for p in params:
            res[p] = self.getParam(chan, p)
        return res


    def setParams(self, chan, params):
        """Sets multiple parameters on multiclamp.
        
        Arguments:
        chan -- Use the multiclamp device associated with this channel
        params -- Dict of parameters to set. 
        """
        res = {}
        for p in params:
            #print "Setting", p, params[p]
            try:
                self.setParam(chan, p, params[p])
                res[p] = True
            except:
                printExc("Error while setting parameter %s=%s" % (p, str(params[p])))
                res[p] = False
        return res
        
    def getMode(self, chan):
        return self.getParam(chan, 'Mode')
        
    def setMode(self, chan, mode):
        return self.setParam(chan, 'Mode', mode)

    def listDevices(self):
        """Return a list of strings used to identify devices on a multiclamp.
        These strings should be used to identify the same device across invocations."""
        
        devList = []
        for d in self.devices:
            d = d.copy()
            if MODELS.has_key(d['model']):
                d['model'] = MODELS[d['model']]
            else:
                d['model'] = 'UNKNOWN'
            ## Make sure the order of keys is well defined; string must be identical every time.
            strDesc = ",".join("%s:%s" % (k, d[k]) for k in ['model', 'sn', 'com', 'dev', 'chan'])  
            devList.append(strDesc) 
        return devList
    
    def setSignalByName(self, chan, signal, primary):
        """Set the signal of a MC primary/secondary channel by name. 
        
        Use this function instead of setParam('PrimarySignal', ...). Bugs in the axon driver
        prevent that call from working correctly."""
        model = self.devices[chan]['model']
        priMap = ['PRI', 'SEC']
        
        mode = self.getMode(chan)
        if mode == 'I=0':
            mode = 'IC'
            
        sig = None
        sigMap = SIGNAL_MAP[model][mode][priMap[primary]]
        for k in sigMap:
            if sigMap[k][0] == signal:
                sig = "SIGNAL_" + k
        if sig is None:
            raise Exception("Signal name '%s' not found" % signal)
        if primary == 0:
            self.setParam(chan, 'PrimarySignal', sig)
        elif primary == 1:
            self.setParam(chan, 'SecondarySignal', sig)

    def getPrimarySignalInfo(self, chan):
        return self.getSignalInfo(chan, 0)

    def getSecondarySignalInfo(self, chan):
        return self.getSignalInfo(chan, 1)

    def setPrimarySignalByName(self, chan, signal):
        return self.setSignalByName(chan, signal, 0)

    def setSecondarySignalByName(self, chan, signal):
        return self.setSignalByName(chan, signal, 1)
    
    def getSignalInfo(self, chan, primary=0):
        """Return a tuple (signalName, gain, units) for the current signal
        
        the outputChan argument defaults to 'Primary' and can be set to 'Secondary' instead.
        """
        #self.selectDev(devID)
        model = self.devices[chan]['model']
        
        priMap = ['PRI', 'SEC']
        
        if primary == 0:
            outputChan = 'Primary'
        elif primary == 1:
            outputChan = 'Secondary'
            
        sig = self.getParam(chan, outputChan+'Signal')[7:]
        
        mode = self.getMode(chan)
        if mode == 'I=0':
            mode = 'IC'
            
        ##print devID, model, mode, primary, sig
        (name, gain, units) = SIGNAL_MAP[model][mode][priMap[primary]][sig]
        
        xGain = self.getParam(chan, outputChan + 'SignalGain')
        ### Silly workaround-- MC700A likes to tell us that secondary signal gain is 0
        #if xGain < 1e-10:
                #xGain = 1.0
        gain2 = float(gain) * xGain
        #print "%s gain = %f * %f = %f" % (outputChan, float(gain), float(xGain[0]), gain2)
        return (name, gain2, units)

    
    def listSignals(self, chan, mode=None):
        """Return two lists of signal names that may be used for this channel:
           ( [primary signals], [secondary signals] )
        If mode is omitted, then the current mode of the channel is used."""
        
        if mode is None:
            mode = self.getMode(chan)
        if mode == 'I=0':
            mode = 'IC'
        model = self.devices[chan]['model']
        sigmap = SIGNAL_MAP[model][mode]
        pri = [v[0] for v in sigmap['PRI'].values()]
        sec = [v[0] for v in sigmap['SEC'].values()]
        return (pri, sec)
        
    def channelIndex(self, channel):
        devs = self.listDevices()
        try:
            return devs.index(channel)
        except ValueError:
            raise Exception("Device not found with description '%s'. Options are: '%s'" % (str(channel), str(devs)))
    
    #def stateDiff(self, state):
        #"""Compare the state of the multiclamp to the expected state (s1), return the keys that differ."""
        #m = []
        #for k in state.keys():
            #v = state[k]
            #if type(v) == bool:
                #if (v and s2[k][0] != 'true') or (not v and s2[k][0] != 'false'):
                    #m.append(k)
            #elif type(v) == int:
                #if v != int(s2[k][0]):
                    #m.append(k)
            #elif type(v) == float:
                #if v - float(s2[k][0]) > 1e-30:
                    #m.append(k)
        #return m
    



    ################   Begin Low-level driver calls    ###########################
    
    
    def connect(self):
        """(re)create connection to commander."""
        if self.handle is not None:
            self.disconnect()
        (self.handle, err) = axlib.CreateObject()
        if self.handle == 0:
            self.handle = None
            self.raiseError("Error while initializing Axon library:", err)
        self.findDevices()
        
    def disconnect(self):
        """Destroy connection to commander"""
        if self.handle is not None:
            axlib.DestroyObject(self.handle)
            self.handle = None


    def findMultiClamp(self):
        if len(self.devices) == 0:
            fn = 'FindFirstMultiClamp'
        else:
            fn = 'FindNextMultiClamp'
            
        try:
            serial = create_string_buffer('\0'*16)
            ret = self.call(fn, pszSerialNum=serial, uBufSize=16)
        except:
            if sys.exc_info()[1][0] == 6000:  ## We have reached the end of the device list
                return None
            raise
        return {'sn': ret['pszSerialNum'], 'model': ret['puModel'], 'com': ret['puCOMPortID'], 'dev': ret['puDeviceID'], 'chan': ret['puChannelID']}
    
    def findDevices(self):
        self.devices = []
        while True:
            dev = self.findMultiClamp()
            if dev is None:
                break
            else:
                self.devices.append(dev)
        self.devStates = [None] * len(self.devices)
        for h in self.chanHandles:  ## Update any channel objects that have been created
            try:
                ind = self.channelIndex(h)
            except:
                ind = None
            self.chanHandles[h].setChan(ind)

    def selectDev(self, devID):
        if devID >= len(self.devices):
            raise Exception("Device %d does not exist" % devID)
        d = self.devices[devID]
        self.call('SelectMultiClamp', pszSerialNum=d['sn'], uModel=d['model'], uCOMPortID=d['com'], uDeviceID=d['dev'], uChannelID=d['chan'])


    def call(self, fName, *args, **kargs):   ## call is only used for functions that return a bool error status and have a pnError argument passed by reference.
        ret = axlib('functions', fName)(self.handle, *args, **kargs)
        if ret() == 0:
            funcStr = "%s(%s)" % (fName, ', '.join(map(str, args) + ["%s=%s" % (k, str(kargs[k])) for k in kargs]))
            self.raiseError("Error while running function  %s\n      Error:" % funcStr, ret['pnError'])
            
        return ret
    
    def raiseError(self, msg, err):
        raise Exception(err, msg + " " + self.errString(err))

    def printError(self, msg, err):
        print msg + self.errString(err)

    def errString(self, err):
        try:
            return axlib.BuildErrorText(self.handle, err, create_string_buffer('\0'*256), 256)['sTxtBuf']
        except:
            sys.excepthook(*sys.exc_info())
            return "<could not generate error message>"

    def telegraphMessage(self, msg, devID, state):
        with self.lock:
            if msg == 'update':
                self.devStates[devID] = state
            elif 'msg' == 'reconnect':
                self.connect()
        





### Create instance of driver class
MultiClamp()

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





## In order to properly interpret the output of getPrimarySignal and getSecondarySignal, 
## we also need to know the model and mode of the amplifier and translate via this table
## Note: Completely retarded. This should have been handled by the axon library

SIGNAL_MAP = {
    axlib.HW_TYPE_MC700A: {
        'VC': {
            'PRI': {
                "VC_MEMBPOTENTIAL": ("MembranePotential", 10.0, 'V'),
                "VC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "VC_PIPPOTENTIAL": ("PipettePotential", 1.0, 'V'),
                "VC_100XACMEMBPOTENTIAL": ("100XACMembranePotential", 100., 'V'),
                "VC_AUXILIARY1": ("BathPotential", 1., 'V')
            },
            'SEC': {
                "VC_MEMBPOTENTIAL": ("MembranePlusOffsetPotential", 10.0, 'V'),
                "VC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "VC_PIPPOTENTIAL": ("PipettePotential", 1., 'V'),
                "VC_100XACMEMBPOTENTIAL": ("100XACPipettePotential", 100., 'V'),
                "VC_AUXILIARY1": ("BathPotential", 1., 'V')
            }
        },
        'IC': {
            'PRI': {   ## Driver bug? Primary IC signals use VC values. Bah.
                "VC_PIPPOTENTIAL": ("MembranePotential", 1.0, 'V'),
                "VC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "VC_MEMBPOTENTIAL": ("CommandCurrent", 0.5e9, 'A'),
                "VC_100XACMEMBPOTENTIAL": ("100XACMembranePotential", 100., 'V'),
                "VC_AUXILIARY1": ("BathPotential", 1., 'V')
            },
            'SEC': {
                "IC_CMDCURRENT": ("CommandCurrent", 0.5e9, 'A'),
                "IC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "IC_MEMBPOTENTIAL": ("MembranePlusOffsetPotential", 1.0, 'V'),
                "IC_100XACMEMBPOTENTIAL": ("100XACMembranePotential", 100., 'V'),
                "IC_AUXILIARY1": ("BathPotential", 1., 'V')
            }
        }
    },
        
    axlib.HW_TYPE_MC700B: {
        'VC': {
            'PRI': {
                "VC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "VC_MEMBPOTENTIAL": ("MembranePotential", 10.0, 'V'),
                "VC_PIPPOTENTIAL": ("PipettePotential", 1.0, 'V'),
                "VC_100XACMEMBPOTENTIAL": ("100XACMembranePotential", 100., 'V'),
                "VC_EXTCMDPOTENTIAL": ("ExternalCommandPotential", 50., 'V'),
                "VC_AUXILIARY1": ("Auxiliaryl", 1., 'V'),
                "VC_AUXILIARY2": ("Auxiliary2", 1., 'V')
            },
            'SEC': {
                "VC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "VC_MEMBPOTENTIAL": ("MembranePotential", 10.0, 'V'),
                "VC_PIPPOTENTIAL": ("PipettePotential", 1.0, 'V'),
                "VC_100XACMEMBPOTENTIAL": ("100XACMembranePotential", 100., 'V'),
                "VC_EXTCMDPOTENTIAL": ("ExternalCommandPotential", 50., 'V'),
                "VC_AUXILIARY1": ("Auxiliaryl", 1., 'V'),
                "VC_AUXILIARY2": ("Auxiliary2", 1., 'V')
            }
        },
        'IC': {
            'PRI': {
                "IC_MEMBPOTENTIAL": ("MembranePotential", 10.0, 'V'),
                "IC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "IC_CMDCURRENT": ("CommandCurrent", 0.5e9, 'A'),
                "IC_100XACMEMBPOTENTIAL": ("100XACMembranePotential", 100., 'V'),
                "IC_EXTCMDCURRENT": ("ExternalCommandCurrent", 2.5e9, 'A'),
                "IC_AUXILIARY1": ("Auxiliary1", 1., 'V'),
                "IC_AUXILIARY2": ("Auxiliary2", 1., 'V')
            },
            'SEC': {
                "IC_MEMBPOTENTIAL": ("MembranePotential", 10.0, 'V'),
                "IC_MEMBCURRENT": ("MembraneCurrent", 0.5e9, 'A'),
                "IC_PIPPOTENTIAL": ("PipettePotential", 1.0, 'V'),
                "IC_100XACMEMBPOTENTIAL": ("100XACMembranePotential", 100., 'V'),
                "IC_EXTCMDCURRENT": ("ExternalCommandCurrent", 2.5e9, 'A'),
                "IC_AUXILIARY1": ("Auxiliary1", 1., 'V'),
                "IC_AUXILIARY2": ("Auxiliary2", 1., 'V')
            }
        }
    }
}
    