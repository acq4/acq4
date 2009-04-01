# -*- coding: utf-8 -*-
from lib.drivers.nidaq import NIDAQ, SuperTask
from lib.devices.Device import *


class NiDAQ(Device):
    def __init__(self, dm, config, name):
        self.dm = dm
        self.config = config
        self.name = name
        ## make local copy of device handle
        self.n = NIDAQ
        print "Created NiDAQ handle, devices are %s" % repr(self.n.listDevices())
    
    def createTask(self, cmd):
        return Task(self, cmd)
        


class Task(DeviceTask):
    def __init__(self, dev, cmd):
        self.dev = dev
        self.cmd = cmd
        
        ## get DAQ device
        #daq = self.devm.getDevice(...)
        
        
        ## Create supertask from nidaq driver
        self.st = SuperTask(self.dev.n)
        
    def configure(self, tasks, startOrder):
        
        ## Request to all devices that they create the channels they use on this task
        for dName in tasks:
            if hasattr(tasks[dName], 'createChannels'):
                tasks[dName].createChannels(self)
        
        ## Determine the sample clock source, configure tasks
        self.st.configureClocks(rate=self.cmd['rate'], nPts=self.cmd['numPts'])

        ## Determine how the protocol will be triggered
        if 'triggerChan' in self.cmd:
            self.st.setTrigger(trigger)
        elif 'triggerDevice' in self.cmd:
            tDev = self.dev.dm.getDevice(self.cmd['triggerDevice'])
            self.st.setTrigger(tDev.getTriggerChannel())
        
    def addChannel(self, *args, **kwargs):
        return self.st.addChannel(*args, **kwargs)
        
    def setWaveform(self, *args, **kwargs):
        return self.st.setWaveform(*args, **kwargs)
        
    def reserve(self):
        pass
        
    def start(self):
        self.st.start()
        
    def isDone(self):
        return self.st.isDone()
        
    def stop(self):
        self.st.stop(wait=True)
        
    def release(self):
        pass
        
    def getResult(self):
        ## Results should be collected by individual devices
        return None
        
        ### Make sure all tasks are finished
        #while not self.st.isDone():
            #time.sleep(10e-6)
        
        ### Read data from input tasks
        #data = self.st.getAllData()
        
        #self.st.stop()
        
    def getData(self, channel):
        """Return the data collected for a specific channel. Return looks like:
        {
          'data': ndarray,
          'info': {'rate': xx, 'nPts': xx, ...}
        }
        """
        
        res = self.st.getResult(channel)
        # if type(res['info']) is not dict:
          # res['info'] = {'info': res['info']}
        # res['info'] = {}
        # res['info']['rate'] = self.cmd['rate']
        # res['info']['nPts'] = self.cmd['numPts']
        # res['info']['time'] = self.st.startTime
        return res
        
    def devName(self):
        return self.dev.name