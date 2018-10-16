# -*- coding: utf-8 -*-
from __future__ import print_function
import six
import sys, re, types, ctypes, os, time
import ctypes
from numpy import *
import numpy as np
import acq4.util.ptime as ptime  ## platform-independent precision timing
import acq4.util.debug as debug
import acq4.util.clibrary as clibrary
from . import SuperTask
from .base import NIDAQError

dtypes = {  ## for converting numpy dtypes to nidaq type strings
    '<f8': 'F64',
    '<i2': 'I16',
    '<i4': 'I32',
    '<u2': 'U16',
    '<u4': 'U32',
    '|u1': 'U8',
    #float64.descr[0][1]: 'F64',
    #int16.descr[0][1]: 'I16',
    #int32.descr[0][1]: 'I32',
    #uint16.descr[0][1]: 'U16',
    #uint32.descr[0][1]: 'U32',
    #uint8.descr[0][1]: 'U8'
}
for d in list(dtypes.keys()):
    dtypes[dtypes[d]] = d
    dtypes[dtype(d)] = dtypes[d]



def init():
    modDir = os.path.dirname(__file__)
    headerFiles = [os.path.join(modDir, "NIDAQmx.h")]
    #xmlFiles = [os.path.join(os.path.dirname(__file__), "NIDAQmx.xml")]
    #defs = cheader.getDefs(headerFiles)
    
    ## cache files appear to be platform-dependent due to some pickling bug..
    cacheFile = os.path.join(modDir, 'NIDAQmx_headers_%s.cache' % sys.platform)   
    
    global DEFS
    DEFS = clibrary.CParser(headerFiles, cache=cacheFile, types={'__int64': ('long long')}, verbose=False)
    global LIB
    LIB = clibrary.CLibrary(ctypes.windll.nicaiu, DEFS, prefix=['DAQmx', 'DAQmx_'])
    
    
    global NIDAQ
    NIDAQ = _NIDAQ()
    #for k in defs:
        #setattr(sys.modules[__name__], re.sub('^DAQmx_?', '', k), defs[k])
    #NIDAQ.functions = cheader.getFuncs(xmlFiles)
    #time.clock()


