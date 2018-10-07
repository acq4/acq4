# -*- coding: utf-8 -*-
from __future__ import print_function
from ctypes import *
import sys, re, types, ctypes, os
import cheader

def init():
    ## System-specific code
    headerFile = [os.path.join(os.path.dirname(__file__), "AxMultiClampMsg.h")]
    replace = {
        'AXMCCMSG': '',
        'WINAPI': ''
    }
    global FUNCTIONS
    defs, FUNCTIONS = cheader.getDefs(headerFile, replace=replace)
    
    global MULTICLAMP
    MULTICLAMP = _MULTICLAMP()
    
    for k in defs:
        setattr(sys.modules[__name__], re.sub('^MCCMSG_?', '', k), defs[k])
    #MULTICLAMP.functions = cheader.getFuncs(xmlFiles)


def invertDict(d):
    d2 = {}
    for k in d.keys():
        d2[d[k]] = k
    return d2



class _MULTICLAMP:
    MC_CREATED = False
    
    def __init__(self):
        if _MULTICLAMP.MC_CREATED:
            raise Exception("Will not create another object instance--use the pre-existing MULTICLAMP object.")
        self.mc = windll.AxMultiClampMsg
        _MULTICLAMP.MC_CREATED = True
        
        errCode = c_int(0)
        self.handle = self._call('MCCMSG_CreateObject', byref(errCode))
        if self.handle == 0:
            raise Exception("Error %d creating MC object", errCode.value)
        self.findDevices()
    
    def __del__(self):
        self.__class__.MC_CREATED = False

    def __getattr__(self, attr):
        attr = attr[0].upper() + attr[1:]
        if attr[0] != "_" and hasattr(self.mc, 'MCCMSG_' + attr):
            return lambda *args: self.call(attr, *args)
        else:
            raise Exception("No name '%s' found" % attr)

    def call(self, f, devID=None, arg=None):
        if devID is None:
            raise Exception("Not enough arguments to function %s" % f)
        func = "MCCMSG_" + f
        fsig = FUNCTIONS[func]
        #print f, devID, arg
        self.selectDev(devID)
        unmap = False
        unref = False
        unbool = False
        
        if len(fsig[2]) < 3:
            arg = []
        else:
            if f[:3].lower() == 'get':
                if arg is not None:
                    raise Exception("Too many arguments to function %s" % f)
                unref = True
                if fsig[2][1][0] == 'double':
                    ref = c_double(0)
                    arg = byref(ref)
                elif fsig[2][1][0] == 'BOOL':
                    ref = c_int(0)
                    arg = byref(ref)
                    unbool = True
                elif fsig[2][1][0] == 'UINT':
                    ref = c_uint(0)
                    arg = byref(ref)
                    unmap = True
            else:
                if arg is None:
                    raise Exception("Missing argument %s for function %s" % (fsig[2][1][2], f))
                if fsig[2][1][0] == 'double':
                    arg = c_double(arg)
                elif fsig[2][1][0] == 'BOOL':
                    if arg:
                        print("Interpreting parameter as c_int(1)")
                        arg = c_int(1)
                    else:
                        print("Interpreting parameter as c_int(0)")
                        arg = c_int(0)
                elif fsig[2][1][0] == 'UINT':
                    arg = c_uint(self.nameToInt(arg, f))
        
        errCode = c_int(0)
        args = (self.handle, arg, byref(errCode))
        
        #if len(args) != len(fsig[2]):
            #raise Exception("Function %s takes %d args, %d given" % (f, len(fsig[2])-2, len(args)-2))
        
        ret = self._call(func, *args)
        #print "Call %s%s returned %s" % (func, str(args), str(ret))
        if ret == 0:
            raise Exception(errCode.value, self.error(errCode))
            
        ## Rediculous workaround--700A likes to claim it's secondary signal gain is 0
        if func == 'MCCMSG_GetSecondarySignalGain' and self.devices[devID]['model'] == HW_TYPE_MC700A:
            return 1
            
        if unref:
            if unmap:
                return self.intToName(ref.value, f)
            elif unbool:
                return ref.value == 1
            else:
                return ref.value
        else:
            return None
        
    def _call(self, func, *args):
        try:
            return getattr(self.mc, func)(*args)
        except:
            print(func, args)
            raise
        
    def error(self, errCode):
        buf = create_string_buffer(b'\0' * 256)
        try:
            self._call('MCCMSG_BuildErrorText', self.handle, errCode, buf, c_int(256))
            return str(buf.value)
        except:
            raise
            #raise Exception("Error getting error message :(")


    def findMultiClamp(self):
        serial = create_string_buffer(b'\0'*16)
        model = c_uint(0)
        port = c_uint(0)
        devID = c_uint(0)
        chanID = c_uint(0)
        erNum = c_uint(0)
        if len(self.devices) == 0:
            fn = 'MCCMSG_FindFirstMultiClamp'
        else:
            fn = 'MCCMSG_FindNextMultiClamp'
        ret = self._call(fn, self.handle, byref(model), serial, 16, byref(port), byref(devID), byref(chanID), byref(erNum))
        if ret == 0:
            return None
            raise Exception(ret, self.error(erNum))
        return {'serial': str(serial.value), 'model': model.value, 'port': port.value, 'device': devID.value, 'channel': chanID.value}
    
    def findDevices(self):
        self.devices = []
        while True:
            dev = self.findMultiClamp()
            if dev is None:
                break
            else:
                self.devices.append(dev)
        
    def selectDev(self, devID):
        if devID >= len(self.devices):
            raise Exception("Device %d does not exist" % devID)
        d = self.devices[devID]
        erNum = c_uint(0)
        ret = self._call('MCCMSG_SelectMultiClamp', self.handle, c_uint(d['model']), c_char_p(d['serial']), c_uint(d['port']), c_uint(d['device']), c_uint(d['channel']), byref(erNum))
        if ret == 0:
            raise Exception(erNum.value, self.error(erNum))
        
    def nameToInt(self, name, fn):
        return NAME_MAPS[fn][name]
        
    def intToName(self, num, fn):
        return INV_NAME_MAPS[fn][num]
        
    def getNumDevices(self, *args):
        if len(args) > 0:
            raise Exception("getNumDevices takes no arguments")
        return len(self.devices)
    
    def getDeviceInfo(self, devID):
        if devID >= len(self.devices):
            raise Exception("Device %d does not exist" % devID)
        models = {
            HW_TYPE_MC700A: 'MC700A',
            HW_TYPE_MC700B: 'MC700B'
        }
        d = self.devices[devID]
        if d['model'] in models:
            model = models[d['model']]
        else:
            model = 'UNKNOWN'
            
        return [model, d['serial'], d['port'], d['device'], d['channel']]
        
    def getSignalInfo(self, devID, primary):
        self.selectDev(devID)
        model = self.devices[devID]['model']
        
        priMap = ['PRI', 'SEC']
        
        if primary == 0:
            sig = self.getPrimarySignal(devID)
        elif primary == 1:
            sig = self.getSecondarySignal(devID)
        
        mode = self.getMode(devID)
        if mode == 'I=0':
            mode = 'IC'
            
        #print devID, model, mode, primary, sig
        info = SIGNAL_MAP[model][mode][priMap[primary]][sig]
        return list(info)
        
    
    
    def setSignalByName(self, devID, signal, primary):
        self.selectDev(devID)
        model = self.devices[devID]['model']
        
        priMap = ['PRI', 'SEC']
        
        mode = self.getMode(devID)
        if mode == 'I=0':
            mode = 'IC'
            
        sig = None
        sigMap = SIGNAL_MAP[model][mode][priMap[primary]]
        for k in sigMap:
            if sigMap[k][0] == signal:
                sig = k
        if sig is None:
            raise Exception("Signal name '%s' not found" % signal)
        if primary == 0:
            self.setPrimarySignal(devID, sig)
        elif primary == 1:
            self.setSecondarySignal(devID, sig)

    def getPrimarySignalInfo(self, devID):
        return self.getSignalInfo(devID, 0)

    def getSecondarySignalInfo(self, devID):
        return self.getSignalInfo(devID, 1)

    def setPrimarySignalByName(self, devID, signal):
        return self.setSignalByName(devID, signal, 0)

    def setSecondarySignalByName(self, devID, signal):
        return self.setSignalByName(devID, signal, 1)


