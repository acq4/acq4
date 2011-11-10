# -*- coding: utf-8 -*-
from lib.devices.Laser import *
#import serial, struct
from lib.drivers.Coherent import *
from Mutex import Mutex
import debug

class CoherentLaser(Laser):

    def __init__(self, dm, config, name):
        self.port = config['port']-1  ## windows com ports start at COM1, pyserial ports start at 0
        self.baud = config.get('baud', 19200)
        self.driver = Coherent(self.port, self.baud)
        self.driverLock = Mutex(QtCore.QMutex.Recursive)
        
        self.coherentLock = Mutex(QtCore.QMutex.Recursive)
        self.coherentPower = 0
        self.coherentWavelength = 0
        
        self.mThread = CoherentThread(self, self.driver, self.driverLock)
        self.mThread.sigPowerChanged.connect(self.powerChanged)
        self.mThread.sigWavelengthChanged.connect(self.wavelengthChanged)
        self.mThread.start()
        Laser.__init__(self, dm, config, name)
        
        self.hasShutter = True
        self.hasTunableWavelength = True
        
    def powerChanged(self, power):
        with self.coherentLock:
            self.coherentPower = power
            self.setParam(currentPower=power)
            powerOk = self.checkPowerValidity(power)
            self.sigOutputPowerChanged.emit(power, powerOk)
                
    def wavelengthChanged(self, wl):
        with self.coherentLock:
            self.coherentWavelength = wl
        
    def outputPower(self):
        with self.coherentLock:
            return self.coherentPower
    
    def getWavelength(self):
        with self.coherentLock:
            return self.coherentWavelength
        
    def setWavelength(self, wl):
        with self.coherentLock:
            self.driver.setWavelength(wl*1e9)
            
    def getWavelengthRange(self):
        with self.driverLock:
            bounds = self.driver.getWavelengthRange()
        return bounds[0]*1e-9, bounds[1]*1e-9
        
    def openShutter(self):
        with self.driverLock:
            self.driver.setShutter(True)
        Laser.openShutter(self)
        
    def closeShutter(self):
        with self.driverLock:
            self.driver.setShutter(False)
        Laser.closeShutter(self)
        
    def createTask(self, cmd):
        return CoherentTask(self, cmd)
        
class CoherentTask(LaserTask):
    def start(self):
        self.dev.openShutter()
        LaserTask.start(self)
        
    def stop(self, abort):
        self.dev.closeShutter()
        LaserTask.stop(self, abort)
        
        
class CoherentThread(QtCore.QThread):

    sigPowerChanged = QtCore.Signal(object)
    sigWavelengthChanged = QtCore.Signal(object)
    sigError = QtCore.Signal(object)

    def __init__(self, dev, driver, lock):
        QtCore.QThread.__init__(self)
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
                self.sigPowerChanged.emit(power)
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


