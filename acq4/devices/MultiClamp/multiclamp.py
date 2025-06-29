import numpy as np
import time
from MetaArray import MetaArray, axis

from acq4.Manager import logMsg
from acq4.devices.PatchClamp import PatchClamp
from pyqtgraph import multiprocess
from .taskGUI import MultiClampTaskGui
from ..Device import DeviceTask
from ...util.Mutex import Mutex
from ...util.debug import printExc


class MultiClamp(PatchClamp):
    """
    Driver for Molecular Devices MultiClamp 700A/700B patch clamp amplifiers.
    
    Configuration options:
    
    * **channelID** (str, required): MultiClamp channel identifier string. 
      Format: 'model:MC700A,com:3,dev:0,chan:1'
      Use incorrect string to see available device strings in error message.
    
    * **commandChannel** (dict): DAQ channel for command output
        - device: Name of DAQ device  
        - channel: DAQ channel (e.g., '/Dev1/ao0')
        - type: 'ao'
    
    * **primaryChannel** (dict): DAQ channel for primary signal input
        - device: Name of DAQ device
        - channel: DAQ channel (e.g., '/Dev1/ai10') 
        - type: 'ai'
        - mode: Input mode ('NRSE', 'RSE', 'DIFF')
    
    * **secondaryChannel** (dict): DAQ channel for secondary signal input
        - device: Name of DAQ device
        - channel: DAQ channel (e.g., '/Dev1/ai9')
        - type: 'ai' 
        - mode: Input mode ('NRSE', 'RSE', 'DIFF')
    
    * **vcHolding** (float, optional): Default voltage clamp holding potential (V, default: -65e-3)
    
    * **icHolding** (float, optional): Default current clamp holding current (A, default: 0.0)
    
    * **dllPath** (str, optional): Path to AxMultiClampMsg.dll (usually auto-detected)
    
    * **pythonExecutable** (str, optional): Path to 32-bit python executable for 64-bit systems
    
    * **enableParameterCache** (bool, optional): Enable parameter caching for performance (default: False)
    
    * **defaults** (dict, optional): Default amplifier settings for each mode
        - IC: Dict of current clamp parameters
        - VC: Dict of voltage clamp parameters
        
    Example configuration::
    
        Clamp1:
            driver: 'MultiClamp'
            channelID: 'model:MC700A,com:3,dev:0,chan:1'
            commandChannel:
                device: 'DAQ'
                channel: '/Dev1/ao0'
                type: 'ao'
            primaryChannel:
                device: 'DAQ'
                channel: '/Dev1/ai10'
                mode: 'NRSE'
                type: 'ai'
            secondaryChannel:
                device: 'DAQ'
                channel: '/Dev1/ai9'
                mode: 'NRSE'
                type: 'ai'
            vcHolding: -65e-3
            icHolding: 0.0
            defaults:
                IC:
                    HoldingEnable: False
                    Holding: 0.0
                    NeutralizationEnable: True
                    PrimarySignalGain: 2
                    PrimarySignalLPF: 20e3
                    BridgeBalEnable: True
                    BridgeBalResist: 15e6
                VC:
                    HoldingEnable: False
                    Holding: 0.0
                    WholeCellCompEnable: False
                    RsCompEnable: False
                    PrimarySignalGain: 2
                    PrimarySignalLPF: 20e3
                    LeakSubEnable: False
    """

    # inherited signals: sigStateChanged, sigHoldingChanged

    # remote process used to connect to commander from 32-bit python
    proc = None

    def __init__(self, dm, config, name):
        PatchClamp.__init__(self, dm, config, name)
        self.index = None
        self.devRackGui = None
        self.mc = None

        # Cache MC parameters because they are very expensive to retrieve
        # (especially with multiple channels)
        self._paramCache = {}

        # device parameters that are expected to change when the clamp mode changes
        self.mode_dependent_params = [
            'PrimarySignal', 'SecondarySignal',
            'PrimarySignalGain', 'SecondarySignalGain',
            'Holding', 'HoldingEnable',
            'PipetteOffset',
        ]

        self.stateLock = Mutex(Mutex.Recursive)  ## only for locking self.lastState and self.lastMode
        self.lastState = {}
        self.lastMode = None
        self._switchingToMode = None

        # default holding state
        self.holding = {
            'VC': -50e-3,
            'IC': 0.0,
            'I=0': 0.0
        }

        # Get a handle to the multiclamp driver object, whether that is hosted locally or in a remote process.
        executable = self.config.get('pythonExecutable', None)
        if executable is not None:
            # Run a remote python process to connect to the MC commander.
            # This is used on 64-bit systems where the MC connection must be run with
            # 32-bit python.
            if MultiClamp.proc is False:
                raise Exception("Already connected to multiclamp locally; cannot connect via remote process at the same time.")
            if MultiClamp.proc is None:
                MultiClamp.proc = multiprocess.Process(executable=executable, copySysPath=False)
                try:
                    self.proc.mc_mod = self.proc._import('acq4.drivers.MultiClamp')
                    self.proc.mc_mod._setProxyOptions(deferGetattr=False)
                except:
                    MultiClamp.proc.close()
                    MultiClamp.proc = None
                    raise
            mcmod = self.proc.mc_mod
        else:
            if MultiClamp.proc not in (None, False):
                raise Exception("Already connected to multiclamp via remote process; cannot connect locally at the same time.")
            else:
                # don't allow remote process to be used for other channels.
                MultiClamp.proc = False

            try:
                import acq4.drivers.MultiClamp as MultiClampDriver
            except RuntimeError as exc:
                if exc.args and "32-bit" in exc.args[0]:
                    raise Exception("MultiClamp commander does not support access by 64-bit processes. To circumvent this problem, "
                                    "Use the 'pythonExecutable' device configuration option to connect via a 32-bit python instead.")
                else:
                    raise
            mcmod = MultiClampDriver

        # Ask driver to use a specific DLL if specified in config
        dllPath = self.config.get('dllPath', None)
        if dllPath is not None:
            mcmod.getAxlib(dllPath)

        # Create driver instance
        mc = mcmod.MultiClamp.instance()

        # get a handle to our specific multiclamp channel
        if executable is not None:
            self.mc = mc.getChannel(self.config['channelID'], multiprocess.proxy(self.mcUpdate, callSync='off'))
        else:
            self.mc = mc.getChannel(self.config['channelID'], self.mcUpdate)
        
        ## wait for first update..
        start = time.time()
        while self.mc.getState() is None:
            time.sleep(0.1)
            if time.time() - start > 10:
                raise Exception("Timed out waiting for first update from multi clamp commander.")
        
        print("Created MultiClamp device", self.config['channelID'])

        ## set configured holding values
        if 'vcHolding' in self.config:
            self.holding['VC'] = self.config['vcHolding']
        if 'icHolding' in self.config:
            self.holding['IC'] = self.config['icHolding']

        ## Set up default MC settings for each mode, then leave MC in I=0 mode
        # look for 'defaults', followed by 'settings' (for backward compatibility)
        defaults = self.config.get('defaults', self.config.get('settings', None))
        for mode in ['IC', 'VC']:
            self.setMode(mode) # Set mode even if we have no parameters to set;
                               # this ensures that self.lastState is filled.
            if defaults is not None and mode in defaults:
                self.mc.setParams(defaults[mode])
        self.setMode('I=0')  ## safest mode to leave clamp in

        
        dm.declareInterface(name, ['clamp'], self)

    def description(self):
        return self.config['channelID']

    def listChannels(self):
        return {
            ch: self.config[ch].copy()
            for ch in ['commandChannel', 'primaryChannel', 'secondaryChannel']
        }

    def quit(self):
        if self.mc is not None:
            self.mc.mc.quit()

    def mcUpdate(self, state=None, mode=None):
        """MC state (or internal holding state) has changed, handle the update."""
        with self.stateLock:
            self._paramCache = {}  # not sure if this is necessary or helpful
            if state is None:
                state = self.getLastState(mode)
            mode = state['mode']
            state['holding'] = self.holding[mode]
            self.lastState[mode] = state.copy()
            if self.lastMode != state['mode']:
                if self.lastMode is not None and state['mode'] != self._switchingToMode and state['mode'] != 'I=0':
                    # User changed the mode manually; we need to update the holding value immediately.
                    self.setHolding(state['mode'])
                    logMsg("Warning: MultiClamp mode should be changed from ACQ4, not from the MultiClamp Commander window.", msgType='error')

                self.lastMode = state['mode']
                self._switchingToMode = None

        self.sigStateChanged.emit(state)

    def getLastState(self, mode=None):
        """Return the last known state for the given mode."""
        if mode is None:
            mode = self.mc.getMode()
        with self.stateLock:
            if mode in self.lastState:
                return self.lastState[mode]

    def extCmdScale(self, mode):
        """Return our best guess as to the external command sensitivity for the given mode."""
        s = self.getLastState(mode)
        if s is not None:
            return s['extCmdScale']
        elif mode == 'VC':
            return 50
        else:
            return 2.5e9
        
    def getState(self):
        return self.mc.getState()

    def getParam(self, param):
        if param not in self._paramCache:
            val = self.mc.getParam(param)
            if self.config.get('enableParameterCache', False):
                self._paramCache[param] = val
            else:
                return val
        return self._paramCache[param]

    def setParam(self, param, value):
        if self.config.get('enableParameterCache', False):
            if param in self._paramCache and self._paramCache[param] == value:
                return
            # use special setters for primary / secondary signals due to MCC bugs
            if param == 'PrimarySignal':
                self.mc.setPrimarySignal(value)
            elif param == 'SecondarySignal':
                self.mc.setSecondarySignal(value)
            else:
                self.mc.setParam(param, value)
            self._paramCache.pop(param)
            self.getParam(param)
        else:
            self.mc.setParam(param, value)

    def taskInterface(self, taskRunner):
        return MultiClampTaskGui(self, taskRunner)
    
    def createTask(self, cmd, parentTask):
        return MultiClampTask(self, cmd, parentTask)
    
    def getHolding(self, mode=None):
        if mode is None:  ## If no mode is specified, use the current mode
            mode = self.mc.getMode()
        mode = mode.upper()
        if mode == 'I=0':
            return 0.0
        else:
            return self.holding[mode]
            
    def setHolding(self, mode=None, value=None):
        """Define and/or set the holding values for this device. 

        Note--these are ACQ4-controlled holding values, NOT the holding values used by the amplifier.
        It is important to have this because the amplifier's holding values cannot be changed
        before switching modes.
        """
        with self.dm.reserveDevices([self, self.config['commandChannel']['device']]):
            currentMode = self.mc.getMode()
            if mode is None:  ## If no mode is specified, use the current mode
                mode = currentMode
                if mode == 'I=0':  ## ..and if the current mode is I=0, do nothing.
                    return
            mode = mode.upper()
            if mode == 'I=0':
                raise ValueError("Can't set holding value for I=0 mode.")

            ## Update stored holding value if value is supplied
            if value is not None:
                if self.holding[mode] == value:
                    return
                self.holding[mode] = value
                state = self.lastState[mode]
                state['holding'] = value
                if mode == currentMode:
                    self.sigStateChanged.emit(state)
                self.sigHoldingChanged.emit(mode, value)

            ## We only want to set the actual DAQ channel if:
            ##   - currently in I=0, or
            ##   - currently in the mode that was changed
            if mode != currentMode and currentMode != 'I=0':
                return

            holding = self.holding[mode]
            daq = self.getDAQName('command')
            chan = self.config['commandChannel']['channel']
            daqDev = self.dm.getDevice(daq)
            s = self.extCmdScale(mode)  ## use the scale for the last remembered state from this mode
            if s == 0:
                if holding == 0.0:
                    s = 1.0
                else:
                    raise ValueError('Can not set holding value for multiclamp--external command sensitivity is disabled by commander.')
            scale = 1.0 / s
            daqDev.setChannelValue(chan, holding*scale, block=False)

    def autoPipetteOffset(self):
        with self.dm.reserveDevices([self]):
            self.mc.autoPipetteOffset()
        
    def autoBridgeBalance(self):
        with self.dm.reserveDevices([self]):
            self.mc.autoBridgeBal()

    def autoCapComp(self):
        with self.dm.reserveDevices([self]):
            self.mc.autoFastComp()
            self.mc.autoSlowComp()

    def listSignals(self, mode):
        return self.mc.listSignals(mode)
        
    def getMode(self):
        return self.mc.getMode()

    def setMode(self, mode):
        """Set the mode for a multiclamp channel, gracefully switching between VC and IC modes."""
        mode = mode.upper()
        if mode not in ['VC', 'IC', 'I=0']:
            raise ValueError(f'MultiClamp mode "{mode}" not recognized.')

        # these parameters change with clamp mode; need to invalidate cache
        for param in self.mode_dependent_params:
            self._paramCache.pop(param, None)

        with self.dm.reserveDevices([self, self.config['commandChannel']['device']]):
            mcMode = self.mc.getMode()
            if mcMode == mode:  ## Mode is already correct
                return

            # If switching ic <-> vc, switch to i=0 first
            if (mcMode=='IC' and mode=='VC') or (mcMode=='VC' and mode=='IC'):
                self._switchingToMode = 'I=0'
                self.mc.setMode('I=0')
                mcMode = 'I=0'
            if mcMode=='I=0':
                # Set holding level before leaving I=0 mode
                self.setHolding(mode)
            self._switchingToMode = mode
            self.mc.setMode(mode)

            # MC requires 200-400 ms to mode switch; don't allow anyone else to access during that time.
            time.sleep(0.5)

    def getDAQName(self, channel):
        """Return the DAQ name used by this device. (assumes there is only one DAQ for now)"""
        return self.config[f'{channel}Channel']['device']


