# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.drivers.MultiClamp.MultiClamp2 import MultiClamp as MultiClampDriver
from lib.devices.Device import *
from lib.util.metaarray import MetaArray, axis
from lib.util.Mutex import Mutex, MutexLocker
from PyQt4 import QtCore
from numpy import *
import sys, traceback
from DeviceGui import *
from protoGUI import *
from lib.util.debug import *

class MultiClamp2(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.index = None
        self.devRackGui = None
        
        self.mc = MultiClampDriver.instance().getChannel(self.config['channelID'])
        
        print "Created MultiClamp device"
    
        self.holding = {
            'VC': -50e-3,
            'IC': 0.0
        }
        if 'vcHolding' in self.config:
            self.holding['VC'] = self.config['vcHolding']
        if 'icHolding' in self.config:
            self.holding['IC'] = self.config['icHolding']

        ## Set up default MC settings for each mode, then leave MC in I=0 mode
        if 'settings' in self.config:
            for mode in ['IC', 'VC']:
                if mode in self.config['settings']:
                    self.setMode(mode)
                    self.mc.setParams(self.config['settings'][mode])
        self.setMode('I=0')  ## safest mode to leave clamp in

    def deviceInterface(self):
        with MutexLocker(self.lock):
            if self.devRackGui is None:
                self.devRackGui = MCRackGui(self)
            return self.devRackGui

    def protocolInterface(self, prot):
        with MutexLocker(self.lock):
            return MultiClampProtoGui(self, prot)

    #def setParams(self, params):
        #with MutexLocker(self.lock):
            #self.mc.setParams(params)
    
    #def getParam(self, param, cache=None):
        #with MutexLocker(self.lock):
            #return self.getParam(param)
    
    def createTask(self, cmd):
        with MutexLocker(self.lock):
            return MultiClampTask(self, cmd)
    
    #def getMode(self):
        #with MutexLocker(self.lock):
            #return self.mc.getMode()
    
    def setHolding(self, mode=None, value=None):
        """Define and set the holding values for this device"""
        #print "setHolding", mode, value
        with MutexLocker(self.lock):
            if mode is not None and value is not None:
                #print "   update holding value"
                self.holding[mode] = value
                
            mode = self.mc.getMode()
            if mode == 'I=0':
                mode = 'IC'
            if mode not in self.holding:
                #print "    mode %s not in %s" % (mode, str(self.holding))
                return
            holding = self.holding[mode]
            daq, chan = self.config['commandChannel'][:2]
            daqDev = self.dm.getDevice(daq)
            scale = self.config['cmdScale'][mode]
            #print "     setChannelValue", chan, holding
            daqDev.setChannelValue(chan, holding*scale, block=False)
        
    def getChanIndex(self):
        """Given a channel name (as defined in the configuration), return the device index to use when making calls to the MC"""
        with MutexLocker(self.lock):
            if self.index is None:
                devs = self.mc.listDevices()
                if self.channelID not in devs:
                    raise Exception("Could not find device on multiclamp with description '%s'" % self.channelID)
                self.index = devs.index(self.channelID)
            return self.index
        
    def listSignals(self, mode):
        return self.mc.listSignals(mode)
        
    #def listModeSignals(self):
        ### Todo: move this upstream to the multiclamp driver (and make it actually correct)
        #with MutexLocker(self.lock):
            #sig = {
                #'primary': {
                    #'IC': ['MembranePotential'],
                    #'I=0': ['MembranePotential'],
                    #'VC': ['MembraneCurrent']
                #},
                #'secondary': {
                    #'IC': ['MembranePotential', 'MembraneCurrent'],
                    #'I=0': ['MembranePotential', 'MembraneCurrent'],
                    #'VC': ['MembraneCurrent', 'MembranePotential']
                #}
            #}
            #return sig
        
    def setMode(self, mode):
        """Set the mode for a multiclamp channel, gracefully switching between VC and IC modes."""
        with MutexLocker(self.lock):
            mode = mode.upper()
            if mode not in ['VC', 'IC', 'I=0']:
                raise Exception('MultiClamp mode "%s" not recognized.' % mode)
            
            mcMode = self.mc.getMode()
            if mcMode == mode:  ## Mode is already correct
                return
                
            ## If switching ic <-> vc, switch to i=0 first
            if (mcMode=='IC' and mode=='VC') or (mcMode=='VC' and mode=='IC'):
                self.mc.setMode('I=0')
                mcMode = 'I=0'
            
            if mcMode=='I=0':
                ## Set holding level before leaving I=0 mode
                self.setHolding()
            
            self.mc.setMode(mode)
            
            ## Clamp should not be used until it has had time to settle after switching modes. (?)
            #self.readyTime = ptime.time() + 0.1

    def getDAQName(self):
        """Return the DAQ name used by this device. (assumes there is only one DAQ for now)"""
        with MutexLocker(self.lock):
            daq, chan = self.config['commandChannel'][:2]
            return daq


class MultiClampTask(DeviceTask):
    recordParams = ['Holding', 'HoldingEnable', 'PipetteOffset', 'FastCompCap', 'SlowCompCap', 'FastCompTau', 'SlowCompTau', 'NeutralizationEnable', 'NeutralizationCap', 'WholeCellCompEnable', 'WholeCellCompCap', 'WholeCellCompResist', 'RsCompEnable', 'RsCompBandwidth', 'RsCompCorrection', 'PrimarySignalGain', 'PrimarySignalLPF', 'PrimarySignalHPF', 'OutputZeroEnable', 'OutputZeroAmplitude', 'LeakSubEnable', 'LeakSubResist', 'BridgeBalEnable', 'BridgeBalResist']
    
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        with MutexLocker(self.dev.lock):
            self.usedChannels = None
            self.daqTasks = {}

            ## Sanity checks and default values for command:
            
            if ('mode' not in self.cmd) or (type(self.cmd['mode']) is not str) or (self.cmd['mode'].upper() not in ['IC', 'VC', 'I=0']):
                raise Exception("Multiclamp command must specify clamp mode (IC, VC, or I=0)")
            self.cmd['mode'] = self.cmd['mode'].upper()
            
            ## If primary and secondary modes are not specified, use default values
            defaultModes = {
                'VC': {'primary': 'MembraneCurrent', 'secondary': 'PipettePotential'},  ## MC700A does not have MembranePotential signal
                'IC': {'primary': 'MembranePotential', 'secondary': 'MembraneCurrent'},
                'I=0': {'primary': 'MembranePotential', 'secondary': None},
            }
            for ch in ['primary', 'secondary']:
                if ch not in self.cmd:
                    self.cmd[ch] = defaultModes[self.cmd['mode']][ch]

            if 'command' not in self.cmd:
                self.cmd['command'] = None

    def configure(self, tasks, startOrder):
        """Sets the state of a remote multiclamp to prepare for a program run."""
        #print "mc configure"
        with MutexLocker(self.dev.lock):
                
            ## Set state of clamp
            self.dev.setMode(self.cmd['mode'])
            if self.cmd['primary'] is not None:
                self.dev.mc.setPrimarySignalByName(self.cmd['primary'])
            if self.cmd['secondary'] is not None:
                self.dev.mc.setSecondarySignalByName(self.cmd['secondary'])
            
            if self.cmd.has_key('parameters'):
                self.dev.mc.setParams(self.cmd['parameters'])
            
            self.state = {}
            if self.cmd.has_key('recordState') and self.cmd['recordState']:
                self.state = self.dev.mc.getParams(MultiClampTask.recordParams)
                
            self.state['primarySignal'] = self.dev.mc.getPrimarySignalInfo()
            self.state['secondarySignal'] = self.dev.mc.getSecondarySignalInfo()
            
            ## set holding level
            if 'holding' in self.cmd:
                self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
            #print "mc configure complete"
        
                
    def getUsedChannels(self):
        """Return a list of the channels this task uses"""
        with MutexLocker(self.dev.lock):
            if self.usedChannels is None:
                self.usedChannels = []
                for ch in ['primary', 'secondary', 'command']:
                    if self.cmd[ch] is not None:
                        self.usedChannels.append(ch)
                        
            return self.usedChannels
        
                
    def createChannels(self, daqTask):
        ## Is this the correct DAQ device for any of my channels?
        ## create needed channels + info
        ## write waveform to command channel if needed
        with MutexLocker(self.dev.lock):
            
            for ch in self.getUsedChannels():
                chConf = self.dev.config[ch+'Channel']
                    
                if chConf[0] == daqTask.devName():
                    if ch == 'command':
                        daqTask.addChannel(chConf[1], 'ao')
                        scale = self.dev.config['cmdScale'][self.cmd['mode']]
                        cmdData = self.cmd['command'] * scale
                        daqTask.setWaveform(chConf[1], cmdData)
                    else:
                        if len(chConf) < 3:
                            mode = 'RSE'
                        else:
                            mode = chConf[2]
                        daqTask.addChannel(chConf[1], 'ai', mode)
                    self.daqTasks[ch] = daqTask
        
    def start(self):
        ## possibly nothing required here, DAQ will start recording.
        pass
        
    def isDone(self):
        ## DAQ task handles this for us.
        return True
        
    def getResult(self):
        ## Access data recorded from DAQ task
        ## create MetaArray and fill with MC state info
        #self.state['startTime'] = self.daqTasks[self.daqTasks.keys()[0]].getStartTime()
        with MutexLocker(self.dev.lock):
            channels = self.getUsedChannels()
            result = {}
            #result['info'] = self.state
            for ch in channels:
                chConf = self.dev.config[ch+'Channel']
                result[ch] = self.daqTasks[ch].getData(chConf[1])
                # print result[ch]
                nPts = result[ch]['info']['numPts']
                rate = result[ch]['info']['rate']
                if ch == 'command':
                    result[ch]['data'] = result[ch]['data'] / self.dev.config['cmdScale'][self.cmd['mode']]
                    result[ch]['name'] = 'Command'
                    if self.cmd['mode'] == 'VC':
                        result[ch]['units'] = 'V'
                    else:
                        result[ch]['units'] = 'A'
                else:
                    scale = 1.0 / self.state[ch + 'Signal'][1]
                    result[ch]['data'] = result[ch]['data'] * scale
                    #if ch == 'secondary':
                        #print scale, result[ch]['data'].max(), result[ch]['data'].min()
                    result[ch]['units'] = self.state[ch + 'Signal'][2]
                    #result[ch]['name'] = self.state[ch + 'Signal'][0]
                    result[ch]['name'] = ch
            # print result
                
            if len(result) == 0:
                return None
                
            ## Copy state from first channel (assume this is the same for all channels)
            firstChInfo = result[channels[0]]['info']
            for k in firstChInfo:
                self.state[k] = firstChInfo[k]
                
            #timeVals = linspace(0, float(self.state['numPts']-1) / float(self.state['rate']), self.state['numPts'])
            timeVals = linspace(0, float(nPts-1) / float(rate), nPts)
            chanList = [atleast_2d(result[x]['data']) for x in result]
            # for l in chanList:
            # print l.shape
            cols = [(result[x]['name'], result[x]['units']) for x in result]
            # print cols
            #print [a.shape for a in chanList]
            try:
                arr = concatenate(chanList)
            except:
                for a in chanList:
                    print a.shape
                raise
            info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [self.state]
            marr = MetaArray(arr, info=info)
                
            return marr
    
    def stop(self):
        with MutexLocker(self.dev.lock):
            ## This is just a bit sketchy, but these tasks have to be stopped before the holding level can be reset.
            for ch in self.daqTasks:
                self.daqTasks[ch].stop()
            self.dev.setHolding()
        
        