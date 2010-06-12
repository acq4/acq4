# -*- coding: utf-8 -*-
from debug import *
try:
    from lib.drivers.nidaq import NIDAQ, SuperTask
except:
    printExc("Error while loading nidaq library; devices will not be available.")
    
from lib.devices.Device import *
import threading, time, traceback, sys
from protoGUI import *
#from numpy import byte
import numpy
#from scipy.signal import resample, bessel, lfilter
import scipy.signal, scipy.ndimage

from lib.util.debug import *

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

    @staticmethod
    def downsample(data, ds, method, **kargs):
        if method == 'subsample':
            data = data[::ds].copy()
        
        elif method == 'mean':
            # decimate by averaging points together (does not remove HF noise, just folds it down.)
            if res['info']['type'] in ['di', 'do']:
                data = NiDAQ.meanResample(data, ds, binary=True)
            else:
                data = NiDAQ.meanResample(data, ds)
            
        elif method == 'fourier':            
            # Decimate using fourier resampling -- causes ringing artifacts, very slow to compute (possibly uses butterworth filter?)
            newLen = int(data.shape[0] / ds)
            data = scipy.signal.resample(data, newLen, window=8) # Use a kaiser window with beta=8
        
        elif method == 'bessel_mean':
            # Lowpass, then average. Bessel filter has less efficient lowpass characteristics and filters some of the passband as well.
            data = NiDAQ.lowpass(data, 2.0/ds, filter='bessel', order=4, bidir=True)
            data = NiDAQ.meanResample(data, ds)
        
        elif method == 'butterworth_mean':
            # Lowpass, then average. Butterworth filter causes ringing artifacts.
            data = NiDAQ.lowpass(data, 1.0/ds, bidir=True, filter='butterworth')
            data = NiDAQ.meanResample(data, ds)
        
        elif method == 'lowpass_mean':
            # Lowpass, then average. (for testing)
            data = NiDAQ.lowpass(data, **kargs)
            data = NiDAQ.meanResample(data, ds)
        
        return data
        
    @staticmethod
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
    
    @staticmethod
    def lowpass(data, cutoff, order=4, bidir=True, filter='bessel', stopCutoff=None, gpass=1., gstop=60., samplerate=None):
        """Bi-directional bessel/butterworth lowpass filter"""
        if samplerate is not None:
            cutoff /= 0.5*samplerate
            if stopCutoff is not None:
                stopCutoff /= 0.5*samplerate
        
        if filter == 'bessel':
            ## How do we compute Wn?
            ### function determining magnitude transfer of 4th-order bessel filter
            #from scipy.optimize import fsolve

            #def m(w):  
                #return 105. / (w**8 + 10*w**6 + 135*w**4 + 1575*w**2 + 11025.)**0.5
            #v = fsolve(lambda x: m(x)-limit, 1.0)
            #Wn = cutoff / (sampr*v)
            b,a = scipy.signal.bessel(order, cutoff, btype='low') 
        elif filter == 'butterworth':
            if stopCutoff is None:
                stopCutoff = cutoff * 2.0
            ord, Wn = scipy.signal.buttord(cutoff, stopCutoff, gpass, gstop)
            print "butterworth ord %f   Wn %f   c %f   sc %f" % (ord, Wn, cutoff, stopCutoff)
            b,a = scipy.signal.butter(ord, Wn, btype='low') 
        else:
            raise Exception('Unknown filter type "%s"' % filter)
            
        padded = numpy.hstack([data[:100], data, data[-100:]])   ## can we intelligently decide how many samples to pad with?

        if bidir:
            data = scipy.signal.lfilter(b, a, scipy.signal.lfilter(b, a, padded)[::-1])[::-1][100:-100]  ## filter twice; once forward, once reversed. (This eliminates phase changes)
        else:
            data = scipy.signal.lfilter(b, a, padded)[100:-100]
        return data



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
        data = res['data']
        
        if 'denoiseMethod' in self.cmd:
            method = self.cmd['denoiseMethod']
            if method == 'None':
                pass
            elif method == 'Pointwise':
                width = self.cmd['denoiseWidth']
                thresh = self.cmd['denoiseThreshold']
                
                res['info']['denoiseMethod'] = method
                res['info']['denoiseWidth'] = width
                res['info']['denoiseThreshold'] = threshold
                pass  ## denoise here
            else:
                printExc("Unknown denoise method '%s'" % str(method))
            
            
        if 'downsample' in self.cmd:
            ds = self.cmd['downsample']
        else:
            ds = 1
            
        if 'filterMethod' in self.cmd:
            method = self.cmd['filterMethod']
            
            fScale = 0.5 * res['info']['rate'] / ds
            
            if method == 'None':
                pass
            #elif method == 'gaussian':
                #width = self.cmd['gaussianWidth']
                
                #data = scipy.ndimage.gaussian_filter(data, width)
                
                #res['info']['filterMethod'] = method
                #res['info']['filterWidth'] = width
            elif method == 'bessel':
                cutoff = self.cmd['besselCutoff']
                order = self.cmd['besselOrder']
                
                data = NiDAQ.lowpass(data, filter='bessel', cutoff=cutoff*fScale, order=order, samplerate=res['info']['rate'])
                
                res['info']['filterMethod'] = method
                res['info']['filterCutoff'] = cutoff
                res['info']['filterOrder'] = order
            elif method == 'butterworth':
                passF = self.cmd['butterworthPassband']
                stopF = self.cmd['butterworthStopband']
                passDB = self.cmd['butterworthPassDB']
                passDB = self.cmd['butterworthStopDB']
                
                data = NiDAQ.lowpass(data, filter='butterworth', cutoff=passF*fScale, stopCutoff=stopF*fScale, gpass=passDB, gstop=stopDB, samplerate=res['info']['rate'])
                
                res['info']['filterMethod'] = method
                res['info']['filterPassband'] = passF
                res['info']['filterStopband'] = stopF
                res['info']['filterPassbandDB'] = passDB
                res['info']['filterStopbandDB'] = stopDB
                
            else:
                printExc("Unknown filter method '%s'" % str(method))
                
        
        if ds > 1:
        
            if res['info']['type'] in ['di', 'do']:
                res['data'] = (res['data'] > 0).astype(numpy.byte)
                dsMethod = 'subsample'
                data = data[::ds]
                res['info']['downsampling'] = ds
                res['info']['downsampleMethod'] = 'subsample'
                res['info']['rate'] = res['info']['rate'] / ds
            elif res['info']['type'] in ['ai', 'ao']:
                data = NiDAQ.meanResample(data, ds)
                res['info']['downsampling'] = ds
                res['info']['downsampleMethod'] = 'mean'
                res['info']['rate'] = res['info']['rate'] / ds
            else:
                dsMethod = None
                
        res['data'] = data
        res['info']['numPts'] = data.shape[0]
                
        return res
        
    def devName(self):
        return self.dev.name
        



