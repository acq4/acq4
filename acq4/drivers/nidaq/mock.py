# -*- coding: utf-8 -*-
from __future__ import print_function
import six
import sys, time, os
import numpy as np
import acq4.util.clibrary as clibrary
import ctypes
modDir = os.path.dirname(__file__)
headerFiles = [os.path.join(modDir, "NIDAQmx.h")]
cacheFile = os.path.join(modDir, 'NIDAQmx_headers_%s.cache' % sys.platform)   

DEFS = clibrary.CParser(headerFiles, cache=cacheFile, types={'__int64': ('long long')}, verbose=False)

from . import SuperTask

class MockNIDAQ:
    def __init__(self):
        self.lib = clibrary.CLibrary(None, DEFS, prefix='DAQmx_')
        #self.data = mockdata.getMockData('cell')
        #self.data = hstack([self.data, self.data])
        #self.sampleRate = 20000.
        #self.loopTime = 20.
        #self.dataPtr = 0.0
        self.devs = {
            'Dev1': {
                'aiChans': {'/Dev1/ai0': 0, '/Dev1/ai1': 0, '/Dev1/ai2': 0, '/Dev1/ai3': 0},
                'aoChans': {'/Dev1/ao0': 0, '/Dev1/ao1': 0, '/Dev1/ao2': 0, '/Dev1/ao3': 0},
                'ports': {'/Dev1/port0': 0},
                'lines': {'/Dev1/port0/line0': 0, '/Dev1/port0/line1': 0, '/Dev1/port0/line2': 0, '/Dev1/port0/line3': 0,},
            }
        }
        self.clocks = {}

    def __getattr__(self, attr):
        return getattr(self.lib, attr)

    def listAIChannels(self, dev):
        return list(self.devs[dev]['aiChans'].keys())
    
    def listAOChannels(self, dev):
        return list(self.devs[dev]['aoChans'].keys())

    def listDILines(self, dev):
        return list(self.devs[dev]['lines'].keys())

    def listDIPorts(self, dev):
        return list(self.devs[dev]['ports'].keys())

    def listDOLines(self, dev):
        return list(self.devs[dev]['lines'].keys())

    def listDOPorts(self, dev):
        return list(self.devs[dev]['ports'].keys())
    
    def listDevices(self):
        return list(self.devs.keys())

    def createTask(self, *args):
        return self
    
    def createSuperTask(self):
        return SuperTask.SuperTask(self)
    
    def start(self):
        self.dataPtr = time.time()
    
    def read(self, size):
        #dataLen = size / self.sampleRate
        #dataEnd = self.dataPtr + dataLen
        #now = time.time()
        #if dataEnd > now:
            #time.sleep(dataEnd-now)
        #start = int((self.dataPtr % self.loopTime) * self.sampleRate)
        #stop = int(start + size)
        #self.dataPtr = dataEnd
        ##print "read", start, stop
        ##print "DAQ Returning %d:%d at %f" % (start, stop, time.time())
        #return (self.data[:, start:stop], size)
        return np.zeros(size)
    
    def GetReadAvailSampPerChan(self):
        return self.sampleRate * (time.time() - self.dataPtr)

    def createTask(self):
        return Task(self)

    def interpretMode(self, mode):
        modes = {
            'rse': self.lib.Val_RSE,
            'nrse': self.lib.Val_NRSE,
            'diff': self.lib.Val_Diff,
            'chanperline': self.lib.Val_ChanPerLine,
            'chanforalllines': self.lib.Val_ChanForAllLines
        }
        if isinstance(mode, six.string_types):
            mode = mode.lower()
            mode = modes.get(mode, None)
        return mode
    
    def interpretChannel(self, chan):

        parts = chan.lstrip('/').split('/')
        dev = parts.pop(0)
        if len(parts) == 1 and parts[0].startswith('line'):
            # normalize "/Dev1/line0' => ('Dev1', 'port0/line0')
            chan = 'port0/' + parts[0]
        else:
            chan = '/'.join(parts)
        return dev, chan

    def writeAnalogSample(self, chan, value, vRange=[-10., 10.], timeout=10.0):
        """Set the value of an AO or DO port"""
        t = self.createTask()
        t.CreateAOVoltageChan(chan, "", vRange[0], vRange[1], self.lib.Val_Volts, None)
        #t.WriteAnalogScalarF64(True, timeout, value, None)
        
    def readAnalogSample(self, chan, mode=None, vRange=[-10., 10.], timeout=10.0):
        """Get the value of an AI port"""
        if mode is None:
            mode = self.lib.Val_Cfg_Default
        else:
            mode = self.interpretMode(mode)
        t = self.createTask()
        t.CreateAIVoltageChan(chan, "", mode, vRange[0], vRange[1], self.lib.Val_Volts, None)
        #val = ctypes.c_double(0.)
        #t.ReadAnalogScalarF64(timeout, byref(val), None)
        #return val.value
        return 0.0

    def writeDigitalSample(self, chan, value, timeout=10.):
        """Set the value of an AO or DO port"""
        dev, chan = self.interpretChannel(chan)
        chan = '/%s/%s' % (dev, chan)
        self.devs[dev]['lines'][chan] = value
        # t = self.createTask()
        # t.CreateDOChan(chan, "", self.lib.Val_ChanForAllLines)
        #t.WriteDigitalScalarU32(True, timeout, value, None)
        
    def readDigitalSample(self, chan, timeout=10.0):
        """Get the value of an AI port"""
        dev, chan = self.interpretChannel(chan)
        chan = '/%s/%s' % (dev, chan)
        return self.devs[dev]['lines'][chan]
        # t = self.createTask()
        # t.CreateDIChan(chan, "", self.lib.Val_ChanForAllLines)
        # val = ctypes.c_ulong(0)
        # t.ReadDigitalScalarU32(timeout, byref(val), None)
        # return val.value

    def startClock(self, clock, duration):
        self.clocks[clock] = (time.time(), duration)

    def stopClock(self, clock):
        if clock not in self.clocks:
            return
        now = time.time()
        start, dur = self.clocks[clock]
        diff = (start+dur)-now
        if diff > 0:
            time.sleep(diff)

    def checkClock(self, clock):
        now = time.time()
        start, dur = self.clocks[clock]
        diff = (start+dur)-now
        return diff <= 0


