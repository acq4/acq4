# -*- coding: utf-8 -*-
from acq4.devices.Laser import *
#import serial, struct
from acq4.drivers.MaiTai import *
from acq4.devices.Laser.MaiTaiDevGui import MaiTaiDevGui
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
import acq4.util.debug as debug
import time

class MaiTaiLaser(Laser):

    sigRelativeHumidityChanged = QtCore.Signal(object)
    sigPumpPowerChanged = QtCore.Signal(object)
    sigPulsingStateChanged = QtCore.Signal(object)
    sigWavelengthChanged = QtCore.Signal(object)
    sigModeChanged = QtCore.Signal(object)
    
    def __init__(self, dm, config, name):
        self.port = config['port']-1  ## windows com ports start at COM1, pyserial ports start at 0
        self.baud = config.get('baud', 9600)
        self.driver = MaiTai(self.port, self.baud)
        self.driverLock = Mutex(QtCore.QMutex.Recursive)  ## access to low level driver calls
        
        self.maiTaiLock = Mutex(QtCore.QMutex.Recursive)  ## access to self.attributes
        self.maiTaiPower = 0.
        self.maiTaiWavelength = 0
        self.maiTaiHumidity = 0.
        self.maiTaiPumpPower = 0.
        self.maiTaiMode = None
        
        self.mThread = MaiTaiThread(self, self.driver, self.driverLock)
        self.mThread.sigPowerChanged.connect(self.powerChanged)
        self.mThread.sigWLChanged.connect(self.wavelengthChanged)
        self.mThread.sigRelHumidityChanged.connect(self.humidityChanged)
        self.mThread.sigPPowerChanged.connect(self.pumpPowerChanged)
        self.mThread.sigPulsingSChanged.connect(self.pulsingStateChanged)
        self.mThread.sigMoChanged.connect(self.modeChanged)
        self.mThread.start()
        
        Laser.__init__(self, dm, config, name)
        
        self.hasShutter = True
        self.hasTunableWavelength = True
        
        if self.hasExternalSwitch:
            if not self.getInternalShutter():
                self.setChanHolding('externalSwitch', 1)
        
        dm.sigAbortAll.connect(self.closeInternalShutter)
        
    def isLaserOn(self):
       with self.driverLock:
           return self.driver.isLaserOn()
       
    def switchLaserOn(self):
        with self.driverLock:
            self.driver.turnLaserOn()

    def switchLaserOff(self):
        with self.driverLock:
            self.driver.turnLaserOff()
            
    def powerChanged(self, power):
        with self.maiTaiLock:
            self.maiTaiPower = power
            self.setParam(currentPower=power)
            powerOk = self.checkPowerValidity(power)
            self.sigOutputPowerChanged.emit(power, powerOk)
                
    def wavelengthChanged(self, wl):
        with self.maiTaiLock:
            self.maiTaiWavelength = wl
            self.sigWavelengthChanged.emit(wl)
    
    def humidityChanged(self,hum):
        with self.maiTaiLock:
            self.maiTaiHumidity = hum
            self.sigRelativeHumidityChanged.emit(hum)
            
    def pumpPowerChanged(self,pP):
        with self.maiTaiLock:
            self.maiTaiPumpPower = pP
            self.sigPumpPowerChanged.emit(pP)
    
    def pulsingStateChanged(self, pulse):
        with self.maiTaiLock:
            self.maiTaiPumpPower = pulse
            self.sigPulsingStateChanged.emit(pulse)
    
    def humidity(self):
        with self.maiTaiLock:
            return self.maiTaiHumidity 
    
    def modeChanged(self,mode):
        with self.maiTaiLock:
            self.maiTaiMode = mode
            self.sigModeChanged.emit(mode)
    
    def outputPower(self):
        with self.maiTaiLock:
            return self.maiTaiPower
    
    def getPumpPower(self):
        with self.maiTaiLock:
            return self.maiTaiPumpPower
    
    def getWavelength(self):
        with self.driverLock:
            return self.driver.getWavelength()*1e-9
        
    def setWavelength(self, wl):
        with self.driverLock:
            self.driver.setWavelength(wl*1e9)
            
    def getWavelengthRange(self):
        with self.driverLock:
            bounds = self.driver.getWavelengthRange()
        return bounds[0]*1e-9, bounds[1]*1e-9
    
    def openInternalShutter(self):
        with self.driverLock:
            self.driver.setShutter(True)
        
    def closeInternalShutter(self):
        with self.driverLock:
            self.driver.setShutter(False)
        
    def getInternalShutter(self):
        with self.driverLock:
            return self.driver.getShutter()
    
    def externalSwitchON(self):
        if self.hasExternalSwitch:
            self.setChanHolding('externalSwitch', 1)
    
    def externalSwitchOFF(self):
        if self.hasExternalSwitch:
            self.setChanHolding('externalSwitch', 0)
    
    def acitvateAlignmentMode(self):
        with self.driverLock:
            self.greenPowerIRMode = self.driver.getLastCommandedPumpLaserPower()
        with self.driverLock:
            self.driver.setPumpMode('Green Power')
        self.mThread.alignmentMode = True
        
    def deactivateAlignmentMode(self):
        with self.driverLock:
            self.driver.setPumpLaserPower(self.greenPowerIRMode)
        with self.driverLock:
            self.driver.setPumpMode('IR Power')
        self.mThread.alignmentMode = False
    
    def createTask(self, cmd, parentTask):
        return MaiTaiTask(self, cmd, parentTask)

    def deviceInterface(self, win):
        return MaiTaiDevGui(self)
    
