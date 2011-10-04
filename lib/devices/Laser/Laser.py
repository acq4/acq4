from PyQt4 import QtGui, QtCore
#import configfile
from lib.Manager import getManager, logExc, logMsg
from Mutex import Mutex
from lib.devices.DAQGeneric import DAQGeneric, DAQGenericTask
from LaserDevGui import LaserDevGui
from LaserProtocolGui import LaserProtoGui
import os
import time
import numpy as np
from scipy import stats
from functions import siFormat



class Laser(DAQGeneric):
    """The laser device accomplishes a few tasks:
       - Calibration of laser power so that the power at the specimen can be controlled
         (via pockels cell or Q-switch PWM)
       - Immediate recalibration from photocell or internal measurements
       - integrated control of shutters, q-switches, and pockels cells
       - Pulse commands, allowing the user to specify the energy per pulse
       - Control of wavelength and dispersion tuning when available

    Configuration examples:
    
    Laser-blue:
        driver: 'Laser'
        config:
            scope: 'Microscope'
            shutter:
                channel: 'DAQ', '/Dev3/line14'
                delay: 10*ms
            wavelength: 473*nm
            power: 10*mW
            alignmentMode:
                shutter: True
    
    Laser-UV:
        driver: 'Laser'
        config: 
            scope: 'Microscope'
            pulseRate: 100*kHz                      ## Laser's pulse rate
            powerIndicator: 
                channel: 'DAQ', '/Dev1/ai11'      ## photocell channel for immediate recalibration
                rate: 1.2*MHz
                settlingTime: 1*ms
                measurmentTime: 5*ms
            shutter:
                channel: 'DAQ', '/Dev1/line10'    ## channel for triggering shutter
                delay: 10*ms                      ## how long it takes the shutter to fully open
            qSwitch:
                channel: 'DAQ', '/Dev1/line11'    ## channel for triggering q-switch
            wavelength: 355*nm
            alignmentMode:
                qSwitch: False                    ## For alignment, shutter is open but QS is off
                shutter: True
            
    Laser-2p:
        driver: 'CoherentLaser'
        config: 
            serialPort: 6                         ## serial port connected to laser
            scope: 'Microscope'
            pulseRate: 100*kHz                      ## Laser's pulse rate; limits minimum pulse duration
            pCell:
                channel: 'DAQ', '/Dev2/ao1'       ## channel for pockels cell control
            namedWavelengths:
                UV uncaging: 710*nm
                AF488: 976*nm
            alignmentMode:
                pCellVoltage:
                
    Notes: 
        must handle CW (continuous wave), QS (Q-switched), ML (modelocked) lasers
        
        
        
    Protocol examples:
    
    { 'wavelength': 780*nm, 'powerWaveform': array([...]) }  ## calibrated; float array in W
    { 'switchWaveform': array([...]) }                       ## uncalibrated; 0=off -> 1=full power
    { 'pulse': [(0.5*s, 100*uJ), ...] }                     ## (time, pulse energy) pairs
    """
    
    sigPowerChanged = QtCore.Signal(object)
    
    def __init__(self, manager, config, name):
        self.config = config
        self.hasPowerIndicator = False
        self.hasShutter = False
        self.hasQSwitch = False
        self.hasPCell = False
        self.hasTunableWavelength = False
        
        self.params = {
            'expectedPower': config.get('power', None), ## Expected output
            'currentPower': None, ## Last measured output power
            'scopeTransmission': None, ## percentage of output power that is transmitted to slice
            'tolerance': None,
            'useExpectedPower': True
            }
        
        daqConfig = {} ### DAQ generic needs to know about powerIndicator, pCell, shutter, qswitch
        if 'powerIndicator' in config:
            self.hasPowerIndicator = True
            #### name of powerIndicator is config['powerIndicator']['channel'][0]
            #daqConfig['powerInd'] = {'channel': config['powerIndicator']['channel'], 'type': 'ai'}
        if 'shutter' in config:
            daqConfig['shutter'] = {'channel': config['shutter']['channel'], 'type': 'do'}
            self.hasShutter = True
        if 'qSwitch' in config:
            daqConfig['qSwitch'] = {'channel': config['qSwitch']['channel'], 'type': 'do'}
        if 'pCell' in config:
            daqConfig['pCell'] = {'channel': config['pCell']['channel'], 'type': 'ao'}
                        
        DAQGeneric.__init__(self, manager, daqConfig, name)
        
       
        self._configDir = os.path.join('devices', self.name + '_config')
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.variableLock = Mutex(QtCore.QMutex.Recursive)
        self.calibrationIndex = None
        self.getPowerHistory()
        
    def configDir(self):
        """Return the name of the directory where configuration/calibration data should be stored"""
        return self._configDir
    
    def setParam(self, **kwargs):
        """Set the self.calcPower variable. setting can be 'expected' or 'current'"""
        with self.variableLock:
            for k in kwargs:
                self.params[k] = kwargs[k]
    
    def getCalibrationIndex(self):
        with self.lock:
            if self.calibrationIndex is None:
                calDir = self.configDir()
                fileName = os.path.join(calDir, 'index')
                index = self.dm.readConfigFile(fileName)
                self.calibrationIndex = index
            return self.calibrationIndex
        
    def getPowerHistory(self):
        with self.variableLock:
            fileName = os.path.join(self.configDir(), 'powerHistory')
            if os.path.exists(os.path.join(self.dm.configDir, fileName)):
                ph = self.dm.readConfigFile(fileName)
                self.powerHistoryCount = len(ph)
                self.params['expectedPower'] = ph.values()[-1]['expectedPower']
                return ph
            else:
                date = str(time.strftime('%Y.%m.%d %H:%M:%S'))
                self.dm.writeConfigFile({'entry_0': {'date':date, 'expectedPower':0}}, fileName)
                self.params['expectedPower'] = 0
                self.powerHistoryCount = 1
                
    def appendPowerHistory(self, power):
        with self.variableLock:
            calDir = self.configDir()
            fileName = os.path.join(calDir, 'powerHistory')
            date = str(time.strftime('%Y.%m.%d %H:%M:%S'))
            self.dm.appendConfigFile({'entry_'+str(self.powerHistoryCount):{'date': date, 'expectedPower':power}}, fileName)
            
    

    def writeCalibrationIndex(self, index):
        with self.lock:
            calDir = self.configDir()
            fileName = os.path.join(calDir, 'index')
            self.dm.writeConfigFile(index, fileName)
            #configfile.writeConfigFile(index, fileName)
            self.calibrationIndex = index
        
    def setAlignmentMode(self, b):
        """If true, configures the laser for low-power alignment mode. 
        Note: If the laser achieves low power solely through PWM, then
        alignment mode will only be available during protocols."""
        
        pass
    
    def setWavelength(self, wl):
        """Set the laser's wavelength (if tunable).
        Arguments:
          wl:  """
        raise HelpfulException("%s device does not support wavelength tuning." %str(self.name), reasons=["Hardware doesn't support tuning.", "setWavelenth function is not reimplemented in subclass."])
    
    def getWavelength(self):
        return self.config.get('wavelength', None)
        
    
    
    def createTask(self, cmd):
        return LaserTask(self, cmd)
        
    def protocolInterface(self, prot):
        return LaserProtoGui(self, prot)
        
    def deviceInterface(self, win):
        return LaserDevGui(self)
        
    def outputPower(self):
        """Return the current output power of the laser (excluding the effect of pockel cell, shutter, etc.)
        This information is determined in one of a few ways:
           1. The laser directly reports its power output (function needs to be reimplemented in subclass)
           2. A photodiode receves a small fraction of the beam and reports an estimated power
           3. The output power is specified in the config file
        """
        
        if self.hasPowerIndicator:
            ## run a protocol that checks the power
            daqName = self.config[self.config.keys()[0]]['channel'][0]
            powerInd = self.config['powerIndicator']['channel']
            rate = self.config['powerIndicator']['rate']
            sTime = self.config['powerIndicator']['settlingTime']
            mTime = self.config['powerIndicator']['measurmentTime']
            
            reps = 10
            dur = 0.1 + reps*0.1+(sTime+mTime)
            nPts = dur*rate
            
            ### create a waveform that flashes the QSwitch(or other way of turning on) the number specified by reps
            waveform = np.zeros(nPts, dtype=np.byte)
            for i in range(reps):
                waveform[(i+1)/10.*rate:((i+1)/10.+sTime+mTime)*rate] = 1 ## divide i+1 by 10 to increment by hundreds of milliseconds
            
            cmd = {
                'protocol': {'duration': dur},
                self.name: {'switchWaveform':waveform, 'shutterMode':'closed'},
                powerInd[0]: {powerInd[1]: {'record':True, 'recordInit':False}},
                daqName: {'numPts': nPts, 'rate': rate}
            }
            
            task = getManager().createTask(cmd)
            task.execute()
            result = task.getResult()
            
            ## pull out time that laser was on and off so that power can be measured in each state -- discard the settlingTime around each state change
            onMask = np.zeros(nPts, dtype=np.byte)
            offMask = np.zeros(nPts, dtype=np.byte)
            for i in range(reps):
                onMask[((i+1)/10+sTime)*rate:((i+1)/10+sTime+mTime)*rate] = 1
                offMask[(i/10.+2*sTime+mTime)*rate:(i/10.)*rate] = 1
            laserOn = result[onMask==True]
            laserOff = result[offMask==True]
            powerOn = laserOn.mean()
            powerOff = laserOff.mean()
            t, prob = stats.ttest_ind(laserOn, laserOff)
            if prob < 0.01: ### if powerOn is statistically different from powerOff
                #self.devGui.ui.outputPowerLabel.setText(siFormat(powerOn, suffix='W')) ## NO! device does not talk to GUI!
                self.sigPowerChanged.emit(powerOn)
                with self.variableLock:
                    self.params['currentPower'] = powerOn
                    #self.devGui.ui.samplePowerLabel.setText(siFormat(powerOn*self.scopeTransmission, suffix='W'))
                    pmin = self.params['expectedPower'] - self.params['expectedPower']*self.params['tolerance']
                    pmax = self.params['expectedPower'] + self.params['expectedPower']*self.params['tolerance']
                if powerOn < pmin or powerOn > pmax:
                    raise HelpfulException("Power is outside expected range. Please adjust expected value or adjust the tuning of your laser.")
                return powerOn
            
            else:
                raise Exception("No QSwitch (or other way of turning on) detected while measuring Laser.outputPower()")
            
        ## return the power specified in the config file if there's no powerIndicator
        else:
            return self.config.get('power', None)
        
    def getPCellWaveform(self, powerCmd):
        ### return a waveform of pCell voltages to give the power in powerCmd
        pass

            
    def testProtocol(self):
        daqName = self.getDAQName('shutter')
        powerInd = self.config['powerIndicator']['channel']
        rate = self.config['powerIndicator']['rate']
        sTime = self.config['powerIndicator']['settlingTime']
        mTime = self.config['powerIndicator']['measurmentTime']
        reps = 10
        dur = 0.1 + reps*0.1+(0.001+0.005)
        nPts = dur*rate
       
        
        
        ### create a waveform that flashes the QSwitch(or other way of turning on) the number specified by reps
        waveform = np.zeros(nPts, dtype=np.byte)
        for i in range(reps):
            waveform[(i+1)/10.*rate:((i+1)/10.+sTime+mTime)*rate] = 1 ## divide i+1 by 10 to increment by hundreds of milliseconds
        
        cmd = {
            'protocol': {'duration': dur},
            self.name: {'switchWaveform':waveform, 'shutterMode':'closed'},
            powerInd[0]: {powerInd[1]: {'record':True, 'recordInit':False}},
            daqName: {'numPts': nPts, 'rate': rate}
        }
        
        task = getManager().createTask(cmd)
        task.execute()
        result = task.getResult()
        
        


