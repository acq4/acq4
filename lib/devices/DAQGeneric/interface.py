# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.Device import *
from lib.util.MetaArray import MetaArray, axis
from lib.util.Mutex import Mutex, MutexLocker
from numpy import *
from protoGUI import *

class DAQGeneric(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        ## Do some sanity checks here on the configuration
        
        self.holding = {}
        for ch in config:
            if 'scale' not in config[ch]:
                config[ch]['scale'] = 1.0
            #print "chan %s scale %f" % (ch, config[ch]['scale'])
            self.holding[ch] = None
        
    
    def createTask(self, cmd):
        return DAQGenericTask(self, cmd)
    
        
    def setHolding(self, channel, level=None):
        """Define and set the holding values for this channel"""
        with MutexLocker(self.lock):
            #print "set holding", channel, level
            ### Set correct holding level here...
            if level is not None:
                self.holding[channel] = level
            if self.holding[channel] is None:
                return
            daq, chan = self.config[channel]['channel']
            daqDev = self.dm.getDevice(daq)
            scale = self.config[channel]['scale']
            daqDev.setChannelValue(chan, self.holding[channel]*scale, block=False)
        
        
    #def devRackInterface(self):
        #"""Return a widget with a UI to put in the device rack"""
        #pass
        
    def protocolInterface(self, prot):
        """Return a widget with a UI to put in the protocol rack"""
        return DAQGenericProtoGui(self, prot)

    def getDAQName(self, channel):
        return self.config[channel]['channel'][0]

    def quit(self):
        pass

class DAQGenericTask(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.daqTasks = {}
        self.initialState = {}
        
        ## Stores the list of channels that will generate or acquire buffered samples
        self.bufferedChannels = []
        
    def configure(self, tasks, startOrder):
        ## Record initial state or set initial value
        with MutexLocker(self.dev.lock):
            #self.daqTasks = {}
            self.initialState = {}
            for ch in self.cmd:
                dev = self.dev.dm.getDevice(self.dev.config[ch]['channel'][0])
                if 'preset' in self.cmd[ch]:
                    dev.setChannelValue(self.dev.config[ch]['channel'][1], self.cmd[ch]['preset'])
                elif 'holding' in self.cmd[ch]:
                    self.dev.setHolding(ch, self.cmd[ch]['holding'])
                if 'recordInit' in self.cmd[ch] and self.cmd[ch]['recordInit']:
                    self.initialState[ch] = self.dev.getChannelValue(ch)
                
    def createChannels(self, daqTask):
        self.daqTasks = {}
        #print "createChannels"
        with MutexLocker(self.dev.lock):
            ## Is this the correct DAQ device for any of my channels?
            ## create needed channels + info
            ## write waveform to command channel if needed
            
            for ch in self.dev.config:
                #print "  creating channel %s.." % ch
                if ch not in self.cmd:
                    #print "    ignoring channel", ch, "not in command"
                    continue
                chConf = self.dev.config[ch]
                if chConf['channel'][0] != daqTask.devName():
                    #print "    ignoring channel", ch, "wrong device"
                    continue
                
                ## Input channels are only used if the command has record: True
                if chConf['type'] in ['ai', 'di']:
                    if ('record' not in self.cmd[ch]) or (not self.cmd[ch]['record']):
                        #print "    ignoring channel", ch, "recording disabled"
                        continue
                    
                ## Output channels are only added if they have a command waveform specified
                elif chConf['type'] in ['ao', 'do']:
                    if 'command' not in self.cmd[ch]:
                        #print "    ignoring channel", ch, "no command"
                        continue
                
                self.bufferedChannels.append(ch)
                #self.cmd[ch]['task'] = daqTask  ## ALSO DON't FORGET TO DELETE IT, ASS.
                if chConf['type'] in ['ao', 'do']:
                    scale = self.getChanScale(ch)
                    cmdData = self.cmd[ch]['command']
                    if cmdData is None:
                        #print "No command for channel %s, skipping." % ch
                        continue
                    cmdData = cmdData * scale
                    if chConf['type'] == 'do':
                        cmdData = cmdData.astype(uint32)
                        cmdData[cmdData<=0] = 0
                        cmdData[cmdData>0] = 0xFFFFFFFF
                    #print "channel", chConf['channel'][1], cmdData
                    daqTask.addChannel(chConf['channel'][1], chConf['type'])
                    self.daqTasks[ch] = daqTask  ## remember task so we can stop it later on
                    daqTask.setWaveform(chConf['channel'][1], cmdData)
                else:
                    daqTask.addChannel(chConf['channel'][1], chConf['type'])
                    self.daqTasks[ch] = daqTask  ## remember task so we can stop it later on
                #print "  done: ", self.daqTasks.keys()
        
    def getChanScale(self, chan):
        with MutexLocker(self.dev.lock):
            ## Scale defaults to 1.0
            ## - can be overridden in configuration
            ## - can be overridden again in command
            scale = 1.0
            if 'scale' in self.dev.config[chan]:
                scale = self.dev.config[chan]['scale']
            if 'scale' in self.cmd[chan]:
                scale = self.cmd[chan]['scale']
            return scale
        
    def start(self):
        ## possibly nothing required here, DAQ will start recording without our help.
        pass
        
    def isDone(self):
        ## DAQ task handles this for us.
        return True
        
    def stop(self, abort=False):
        with MutexLocker(self.dev.lock):
            ## This is just a bit sketchy, but these tasks have to be stopped before the holding level can be reset.
            #print "STOP"
            for ch in self.daqTasks:
                #print "Stop task", ch
                self.daqTasks[ch].stop(abort=abort)
            for ch in self.cmd:
                if 'holding' in self.cmd[ch]:
                    self.dev.setHolding(ch, self.cmd[ch]['holding'])
        
    def getResult(self):
        ## Access data recorded from DAQ task
        ## create MetaArray and fill with MC state info
        #self.state['startTime'] = self.daqTasks[self.daqTasks.keys()[0]].getStartTime()
        
        ## Collect data and info for each channel in the command
        result = {}
        #print "buffered channels:", self.bufferedChannels
        for ch in self.bufferedChannels:
            #result[ch] = self.cmd[ch]['task'].getData(self.dev.config[ch]['channel'][1])
            result[ch] = self.daqTasks[ch].getData(self.dev.config[ch]['channel'][1])
            result[ch]['data'] = result[ch]['data'] / self.getChanScale(ch)
            if 'units' in self.dev.config[ch]:
                result[ch]['units'] = self.dev.config[ch]['units']
            else:
                result[ch]['units'] = None
            #del self.cmd[ch]['task']
        #print "RESULT:", result    
        ## Todo: Add meta-info about channels that were used but unbuffered
        
        
        if len(result) > 0:
            meta = result[result.keys()[0]]['info']
            #print meta
            rate = meta['rate']
            nPts = meta['numPts']
            ## Create an array of time values
            timeVals = linspace(0, float(nPts-1) / float(rate), nPts)
            
            ## Concatenate all channels together into a single array, generate MetaArray info
            chanList = [atleast_2d(result[x]['data']) for x in result]
            cols = [(x, result[x]['units']) for x in result]
            # print cols
            arr = concatenate(chanList)
            info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [{'rate': rate, 'numPts': nPts, 'startTime': meta['startTime']}]
            marr = MetaArray(arr, info=info)
            #print marr    
            return marr
            
        else:
            return None
            
    def storeResult(self, dirHandle):
        DeviceTask.storeResult(self, dirHandle)
        for ch in self.cmd:
            if 'recordInit' in self.cmd[ch] and self.cmd[ch]['recordInit']:
                dirHandle.setAttribute((self.dev.name, ch), self.initialState[ch])
           