class MultiClampTask(DeviceTask):
    recordParams = [
        'BridgeBalEnable',
        'BridgeBalResist',
        'FastCompCap',
        'FastCompTau',
        'Holding',
        'HoldingEnable',
        'LeakSubEnable',
        'LeakSubResist',
        'NeutralizationCap',
        'NeutralizationEnable',
        'OutputZeroAmplitude',
        'OutputZeroEnable',
        'PipetteOffset',
        'PrimarySignalHPF',
        'PrimarySignalLPF',
        'RsCompBandwidth',
        'RsCompCorrection',
        'RsCompEnable',
        'SlowCompCap',
        'SlowCompTau',
        'WholeCellCompCap',
        'WholeCellCompEnable',
        'WholeCellCompResist',
    ]

    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.cmd = cmd

        self.usedChannels = None
        self.daqTasks = {}

        ## Sanity checks and default values for command:
        
        if ('mode' not in self.cmd) or (type(self.cmd['mode']) is not str) or (self.cmd['mode'].upper() not in ['IC', 'VC', 'I=0']):
            raise ValueError("Multiclamp command must specify clamp mode (IC, VC, or I=0)")
        self.cmd['mode'] = self.cmd['mode'].upper()
        
        for ch in ['primary', 'secondary']:
            if ch not in self.cmd:
                self.cmd[ch] = None # defaultModes[self.cmd['mode']][ch]

    def getConfigOrder(self):
        """return lists of devices that should be configured (before, after) this device"""
        return ([], [self.dev.getDAQName("primary")])

    def configure(self):
        """Sets the state of a remote multiclamp to prepare for a program run."""
        #from debug import Profiler
        #prof = Profiler()
        ## Set state of clamp

        ## set holding level
        if 'holding' in self.cmd and self.cmd['mode'] != 'I=0':
            self.dev.setHolding(self.cmd['mode'], self.cmd['holding'])
        
        self.dev.setMode(self.cmd['mode'])
        if self.cmd['primary'] is not None:
            self.dev.setPrimarySignal(self.cmd['primary'])
        if self.cmd['secondary'] is not None:
            self.dev.setSecondarySignal(self.cmd['secondary'])

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

        if 'parameters' in self.cmd:
            self.dev.mc.setParams(self.cmd['parameters'])

        #prof.mark('    Multiclamp: set params')

        #self.state = self.dev.mc.getState()
        self.state = self.dev.getLastState()
        
        #prof.mark('    Multiclamp: get state')
        
        recordState = self.cmd.get('recordState', False)
        if recordState is not False:
            if recordState is True:
                recordParams = MultiClampTask.recordParams
            elif isinstance(recordState, list):
                recordParams = recordState
            else:
                raise TypeError("MultiClamp task command['recordParams'] must be bool or list")

            exState = self.dev.mc.getParams(recordParams)
            self.state['ClampParams'] = {}
            for k in exState:
                self.state['ClampParams'][k] = exState[k]
                
        #prof.mark('    Multiclamp: recordState?')
                
        self.holdingVal = self.dev.getHolding(self.cmd['mode'])
        
        #prof.mark('    Multiclamp: set holding')
                
    def getUsedChannels(self):
        """Return a list of the channels this task uses"""
        if self.usedChannels is None:
            self.usedChannels = ['primary']
            if self.cmd.get('recordSecondary', True):
                self.usedChannels.append('secondary')
            if 'command' in self.cmd:
                self.usedChannels.append('command')
            
        return self.usedChannels        
                
    def createChannels(self, daqTask):
        ## Is this the correct DAQ device for any of my channels?
        ## create needed channels + info
        ## write waveform to command channel if needed

        ## NOTE: no guarantee that self.configure has been run before createChannels is called!
        for ch in self.getUsedChannels():
            chConf = self.dev.config[f'{ch}Channel']

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
        channels = self.getUsedChannels()
        result = {}
        #result['info'] = self.state
        for ch in channels:
            chConf = self.dev.config[f'{ch}Channel']
            result[ch] = self.daqTasks[ch].getData(chConf['channel'])
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
                scale = self.state[f'{ch}ScaleFactor']
                result[ch]['data'] = result[ch]['data'] * scale
                #result[ch]['units'] = self.state[ch + 'Signal'][2]
                result[ch]['units'] = self.state[f'{ch}Units']
                result[ch]['name'] = ch

        if len(result) == 0:
            return None

        daqState = {ch: result[ch]['info'] for ch in result}
        ## record command holding value
        if 'command' not in daqState:
            daqState['command'] = {}
        daqState['command']['holding'] = self.holdingVal

        #timeVals = linspace(0, float(self.state['numPts']-1) / float(self.state['rate']), self.state['numPts'])
        timeVals = np.linspace(0, float(nPts-1) / float(rate), nPts)
        chanList = [np.atleast_2d(result[x]['data']) for x in result]
        # for l in chanList:
        cols = [(result[x]['name'], result[x]['units']) for x in result]
        try:
            arr = np.concatenate(chanList)
        except:
            for a in chanList:
                print(a.shape)
            raise

        info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [{'ClampState': self.state, 'DAQ': daqState}]

        taskInfo = self.cmd.copy()
        if 'command' in taskInfo:
            del taskInfo['command']
        info[-1]['Protocol'] = taskInfo
        info[-1]['startTime'] = result[list(result.keys())[0]]['info']['startTime']

        return MetaArray(arr, info=info)
    
    def stop(self, abort=False):
        ## This is just a bit sketchy, but these tasks have to be stopped before the holding level can be reset.
        for ch in self.daqTasks:
            self.daqTasks[ch].stop(abort=abort)
        self.dev.setHolding()
