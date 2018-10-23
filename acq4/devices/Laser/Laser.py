from __future__ import print_function
from acq4.util import Qt
#import configfile
from acq4.Manager import getManager, logExc, logMsg
from acq4.util.Mutex import Mutex
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask
from acq4.devices.OptomechDevice import OptomechDevice
from .LaserDevGui import LaserDevGui
from .LaserTaskGui import LaserTaskGui
import os
import time
import numpy as np
from scipy import stats
from acq4.pyqtgraph.functions import siFormat
from acq4.util.HelpfulException import HelpfulException
import acq4.pyqtgraph as pg
import acq4.util.metaarray as metaarray
from acq4.devices.NiDAQ.nidaq import NiDAQ
import acq4.util.ptime as ptime


class Laser(DAQGeneric, OptomechDevice):
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
            parentDevice: 'Microscope'
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
            parentDevice: 'Microscope'
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
            parentDevice: 'Microscope'
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
        
        
        
    Task examples:
    
    { 'wavelength': 780*nm, 'powerWaveform': array([...]) }  ## calibrated; float array in W
    { 'switchWaveform': array([...]) }                       ## uncalibrated; 0=off -> 1=full power
    { 'pulse': [(0.5*s, 100*uJ), ...] }                     ## (time, pulse energy) pairs
    """
    
    sigOutputPowerChanged = Qt.Signal(object, object)  ## power, bool (power within expected range)
    sigSamplePowerChanged = Qt.Signal(object)
    sigWavelengthChanged = Qt.Signal(object)
    
    def __init__(self, manager, config, name):
        self.config = config
        self.manager = manager
        self.hasPowerIndicator = False
        self.hasShutter = False
        self.hasTriggerableShutter = False
        self.hasQSwitch = False
        self.hasPCell = False
        self.hasTunableWavelength = False
        
        self.params = {
            'expectedPower': config.get('power', None), ## Expected output
            'currentPower': None, ## Last measured output power
            'scopeTransmission': None, ## percentage of output power that is transmitted to slice
            'tolerance': 10.0, ## in %
            'useExpectedPower': True,
            'powerAlert': True, ## set True if you want changes in output power to raise an error
            'powerUpdateInterval': config.get('powerUpdateInterval', 60),  # Time in seconds before power must be measured again (if requested)
        }
        
        self._lastPowerMeasureTime = None

        daqConfig = {} ### DAQ generic needs to know about powerIndicator, pCell, shutter, qswitch
        if 'powerIndicator' in config:
            self.hasPowerIndicator = True
            #### name of powerIndicator is config['powerIndicator']['channel'][0]
            #daqConfig['powerInd'] = {'channel': config['powerIndicator']['channel'], 'type': 'ai'}
        if 'shutter' in config:
            daqConfig['shutter'] = config['shutter']
            self.hasTriggerableShutter = True
            self.hasShutter = True
        if 'qSwitch' in config:
            daqConfig['qSwitch'] = config['qSwitch']
            self.hasQSwitch = True
        if 'pCell' in config:
            daqConfig['pCell'] = config['pCell']
            self.hasPCell = True
                        
        daqConfig['power'] = {'type': 'ao', 'units': 'W'}  ## virtual channel used for creating control widgets
        DAQGeneric.__init__(self, manager, daqConfig, name)
        OptomechDevice.__init__(self, manager, config, name)
       
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.variableLock = Mutex(Qt.QMutex.Recursive)
        self.calibrationIndex = None
        self.pCellCalibration = None
        self.getPowerHistory()
        
        #self.scope = manager.getDevice(self.config['scope'])
        #self.scope.sigObjectiveChanged.connect(self.objectiveChanged)
        self.sigGlobalSubdeviceChanged.connect(self.opticStateChanged) ## called when objectives/filters have been switched
        
        manager.declareInterface(name, ['laser'], self)
        manager.sigAbortAll.connect(self.closeShutter)
        
    def setParam(self, **kwargs):
        with self.variableLock:
            for k in kwargs:
                self.params[k] = kwargs[k]
                
    def getParam(self, arg):
        with self.variableLock:
            return self.params[arg]
    
    def getCalibrationIndex(self):
        with self.lock:
            if self.calibrationIndex is None:
                index = self.readConfigFile('index')
                self.calibrationIndex = index
                self.pCellCalibration = index.get('pCellCalibration', None)
            return self.calibrationIndex
        
    def getPowerHistory(self):
        with self.variableLock:
            ph = self.readConfigFile('powerHistory')
            if ph == {}:
                date = str(time.strftime('%Y.%m.%d %H:%M:%S'))
                self.writeConfigFile({'entry_0': {'date':date, 'expectedPower':0}}, 'powerHistory')
                self.params['expectedPower'] = 0
                self.powerHistoryCount = 1
            else:
                self.powerHistoryCount = len(ph)
                self.params['expectedPower'] = list(ph.values())[-1]['expectedPower']
                return ph
                
    def appendPowerHistory(self, power):
        with self.variableLock:
            date = str(time.strftime('%Y.%m.%d %H:%M:%S'))
            self.appendConfigFile({'entry_'+str(self.powerHistoryCount):{'date': date, 'expectedPower':power}}, 'powerHistory')

    def writeCalibrationIndex(self, index):
        with self.lock:
            self.writeConfigFile(index, 'index')
            self.calibrationIndex = index
        
    def setAlignmentMode(self, b):
        """If true, configures the laser for low-power alignment mode. 
        Note: If the laser achieves low power solely through PWM, then
        alignment mode will only be available during tasks."""
        
        pass
    
    def setWavelength(self, wl):
        """Set the laser's wavelength (if tunable).
        Arguments:
          wl:  """
        raise HelpfulException("%s device does not support wavelength tuning." %str(self.name()), reasons=["Hardware doesn't support tuning.", "setWavelenth function is not reimplemented in subclass."])
    
    def getWavelength(self):
        return self.config.get('wavelength', 0)
    
    def getWavelengthRange(self):
        pass
        
    def openShutter(self):
        if self.hasTriggerableShutter:
            self.setChanHolding('shutter', 1)
    
    def closeShutter(self):
        if self.hasTriggerableShutter:
            self.setChanHolding('shutter', 0)

    def getShutter(self):
        """Return True if the shutter is open."""
        if self.hasTriggerableShutter:
            return self.getChanHolding('shutter') > 0
        else:
            raise Exception("No shutter on this laser.")
   
    def openQSwitch(self):
        if self.hasQSwitch:
            self.setChanHolding('qSwitch', 1)
    
    def closeQSwitch(self):
        if self.hasQSwitch:
            self.setChanHolding('qSwitch', 0)
            
    def getCalibration(self, opticState=None, wavelength=None):
        """Return the calibrated laser transmission for the given objective and wavelength.
        If either argument is None, then it will be replaced with the currently known value.
        Returns None if there is no calibration."""
        
        if opticState is None:
            opticState = self.getDeviceStateKey()
            
        if wavelength is None:
            wl = self.getWavelength()
        else:
            wl = wavelength

        ## look up transmission value for this objective in calibration list
        index = self.getCalibrationIndex()
        vals = index.get(opticState, None)
        if vals is None:
            return None
        wl = siFormat(wl, suffix='m')
        vals = vals.get(wl, None)
        if vals is None:
            return None
        
        return vals['transmission']
            
    def opticStateChanged(self, change):
        self.updateSamplePower()
    
    def createTask(self, cmd, parentTask):
        return LaserTask(self, cmd, parentTask)
        
    def taskInterface(self, taskRunner):
        return LaserTaskGui(self, taskRunner)
        
    def deviceInterface(self, win):
        return LaserDevGui(self)
    
    def getDAQName(self, channel=None):
        if channel is None:
            if self.hasTriggerableShutter:
                ch = 'shutter'
                daqName = DAQGeneric.getDAQName(self, 'shutter')
            elif self.hasPCell:
                ch = 'pCell'
                daqName = DAQGeneric.getDAQName(self, 'pCell')
            elif self.hasQSwitch:
                ch = 'qSwitch'
                daqName = DAQGeneric.getDAQName(self, 'qSwitch')
            else:
                return (None, None)
            #raise HelpfulException("LaserTask can't find name of DAQ device to use for this task.")
            return (daqName, ch)
        else:
            return DAQGeneric.getDAQName(self, channel)
        
    def calibrate(self, powerMeter, mTime, sTime):
        #meter = str(self.ui.meterCombo.currentText())
        #obj = self.manager.getDevice(scope).getObjective()['name']
        opticState = self.getDeviceStateKey()
        #print "Laser.calibrate() opticState:", opticState
        wavelength = siFormat(self.getWavelength(), suffix='m')
        date = time.strftime('%Y.%m.%d %H:%M', time.localtime())
        index = self.getCalibrationIndex()
        
        ## Run calibration
        if not self.hasPCell:
            power, transmission = self.runCalibration(powerMeter=powerMeter, measureTime=mTime, settleTime=sTime)
            #self.setParam(currentPower=power, scopeTransmission=transmission)  ## wrong--power is samplePower, not outputPower.
        else:
            raise Exception("Pockel Cell calibration is not yet implented.")
            #if index.has_key('pCellCalibration') and not self.ui.recalibratePCellCheck.isChecked():
                #power, transmission = self.runCalibration() ## need to tell it to run with open pCell
            #else:
                #minVal = self.ui.minVSpin.value()
                #maxVal = self.ui.maxVSpin.value()
                #steps = self.ui.stepsSpin.value()
                #power = []
                #arr = np.zeros(steps, dtype=[('voltage', float), ('trans', float)])
                #for i,v in enumerate(np.linspace(minVal, maxVal, steps)):
                    #p, t = self.runCalibration(pCellVoltage=v) ### returns power at sample(or where powermeter was), and transmission through whole system
                    #power.append(p)
                    #arr[i]['trans']= t
                    #arr[i]['voltage']= v
                #power = (min(power), max(power))
                #transmission = (arr['trans'].min(), arr['trans'].min())
                #arr['trans'] = arr['trans']/arr['trans'].max()
                #minV = arr['voltage'][arr['trans']==arr['trans'].min()]
                #maxV = arr['voltage'][arr['trans']==arr['trans'].max()]
                #if minV < maxV:
                    #self.dev.pCellCurve = arr[arr['voltage']>minV * arr['voltage']<maxV]
                #else:
                    #self.dev.pCellCurve = arr[arr['voltage']<minV * arr['voltage']>maxV]
                    
                #index['pCellCalibration'] = {'voltage': list(self.dev.pCellCurve['voltage']), 
                                             #'trans': list(self.dev.pCellCurve['trans'])}
                
            
              
        #if scope not in index:
            #index[scope] = {}
        if opticState not in index:
            index[opticState] = {}
        index[opticState][wavelength] = {'power': power, 'transmission':transmission, 'date': date}

        self.writeCalibrationIndex(index)
        self.updateSamplePower()
        
    def runCalibration(self, powerMeter=None, measureTime=0.1, settleTime=0.005, pCellVoltage=None, rate = 100000):
        daqName = self.getDAQName()[0]
        duration = measureTime + settleTime
        nPts = int(rate * duration)
        
        cmdOff = {'protocol': {'duration': duration, 'timeout': duration+5.0},
                self.name(): {'shutterMode':'closed', 'switchWaveform':np.zeros(nPts, dtype=np.byte)},
                powerMeter: {x: {'record':True, 'recordInit':False} for x in getManager().getDevice(powerMeter).listChannels()},
                daqName: {'numPts': nPts, 'rate':rate}
                }
        
        if self.hasPowerIndicator:
            powerInd = self.config['powerIndicator']['channel']
            cmdOff[powerInd[0]] = {powerInd[1]: {'record':True, 'recordInit':False}}
            
        if pCellVoltage is not None:
            if self.hasPCell:
                a = np.zeros(nPts, dtype=float)
                a[:] = pCellVoltage
                cmdOff[self.name()]['pCell'] = a
            else:
                raise Exception("Laser device %s does not have a pCell, therefore no pCell voltage can be set." %self.name())
            
        cmdOn = cmdOff.copy()
        wave = np.ones(nPts, dtype=np.byte)
        wave[-1] = 0
        shutterDelay = self.config.get('shutter', {}).get('delay', 0)
        wave[:shutterDelay*rate] = 0
        cmdOn[self.name()]={'shutterMode':'open', 'switchWaveform':wave}
        
        #print "cmdOff: ", cmdOff
        taskOff = getManager().createTask(cmdOff)
        taskOff.execute()
        resultOff = taskOff.getResult()
        
        taskOn = getManager().createTask(cmdOn)
        taskOn.execute()
        resultOn = taskOn.getResult()
            
        measurementStart = (shutterDelay+settleTime)*rate
            
        if self.hasPowerIndicator:
            powerOutOn = resultOn[powerInd[0]][0][measurementStart:].mean()
        else:
            powerOutOn = self.outputPower()
            
        laserOff = resultOff[powerMeter][0][measurementStart:]
        laserOn = resultOn[powerMeter][0][measurementStart:]
    
        t, prob = stats.ttest_ind(laserOn.asarray(), laserOff.asarray())
        if prob > 0.001:
            raise Exception("Power meter device %s could not detect laser." %powerMeter)
        else:
            powerSampleOn = laserOn.mean()
            transmission = powerSampleOn/powerOutOn
            return (powerSampleOn, transmission)
       
    def getCalibrationList(self):
        """Return a list of available calibrations."""
        calList = []
        index = self.getCalibrationIndex()
        if 'pCellCalibration' in index:
            index.pop('pCellCalibration')
        #self.microscopes.append(scope)
        for opticState in index:
            for wavelength in index[opticState]:
                cal = index[opticState][wavelength]
                power = cal['power']
                trans = cal['transmission']
                date = cal['date']
                calList.append((opticState, wavelength, trans, power, date))
        return calList
        
    def outputPower(self, forceUpdate=False):
        """
        Return the output power of the laser in Watts.
        
        The power returned does not account for the effects of pockels cell, shutter, etc.
        This information is determined in one of a few ways:

           1. The laser directly reports its power output (function needs to be reimplemented in subclass)
           2. A photodiode receves a small fraction of the beam and reports an estimated power
           3. The output power is specified in the config file
           
        Use checkPowerValidity(power) to determine whether this level is within the expected range.

        Subsequent calls to outputPower() may return a cached value (the maximum age of this value is
        determined by the powerUpdateInterval config parameter). Use forceUpdate=True to ignore any
        cached values.
        """
        now = ptime.time()
        needUpdate = (
            forceUpdate is True or 
            self.params['currentPower'] is None or 
            self._lastPowerMeasureTime is None or 
            now - self._lastPowerMeasureTime > self.params['powerUpdateInterval']
        )

        if needUpdate:
            self.params['currentPower'] = self._measurePower()
            self._lastPowerMeasureTime = ptime.time()
        return self.params['currentPower']

    def _measurePower(self):
        if self.hasPowerIndicator:
            ## run a task that checks the power
            daqName =  self.getDAQName('shutter')
            powerInd = self.config['powerIndicator']['channel']
            rate = self.config['powerIndicator']['rate']
            
            pConfig = getManager().getDevice(self.config['powerIndicator']['channel'][0]).listChannels()[self.config['powerIndicator']['channel'][1]]
            sTime = pConfig.get('settlingTime', None)
            mTime = pConfig.get('measurementTime', None)
            
            if mTime is None or sTime is None:
                raise Exception("The power indicator (%s) specified for %s needs to be configured with both a 'settlingTime' value and a 'measurementTime' value." %(self.config['powerIndicator']['channel'], self.name()))
            
            dur = 0.1 + (sTime+mTime)
            nPts = int(dur*rate)
            
            ### create a waveform that flashes the QSwitch(or other way of turning on) the number specified by reps
            waveform = np.zeros(nPts, dtype=np.byte)
            #for i in range(reps):
                #waveform[(i+1)/10.*rate:((i+1)/10.+sTime+mTime)*rate] = 1 ## divide i+1 by 10 to increment by hundreds of milliseconds
            waveform[0.1*rate:-2] = 1
            
            measureMode = self.measurementMode()
            cmd = {
                'protocol': {'duration': dur},
                self.name(): {'switchWaveform':waveform, 'shutterMode': measureMode['shutter']},
                powerInd[0]: {powerInd[1]: {'record':True, 'recordInit':False}},
                daqName: {'numPts': nPts, 'rate': rate}
            }
            #print "outputPowerCmd: ", cmd
            task = getManager().createTask(cmd)
            task.execute(processEvents=False)  # disable event processing to prevent recurrent requests
            result = task.getResult()
            
            ## pull out time that laser was on and off so that power can be measured in each state -- discard the settlingTime around each state change
            #onMask = np.zeros(nPts, dtype=np.byte)
            #offMask = np.zeros(nPts, dtype=np.byte)
            #for i in range(reps):
                #onMask[((i+1)/10+sTime)*rate:((i+1)/10+sTime+mTime)*rate] = 1
                #offMask[(i/10.+2*sTime+mTime)*rate:(i+1/10.)*rate] = 1
            powerIndTrace = result[powerInd[0]]
            if powerIndTrace is None:
                raise Exception("No data returned from power indicator")
            laserOn = powerIndTrace[0][0.1*rate:-2].asarray()
            laserOff = powerIndTrace[0][:0.1*rate].asarray()

            t, prob = stats.ttest_ind(laserOn, laserOff)
            if prob < 0.01: ### if powerOn is statistically different from powerOff
                powerOn = laserOn.mean()
                if powerOn < 0:
                    powerOn = 0.0
                powerOff = laserOff.mean()
                #self.devGui.ui.outputPowerLabel.setText(siFormat(powerOn, suffix='W')) ## NO! device does not talk to GUI!
                self.setParam(currentPower=powerOn)
                powerOk = self.checkPowerValidity(powerOn)
                self.sigOutputPowerChanged.emit(powerOn, powerOk)
                self.updateSamplePower()
                return powerOn
            else:
                logMsg("No laser pulse detected by power indicator '%s' while measuring Laser.outputPower()" % powerInd[0], msgType='warning')
                self.setParam(currentPower=0.0)
                self.updateSamplePower()
                return 0.0
            
        ## return the power specified in the config file if there's no powerIndicator
        else:
            return self.config.get('power', None)

    def updateSamplePower(self):
        ## Report new sample power given the current state of the laser
        trans = self.getCalibration()
        if trans is None:
            self.setParam(scopeTransmission=None)
            self.setParam(samplePower=None)
            self.sigSamplePowerChanged.emit(None)
        else:
            self.setParam(scopeTransmission=trans)
            power = self.getParam('currentPower') * trans
            self.setParam(samplePower=power)
            self.sigSamplePowerChanged.emit(power)
        
    def samplePower(self, power=None):
        """
        Return the estimated power-at-sample for a given output power.
        If power is None, the current output power of the laser is used instead.
        """
        trans = self.getParam('scopeTransmission')
        if trans is None:
            return None
        
        if power is None:
            power = self.outputPower()
        if power is None:
            return None
            
        return power * trans
        

    def checkPowerValidity(self, power):
        """Return boolean indicating whether power is inside the expected power range."""
        with self.variableLock:
            diff = self.params['expectedPower']*self.params['tolerance']/100.0
            expected = self.params['expectedPower']
        return  (not self.getParam('powerAlert')) or (abs(power-expected) <= diff)
            #if self.getParam('powerAlert'):
                #logMsg("%s power is outside expected range. Please adjust expected value or adjust the tuning of the laser." %self.name(), msgType='error')
        
    def getPCellWaveform(self, powerCmd, cmd):
        ### return a waveform of pCell voltages to give the power in powerCmd
        return
        #if self.hasPCell:
            #print cmd
            #print 'powercmd: ',powerCmd
            #print np.amax(powerCmd)
            
            #raise Exception("Support for pockel cells is not yet implemented.")
    

    def getChannelCmds(self, cmd, rate):
        ### cmd is a dict and can contain 'powerWaveform' or 'switchWaveform' keys with the array as a value
        
        
        if 'switchWaveform' in cmd:
            cmdWaveform = cmd['switchWaveform']
            vals = np.unique(cmd['switchWaveform'])
            if not self.hasPCell and len(vals)==2 and (1 or 1.0) not in vals: ## check to make sure we can give the specified power.
                raise Exception('An analog power modulator is neccessary to get power values other than zero and one (full power). The following values (as percentages of full power) were requested: %s. This %s device does not have an analog power modulator.' %(str(vals), self.name()))
        elif 'powerWaveform' in cmd:
            cmdWaveform = cmd['powerWaveform']
        else:
            raise Exception('Not sure how to generate channel commands for %s' %str(cmd))
        
        nPts = len(cmdWaveform)
        daqCmd = {}
        #if self.dev.config.get('pCell', None) is not None:
        if self.hasPCell:
            ## convert power values using calibration data
            if 'switchWaveform' in cmd:
                with self.variableLock:
                    if self.params['useExpectedPower']:
                        power = self.params['expectedPower']
                    else:
                        power = self.params['currentPower']
                    transmission = self.params['scopeTransmission']
                    if transmission is None:
                        raise Exception('Power transmission has not been calibrated for "%s" with the current optics and wavelength.' % self.name())
                    #transmission = 0.1
                powerCmd = cmd['switchWaveform']*power*transmission
            else:
                powerCmd = cmd['powerWaveform']
            daqCmd['pCell'] = self.getPCellWaveform(powerCmd, cmd)
        else:
            if len(np.unique(cmdWaveform)) > 2: ## check to make sure command doesn't specify powers we can't do
                raise Exception("%s device does not have an analog power modulator, so can only have a binary power command." %str(self.name()))
            
        if self.hasQSwitch:
        #if self.dev.config.get('qSwitch', None) is not None:
            qswitchCmd = np.zeros(nPts, dtype=np.byte)
            qswitchCmd[cmdWaveform > 1e-5] = 1
            daqCmd['qSwitch'] = qswitchCmd
            
        if self.hasTriggerableShutter:
            shutterCmd = np.zeros(nPts, dtype=np.byte)
            delay = self.config['shutter'].get('delay', 0.0) 
            shutterCmd[cmdWaveform != 0] = 1 ## open shutter when we expect power
            ## open shutter a little before we expect power because it has a delay
            delayPts = int(delay*rate) 
            a = np.argwhere(shutterCmd[1:]-shutterCmd[:-1] == 1)+1
            for i in a:
                start = i-delayPts
                if start < 0:
                    print(start, delayPts, i)
                    raise HelpfulException("Shutter takes %g seconds to open. Power pulse cannot be started before then." %delay)
                shutterCmd[start:i+1] = 1
            daqCmd['shutter'] = shutterCmd
            
        return daqCmd

    def measurementMode(self):
        """
        Return mode hints used to automatically generate the task used to measure laser power.

        """
        default = {
            'shutter': 'auto'
            }

        return self.config.get('powerMeasureMode', default)

    def testTask(self):
        daqName = self.getDAQName('shutter')
        powerInd = self.config['powerIndicator']['channel']
        rate = self.config['powerIndicator']['rate']
        sTime = self.config['powerIndicator']['settlingTime']
        mTime = self.config['powerIndicator']['measurementTime']
        reps = 10
        dur = 0.1 + reps*0.1+(0.001+0.005)
        nPts = int(dur*rate)
       
        measureMode = self.measurementMode()
        
        ### create a waveform that flashes the QSwitch(or other way of turning on) the number specified by reps
        waveform = np.zeros(nPts, dtype=np.byte)
        for i in range(reps):
            waveform[(i+1)/10.*rate:((i+1)/10.+sTime+mTime)*rate] = 1 ## divide i+1 by 10 to increment by hundreds of milliseconds
        
        cmd = {
            'protocol': {'duration': dur},
            self.name(): {'switchWaveform':waveform, 'shutterMode': 'off'},
            powerInd[0]: {powerInd[1]: {'record':True, 'recordInit':False}},
            daqName: {'numPts': nPts, 'rate': rate}
        }
        
        task = getManager().createTask(cmd)
        task.execute()
        result = task.getResult()
        



class LaserTask(DAQGenericTask):
    """
    
    Example task command structure:
    {                                  #### powerWaveform, switchWaveform and pulses are mutually exclusive; result of specifying more than one is undefined
        'powerWaveform': array(...),   ## array of power values (specifies the power that should enter the sample)
                                       ## only useful if there is an analog modulator of some kind (Pockel cell, etc)
        'switchWaveform': array(...),  ## array of values 0-1 specifying the fraction of full power to output.
                                       ## For Q-switched lasers, a value > 0 activates the switch
        'pulses': [(time, energy, duration), ...], ### Not yet implemented:
                                       ## the device will generate its own command structure with the requested pulse energies.
                                       ## duration may only be specified if a modulator is available.
                                       
                                       
                                       #####   Specifically specifying the daqGeneric cmd for the qSwitch, pCell or shutter gets precedent over waveforms that might be calculated from a 'powerWaveform', 'switchWaveform', or 'pulses' cmd
        'pCell': {'command':array(....),               ## daqGeneric command that gets passed straight through
                  'preset': value
                  'holding': value}
        'qSwitch: {'command':array(....), etc}         ## array of 0/1 values that specify whether qSwitch is off (0) or on (1)           
        'shutter': {'command':array(....), etc}          ## array of 0/1 values that specify whether shutter is open (1) or closed (0)
       
        
                                       #### 'shutter' and 'shutterMode' are exclusive; if 'shutter' is specified shutterMode will be ignored
        'shutterMode': 'auto',         ## specifies how the shutter should be used:
                                       ##   auto -- the shutter is opened immediately (with small delay) before laser output is needed
                                       ##           and closed immediately (with no delay) after. Default.
                                       ##   open -- the shutter is opened for the whole task and returned to its holding state afterward
                                       ##   closed -- the shutter is kept closed for the task and returned to its holding state afterward
                                       
        'wavelength': x,               ## sets the wavelength before executing the task
        'checkPower': True,            ## If true, the laser will check its output power before executing the task. 
        'ignorePowerWaveform': False   ## If True, the power waveform is merely passed through to the task results 
                                       ## (it is assumed the command also has raw waveforms in this case)
        'alignMode': False             ## If true, put the laser into alignment mode for the entire duration of the task.
        
    }
    
    """
    def __init__(self, dev, cmd, parentTask):
        self.cmd = cmd
        self.dev = dev ## this happens in DAQGeneric initialization, but we need it here too since it is used in making the waveforms that go into DaqGeneric.__init__
        if 'shutterMode' not in cmd:
            cmd['shutterMode'] = 'auto'
            
        ## create task structure to pass to daqGeneric, and retain a pointer to it here; DAQGeneric tasks will get filled in from LaserTask when self.configure() gets called
        cmd['daqProtocol'] = {}
        if 'shutter' in dev.config:
            cmd['daqProtocol']['shutter'] = {}
        if 'qSwitch' in dev.config:
            cmd['daqProtocol']['qSwitch'] = {}
        if 'pCell' in dev.config:
            cmd['daqProtocol']['pCell'] = {}
            
        #cmd['daqProtocol']['power'] = {}
        
        if cmd.get('alignMode', False):
            alignConfig = self.dev.config.get('alignmentMode', None)
            #if alignConfig is None:
            #    raise Exception("Laser alignment mode requested, but this laser has no 'alignmentMode' in its configuration.")
            if alignConfig is not None:
                if 'shutter' in alignConfig:
                    cmd['daqProtocol']['shutter']['preset'] = 1 if alignConfig['shutter'] else 0
                if 'qSwitch' in alignConfig:
                    cmd['daqProtocol']['qSwitch']['preset'] = 1 if alignConfig['qSwitch'] else 0
                if 'pCell' in alignConfig:
                    cmd['daqProtocol']['pCell']['preset'] = alignConfig['pCell']
                elif 'power' in alignConfig:
                    raise Exception("Alignment mode by power not implemented yet.")
                

        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'], parentTask)
        
    def configure(self):
        ##  Get rate: first get name of DAQ, then ask the DAQ task for its rate
        daqName, ch = self.dev.getDAQName()
        if daqName is None:
            return
        tasks = self.parentTask().tasks
        daqTask = tasks[daqName]
        rate = daqTask.getChanSampleRate(self.dev.config[ch]['channel'][1])
        
        ### do a power check if requested
        if self.cmd.get('checkPower', False):
            self.dev.outputPower()
            
        ### set wavelength
        if 'wavelength' in self.cmd:
            self.dev.setWavelength(self.cmd['wavelength'])
            
        ### send power/switch waveforms to device for pCell/qSwitch/shutter cmd calculation
        #print "Cmd:", self.cmd
        if 'powerWaveform' in self.cmd and not self.cmd.get('ignorePowerWaveform', False):
            calcCmds = self.dev.getChannelCmds({'powerWaveform':self.cmd['powerWaveform']}, rate)
        elif 'switchWaveform' in self.cmd:
            calcCmds = self.dev.getChannelCmds({'switchWaveform':self.cmd['switchWaveform']}, rate)
        elif 'pulse' in self.cmd:
            raise Exception('Support for (pulseTime/energy) pair commands is not yet implemented.')
        else:
            calcCmds = {}

        
        ### set up shutter, qSwitch and pCell -- self.cmd['daqProtocol'] points to the command structure that the DAQGeneric will use, don't set self.cmd['daqProtocol'] equal to something else!
        if 'shutter' in self.cmd:
            self.cmd['daqProtocol']['shutter'] = self.cmd['shutter']
            self.cmd['daqProtocol']['shutter']['command'][-1] = 0
        elif 'shutterMode' in self.cmd:
            if self.cmd['shutterMode'] is 'auto':
                if 'shutter' in calcCmds:
                    self.cmd['daqProtocol']['shutter'] = {'command': calcCmds['shutter']}
            elif self.cmd['shutterMode'] is 'closed':
                #self.cmd['daqProtocol']['shutter']['command'] = np.zeros(len(calcCmds['shutter']), dtype=np.byte)
                self.cmd['daqProtocol']['shutter'] = {'preset': 0}
            elif self.cmd['shutterMode'] is 'open':
                self.cmd['daqProtocol']['shutter'] = {'preset': 1}
                # self.cmd['daqProtocol']['shutter'] = {'command': np.ones(len(calcCmds['shutter']), dtype=np.byte)}
                
                # ## set to holding value, not 0
                # self.cmd['daqProtocol']['shutter']['command'][-1] = 0
            
        if 'pCell' in self.cmd:
            self.cmd['daqProtocol']['pCell'] = self.cmd['pCell']
        elif 'pCell' in calcCmds:
            self.cmd['daqProtocol']['pCell']['command'] = calcCmds['pCell']
            
        if 'qSwitch' in self.cmd:
            self.cmd['daqProtocol']['qSwitch'] = self.cmd['qSwitch']
            self.cmd['daqProtocol']['qSwitch']['command'][-1] = 0
        elif 'qSwitch' in calcCmds:
            self.cmd['daqProtocol']['qSwitch']['command'] = calcCmds['qSwitch']
            self.cmd['daqProtocol']['qSwitch']['command'][-1] = 0
        
        #if 'powerWaveform' in self.cmd: ## send powerWaveform into daqProtocol so it can be downsampled with the other data
            #self.cmd['daqProtocol']['power']['command'] = self.cmd['powerWaveform']
        
        self.currentPower = self.dev.getParam('currentPower')
        self.expectedPower = self.dev.getParam('expectedPower')
        
        DAQGenericTask.configure(self) ## DAQGenericTask will use self.cmd['daqProtocol']
        
    def getResult(self):
        ## getResult from DAQGeneric, then add in command waveform
        result = DAQGenericTask.getResult(self)
        if result is None:
            return None
        
        arr = result.view(np.ndarray)
        
        daqInfo = result._info[-1]['DAQ']
        ## find DAQ info for any output channel
        for ch in ['shutter', 'qSwitch', 'pCell']:
            if ch in daqInfo:
                ds = daqInfo[ch].get('downsampling', 1)
                break
        
        if 'powerWaveform' in self.cmd:
            ## downsample power waveform to match other channels
            power = self.cmd['powerWaveform']
            if ds > 1:
                power = NiDAQ.meanResample(power, ds)
            arr = np.append(arr, power[np.newaxis, :], axis=0)
            
            #result = np.append(result, self.cmd['powerWaveform'][np.newaxis, :], axis=0)
            result._info[0]['cols'].append({'name': 'power', 'units': 'W'})
        elif 'switchWaveform' in self.cmd:
            switch = self.cmd['switchWaveform']
            if ds > 1:
                switch = NiDAQ.meanResample(switch, ds)
            arr = np.append(arr, switch[np.newaxis, :], axis=0)
            #result = np.append(result, self.cmd['switchWaveform'][np.newaxis, :], axis=0)
            result._info[0]['cols'].append({'name': 'switch'})
        #elif 'power' in self.cmd:
            #arr = np.append(arr, self.cmd['power']['command'][np.newaxis, :], axis=0)
            #result._info[0]['cols'].append({'name': str(self.cmd['power']['type'])})
            
        info = {'currentPower': self.currentPower, 
                'expectedPower': self.expectedPower, 
                'requestedWavelength':self.cmd.get('wavelength', None), 
                'shutterMode':self.cmd['shutterMode'],
                'powerCheckRequested':self.cmd.get('checkPower', False),
                'pulsesCmd': self.cmd.get('pulses', None)
                }
              
        
        result._info[-1]['Laser'] = info
        
        result = metaarray.MetaArray(arr, info=result._info)
        self.dev.lastResult = result
       
        return result
    
    #def storeResult(self, dirHandle):
        #pass