init()

## Crapton of stuff to remember that is not provided by header files

MODE_LIST = {
    "VC": MODE_VCLAMP,
    "IC": MODE_ICLAMP,
    "I=0": MODE_ICLAMPZERO,
}
MODE_LIST_INV = invertDict(MODE_LIST) 


PRI_OUT_MODE_LIST = {
    "VC_MEMBCURRENT":         PRI_SIGNAL_VC_MEMBCURRENT,
    "VC_MEMBPOTENTIAL":       PRI_SIGNAL_VC_MEMBPOTENTIAL,
    "VC_PIPPOTENTIAL":        PRI_SIGNAL_VC_PIPPOTENTIAL,
    "VC_100XACMEMBPOTENTIAL": PRI_SIGNAL_VC_100XACMEMBPOTENTIAL,
    "VC_EXTCMDPOTENTIAL":     PRI_SIGNAL_VC_EXTCMDPOTENTIAL,
    "VC_AUXILIARY1":          PRI_SIGNAL_VC_AUXILIARY1,
    "VC_AUXILIARY2":          PRI_SIGNAL_VC_AUXILIARY2,
    "IC_MEMBPOTENTIAL":       PRI_SIGNAL_IC_MEMBPOTENTIAL,
    "IC_MEMBCURRENT":         PRI_SIGNAL_IC_MEMBCURRENT,
    "IC_CMDCURRENT":          PRI_SIGNAL_IC_CMDCURRENT,
    "IC_100XACMEMBPOTENTIAL": PRI_SIGNAL_IC_100XACMEMBPOTENTIAL,
    "IC_EXTCMDCURRENT":       PRI_SIGNAL_IC_EXTCMDCURRENT,
    "IC_AUXILIARY1":          PRI_SIGNAL_IC_AUXILIARY1,
    "IC_AUXILIARY2":          PRI_SIGNAL_IC_AUXILIARY2
}
PRI_OUT_MODE_LIST_INV = invertDict(PRI_OUT_MODE_LIST)


