# -*- coding: utf-8 -*-
from __future__ import with_statement
from acq4.drivers.MultiClamp.MultiClamp import MultiClamp as MultiClampDriver
from acq4.devices.Device import *
from acq4.util.metaarray import MetaArray, axis
from acq4.util.Mutex import Mutex, MutexLocker
from PyQt4 import QtCore
from numpy import *
import sys, traceback
from DeviceGui import *
from taskGUI import *
from acq4.util.debug import *

class MultiClamp(Device):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config
        self.lock = Mutex(Mutex.Recursive)
        self.index = None
        self.devRackGui = None
        
        self.stateLock = Mutex(Mutex.Recursive)  ## only for locking self.lastState and self.lastMode
        self.lastState = {}
        self.lastMode = None


        try:
            # default holding state
            self.holding = {
                'VC': -50e-3,
                'IC': 0.0,
                'I=0': 0.0
            }
                
            self.mc = MultiClampDriver.instance().getChannel(self.config['channelID'], self.mcUpdate)
            
            ## wait for first update..
            c = 0
            while self.mc.getState() is None:
                time.sleep(0.1)
                c += 1
                if c > 50:
                    raise Exception("Timed out waiting for first update from multi clamp commander.")
            
            print "Created MultiClamp device", self.config['channelID']

            ## set configured holding values
            if 'vcHolding' in self.config:
                self.holding['VC'] = self.config['vcHolding']
            if 'icHolding' in self.config:
                self.holding['IC'] = self.config['icHolding']

            ## Set up default MC settings for each mode, then leave MC in I=0 mode
            if 'settings' in self.config:
                for mode in ['IC', 'VC']:
                    if mode in self.config['settings']:
                        #print "set mode", mode
                        self.setMode(mode)
                        #print "set params"
                        self.mc.setParams(self.config['settings'][mode])
            self.setMode('I=0')  ## safest mode to leave clamp in

        except:
            try:
                mc = MultiClampDriver.instance()
                if mc is not None:
                    mc.quit()
            except:
                pass
            raise
        
        dm.declareInterface(name, ['clamp'], self)

    def listChannels(self):
        chans = {}
        for ch in ['commandChannel', 'primaryChannel', 'secondaryChannel']:
            chans[ch] = self.config[ch].copy()
        return chans

    def quit(self):
        mc = MultiClampDriver.instance()
        if mc is not None:
            mc.quit()

    def mcUpdate(self, state=None, mode=None):
        """MC state (or internal holding state) has changed, handle the update."""
        
        #print "lock for update..."
        with self.stateLock:
            if state is None:
                state = self.lastState[mode]
            #print "  got lock for update"
            mode = state['mode']
            #if mode == 'I=0':
                #mode = 'IC'
            state['holding'] = self.holding[mode]
            self.lastState[mode] = state.copy()
            self.lastMode = state['mode']
            ## Has mode changed? has extCmdScale changed?
            
        #QtCore.QObject.emit(self, QtCore.SIGNAL('stateChanged'), state)
        self.sigStateChanged.emit(state)
        
    def getLastState(self, mode=None):
        """Return the last known state for the given mode."""
        with self.stateLock:
            #if mode == 'I=0':
                #mode = 'IC'
            if mode is None:
                mode = self.mc.getMode()
            if mode in self.lastState:
                return self.lastState[mode]
        
        
    def extCmdScale(self, mode):
        """Return our best guess as to the external command sensitivity for the given mode."""
        s = self.getLastState(mode)
        if s is not None:
            return s['extCmdScale']
        else:
            if mode == 'VC':
                return 50
            else:
                return 2.5e9
        
    def getState(self):
        return self.mc.getState()

    def getParam(self, param):
        return self.mc.getParam(param)

    def setParam(self, param, value):
        return self.mc.setParam(param, value)

    def deviceInterface(self, win):
        with MutexLocker(self.lock):
            if self.devRackGui is None:
                self.devRackGui = MCDeviceGui(self, win)
            return self.devRackGui

    def taskInterface(self, task):
        with MutexLocker(self.lock):
            return MultiClampTaskGui(self, task)

    #def setParams(self, params):
        #with MutexLocker(self.lock):
            #self.mc.setParams(params)
    
    #def getParam(self, param, cache=None):
        #with MutexLocker(self.lock):
            #return self.getParam(param)
    
    def createTask(self, cmd, parentTask):
        with MutexLocker(self.lock):
            return MultiClampTask(self, cmd, parentTask)
    
    #def getMode(self):
        #with MutexLocker(self.lock):
            #return self.mc.getMode()
    
    def getHolding(self, mode=None):
        with MutexLocker(self.lock):
            if mode is None:  ## If no mode is specified, use the current mode
                mode = self.mc.getMode()
            if mode == 'I=0':
                return 0.0
            else:
                return self.holding[mode]
            
    def setHolding(self, mode=None, value=None):
        """Define and/or set the holding values for this device. 
        Note--these are computer-controlled holding values, NOT the holding values used by the amplifier.
        It is important to have this because the amplifier's holding values can not be changed
        before switching modes."""
        
        with MutexLocker(self.lock):
            currentMode = self.mc.getMode()
            if mode is None:  ## If no mode is specified, use the current mode
                mode = currentMode
                if mode == 'I=0':  ## ..and if the current mode is I=0, do nothing.
                    return
            if mode == 'I=0':
                raise Exception("Can't set holding value for I=0 mode.")
            
            ## Update stored holding value if value is supplied
            if value is not None:
                self.holding[mode] = value
                self.mcUpdate(mode=mode)
                
            ## We only want to set the actual DAQ channel if:
            ##   - currently in I=0, or 
            ##   - currently in the mode that was changed
            if mode != currentMode and currentMode != 'I=0':
                return
            
            holding = self.holding[mode]
            daq = self.config['commandChannel']['device']
            chan = self.config['commandChannel']['channel']
            #daq, chan = self.config['commandChannel'][:2]
            daqDev = self.dm.getDevice(daq)
            s = self.extCmdScale(mode)  ## use the scale for the last remembered state from this mode
            if s == 0:
                if holding == 0.0:
                    s = 1.0
                else:
                    #print self.mc.getState()
                    raise Exception('Can not set holding value for multiclamp--external command sensitivity is disabled by commander.')
            scale = 1.0 / s
            #print "     setChannelValue", chan, holding
            daqDev.setChannelValue(chan, holding*scale, block=False)
        
    #def getChanIndex(self):
        #"""Given a channel name (as defined in the configuration), return the device index to use when making calls to the MC"""
        #with MutexLocker(self.lock):
            #if self.index is None:
                #devs = self.mc.listDevices()
                #if self.channelID not in devs:
                    #raise Exception("Could not find device on multiclamp with description '%s'" % self.channelID)
                #self.index = devs.index(self.channelID)
            #return self.index
        
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
        with self.lock:
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
                #print "  set intermediate i0"
            if mcMode=='I=0':
                ## Set holding level before leaving I=0 mode
                #print "  set holding"
                self.setHolding(mode)
            #print "  set mode"
            self.mc.setMode(mode)

    def getDAQName(self):
        """Return the DAQ name used by this device. (assumes there is only one DAQ for now)"""
        with MutexLocker(self.lock):
            return self.config['commandChannel']['device']


