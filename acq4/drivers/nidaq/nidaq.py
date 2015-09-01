# -*- coding: utf-8 -*-
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
for d in dtypes.keys():
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
        return self.GetSysDevNames().split(", ")

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
                ret = ctypes.create_string_buffer('\0' * buffSize)
                args += (ret, buffSize)
                
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
            print "NiDAQ Warning while running function '%s%s'" % (func, str(args))
            print self.error(errCode)
            
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
            print func, args
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
        if isinstance(mode, basestring):
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
        if parts[0][:3] != 'Dev':
            devs = self.GetTaskDevices().split(', ')
            if len(devs) != 1:
                raise Exception("Cannot determine device to prepend on channel '%s'" % n)
            parts = [devs[0]] + parts
        return '/' + '/'.join(parts)
        
    def taskType(self):
        #print "taskType:"
        ch = self.GetTaskChannels().split(', ')
        #print ch
        ch = self.absChannelName(ch[0])
        #print "First task channel:", ch
        return self.GetChanType(ch)

    def isInputTask(self):
        return self.taskType() in [LIB.Val_AI, LIB.Val_DI]

    def isOutputTask(self):
        return self.taskType() in [LIB.Val_AO, LIB.Val_DO]


#class SuperTask:
    #"""Class for creating and lumping together multiple synchronous tasks. Holds and assembles arrays for writing to each task as well as per-channel meta data."""
    
    #def __init__(self, daq):
        #self.daq = daq
        #self.tasks = {}
        #self.taskInfo = {}
        #self.channelInfo = {}
        #self.dataWrtten = False
        #self.devs = daq.listDevices()
        #self.triggerChannel = None
        #self.result = None
        
    #def absChanName(self, chan):
        #parts = chan.lstrip('/').split('/')
        #if not parts[0] in self.devs:
            #if len(self.devs) == 1:
                #parts = self.devs + parts
            #else:
                #raise Exception("Can not determine device to use for channel %s" % chan)
        #return '/' + '/'.join(parts)
        
    #def getTaskKey(self, chan, typ=None):
        #"""Return the task that would be responsible for handling a particular channel"""
        #chan = self.absChanName(chan)
        #if chan in self.channelInfo and 'task' in self.channelInfo[chan]:
            #return self.channelInfo[chan]['task']
        
        #if typ is None and chan in self.channelInfo and 'type' in self.channelInfo[chan]:
            #typ = self.channelInfo[chan]['type']

        #if typ is None:
            #raise Exception('Must specify type of task (ai, ao, di, do)')
        #parts = chan.lstrip('/').split('/')
        #devn = parts[0]
        #return (devn, typ)
        
    #def getTask(self, chan, typ=None):
        #"""Return the task which should be used for this channel and i/o type. Creates the task if needed."""
        #key = self.getTaskKey(chan, typ)
        #if not self.tasks.has_key(key):
            #self.tasks[key] = self.daq.createTask()
            #self.taskInfo[key] = {'cache': None, 'chans': [], 'dataWritten': False}
        #return self.tasks[key]
        
    #def addChannel(self, chan, typ, mode=None, vRange=[-10., 10.]):
        #chan = self.absChanName(chan)
        #(dev, typ) = self.getTaskKey(chan, typ)
        #t = self.getTask(chan, typ)
        
        ### Determine mode to use for this channel
        #if mode is None:
            #if typ == 'ai':
                #mode = LIB.Val_RSE
            #elif typ in ['di', 'do']:
                #mode = LIB.Val_ChanPerLine
        #elif isinstance(mode, basestring):
            #modes = {
                #'rse': LIB.Val_RSE,
                #'nrse': LIB.Val_NRSE,
                #'diff': LIB.Val_Diff,
                #'chanperline': LIB.Val_ChanPerLine,
                #'chanforalllines': LIB.Val_ChanForAllLines
            #}
            #try:
                #mode = modes[mode.lower()]
            #except:
                #raise Exception("Unrecognized channel mode '%s'" % mode)
            
        #if typ == 'ai':
            ##print 'CreateAIVoltageChan(%s, "", %s, vRange[0], vRange[1], Val_Volts, None)' % (chan, str(mode))
            #t.CreateAIVoltageChan(chan, "", mode, vRange[0], vRange[1], Val_Volts, None)
        #elif typ == 'ao':
            ##print 'CreateAOVoltageChan(%s, "", vRange[0], vRange[1], Val_Volts, None)' % (chan)
            #t.CreateAOVoltageChan(chan, "", vRange[0], vRange[1], Val_Volts, None)
        #elif typ == 'di':
            ##print 'CreateDIChan(%s, "", %s)' % (chan, str(mode))
            #t.CreateDIChan(chan, "", mode)
        #elif typ == 'do':
            ##print 'CreateDOChan(%s, "", %s)' % (chan, str(mode))
            #t.CreateDOChan(chan, "", mode)
        #else:
            #raise Exception("Don't know how to create channel type %s" % typ)
        #self.taskInfo[(dev, typ)]['chans'].append(chan)
        #self.channelInfo[chan] = {
            #'task': (dev, typ),
            #'index': t.GetTaskNumChans()-1,
        #}

    ## def setChannelInfo(self, chan, info):
        ## chan = self.absChanName(chan)
        ## self.channelInfo[chan] = info

    #def setWaveform(self, chan, data):
        #chan = self.absChanName(chan)
        #if chan not in self.channelInfo:
            #raise Exception('Must create channel (%s) before setting waveform.' % chan)
        ### For now, all ao waveforms must be between -10 and 10
        
        #typ = self.channelInfo[chan]['task'][1]
        #if typ in 'ao' and (any(data > 10.0) or any(data < -10.0)):
            #self.channelInfo[chan]['data'] = clip(data, -10.0, 10.0)
            #self.channelInfo[chan]['clipped'] = True
        #else:
            #self.channelInfo[chan]['data'] = data
            #self.channelInfo[chan]['clipped'] = False
            
        #key = self.getTaskKey(chan)
        #self.taskInfo[key]['dataWritten'] = False

        ## if info is not None:
            ## self.channelInfo[chan]['info'] = info
        
    #def getTaskData(self, key):
        ##key = self.getTaskKey(key)
        #if self.taskInfo[key]['cache'] is None:
            ### Assemble waveforms in correct order
            #waves = []
            #for c in self.taskInfo[key]['chans']:
                #if 'data' not in self.channelInfo[c]:
                    #raise Exception("No data specified for DAQ channel %s" % c)
                #waves.append(atleast_2d(self.channelInfo[c]['data']))
            #self.taskInfo[key]['cache'] = concatenate(waves)
        #return self.taskInfo[key]['cache']
        
    #def writeTaskData(self):
        #for k in self.tasks:
            #if self.tasks[k].isOutputTask() and not self.taskInfo[k]['dataWritten']:
                #d = self.getTaskData(k)
                ##print "  Writing %s to task %s" % (d.shape, str(k))
                #self.tasks[k].write(d)
                #self.taskInfo[k]['dataWritten'] = True
        
    #def hasTasks(self):
        #return len(self.tasks) > 0
        
    #def configureClocks(self, rate, nPts):
        #"""Configure sample clock and triggering for all tasks"""
        #clkSource = None
        #if len(self.tasks) == 0:
            #raise Exception("No tasks to configure.")
        #keys = self.tasks.keys()
        #self.numPts = nPts
        #self.rate = rate
        
        ### Make sure we're only using 1 DAQ device (not sure how to tie 2 together yet)
        #ndevs = len(set([k[0] for k in keys]))
        ##if ndevs > 1:
            ##raise Exception("Multiple DAQ devices not yet supported.")
        #dev = keys[0][0]
        
        #if (dev, 'ao') in keys:  ## Try ao first since E-series devices don't seem to work the other way around..
            #clkSource = 'ao' # '/Dev1/ao/SampleClock'
        #elif (dev, 'ai') in keys:
            #clkSource = 'ai'  # '/Dev1/ai/SampleClock'
        #else:
            ### Only digital tasks, configure a fake AI task so we can use the ai sample clock.
            ### Even better: Configure a counter to make a clock..
            #aich = '/%s/ai0' % dev
            #self.addChannel(aich, 'ai')
            #clkSource = 'ai'  # '/Dev1/ai/SampleClock'
        
        #self.clockSource = (dev, clkSource)
        
        ### Configure sample clock, rate for all tasks
        #clk = '/%s/%s/SampleClock' % (dev, clkSource)
        
        
        ##keys = self.tasks.keys()
        ##keys.remove(self.clockSource)
        ##keys.insert(0, self.clockSource)
        ##for k in keys:

        #for k in self.tasks:
            ### TODO: this must be skipped for the task which uses clkSource by default.
            #if k[1] != clkSource:
                ##print "%s CfgSampClkTiming(%s, %f, Val_Rising, Val_FiniteSamps, %d)" % (str(k), clk, rate, nPts)
                #self.tasks[k].CfgSampClkTiming(clk, rate, Val_Rising, Val_FiniteSamps, nPts)
            #else:
                ##print "%s CfgSampClkTiming('', %f, Val_Rising, Val_FiniteSamps, %d)" % (str(k), rate, nPts)
                #self.tasks[k].CfgSampClkTiming("", rate, Val_Rising, Val_FiniteSamps, nPts)

        
    #def setTrigger(self, trig):
        ##self.tasks[self.clockSource].CfgDigEdgeStartTrig(trig, Val_Rising)

        #for t in self.tasks:
            #if t[1] in ['di', 'do']:   ## M-series DAQ does not have trigger for digital acquisition
                ##print "  skipping trigger for digital task"
                #continue
            ##print t
            #if self.tasks[t].absChannelName(trig) == '/%s/%s/StartTrigger' % t:
                ##print "  Skipping trigger set; already correct."
               #continue
            ##print "  trigger %s %s" % (str(t), trig)
            #self.tasks[t].CfgDigEdgeStartTrig(trig, Val_Rising)
        #self.triggerChannel = trig

    #def start(self):
        #self.writeTaskData()  ## Only writes if needed.
        
        #self.result = None
        ### TODO: Reserve all hardware needed before starting tasks
        
        #keys = self.tasks.keys()
        ### move clock task key to the end
        #if self.clockSource in keys:
            ##print "  Starting %s last" % str(tt) 
            #keys.remove(self.clockSource)
            #keys.append(self.clockSource)
        #for k in keys[:-1]:
            ##print "starting task", k
            #self.tasks[k].start()
        ##self.startTime = time.clock()
        #self.startTime = ptime.time()
        ##print "start time:", self.startTime
        #self.tasks[keys[-1]].start()
        ##print "starting clock task:", keys[-1]
        
