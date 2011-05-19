# -*- coding: utf-8 -*-
from ctypes import *
import sys, re, types, ctypes, os, time
from numpy import *
#import cheader
import ptime  ## platform-independent precision timing
import debug
import clibrary


dtypes = {
    float64: 'F64',
    int16: 'I16',
    int32: 'I32',
    uint16: 'U16',
    uint32: 'U32',
    uint8: 'U8'
}
for d in dtypes.keys():
    dtypes[dtypes[d]] = d
    dtypes[dtype(d)] = dtypes[d]



def init():
    modDir = os.path.dirname(__file__)
    headerFiles = [os.path.join(modDir, "NIDAQmx.h")]
    #xmlFiles = [os.path.join(os.path.dirname(__file__), "NIDAQmx.xml")]
    #defs = cheader.getDefs(headerFiles)
    global DEFS
    DEFS = clibrary.CParser(headerFiles, cache=os.path.join(modDir, 'NIDAQmx_headers.cache'))
    #lib = CLibrary(None, defs, prefix='DAQmx_')   ## windll.nicaiu
    
    
    global NIDAQ
    NIDAQ = _NIDAQ()
    #for k in defs:
        #setattr(sys.modules[__name__], re.sub('^DAQmx_?', '', k), defs[k])
    #NIDAQ.functions = cheader.getFuncs(xmlFiles)
    #time.clock()


class NIDAQError(Exception):
    pass
class NIDAQWarning(Exception):
    pass

