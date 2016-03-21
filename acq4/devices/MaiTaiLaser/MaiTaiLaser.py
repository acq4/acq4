# -*- coding: utf-8 -*-
from acq4.devices.Laser import *
#import serial, struct
from acq4.drivers.MaiTai import *
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
import acq4.util.debug as debug
import time

class MaiTaiLaser(Laser):

    sigRelativeHumidityChanged = QtCore.Signal(object)
    sigPumpPowerChanged = QtCore.Signal(object)
    sigPulsingStateChanged = QtCore.Signal(object)
    
    
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
        
        self.mThread = MaiTaiThread(self, self.driver, self.driverLock)
        self.mThread.sigPowerChanged.connect(self.powerChanged)
        self.mThread.sigWavelengthChanged.connect(self.wavelengthChanged)
        self.mThread.sigRelHumidityChanged.connect(self.humidityChanged)
        self.mThread.sigPPowerChanged.connect(self.pumpPowerChanged)
        self.mThread.sigPulsingSChanged.connect(self.pulsingStateChanged)
        self.mThread.start()
        Laser.__init__(self, dm, config, name)
        
        self.hasShutter = True
        self.hasTunableWavelength = True
    
    def isLaserOn(self):
       with self.driverLock:
           status = self.driver.checkStatus()
           return bool(status%2)
       
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
        
    def outputPower(self):
        with self.maiTaiLock:
            return self.maiTaiPower
    
    def getPumpPower(self):
        with self.maiTaiLock:
            return self.maiTaiPumpPower
    
    def getWavelength(self):
        with self.maiTaiLock:
            return self.maiTaiWavelength
        
    def setWavelength(self, wl):
        with self.driverLock:
            self.driver.setWavelength(wl*1e9)
            
    def getWavelengthRange(self):
        with self.driverLock:
            bounds = self.driver.getWavelengthRange()
        return bounds[0]*1e-9, bounds[1]*1e-9
    
    def openShutter(self):
        with self.driverLock:
            self.driver.setShutter(True)
        #Laser.openShutter(self)
        
    def closeShutter(self):
        with self.driverLock:
            self.driver.setShutter(False)
        #Laser.closeShutter(self)
        
    def getShutter(self):
        with self.driverLock:
            return self.driver.getShutter()
        
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
    sigWavelengthChanged = QtCore.Signal(object)
    sigRelHumidityChanged = QtCore.Signal(object)
    sigPPowerChanged = QtCore.Signal(object)
    sigPulsingSChanged = QtCore.Signal(object)
    sigError = QtCore.Signal(object)

    def __init__(self, dev, driver, lock):
        Thread.__init__(self)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.dev = dev
        self.driver = driver
        self.driverLock = lock
        self.cmds = {}
        
    def setWavelength(self, wl):
        pass
        
    def setShutter(self, opened):
        wait = QtCore.QWaitCondition()
        cmd = ['setShutter', opened]
        with self.lock:
            self.cmds.append(cmd)
        
    def run(self):
        self.stopThread = False
        with self.driverLock:
            self.sigWavelengthChanged.emit(self.driver.getWavelength()*1e-9)
        while True:
            try:
                with self.driverLock:
                    power = self.driver.getPower() * 1e-3
                    wl = self.driver.getWavelength()*1e-9
                    hum = self.driver.getRelativeHumidity()
                    pumpPower = self.driver.getPumpPower()
                    isPulsing = self.driver.checkPulsing()
                self.sigPowerChanged.emit(power)
                self.sigWavelengthChanged.emit(wl)
                self.sigRelHumidityChanged.emit(hum)
                self.sigPPowerChanged.emit(pumpPower)
                self.sigPulsingSChanged.emit(isPulsing)
                time.sleep(0.5)
            except:
                debug.printExc("Error in Coherent laser communication thread:")
                
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