class Task:
    def __init__(self, nd):
        self.nd = nd
        self.chans = []
        self.chOpts = []
        self.clock = None
        self.nativeClock = None
        self.data = None
        self.mode = None
        
    #def __getattr__(self, attr):
        #return lambda *args: self
    
    def CreateAIVoltageChan(self, *args, **kargs):
        self.chans.append(args[0])
        self.chOpts.append(kargs)
        self.mode = 'ai'
        
    def CreateAOVoltageChan(self, *args, **kargs):
        self.chans.append(args[0])
        self.chOpts.append(kargs)
        self.mode = 'ao'
        
    def CreateDIChan(self, *args, **kargs):
        self.chans.append(args[0])
        self.chOpts.append(kargs)
        self.mode = 'di'
        
    def CreateDOChan(self, *args, **kargs):
        self.chans.append(args[0])
        self.chOpts.append(kargs)
        self.mode = 'do'
        
    def CfgSampClkTiming(self, clock, rate, b, c, nPts):
        if 'ai' in self.chans[0]:
            self.nativeClock = self.device()+'/ai/SampleClock'
        elif 'ao' in self.chans[0]:
            self.nativeClock = self.device()+'/ao/SampleClock'
            
        if clock == '':
            clock = None
        self.clock = clock 
        self.rate = rate 
        self.nPts = nPts
        #print self.chans, self.clock
        
    def GetSampClkMaxRate(self):
        return 2e6
        
    def device(self):
        return '/'+self.chans[0].split('/')[1]
        
    def write(self, data):
        self.data = data
        
        ## Send data off to callbacks if they were specified
        #print "write:", self.chOpts
        for i in range(len(self.chOpts)):
            if 'mockFunc' in self.chOpts[i]:
                self.chOpts[i]['mockFunc'](data[i], 1.0/self.rate)  
        
        return len(data)
        
    def read(self):
        dur = self.nPts / self.rate
        tVals = np.linspace(0, dur, self.nPts)
        if 'd' in self.mode:
            data = np.empty((len(self.chans), self.nPts), dtype=np.int32)
        else:
            data = np.empty((len(self.chans), self.nPts))
            
        for i in range(len(self.chOpts)):
            if 'mockFunc' in self.chOpts[i]:
                data[i] = self.chOpts[i]['mockFunc']()
            else:
                data[i] = 0
        return (data, self.nPts)

    def start(self):
        ## only start clock if it matches the native clock for this channel
        if self.clock is None or self.clock == self.nativeClock:
            dur = self.nPts / self.rate
            self.nd.startClock(self.nativeClock, dur)
        
        
    def stop(self):        
        if self.clock is None:
            self.nd.stopClock(self.nativeClock)
        else:
            self.nd.stopClock(self.clock)

    def isDone(self):
        if self.clock is None:
            return self.nd.checkClock(self.nativeClock)
        else:
            return self.nd.checkClock(self.clock)
        

    def GetTaskNumChans(self):
        return len(self.chans)
        
    def isOutputTask(self):
        return self.mode in ['ao', 'do']
        
    def isInputTask(self):
        return self.mode in ['ai', 'di']
        
    def TaskControl(self, *args):
        pass

    def WriteAnalogScalarF64(self, a, timeout, val, b):
        pass
    
    def WriteDigitalScalarU32(self, a, timeout, val, b):
        pass
    

#class SuperTask:
    #def __init__(self, nd):
        #self.nd = nd

    #def __getattr__(self, attr):
        #print "SuperTask."+attr
        #return lambda *args, **kargs: self


NIDAQ = MockNIDAQ()


#class ModWrapper(object):
    #def __init__(self, wrapped):
        #self.wrapped = wrapped

    #def __getattr__(self, name):
        #try:
            #return getattr(self.wrapped, name)
        #except AttributeError:
            #if name[:3] == 'Val':
                #return None
            #else:
                #return lambda *args: NIDAQ

    #def __iter__

#sys.modules[__name__] = ModWrapper(sys.modules[__name__])