SEC_OUT_MODE_LIST = {
    "VC_MEMBCURRENT":         SEC_SIGNAL_VC_MEMBCURRENT,
    "VC_MEMBPOTENTIAL":       SEC_SIGNAL_VC_MEMBPOTENTIAL,
    "VC_PIPPOTENTIAL":        SEC_SIGNAL_VC_PIPPOTENTIAL,
    "VC_100XACMEMBPOTENTIAL": SEC_SIGNAL_VC_100XACMEMBPOTENTIAL,
    "VC_EXTCMDPOTENTIAL":     SEC_SIGNAL_VC_EXTCMDPOTENTIAL,
    "VC_AUXILIARY1":          SEC_SIGNAL_VC_AUXILIARY1,
    "VC_AUXILIARY2":          SEC_SIGNAL_VC_AUXILIARY2,
    "IC_MEMBPOTENTIAL":       SEC_SIGNAL_IC_MEMBPOTENTIAL,
    "IC_MEMBCURRENT":         SEC_SIGNAL_IC_MEMBCURRENT,
    "IC_CMDCURRENT":          SEC_SIGNAL_IC_CMDCURRENT,
    "IC_PIPPOTENTIAL":        SEC_SIGNAL_IC_PIPPOTENTIAL,
    "IC_100XACMEMBPOTENTIAL": SEC_SIGNAL_IC_100XACMEMBPOTENTIAL,
    "IC_EXTCMDCURRENT":       SEC_SIGNAL_IC_EXTCMDCURRENT,
    "IC_AUXILIARY1":          SEC_SIGNAL_IC_AUXILIARY1,
    "IC_AUXILIARY2":          SEC_SIGNAL_IC_AUXILIARY2,
}
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
    HW_TYPE_MC700A: {
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
            'PRI': {
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
        
    HW_TYPE_MC700B: {
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