class _NIDAQ:
    NIDAQ_CREATED = False
    def __init__(self):
        if _NIDAQ.NIDAQ_CREATED:
            raise Exception("Will not create another nidaq instance--use the pre-existing NIDAQ object.")
        self.lib = CLibrary(windll.nicaiu, DEFS, prefix='DAQmx_')
        self.devices = {}
        # :TODO: initialize the driver
        _NIDAQ.NIDAQ_CREATED = True

    def __repr__(self):
        return "<niDAQmx driver wrapper>"

    def listDevices(self):
        return self.GetSysDevNames().split(", ")

    def __getattr__(self, attr):
        if attr[0] != "_" and hasattr(self.nidaq, 'DAQmx' + attr):
            return lambda *args: self.call(attr, *args)
        else:
            raise NameError(attr)

    def call(self, func, *args):
        func = 'DAQmx' + func
        ret = None
        retType, argSig = self.functions[func]
        #print "CALL: ", func, args, argSig
        
        if func[:8] == "DAQmxGet":
            if argSig[-1][0] == 'data':
                ret = getattr(ctypes, argSig[-1][1])()
                args += (byref(ret),)
            elif argSig[-2][1:] == ('c_char', 1) and argSig[-1][1:] in [('c_ulong', 0), ('c_long', 0)]:
                #print "correct for buffer return"
                tmpargs = args + (getattr(ctypes, argSig[-2][1])(), getattr(ctypes, argSig[-1][1])())
                buffSize = self._call(func, *tmpargs)
                ret = create_string_buffer('\0' * buffSize)
                args += (ret, buffSize)
        
        cArgs = []
        if len(args) > len(argSig):
            raise Exception("Argument list is too long (%d) for function signature: %s" % (len(args), str(argSig)))
        for i in range(0, len(args)):
            arg = args[i]
            #if type(args[i]) in [types.FloatType, types.IntType, types.LongType, types.BooleanType] and argSig[i][2] == 0:
            if hasattr(args[i], '__int__') and argSig[i][2] == 0:  ## all numbers and booleans probably have an __int__ method.
                #print func, i, argSig[i][0], argSig[i][1], type(arg)
                arg = getattr(ctypes, argSig[i][1])(arg)
            #else:
                #print "Warning: passing unknown argument type", type(args[i])
            cArgs.append(arg)
        
        #print "  FINAL CALL: ", cArgs
        errCode = self._call(func, *cArgs)
        if errCode < 0:
            print "NiDAQ Error while running function '%s%s'" % (func, str(args))
            for s in self.error(errCode):
                print s
            raise NIDAQError(errCode)
            #raise NIDAQError(errCode, "Function '%s%s'" % (func, str(args)), *self.error(errCode))
        elif errCode > 0:
            print "NiDAQ Warning while running function '%s%s'" % (func, str(args))
            print self.error(errCode)
            debug.printExc("Traceback:")
            #raise NIDAQWarning(errCode, "Function '%s%s'" % (func, str(args)), *self.error(errCode))
        
        if ret is None:
            return True
        else:
            return ret.value
        
    def _call(self, func, *args):
        try:
            return getattr(self.nidaq, func)(*args)
        except:
            print func, args
            raise
        
    def error(self, errCode):
        return (self.GetErrorString(errCode),
                      self.GetExtendedErrorInfo())

    def __del__(self):
        self.__class__.NIDAQ_CREATED = False

    def createTask(self):
        return Task(self)

    def interpretMode(self, mode):
        modes = {
            'rse': Val_RSE,
            'nrse': Val_NRSE,
            'diff': Val_Diff,
            'chanperline': Val_ChanPerLine,
            'chanforalllines': Val_ChanForAllLines
        }
        if isinstance(mode, basestring):
            mode = mode.lower()
            mode = modes.get(mode, None)
        return mode
        
    
    def writeAnalogSample(self, chan, value, vRange=[-10., 10.], timeout=10.0):
        """Set the value of an AO or DO port"""
        t = self.createTask()
        t.CreateAOVoltageChan(chan, "", vRange[0], vRange[1], Val_Volts, None)
        t.WriteAnalogScalarF64(True, timeout, value, None)
        return
        
    def readAnalogSample(self, chan, mode=None, vRange=[-10., 10.], timeout=10.0):
        """Get the value of an AI port"""
        if mode is None:
            mode = Val_Cfg_Default
        else:
            mode = self.interpretMode(mode)
        t = self.createTask()
        t.CreateAIVoltageChan(chan, "", mode, vRange[0], vRange[1], Val_Volts, None)
        val = c_double(0.)
        t.ReadAnalogScalarF64(timeout, byref(val), None)
        return val.value

    def writeDigitalSample(self, chan, value, timeout=10.):
        """Set the value of an AO or DO port"""
        t = self.createTask()
        t.CreateDOChan(chan, "", Val_ChanForAllLines)
        t.WriteDigitalScalarU32(True, timeout, value, None)
        return
        
    def readDigitalSample(self, chan, timeout=10.0):
        """Get the value of an AI port"""
        t = self.createTask()
        t.CreateDIChan(chan, "", Val_ChanForAllLines)
        val = c_ulong(0)
        t.ReadDigitalScalarU32(timeout, byref(val), None)
        return val.value
        
    #def listPorts(self):
        #ports = {'AI': [], 'AO': [], 'DOP': []}

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
    Val_AI: 'AI',
    Val_AO: 'AO',
    Val_DI: 'DI',
    Val_DO: 'DO',
    Val_CI: 'CI',
    Val_CO: 'CO',
}


        

