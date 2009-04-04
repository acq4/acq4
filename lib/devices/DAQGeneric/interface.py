# -*- coding: utf-8 -*-
from lib.devices.Device import *
from lib.util.MetaArray import MetaArray, axis
from numpy import *

class DAQGeneric(Device):
    def __init__(self, dm, config, name):
        self.dm = dm
        self.config = config.copy()
        self.name = name
        ## Do some sanity checks here on the configuration
    
    def createTask(self, cmd):
        return Task(self, cmd)
    
        
    def setHolding(self, mode=None):
        """Set all channel for this device to its configured holding level. If mode is None, then
        the level is chosen based on the current mode of the channel."""
        ### Set correct holding level here...
        pass
        
        
    def devRackInterface(self):
        """Return a widget with a UI to put in the device rack"""
        pass
        
    def protocolInterface(self):
        """Return a widget with a UI to put in the protocol rack"""
        pass

    def quit(self):
        pass

class Task(DeviceTask):
    def __init__(self, dev, cmd):
        self.dev = dev
        self.cmd = cmd

        
    def configure(self, tasks, startOrder):
        self.daqTasks = {}
                
    def createChannels(self, daqTask):
        ## Is this the correct DAQ device for any of my channels?
        ## create needed channels + info
        ## write waveform to command channel if needed
        
        for ch in self.dev.config:
            if ch not in self.cmd:
                continue
            chConf = self.dev.config[ch]
            if chConf['channel'][0] != daqTask.devName():
                continue
            
            daqTask.addChannel(chConf['channel'][1], chConf['type'])
            if chConf['type'] in ['ao', 'do']:
                daqTask.addChannel(self.dev.config['cmd'][1], 'ao')
                
                scale = self.getChanScale(ch)
                cmdData = self.cmd[ch]['command'] * scale
                daqTask.setWaveform(self.dev.config['cmd'][1], cmdData)
                self.cmd[ch].task = daqTask
            else:
                daqTask.addChannel(self.dev.config[ch][1], 'ai')
                self.daqTasks[ch] = daqTask
        
    def getChanScale(self, chan):
        ## Scale defaults to 1.0
        ## - can be overridden in configuration
        ## - can be overridden again in command
        scale = 1.0
        if scale in self.dev.config[chan]:
            scale = self.dev.config[chan]['scale']
        if scale in self.cmd[ch]:
            scale = self.cmd[ch]['scale']
        return scale
        
    def start(self):
        ## possibly nothing required here, DAQ will start recording without our help.
        pass
        
    def isDone(self):
        ## DAQ task handles this for us.
        return True
        
    def getResult(self):
        ## Access data recorded from DAQ task
        ## create MetaArray and fill with MC state info
        #self.state['startTime'] = self.daqTasks[self.daqTasks.keys()[0]].getStartTime()
        
        ## Collect data and info for each channel in the command
        result = {}
        for ch in self.cmd:
            result[ch] = self.cmd[ch].task.getData(self.dev.config[ch][1])
            
            result[ch]['data'] = result[ch]['data'] / self.getChanScale(ch)
            if 'units' in self.dev.config[ch]:
                result[ch]['units'] = self.dev.config[ch]['units']
            else:
                result[ch]['units'] = None
            
        ## Create an array of time values
        meta = result[result.keys()[0]]
        rate = meta['rate']
        nPts = meta['numPts']
        timeVals = linspace(0, float(nPts-1) / float(rate), nPts)
        
        ## Concatenate all channels together into a single array, generate MetaArray info
        chanList = [atleast_2d(result[x]['data']) for x in result]
        cols = [(x, result[x]['units']) for x in result]
        # print cols
        arr = concatenate(chanList)
        info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [{'rate': rate, 'numPts': nPts, 'startTime': meta['startTime']}]
        marr = MetaArray(arr, info=info)
            
        return marr