class MultiClampTask(DeviceTask):
    
    
    recordParams = ['Holding', 'HoldingEnable', 'PipetteOffset', 'FastCompCap', 'SlowCompCap', 'FastCompTau', 'SlowCompTau', 'NeutralizationEnable', 'NeutralizationCap', 'WholeCellCompEnable', 'WholeCellCompCap', 'WholeCellCompResist', 'RsCompEnable', 'RsCompBandwidth', 'RsCompCorrection', 'PrimarySignalLPF', 'PrimarySignalHPF', 'OutputZeroEnable', 'OutputZeroAmplitude', 'LeakSubEnable', 'LeakSubResist', 'BridgeBalEnable', 'BridgeBalResist']
    
    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.cmd = cmd
        with MutexLocker(self.dev.lock):
            self.usedChannels = None
            self.daqTasks = {}

            ## Sanity checks and default values for command:
            
            if ('mode' not in self.cmd) or (type(self.cmd['mode']) is not str) or (self.cmd['mode'].upper() not in ['IC', 'VC', 'I=0']):
                raise Exception("Multiclamp command must specify clamp mode (IC, VC, or I=0)")
            self.cmd['mode'] = self.cmd['mode'].upper()
            
            ## If primary and secondary modes are not specified, use default values
            #### Disabled this -- just use whatever is currently in use.
            #defaultModes = {
                #'VC': {'primarySignal': 'Membrane Current', 'secondarySignal': 'Pipette Potential'},  ## MC700A does not have MembranePotential signal
                #'IC': {'primarySignal': 'Membrane Potential', 'secondarySignal': 'Membrane Current'},
                #'I=0': {'primarySignal': 'Membrane Potential', 'secondarySignal': None},
            #}
            for ch in ['primary', 'secondary']:
                if ch not in self.cmd:
                    self.cmd[ch] = None # defaultModes[self.cmd['mode']][ch]

            #if 'command' not in self.cmd:
                #self.cmd['command'] = None

    def getConfigOrder(self):
        """return lists of devices that should be configured (before, after) this device"""
        return ([], [self.dev.getDAQName()])

    def configure(self):
        """Sets the state of a remote multiclamp to prepare for a program run."""
        #print "mc configure"
        with MutexLocker(self.dev.lock):
            
            #from debug import Profiler
            #prof = Profiler()
            ## Set state of clamp
            
            ## set holding level
            if 'holding' in self.cmd and self.cmd['mode'] != 'I=0':
                self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
            
            self.dev.setMode(self.cmd['mode'])
            if self.cmd['primary'] is not None:
                self.dev.mc.setPrimarySignal(self.cmd['primary'])
            if self.cmd['secondary'] is not None:
                self.dev.mc.setSecondarySignal(self.cmd['secondary'])

            #prof.mark('    Multiclamp: set state')   ## ~300ms if the commander has to do a page-switch.

            if 'primaryGain' in self.cmd:
                self.dev.mc.setParam('PrimarySignalGain', self.cmd['primaryGain'])
            if 'secondaryGain' in self.cmd:
                try:
                    ## this is likely to fail..
                    self.dev.mc.setParam('SecondarySignalGain', self.cmd['secondaryGain'])
                except:
                    printExc("Warning -- set secondary signal gain failed.")

            #prof.mark('    Multiclamp: set gains')


            if self.cmd.has_key('parameters'):
                self.dev.mc.setParams(self.cmd['parameters'])

            #prof.mark('    Multiclamp: set params')


                
            #self.state = self.dev.mc.getState()
            self.state = self.dev.getLastState()
            
            #prof.mark('    Multiclamp: get state')
            
            if self.cmd.has_key('recordState') and self.cmd['recordState'] is True:
                exState = self.dev.mc.getParams(MultiClampTask.recordParams)
                self.state['ClampParams'] = {}
                for k in exState:
                    self.state['ClampParams'][k] = exState[k]
                    
            #prof.mark('    Multiclamp: recordState?')
                    
            self.holdingVal = self.dev.getHolding(self.cmd['mode'])
            #self.state['primarySignal'] = self.dev.mc.getPrimarySignalInfo()
            #self.state['secondarySignal'] = self.dev.mc.getSecondarySignalInfo()
            
            #print "mc configure complete"
            #prof.mark('    Multiclamp: set holding')
        
                
    def getUsedChannels(self):
        """Return a list of the channels this task uses"""
        with MutexLocker(self.dev.lock):
            if self.usedChannels is None:
                self.usedChannels = []
                for ch in ['primary', 'secondary', 'command']:
                    if ch in self.cmd:
                        self.usedChannels.append(ch)
                        
            return self.usedChannels
        
                
    def createChannels(self, daqTask):
        ## Is this the correct DAQ device for any of my channels?
        ## create needed channels + info
        ## write waveform to command channel if needed
        
        ## NOTE: no guarantee that self.configure has been run before createChannels is called! 
        
        with MutexLocker(self.dev.lock):
            
            for ch in self.getUsedChannels():
                chConf = self.dev.config[ch+'Channel']
                    
                if chConf['device'] == daqTask.devName():
                    if ch == 'command':
                        daqTask.addChannel(chConf['channel'], chConf['type'])
                        scale = self.state['extCmdScale']
                        #scale = self.dev.config['cmdScale'][self.cmd['mode']]
                        if scale == 0.:
                            raise Exception('Can not execute command--external command sensitivity is disabled by MultiClamp commander!', 'ExtCmdSensOff')  ## The second string is a hint for modules that don't care when this happens.
                        cmdData = self.cmd['command'] / scale
                        daqTask.setWaveform(chConf['channel'], cmdData)
                    else:
                        mode = chConf.get('mode', None)
                        daqTask.addChannel(chConf['channel'], chConf['type'], mode)
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
            #print channels
            result = {}
            #result['info'] = self.state
            for ch in channels:
                chConf = self.dev.config[ch+'Channel']
                result[ch] = self.daqTasks[ch].getData(chConf['channel'])
                # print result[ch]
                nPts = result[ch]['info']['numPts']
                rate = result[ch]['info']['rate']
                if ch == 'command':
                    #result[ch]['data'] = result[ch]['data'] / self.dev.config['cmdScale'][self.cmd['mode']]
                    result[ch]['data'] = result[ch]['data'] * self.state['extCmdScale']
                    result[ch]['name'] = 'command'
                    if self.cmd['mode'] == 'VC':
                        result[ch]['units'] = 'V'
                    else:
                        result[ch]['units'] = 'A'
                else:
                    #scale = 1.0 / self.state[ch + 'Signal'][1]
                    scale = self.state[ch + 'ScaleFactor']
                    result[ch]['data'] = result[ch]['data'] * scale
                    #result[ch]['units'] = self.state[ch + 'Signal'][2]
                    result[ch]['units'] = self.state[ch + 'Units']
                    result[ch]['name'] = ch
            # print result
                
            if len(result) == 0:
                return None
                
            ## Copy state from first channel (assume this is the same for all channels)
            #firstChInfo = result[channels[0]]['info']
            #for k in firstChInfo:
                #self.state[k] = firstChInfo[k]
            daqState = {}
            for ch in result:
                daqState[ch] = result[ch]['info']
                
            ## record command holding value
            if 'command' not in daqState:
                daqState['command'] = {}
            daqState['command']['holding'] = self.holdingVal
                
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
            
            info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [{'ClampState': self.state, 'DAQ': daqState}]
            
            taskInfo = self.cmd.copy()
            if 'command' in taskInfo:
                del taskInfo['command']
            info[-1]['Protocol'] = taskInfo
            info[-1]['startTime'] = result[result.keys()[0]]['info']['startTime']
            
            marr = MetaArray(arr, info=info)
                
            return marr
    
    def stop(self, abort=False):
        with MutexLocker(self.dev.lock):
            ## This is just a bit sketchy, but these tasks have to be stopped before the holding level can be reset.
            for ch in self.daqTasks:
                self.daqTasks[ch].stop(abort=abort)
            self.dev.setHolding()
        
        