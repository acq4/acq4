# -*- coding: utf-8 -*-
from lib.drivers.nidaq import NIDAQ, SuperTask
from lib.devices.Device import *
import threading, time, traceback, sys
from protoGUI import *
#from numpy import byte
import numpy
#from scipy.signal import resample, bessel, lfilter
import scipy.signal
from lib.util.debug import *
from debug import *

class NiDAQ(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        ## make local copy of device handle
        self.n = NIDAQ
        print "Created NiDAQ handle, devices are %s" % repr(self.n.listDevices())
        self.lock = threading.RLock()
    
    def createTask(self, cmd):
        return Task(self, cmd)
        
    def setChannelValue(self, chan, value, block=False):
        self.reserve(block=block)
        #print "Setting channel %s to %f" % (chan, value)
        try:
            if 'ao' in chan:
                self.n.writeAnalogSample(chan, value)
            else:
                if value is True or value == 1:
                    value = 0xFFFFFFFF
                else:
                    value = 0
                self.n.writeDigitalSample(chan, value)
        except:
            printExc("Error while setting channel %s to %s:" % (chan, str(value)))
        finally:
            self.release()
        
    def getChannelValue(self, chan):
        self.reserve(block=True)
        #print "Setting channel %s to %f" % (chan, value)
        try:
            if 'ai' in chan:
                val = self.n.readAnalogSample(chan)
            else:
                val = self.n.readDigitalSample(chan)
                if val <= 0:
                    val = 0
                else:
                    val = 1
        except:
            printExc("Error while setting channel %s to %s:" % (chan, str(value)))
            raise
        finally:
            self.release()
        return val
        
    def protocolInterface(self, prot):
        return NiDAQProto(self, prot)
        
    #def listTriggerPorts(self):
        #p = self.n.listDILines()
        #return [x for x in p if 'PFI' in x]

class Task(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        
        ## get DAQ device
        #daq = self.devm.getDevice(...)
        
        
        ## Create supertask from nidaq driver
        self.st = SuperTask(self.dev.n)
        
    def configure(self, tasks, startOrder):
        #print "daq configure", tasks
        ## Request to all devices that they create the channels they use on this task
        for dName in tasks:
            #print "Requesting %s create channels" % dName
            if hasattr(tasks[dName], 'createChannels'):
                tasks[dName].createChannels(self)
        
        ## If no devices requested buffered operations, then do not configure clock.
        ## This might eventually cause some triggering issues..
        if not self.st.hasTasks():
            return
        
        ## Determine the sample clock source, configure tasks
        self.st.configureClocks(rate=self.cmd['rate'], nPts=self.cmd['numPts'])

        ## Determine how the protocol will be triggered
        if 'triggerChan' in self.cmd:
            self.st.setTrigger(trigger)
        elif 'triggerDevice' in self.cmd:
            tDev = self.dev.dm.getDevice(self.cmd['triggerDevice'])
            self.st.setTrigger(tDev.getTriggerChannel(self.dev.name))
        #print "daq configure complete"
        
    def addChannel(self, *args, **kwargs):
        #print "Adding channel:", args
        return self.st.addChannel(*args, **kwargs)
        
    def setWaveform(self, *args, **kwargs):
        return self.st.setWaveform(*args, **kwargs)
        
    def start(self):
        if self.st.hasTasks():
            self.st.start()
        
    def isDone(self):
        if self.st.hasTasks():
            return self.st.isDone()
        else:
            return True
        
        
    def stop(self, wait=False, abort=False):
        if self.st.hasTasks():
            #print "stopping ST..."
            self.st.stop(wait=wait, abort=abort)
            #print "   ST stopped"
        
    def getResult(self):
        ## Results should be collected by individual devices using getData
        return None
        
    def storeResult(self, dirHandle):
        pass
        
    def getData(self, channel):
        """Return the data collected for a specific channel. Return looks like:
        {
          'data': ndarray,
          'info': {'rate': xx, 'numPts': xx, ...}
        }
        """
        #prof = Profiler("    NiDAQ.getData")
        res = self.st.getResult(channel)
        if 'downsample' in self.cmd:
            ds = self.cmd['downsample']
        else:
            ds = 1
            
        if res['info']['type'] in ['di', 'do']:
            res['data'] = (res['data'] > 0).astype(numpy.byte)
            dsMethod = 0
        elif res['info']['type'] == 'ao':
            dsMethod = 1
        else:
            dsMethod = 4
            
        #prof.mark("1")
        if ds > 1:
            data = res['data']
            
                
        return res
        
    def devName(self):
        return self.dev.name
        
    def downsample(self, data, method):
        ## method 0: subsampling
        if dsMethod == 0:
            data = data[::ds].copy()
        
        ## Method 1:
        elif dsMethod == 1:
            # decimate by averaging points together (does not remove HF noise, just folds it down.)
            if res['info']['type'] in ['di', 'do']:
                data = self.meanResample(data, ds, binary=True)
            else:
                data = self.meanResample(data, ds)
                
            #newLen = int(data.shape[0] / ds) * ds
            #data = data[:newLen]
            #data.shape = (data.shape[0]/ds, ds)
            #if res['info']['type'] in ['di', 'do']:
                #data = data.mean(axis=1).round().astype(byte)
            #else:
                #data = data.mean(axis=1)
            
        ## Method 2:
        elif dsMethod == 2:            
            # Decimate using fourier resampling -- causes ringing artifacts.
            newLen = int(data.shape[0] / ds)
            data = scipy.signal.resample(data, newLen, window=8) # Use a kaiser window with beta=8
        
        # Method 3: Lowpass, then average down
        elif dsMethod == 3:
            data = self.lowpass(data, 0.5/ds, order=4, bidir=True)
            data = self.meanResample(data, ds)
        
        return data
            
        res['data'] = data
        res['info']['numPts'] = data.shape[0]
        res['info']['downsampling'] = ds
        res['info']['rate'] = res['info']['rate'] / ds
        #prof.mark("downsample data")
        
    def meanResample(data, ds, binary=False):
        """Resample data by taking mean of ds samples at a time"""
        newLen = int(data.shape[0] / ds) * ds
        data = data[:newLen]
        data.shape = (data.shape[0]/ds, ds)
        if binary:
            data = data.mean(axis=1).round().astype(numpy.byte)
        else:
            data = data.mean(axis=1)
        return data
    
    def lowpass(self, data, cutoff, order=4, bidir=True):
        """Bi-directional bessel lowpass filter"""
        b,a = scipy.signal.bessel(order, 2.0/ds, btype='low') 
        padded = numpy.hstack([data[:100], data, data[-100:]])   ## can we intelligently decide how many samples to pad with?

        if bidir:
            data = scipy.signal.lfilter(b, a, scipy.signal.lfilter(b, a, padded)[::-1])[::-1][100:-100]  ## filter twice; once forward, once reversed. (This eliminates phase changes)
        else:
            data = scipy.signal.lfilter(b, a, padded)[100:-100]
        return data



