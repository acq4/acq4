# -*- coding: utf-8 -*-
from lib.drivers.MultiClamp import MultiClamp as MultiClampDriver
from lib.devices.Device import *
from lib.util.MetaArray import MetaArray, axis
from PyQt4 import QtCore
from numpy import *
import sys, traceback
from DeviceGui import *
from protoGUI import *

class MultiClamp(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.index = None
        self.devRackGui = None
        
        if not config.has_key('host') or config['host'] is None:
            raise Exception("Must specify host running MultiClamp server. (Direct connections not yet supported..)")
        self.host = self.config['host']
        if ':' in self.host:
            (host, c, port) = self.host.partition(':')
            args = (host, port)
        else:
            args = (self.host,)
        self.mc = MultiClampDriver(*args)
        self.mc.setUseCache(True)
        
        try:
            mcs = self.mc.listDevices()
            print "Connected to host %s, devices are %s" % (self.host, repr(mcs))
            self.channelID = self.config['channelID']
        except:
            traceback.print_exception(*(sys.exc_info()))
            print "Error connecting to MultiClamp commander, will try again when needed. (default settings not loaded)"
        
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
                    self.setParams(self.config['settings'][mode])
        self.setMode('I=0')

    def deviceInterface(self):
        if self.devRackGui is None:
            self.devRackGui = MCRackGui(self)
        return self.devRackGui

    def setParams(self, params):
        l = QtCore.QMutexLocker(self.lock)
        ind = self.getChanIndex()
        self.mc.setParams(ind, params)
    
    def createTask(self, cmd):
        l = QtCore.QMutexLocker(self.lock)
        return Task(self, cmd)
    
    def getMode(self):
        l = QtCore.QMutexLocker(self.lock)
        ind = self.getChanIndex()
        return self.mc.runFunction('getMode', [ind])[0]
    
    def setHolding(self, mode=None, value=None):
        """Define and set the holding values for this device"""
        l = QtCore.QMutexLocker(self.lock)
        if mode is not None and value is not None:
            self.holding[mode] = value
            
        mode = self.getMode()
        if mode == 'I=0':
            mode = 'IC'
        if mode not in self.holding:
            return
        holding = self.holding[mode]
        daq, chan = self.config['commandChannel']
        daqDev = self.dm.getDevice(daq)
        daqDev.setChannelValue(chan, holding, block=False)
        
    def getChanIndex(self):
        """Given a channel name (as defined in the configuration), return the device index to use when making calls to the MC"""
        l = QtCore.QMutexLocker(self.lock)
        if self.index is None:
            devs = self.mc.listDevices()
            if self.channelID not in devs:
                raise Exception("Could not find device on multiclamp with description '%s'" % self.channelID)
            self.index = devs.index(self.channelID)
        return self.index
        
    def listModeSignals(self):
        ## Todo: move this upstream to the multiclamp driver (and make it actually correct)
        l = QtCore.QMutexLocker(self.lock)
        sig = {
            'scaled': {
                'IC': ['MembranePotential'],
                'I=0': ['MembranePotential'],
                'VC': ['MembraneCurrent']
            },
            'raw': {
                'IC': ['MembranePotential', 'MembraneCurrent'],
                'I=0': ['MembranePotential', 'MembraneCurrent'],
                'VC': ['MembraneCurrent', 'MembranePotential']
            }
        }
        return sig
        
    def setMode(self, mode):
        """Set the mode for a multiclamp channel, gracefully switching between VC and IC modes."""
        l = QtCore.QMutexLocker(self.lock)
        mode = mode.upper()
        if mode not in ['VC', 'IC', 'I=0']:
            raise Exception('MultiClamp mode "%s" not recognized.' % mode)
        
        chan = self.getChanIndex()

        mcMode = self.mc.runFunction('getMode', [chan])[0]
        if mcMode == mode:
            return
            
        ## If switching ic <-> vc, switch to i=0 first
        if (mcMode=='IC' and mode=='VC') or (mcMode=='VC' and mode=='IC'):
            self.mc.runFunction('setMode', [chan,'I=0'])
            mcMode = 'I=0'
        
        if mcMode=='I=0':
            ## Set holding level before leaving I=0 mode
            self.setHolding()
        
        self.mc.runFunction('setMode', [chan, mode])
        
        ## Clamp should not be used until it has had time to settle after switching modes. (?)
        #self.readyTime = ptime.time() + 0.1

    def clearCache(self):
        l = QtCore.QMutexLocker(self.lock)
        self.mc.clearCache()
        print "Cleared MultiClamp configuration cache."

    def protocolInterface(self, prot):
        l = QtCore.QMutexLocker(self.lock)
        return MultiClampProtoGui(self, prot)

    def getDAQName(self):
        """Return the DAQ name used by this device. (assumes there is only one DAQ for now)"""
        l = QtCore.QMutexLocker(self.lock)
        daq, chan = self.config['commandChannel']
        return daq

    def quit(self):
        l = QtCore.QMutexLocker(self.lock)
        self.mc.disconnect()

class Task(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        l = QtCore.QMutexLocker(self.dev.lock)
        self.recordParams = ['Holding', 'HoldingEnable', 'PipetteOffset', 'FastCompCap', 'SlowCompCap', 'FastCompTau', 'SlowCompTau', 'NeutralizationEnable', 'NeutralizationCap', 'WholeCellCompEnable', 'WholeCellCompCap', 'WholeCellCompResist', 'RsCompEnable', 'RsCompBandwidth', 'RsCompCorrection', 'PrimarySignalGain', 'PrimarySignalLPF', 'PrimarySignalHPF', 'OutputZeroEnable', 'OutputZeroAmplitude', 'LeakSubEnable', 'LeakSubResist', 'BridgeBalEnable', 'BridgeBalResist']
        self.usedChannels = None
        self.daqTasks = {}

        ## Sanity checks and default values for command:
        
        if ('mode' not in self.cmd) or (type(self.cmd['mode']) is not str) or (self.cmd['mode'].upper() not in ['IC', 'VC', 'I=0']):
            raise Exception("Multiclamp command must specify clamp mode (IC, VC, or I=0)")
        self.cmd['mode'] = self.cmd['mode'].upper()
        
        ## If scaled and raw modes are not specified, use default values
        defaultModes = {
            'VC': {'scaled': 'MembraneCurrent', 'raw': 'PipettePotential'},  ## MC700A does not have MembranePotential signal
            'IC': {'scaled': 'MembranePotential', 'raw': 'MembraneCurrent'},
            'I=0': {'scaled': 'MembranePotential', 'raw': None},
        }
        for ch in ['scaled', 'raw']:
            if ch not in self.cmd:
                self.cmd[ch] = defaultModes[self.cmd['mode']][ch]

        if 'command' not in self.cmd:
            self.cmd['command'] = None

    def configure(self, tasks, startOrder):
        """Sets the state of a remote multiclamp to prepare for a program run."""
        l = QtCore.QMutexLocker(self.dev.lock)
            
        ch = self.dev.getChanIndex()
        
        ## Set state of clamp
        self.dev.setMode(self.cmd['mode'])
        if self.cmd['scaled'] is not None:
            self.dev.mc.setPrimarySignalByName(ch, self.cmd['scaled'])
        if self.cmd['raw'] is not None:
            self.dev.mc.setSecondarySignalByName(ch, self.cmd['raw'])
        
        if self.cmd.has_key('parameters'):
            for k in self.cmd['parameters']:
                self.dev.mc.setParameter(ch, k, self.cmd['parameters'][k])
        
        self.state = {}
        if self.cmd.has_key('recordState') and self.cmd['recordState']:
            self.state = self.dev.mc.readParams(ch, self.recordParams)
            
        self.state['scaledSignal'] = self.dev.mc.getSignalInfo(ch, 'Primary')
        self.state['rawSignal'] = self.dev.mc.getSignalInfo(ch, 'Secondary')
        
        ## set holding level
        if 'holding' in self.cmd:
            self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        
                
    def getUsedChannels(self):
        """Return a list of the channels this task uses"""
        l = QtCore.QMutexLocker(self.dev.lock)
        if self.usedChannels is None:
            self.usedChannels = []
            for ch in ['scaled', 'raw', 'command']:
                if self.cmd[ch] is not None:
                    self.usedChannels.append(ch)
                    
        return self.usedChannels
        
                
    def createChannels(self, daqTask):
        ## Is this the correct DAQ device for any of my channels?
        ## create needed channels + info
        ## write waveform to command channel if needed
        l = QtCore.QMutexLocker(self.dev.lock)
        
        for ch in self.getUsedChannels():
            chConf = self.dev.config[ch+'Channel']
            if chConf[0] == daqTask.devName():
                if ch == 'command':
                    daqTask.addChannel(chConf[1], 'ao')
                    scale = self.dev.config['cmdScale'][self.cmd['mode']]
                    cmdData = self.cmd['command'] * scale
                    daqTask.setWaveform(chConf[1], cmdData)
                else:
                    daqTask.addChannel(chConf[1], 'ai')
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
        l = QtCore.QMutexLocker(self.dev.lock)
        
        result = {}
        #result['info'] = self.state
        for ch in self.usedChannels:
            chConf = self.dev.config[ch+'Channel']
            result[ch] = self.daqTasks[ch].getData(chConf[1])
            # print result[ch]
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
                result[ch]['units'] = self.state[ch + 'Signal'][2]
                #result[ch]['name'] = self.state[ch + 'Signal'][0]
                result[ch]['name'] = ch
        # print result
            
        ## Copy state from first channel (assume this is the same for all channels)
        firstChInfo = result[self.usedChannels[0]]['info']
        for k in firstChInfo:
            self.state[k] = firstChInfo[k]
            
        timeVals = linspace(0, float(self.state['numPts']-1) / float(self.state['rate']), self.state['numPts'])
        chanList = [atleast_2d(result[x]['data']) for x in result]
        # for l in chanList:
          # print l.shape
        cols = [(result[x]['name'], result[x]['units']) for x in result]
        # print cols
        #print [a.shape for a in chanList]
        arr = concatenate(chanList)
        info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [self.state]
        marr = MetaArray(arr, info=info)
            
        return marr
    
    def stop(self):
        l = QtCore.QMutexLocker(self.dev.lock)
        self.dev.setHolding()