class LaserTask(DAQGenericTask):
    """
    
    Example protocol command structure:
    {                                  #### powerWaveform, switchWaveform and pulses are mutually exclusive; result of specifying more than one is undefined
        'powerWaveform': array(...),   ## array of power values (specifies the power that should enter the sample)
                                       ## only useful if there is an analog modulator of some kind (Pockel cell, etc)
        'switchWaveform': array(...),  ## array of values 0-1 specifying the fraction of full power to output.
                                       ## For Q-switched lasers, a value > 0 activates the switch
        'pulses': [(time, energy, duration), ...], ### Not yet implemented:
                                       ## the device will generate its own command structure with the requested pulse energies.
                                       ## duration may only be specified if a modulator is available.
                                       
                                       #### shutterWaveform and shutterMode are exclusive; if shutterWaveform is specified shutterMode will be ignored
        'shutterWaveform': array(...)  ## array of 0/1 values that specify whether shutter is open (1) or closed (0)
        'shutterMode': 'auto',         ## specifies how the shutter should be used:
                                       ##   auto -- the shutter is opened immediately (with small delay) before laser output is needed
                                       ##           and closed immediately (with no delay) after.
                                       ##   open -- the shutter is opened for the whole protocol and returned to its holding state afterward
                                       ##   closed -- the shutter is kept closed for the protocol and returned to its holding state afterward
                                       
        'wavelength': x,               ## sets the wavelength before executing the protocol
        'checkPower': True,            ## If true, the laser will check its output power before executing the protocol. 
    }
    
    """
    def __init__(self, dev, cmd):
        self.cmd = cmd
        self.dev = dev ## this happens in DAQGeneric initialization, but we need it here too since it is used in making the waveforms that go into DaqGeneric.__init__
        
        ## create protocol structure to pass to daqGeneric; protocols will get filled in when self.configure() gets called
        cmd['daqProtocol'] = {}
        if 'shutter' in dev.config:
            cmd['daqProtocol']['shutter'] = None
        if 'qswitch' in dev.config:
            cmd['daqProtocol']['qswitch'] = None
        if 'pCell' in dev.config:
            cmd['daqProtocol']['pCell'] = None
            

        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'])
        
    def generateDaqProtocol(self, waveform, rate):
        ### waveform should be in units of power
        nPts = len(waveform)
        daqCmd = {}
        
        if self.dev.config.get('pCell', None) is not None:
            ## convert power values using calibration data
            daqCmd['pCell'] = self.dev.getPCellWaveform(waveform)
        
        if self.dev.config.get('shutter', None) is not None:
            shutterCmd = np.zeros(nPts, dtype=np.byte)
            delay = self.dev.config['shutter'].get('delay', 0.0)
            shutterCmd[waveform != 0] = 1 ## open shutter when we expect power
            ## open shutter a little before we expect power because it has a delay
            delayPts = int(delay*rate)
            a = np.argwhere(shutterCmd[1:]-shutterCmd[:-1] == 1)
            for i in range(len(a)):
                shutterCmd[a[i]-delayPts:a[i]+1] = 1
            daqCmd['shutter'] = shutterCmd
            
        if self.dev.config.get('qswitch', None) is not None:
            qswitchCmd = np.zeros(nPts, dtype=np.byte)
            qswitchCmd[waveform != 0] = 1
            daqCmd['qSwitch'] = qswitchCmd
            
        return daqCmd
        
    def configure(self, tasks, startOrder):
        ## need to generate shutter, qswitch and pcell waveforms that get passed into DaqGenericTask
        daqName = self.dev.getDAQName('shutter')
        daqTask = tasks[daqName]
        rate = daqTask.getChanSampleRate(self.dev.config['shutter']['channel'][1])
        
        if self.cmd.get('checkPower', False):
            self.dev.outputPower()
        if 'powerWaveform' in self.cmd:
            if self.dev.config.get('pCell', None) is None:
                raise Exception("%s device does not have a pockelCell, so cannot have an analog power command." %str(self.dev.name))
            self.cmd['daqProtocol'] = self.generateDaqProtocol(cmd['powerWaveform'], rate)
            
        elif 'switchWaveform' in self.cmd:
            ## convert range 0-1 to full voltage range of device
            
            ## make function in dev instead
            with self.dev.variableLock:
                if self.dev.params['useExpectedPower']:
                    power = self.dev.params['expectedPower']
                else:
                    power = self.dev.params['currentPower']
                transmission = self.dev.params['scopeTransmission']
                transmission = 0.1
            powerCmd = self.cmd['switchWaveform']*power*transmission
            self.cmd['daqProtocol'] = self.generateDaqProtocol(powerCmd, rate)
            
        elif 'pulse' in cmd:
            pass  ## generate pulse waveform
        
        if 'wavelength' in self.cmd:
            self.dev.setWavelength(self.cmd['wavelength'])
        self._DAQCmd = self.cmd['daqProtocol']
        DAQGenericTask.configure(self, tasks, startOrder)

    def getResult(self):
        ## getResult from DAQGeneric, then add in command waveform
        pass
    
    #def storeResult(self, dirHandle):
        #pass