##        for k in keys:
##          if not self.tasks[k].isRunning():
##            print "Warning: task %s didn't start" % str(k)
        
        #if self.triggerChannel is not None:
            ### Set up callback to record time when trigger starts
            #pass
            
            
    #def isDone(self):
        #for t in self.tasks:
            #if not self.tasks[t].isDone():
                ##print "Task", t, "not done yet.."
                #return False
        #return True
        
    #def read(self):
        #data = {}
        #for t in self.tasks:
            #if self.tasks[t].isInputTask():
                ##print "Reading from task", t
                #data[t] = self.tasks[t].read()
        #return data
        
    #def stop(self, wait=False, abort=False):
        ##print "ST stopping, wait=",wait
        ### need to be very careful about stopping and unreserving all hardware, even if there is a failure at some point.
        #try:
            #if wait:
                #while not self.isDone():
                    ##print "Sleeping..", time.time()
                    #time.sleep(10e-6)
                    
            #if not abort and self.isDone():
                ## data must be read before stopping the task,
                ## but should only be read if we know the task is complete.
                #self.getResult()
            
        #finally:
            #for t in self.tasks:
                #try:
                    ##print "  ST Stopping task", t
                    #self.tasks[t].stop()
                    ##print "    ..done"
                #finally:
                    ## unreserve hardware
                    #self.tasks[t].TaskControl(Val_Task_Unreserve)
        ##print "ST stop complete."

    #def getResult(self, channel=None):
        ##print "getresult"
        #if self.result is None:
            #self.result = {}
            #readData = self.read()
            #for k in self.tasks.keys():
                ##print "  ", k
                #if self.tasks[k].isOutputTask():
                    ##print "    output task"
                    #d = self.getTaskData(k)
                    ## print "output data set to:"
                    ## print d
                #else:
                    #d = readData[k][0]
                    ## print "input data set to:", d
                    ##print "    input task, read"
                    ##print "    done"
                #self.result[k] = {
                    #'type': k[1],
                    #'data': d,
                    #'start': self.startTime,
                    #'taskInfo': self.taskInfo[k],
                    #'channelInfo': [self.channelInfo[ch] for ch in self.taskInfo[k]['chans']]
                #}
        #if channel is None:
            #return self.result
        #else:
            #res = self.result[self.channelInfo[channel]['task']]
            #ret = {
                #'data': res['data'][self.channelInfo[channel]['index']],
                #'info': {'startTime': res['start'], 'numPts': self.numPts, 'rate': self.rate, 'type': self.channelInfo[channel]['task'][1]}
            #}
            #if 'clipped' in res:
                #ret['info']['clipped'] = res['clipped']

            ## print "=== result for channel %s=====" % channel
            ## print ret 
            #return ret 
## 
    #def run(self):
        ##print "Start..", time.time()
        #self.start()
        ##print "wait/stop..", time.time()
        ##self.stop(wait=True)
        #while not self.isDone():
            #time.sleep(10e-6)
        ##print "get samples.."
        #r = self.getResult()
        #return r
