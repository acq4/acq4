# -*- coding: utf-8 -*-
import sys, time
import numpy as np

class MockNIDAQ:
    def __init__(self):
        #self.data = mockdata.getMockData('cell')
        #self.data = hstack([self.data, self.data])
        self.sampleRate = 20000.
        self.loopTime = 20.
        self.dataPtr = 0.0
        self.devName = 'MockDev0'
        self.aiChans = {'ai0': 0, 'ai1': 0, 'ai2': 0, 'ai3': 0}
        self.aoChans = {'ao0': 0, 'ao1': 0, 'ao2': 0, 'ao3': 0}
    
    def __getattr__(self, attr):
        return lambda *args: self
    
    def listDevices(self):
        return [self.devName]
    
    #def getDevice(self, ind):
        #return self.devName


    def createTask(self, *args):
        return self
    
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
        
    def stop(self):
        pass

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

    def listAIChannels(self, dev):
        return self.devs[dev].listAIChannels()
    
    def listAOChannels(self, dev):
        return self.devs[dev].listAOChannels()


    def listDILines(self, dev):
        return self.GetDevDILines(dev).split(", ")

    def listDIPorts(self, dev):
        return self.GetDevDIPorts(dev).split(", ")

    def listDOLines(self, dev):
        return self.GetDevDOLines(dev).split(", ")

    def listDOPorts(self, dev):
        return self.GetDevDOPorts(dev).split(", ")
    

class Task:
    pass


class SuperTask:
    pass

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

#sys.modules[__name__] = ModWrapper(sys.modules[__name__])