class MaiTaiTask(LaserTask):
    pass
    # This is disabled--internal shutter in coherent laser should NOT be used by ACQ4; use a separate shutter.
    #
    # def start(self):
    #     # self.shutterOpened = self.dev.getShutter()
    #     # if not self.shutterOpened:
    #     #     self.dev.openShutter()
    #     #     time.sleep(2.0)  ## opening the shutter causes momentary power drop; give laser time to recover
    #     #                      ## Note: It is recommended to keep the laser's shutter open rather than
    #     #                      ## rely on this to open it for you.
    #     LaserTask.start(self)
        
    # def stop(self, abort):
    #     if not self.shutterOpened:
    #         self.dev.closeShutter()
    #     LaserTask.stop(self, abort)
        
class MaiTaiThread(Thread):

    sigPowerChanged = QtCore.Signal(object)
    sigWLChanged = QtCore.Signal(object)
    sigRelHumidityChanged = QtCore.Signal(object)
    sigPPowerChanged = QtCore.Signal(object)
    sigPulsingSChanged = QtCore.Signal(object)
    sigMoChanged = QtCore.Signal(object)
    sigError = QtCore.Signal(object)

    def __init__(self, dev, driver, lock):
        Thread.__init__(self)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.dev = dev
        self.driver = driver
        self.driverLock = lock
        self.cmds = {}
        self.alignmentMode = False
        
    def setWavelength(self, wl):
        pass
        
    def setShutter(self, opened):
        wait = QtCore.QWaitCondition()
        cmd = ['setShutter', opened]
        with self.lock:
            self.cmds.append(cmd)
    def adjustPumpPower(self):
        lastCommandedPPBefore = self.driver.getLastCommandedPumpLaserPower()
        newPP = round(lastCommandedPPBefore*0.98,2) # decrease pump power by 2 % until laser stops pulsing
        self.driver.setPumpLaserPower(newPP)
        time.sleep(2.)
        lastCommandedPPAfter = self.driver.getLastCommandedPumpLaserPower()
        print 'PLP before : after , ', lastCommandedPPBefore, lastCommandedPPAfter
        
        
    def run(self):
        self.stopThread = False
        with self.driverLock:
            self.sigWLChanged.emit(self.driver.getWavelength()*1e-9)
        while True:
            try:
                with self.driverLock:
                    power = self.driver.getPower()
                    wl = self.driver.getWavelength()*1e-9
                    hum = self.driver.getRelativeHumidity()
                    pumpPower = self.driver.getPumpPower()
                    isPulsing = self.driver.checkPulsing()
                    mode = self.driver.getPumpMode()
                    if self.alignmentMode:
                        if isPulsing:
                            self.adjustPumpPower()
                    
                self.sigPowerChanged.emit(power)
                self.sigWLChanged.emit(wl)
                self.sigRelHumidityChanged.emit(hum)
                self.sigPPowerChanged.emit(pumpPower)
                self.sigPulsingSChanged.emit(isPulsing)
                self.sigMoChanged.emit(mode)
                time.sleep(0.5)
            except:
                debug.printExc("Error in MaiTai laser communication thread:")
                
            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(0.02)

        self.driver.close()
    
    def stop(self, block=False):
        with self.lock:
            self.stopThread = True
        if block:
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