class _NIDAQ:
    NIDAQ_CREATED = False
    def __init__(self):
        if _NIDAQ.NIDAQ_CREATED:
            raise Exception("Will not create another nidaq instance--use the pre-existing NIDAQ object.")
        self.devices = {}

        # cached tasks used for scalar AO/AI operations
        # (this shaves a few ms from the cost of reading/writing scalars)
        self._scalarTasks = {}

        # :TODO: initialize the driver
        _NIDAQ.NIDAQ_CREATED = True

    def __repr__(self):
        return "<niDAQmx driver wrapper>"

    def listDevices(self):
        return self.GetSysDevNames().split(b", ")

    def __getattr__(self, attr):
        try:
            return LIB('values', 'DAQmx_' + attr)
        except NameError:
            fn = LIB('functions', 'DAQmx' + attr)
            return lambda *args: self.call(attr, *args)
                
    def call(self, func, *args):
        func = 'DAQmx' + func
        ret = None
        fn = LIB('functions', func)
        retType, argSig = fn.sig
        
        returnValue = None
        if func[:8] == "DAQmxGet":  ## byref arguments will be handled automatically.
            ## functions that return char* can be called with a null pointer to get the size of the buffer needed.
            if (argSig[-2][1] == ['char', '*'] or argSig[-2][1] == ['char', [-1]]) and argSig[-1][0] == 'bufferSize':
                returnValue = argSig[-2][0]
                extra = {returnValue: None, 'bufferSize': 0}
                buffSize = fn(*args, **extra)()
                ret = ctypes.create_string_buffer(b'\0' * buffSize)
                args += (ret, buffSize)

        # Python 3 requires bytes instead of str arguments here
        args = list(args)
        for i,arg in enumerate(args):
            if isinstance(arg, str):
                args[i] = arg.encode()
                
        ## if there is a 'reserved' argument, it MUST be 0 (don't let clibrary try to fill it for us)
        if argSig[-1][0] == 'reserved':
            ret = fn(*args, reserved=None)
        else:
            ret = fn(*args)
        
        
        errCode = ret()
        
        if errCode < 0:
            msg = "NiDAQ Error while running function '%s%s':\n%s" % (func, str(args), self.error())
            raise NIDAQError(errCode, msg)
        elif errCode > 0:
            print("NiDAQ Warning while running function '%s%s'" % (func, str(args)))
            print(self.error(errCode))
            
        if returnValue is not None:  ## If a specific return value was indicated, return it now
            return ret[returnValue]
        
        ## otherwise, try to guess which values should be returned
        vals = ret.auto()
        if len(vals) == 1:
            return vals[0]
        elif len(vals) > 1:
            return vals
        
    def _call(self, func, *args, **kargs):
        try:
            return getattr(self.nidaq, func)(*args, **kargs)
        except:
            print(func, args)
            raise
        
    def error(self, errCode=None):
        """Return a string with error information. If errCode is None, then the currently 'active' error will be used."""
        if errCode is None:
            err = self.GetExtendedErrorInfo()
        else:
            err = self.GetErrorString(errCode)
        err.replace('\\n', '\n')
        return err

    def __del__(self):
        self.__class__.NIDAQ_CREATED = False

    def createTask(self, name=""):
        return Task(self, name)

    def createSuperTask(self):
        from . import SuperTask
        return SuperTask.SuperTask(self)
    
    def interpretMode(self, mode):
        modes = {
            'rse': LIB.Val_RSE,
            'nrse': LIB.Val_NRSE,
            'diff': LIB.Val_Diff,
            'chanperline': LIB.Val_ChanPerLine,
            'chanforalllines': LIB.Val_ChanForAllLines
        }
        if isinstance(mode, six.string_types):
            mode = mode.lower()
            mode = modes.get(mode, None)
        return mode
    
    def writeAnalogSample(self, chan, value, vRange=[-10., 10.], timeout=10.0):
        """Set the value of an AO port"""
        key = ('ao', chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateAOVoltageChan(chan, "", vRange[0], vRange[1], LIB.Val_Volts, None)
            self._scalarTasks[key] = t
        t.WriteAnalogScalarF64(True, timeout, value)
        
    def readAnalogSample(self, chan, mode=None, vRange=[-10., 10.], timeout=10.0):
        """Get the value of an AI port"""
        if mode is None:
            mode = LIB.Val_Cfg_Default
        else:
            mode = self.interpretMode(mode)

        key = ('ai', mode, chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateAIVoltageChan(chan, "", mode, vRange[0], vRange[1], LIB.Val_Volts, None)
            self._scalarTasks[key] = t
        return t.ReadAnalogScalarF64(timeout)

    def writeDigitalSample(self, chan, value, timeout=10.):
        """Set the value of an AO or DO port"""
        key = ('do', chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateDOChan(chan, "", LIB.Val_ChanForAllLines)
            self._scalarTasks[key] = t
        t.WriteDigitalScalarU32(True, timeout, value)
        
    def readDigitalSample(self, chan, timeout=10.0):
        """Get the value of a DI port"""
        key = ('di', chan)
        t = self._scalarTasks.get(key, None)
        if t is None:
            t = self.createTask()
            t.CreateDIChan(chan, "", LIB.Val_ChanForAllLines)
            self._scalarTasks[key] = t
        return t.ReadDigitalScalarU32(timeout)
        
    def listAIChannels(self, dev=None):
        return self.GetDevAIPhysicalChans(dev).split(", ")

    def listAOChannels(self, dev):
        return self.GetDevAOPhysicalChans(dev).split(", ")

    def listDILines(self, dev):
        return self.GetDevDILines(dev).split(", ")

    def listDIPorts(self, dev):
        return self.GetDevDIPorts(dev).split(", ")

    def listDOLines(self, dev):
        return self.GetDevDOLines(dev).split(", ")

    def listDOPorts(self, dev):
        return self.GetDevDOPorts(dev).split(", ")

init()

chTypes = {
    LIB.Val_AI: 'AI',
    LIB.Val_AO: 'AO',
    LIB.Val_DI: 'DI',
    LIB.Val_DO: 'DO',
    LIB.Val_CI: 'CI',
    LIB.Val_CO: 'CO',
}


        

class Task:
    #TaskHandle = None
    
    def __init__(self, nidaq, taskName=""):
        self.nidaq = nidaq
        self.handle = self.nidaq.CreateTask(taskName)

    def __del__(self):
        self.nidaq.ClearTask(self.handle)

    def __getattr__(self, attr):
        func = getattr(self.nidaq, attr)
        return lambda *args: func(self.handle, *args)

    def __repr__(self):
        return "<Task: %s>" % str(self.GetTaskChannels())

    def start(self):
        self.StartTask()

    def stop(self):
        self.StopTask()

    def isDone(self):
        return self.IsTaskDone()

    def read(self, samples=None, timeout=10., dtype=None):
        #reqSamps = samples
        #if samples is None:
        #    samples = self.GetSampQuantSampPerChan()
        #    reqSamps = -1
        if samples is None:
            samples = self.GetSampQuantSampPerChan()
        reqSamps = samples
        
        numChans = self.GetTaskNumChans()
        
        shape = (numChans, samples)
        #print "Shape: ", shape
        
        ## Determine the default dtype based on the task type
        tt = self.taskType()
        if dtype is None:
            if tt in [LIB.Val_AI, LIB.Val_AO]:
                dtype = float64
            elif tt in [LIB.Val_DI, LIB.Val_DO]:
                dtype = uint32  ## uint8 / 16 might be sufficient, but don't seem to work anyway.
            else:
                raise Exception("No default dtype for %s tasks." % chTypes[tt])

        buf = empty(shape, dtype=dtype)
        #samplesRead = ctypes.c_long()
        
        ## Determine the correct function name to call based on the dtype requested
        fName = 'Read'
        if tt == LIB.Val_AI:
            if dtype == float64:
                fName += 'Analog'
            elif dtype in [int16, uint16, int32, uint32]:
                fName += 'Binary'
            else:
                raise Exception('dtype %s not allowed for AI channels (must be float64, int16, uint16, int32, or uint32)' % str(dtype))
        elif tt == LIB.Val_DI:
            if dtype in [uint8, uint16, uint32]:
                fName += 'Digital'
            else:
                raise Exception('dtype %s not allowed for DI channels (must be uint8, uint16, or uint32)' % str(dtype))
        elif tt == LIB.Val_CI:
            fName += 'Counter'
        else:
            raise Exception("read() not allowed for this task type (%s)" % chTypes(tt))
            
        fName += dtypes[np.dtype(dtype).descr[0][1]]
        
        self.SetReadRelativeTo(LIB.Val_FirstSample)
        self.SetReadOffset(0)
        
        ## buf.ctypes is a c_void_p, but the function requires a specific pointer type so we are forced to recast the pointer:
        fn = LIB('functions', fName)
        cbuf = ctypes.cast(buf.ctypes, fn.argCType('readArray'))
        
        nPts = getattr(self, fName)(reqSamps, timeout, LIB.Val_GroupByChannel, cbuf, buf.size)
        return (buf, nPts)

    def write(self, data, timeout=10.):
        numChans = self.GetTaskNumChans()
        #samplesWritten = c_long()
        
        ## Determine the correct write function to call based on dtype and task type
        fName = 'Write'
        tt = self.taskType()
        if tt == LIB.Val_AO:
            if data.dtype == float64:
                fName += 'Analog'
            elif data.dtype in [int16, uint16]:
                fName += 'Binary'
            else:
                raise Exception('dtype %s not allowed for AO channels (must be float64, int16, or uint16)' % str(data.dtype))
        elif tt == LIB.Val_DO:
            if data.dtype in [uint8, uint16, uint32]:
                fName += 'Digital'
            else:
                raise Exception('dtype %s not allowed for DO channels (must be uint8, uint16, or uint32)' % str(data.dtype))
        else:
            raise Exception("write() not implemented for this task type (%s)" % chTypes[tt])
            
        fName += dtypes[data.dtype.descr[0][1]]
        
        
        ## buf.ctypes is a c_void_p, but the function requires a specific pointer type so we are forced to recast the pointer:
        fn = LIB('functions', fName)
        cbuf = ctypes.cast(data.ctypes, fn.argCType('writeArray'))
        
        nPts = getattr(self, fName)(data.size / numChans, False, timeout, LIB.Val_GroupByChannel, cbuf)
        return nPts

    def absChannelName(self, n):
        parts = n.lstrip('/').split('/')
        devs = self.GetTaskDevices().split(', ')
        if parts[0] not in devs:
            if len(devs) != 1:
                raise Exception("Cannot determine device to prepend on channel '%s'" % n)
            parts = [devs[0]] + parts
        return '/' + '/'.join(parts)
        
    def taskType(self):
        # print "taskType:"
        ch = self.GetTaskChannels().split(', ')
        # print ch
        ch = self.absChannelName(ch[0])
        # print "First task channel:", ch
        return self.GetChanType(ch)

    def isInputTask(self):
        return self.taskType() in [LIB.Val_AI, LIB.Val_DI]

    def isOutputTask(self):
        return self.taskType() in [LIB.Val_AO, LIB.Val_DO]
