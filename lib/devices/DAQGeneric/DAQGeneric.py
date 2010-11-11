# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.Device import *
from metaarray import MetaArray, axis
from lib.util.Mutex import Mutex, MutexLocker
from numpy import *
from protoGUI import *
from debug import *
from SpinBox import *

class DAQGeneric(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self._DGLock = Mutex(QtCore.QMutex.Recursive)
        ## Do some sanity checks here on the configuration
        self._DGConfig = config
        self._DGHolding = {}
        for ch in config:
            if 'scale' not in config[ch]:
                config[ch]['scale'] = 1.0
            #print "chan %s scale %f" % (ch, config[ch]['scale'])
            if 'holding' not in config[ch]:
                config[ch]['holding'] = 0.0
            self._DGHolding[ch] = config[ch]['holding']
        
    
    def createTask(self, cmd):
        return DAQGenericTask(self, cmd)
    
        
    def setChanHolding(self, channel, level=None, scale=None):
        """Define and set the holding values for this channel"""
        with self._DGLock:
            #print "set holding", channel, level
            ### Set correct holding level here...
            if level is None:
                level = self._DGHolding[channel]
                if level is None:
                    raise Exception("No remembered holding level for channel %s" % channel)
            else:
                self._DGHolding[channel] = level
            daq, chan = self._DGConfig[channel]['channel']
            daqDev = self.dm.getDevice(daq)
            if scale is None:
                scale = self.getChanScale(channel)
            #print "set", chan, self._DGHolding[channel]*scale
            val = self._DGHolding[channel]*scale
            daqDev.setChannelValue(chan, val, block=False)
            self.emit(QtCore.SIGNAL('holdingChanged'), channel, val)
        
    def getChanHolding(self, chan):
        with self._DGLock:
            return self._DGHolding[chan]
        
    def getChannelValue(self, channel):
        with self._DGLock:
            chConf = self._DGConfig[channel]['channel']
            daq, chan = chConf[:2]
            mode = None
            if len(chConf) > 2:
                mode = chConf[2]
    
            daqDev = self.dm.getDevice(daq)
            if 'scale' in self._DGConfig[channel]:
                scale = self._DGConfig[channel]['scale']
            else:
                scale = 1.0            
            return daqDev.getChannelValue(chan, mode=mode)/scale

        
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return DAQDevGui(self)
        
    def protocolInterface(self, prot):
        """Return a widget with a UI to put in the protocol rack"""
        return DAQGenericProtoGui(self, prot)

    def getDAQName(self, channel):
        return self._DGConfig[channel]['channel'][0]

    def quit(self):
        pass

    def getChanScale(self, chan):
        with MutexLocker(self._DGLock):
            ## Scale defaults to 1.0
            ## - can be overridden in configuration
            scale = 1.0
            if 'scale' in self._DGConfig[chan]:
                scale = self._DGConfig[chan]['scale']
            return scale

    def getChanUnits(self, ch):
        with MutexLocker(self._DGLock):
            if 'units' in self._DGConfig[ch]:
                return self._DGConfig[ch]['units']
            else:
                return None


    def listChannels(self):
        with self._DGLock:
            return dict([(ch, self._DGConfig[ch].copy()) for ch in self._DGConfig])
            
            

class DAQGenericTask(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.daqTasks = {}
        self.initialState = {}
        self._DAQCmd = cmd
        ## Stores the list of channels that will generate or acquire buffered samples
        self.bufferedChannels = []
        
    def getConfigOrder(self):
        """return lists of devices that should be configured (before, after) this device"""
        daqs = set([self.dev.getDAQName(ch) for ch in self._DAQCmd])
        return ([], list(daqs))  ## this device should be configured before its DAQs
        
    def configure(self, tasks, startOrder):
        ## Record initial state or set initial value
        with MutexLocker(self.dev._DGLock):
            #self.daqTasks = {}
            self.initialState = {}
            for ch in self._DAQCmd:
                dev = self.dev.dm.getDevice(self.dev._DGConfig[ch]['channel'][0])
                if 'preset' in self._DAQCmd[ch]:
                    dev.setChannelValue(self.dev._DGConfig[ch]['channel'][1], self._DAQCmd[ch]['preset'])
                elif 'holding' in self._DAQCmd[ch]:
                    self.dev.setChanHolding(ch, self._DAQCmd[ch]['holding'])
                if 'recordInit' in self._DAQCmd[ch] and self._DAQCmd[ch]['recordInit']:
                    self.initialState[ch] = self.dev.getChannelValue(ch)
                
    def createChannels(self, daqTask):
        self.daqTasks = {}
        #print "createChannels"
        with MutexLocker(self.dev._DGLock):
            ## Is this the correct DAQ device for any of my channels?
            ## create needed channels + info
            ## write waveform to command channel if needed
            
            for ch in self.dev._DGConfig:
                #print "  creating channel %s.." % ch
                if ch not in self._DAQCmd:
                    #print "    ignoring channel", ch, "not in command"
                    continue
                chConf = self.dev._DGConfig[ch]
                if chConf['channel'][0] != daqTask.devName():
                    #print "    ignoring channel", ch, "wrong device"
                    continue
                
                ## Input channels are only used if the command has record: True
                if chConf['type'] in ['ai', 'di']:
                    if ('record' not in self._DAQCmd[ch]) or (not self._DAQCmd[ch]['record']):
                        #print "    ignoring channel", ch, "recording disabled"
                        continue
                    
                ## Output channels are only added if they have a command waveform specified
                elif chConf['type'] in ['ao', 'do']:
                    if 'command' not in self._DAQCmd[ch]:
                        #print "    ignoring channel", ch, "no command"
                        continue
                
                self.bufferedChannels.append(ch)
                #_DAQCmd[ch]['task'] = daqTask  ## ALSO DON't FORGET TO DELETE IT, ASS.
                if chConf['type'] in ['ao', 'do']:
                    scale = self.getChanScale(ch)
                    cmdData = self._DAQCmd[ch]['command']
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
                    mode = None
                    if len(chConf['channel']) > 2:
                        mode = chConf['channel'][2]
                    daqTask.addChannel(chConf['channel'][1], chConf['type'], mode=mode)
                    self.daqTasks[ch] = daqTask  ## remember task so we can stop it later on
                #print "  done: ", self.daqTasks.keys()
        
    def getChanScale(self, chan):
        if 'scale' in self._DAQCmd[chan]:
            return self._DAQCmd[chan]['scale']
        else:
            return self.dev.getChanScale(chan)
        
    def getChanUnits(self, chan):
        if 'units' in self._DAQCmd[chan]:
            return self._DAQCmd[chan]['units']
        else:
            return self.dev.getChanUnits(chan)
    
    def start(self):
        ## possibly nothing required here, DAQ will start recording without our help.
        pass
        
    def isDone(self):
        ## DAQ task handles this for us.
        return True
        
    def stop(self, abort=False):
        with MutexLocker(self.dev._DGLock):
            ## This is just a bit sketchy, but these tasks have to be stopped before the holding level can be reset.
            #print "STOP"
            for ch in self.daqTasks:
                #print "Stop task", ch
                self.daqTasks[ch].stop(abort=abort)
            for ch in self._DAQCmd:
                if 'holding' in self._DAQCmd[ch]:
                    self.dev.setChanHolding(ch, self._DAQCmd[ch]['holding'])
        
    def getResult(self):
        ## Access data recorded from DAQ task
        ## create MetaArray and fill with MC state info
        #self.state['startTime'] = self.daqTasks[self.daqTasks.keys()[0]].getStartTime()
        
        ## Collect data and info for each channel in the command
        #prof = Profiler("  DAQGeneric.getResult")
        result = {}
        #print "buffered channels:", self.bufferedChannels
        for ch in self.bufferedChannels:
            #result[ch] = _DAQCmd[ch]['task'].getData(self.dev.config[ch]['channel'][1])
            result[ch] = self.daqTasks[ch].getData(self.dev._DGConfig[ch]['channel'][1])
            #prof.mark("get data for channel "+str(ch))
            #print "get data", ch, self.getChanScale(ch), result[ch]['data'].max()
            result[ch]['data'] = result[ch]['data'] / self.getChanScale(ch)
            result[ch]['units'] = self.getChanUnits(ch)
            #print "channel", ch, "returned:\n  ", result[ch]
            #prof.mark("scale data for channel "+str(ch))
            #del _DAQCmd[ch]['task']
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
            try:
                arr = concatenate(chanList)
            except:
                print chanList
                print [a.shape for a in chanList]
                raise
            info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [{'rate': rate, 'numPts': nPts, 'startTime': meta['startTime']}]
            marr = MetaArray(arr, info=info)
            #print marr
            #prof.mark("post-process data")
            return marr
            
        else:
            return None
            
    def storeResult(self, dirHandle):
        DeviceTask.storeResult(self, dirHandle)
        for ch in self._DAQCmd:
            if 'recordInit' in self._DAQCmd[ch] and self._DAQCmd[ch]['recordInit']:
                dirHandle.setInfo({(self.dev.name, ch): self.initialState[ch]})
           
                
class DAQDevGui(QtGui.QWidget):
    def __init__(self, dev):
        self.dev = dev
        QtGui.QWidget.__init__(self)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        chans = self.dev.listChannels()
        self.widgets = {}
        row = 0
        for ch in chans:
            l = QtGui.QLabel("%s (%s)" % (ch, chans[ch]['channel'][1]))
            if chans[ch]['type'] == 'ao':
                hw = SpinBox(value=self.dev.getChanHolding(ch))
                QtCore.QObject.connect(hw, QtCore.SIGNAL('valueChanged'), self.spinChanged)
            elif chans[ch]['type'] == 'do':
                hw = SpinBox(value=self.dev.getChanHolding(ch), step=1, bounds=(0,1))
                QtCore.QObject.connect(hw, QtCore.SIGNAL('valueChanged'), self.spinChanged)
            else:
                hw = QtGui.QWidget()
            hw.channel = ch
            self.widgets[ch] = (l, hw)
            self.layout.addWidget(l, row, 0)
            self.layout.addWidget(hw, row, 1)
            row += 1
        QtCore.QObject.connect(self.dev, QtCore.SIGNAL('holdingChanged'), self.holdingChanged)
    
    def holdingChanged(self, ch, val):
        self.widgets[ch][1].blockSignals(True)
        self.widgets[ch][1].setValue(val)
        self.widgets[ch][1].blockSignals(False)
        
    def spinChanged(self, spin):
        ch = spin.channel
        self.dev.setChanHolding(ch, spin.value())
        