class Task:
    TaskHandle = c_ulong
    
    def __init__(self, nidaq, taskName=""):
        self.handle = Task.TaskHandle(0)
        self.nidaq = nidaq
        self.nidaq.CreateTask(taskName,byref(self.handle))

    def __del__(self):
        self.nidaq.ClearTask(self.handle)

    def __getattr__(self, attr):
        func = getattr(self.nidaq, attr)
        return lambda *args: func(self.handle, *args)

    def __repr__(self):
        return "<Task: %s>" % str(self.GetTaskChannels())

    def start(self):
        #print "starting task.."
        self.nidaq.StartTask(self.handle)
        #print "started."

    def stop(self):
        #print "stopTask", self.getTaskDevices()
        self.nidaq.StopTask(self.handle)

    def isDone(self):
        b = c_ulong()
        self.nidaq.IsTaskDone(self.handle, byref(b))
        return bool(b.value)

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
            if tt in [Val_AI, Val_AO]:
                dtype = float64
            elif tt in [Val_DI, Val_DO]:
                dtype = uint32  ## uint8 / 16 might be sufficient, but don't seem to work anyway.
            else:
                raise Exception("No default dtype for %s tasks." % chTypes[tt])

        buf = empty(shape, dtype=dtype)
        samplesRead = c_long()
        
        ## Determine the correct function name to call based on the dtype requested
        fName = 'Read'
        if tt == Val_AI:
            if dtype == float64:
                fName += 'Analog'
            elif dtype in [int16, uint16, int32, uint32]:
                fName += 'Binary'
            else:
                raise Exception('dtype %s not allowed for AI channels (must be float64, int16, uint16, int32, or uint32)' % str(dtype))
        elif tt == Val_DI:
            if dtype in [uint8, uint16, uint32]:
                fName += 'Digital'
            else:
                raise Exception('dtype %s not allowed for DI channels (must be uint8, uint16, or uint32)' % str(dtype))
        elif tt == Val_CI:
            fName += 'Counter'
        else:
            raise Exception("read() not allowed for this task type (%s)" % chTypes(tt))
            
        fName += dtypes[dtype]

        #print "Reading, looks like %d samples are available" % self.GetReadAvailSampPerChan()
        #print "Reading, looks like %d samples are available" % self.GetReadTotalSampPerChanAcquired()
        #self.SetReadReadAllAvailSamp(True)
        #self.__getattr__(fName)(-1, timeout, Val_GroupByChannel, buf.ctypes.data, buf.size, byref(samplesRead), None)
        #print "Looks like %d samples are available" % samplesRead.value
        #if samplesRead.value < reqSamps:
            #print "Bailing out, not enough samples"
            #return (buf, samplesRead.value)
        
        self.SetReadRelativeTo(Val_FirstSample)
        self.SetReadOffset(0)
        
        
        #print "%s(%s, %s, Val_GroupByChannel, buf.ctypes.data, %d, byref(samplesRead), None)" % (fName, reqSamps, timeout, buf.size)
        
        self.__getattr__(fName)(reqSamps, timeout, Val_GroupByChannel, buf.ctypes.data, buf.size, byref(samplesRead), None)
        return (buf, samplesRead.value)

    def write(self, data, timeout=10.):
        numChans = self.GetTaskNumChans()
        samplesWritten = c_long()
        
        ## Determine the correct write function to call based on dtype and task type
        fName = 'Write'
        tt = self.taskType()
        if tt == Val_AO:
            if data.dtype == float64:
                fName += 'Analog'
            elif data.dtype in [int16, uint16]:
                fName += 'Binary'
            else:
                raise Exception('dtype %s not allowed for AO channels (must be float64, int16, or uint16)' % str(data.dtype))
        elif tt == Val_DO:
            if data.dtype in [uint8, uint16, uint32]:
                fName += 'Digital'
            else:
                raise Exception('dtype %s not allowed for DO channels (must be uint8, uint16, or uint32)' % str(data.dtype))
        else:
            raise Exception("write() not implemented for this task type (%s)" % chTypes[tt])
            
        fName += dtypes[data.dtype]
        self.__getattr__(fName)(data.size / numChans, False, timeout, Val_GroupByChannel, data.ctypes.data, byref(samplesWritten), None)
        return samplesWritten.value

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
        return self.taskType() in [Val_AI, Val_DI]

    def isOutputTask(self):
        return self.taskType() in [Val_AO, Val_DO]


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
                #mode = Val_RSE
            #elif typ in ['di', 'do']:
                #mode = Val_ChanPerLine
        #elif isinstance(mode, basestring):
            #modes = {
                #'rse': Val_RSE,
                #'nrse': Val_NRSE,
                #'diff': Val_Diff,
                #'chanperline': Val_ChanPerLine,
                #'chanforalllines': Val_ChanForAllLines
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
