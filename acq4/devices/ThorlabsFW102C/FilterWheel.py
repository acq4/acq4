# -*- coding: utf-8 -*-
from acq4.devices.OptomechDevice import *
from acq4.drivers.ThorlabsFW102C import *
from acq4.devices.FilterWheel.FilterWheelDevGui import FilterWheelDevGui
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
import acq4.util.debug as debug
import time

class FilterWheel(Device, OptomechDevice):

    sigFilterWheelPositionChanged = QtCore.Signal(object)
    sigFilterWheelSpeedChanged = QtCore.Signal(object)
    sigFilterWheelTrigModeChanged = QtCore.Signal(object)
    
    def __init__(self, dm, config, name):
        
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        
        self.port = config['port']-1  ## windows com ports start at COM1, pyserial ports start at 0
        self.baud = config.get('baud', 115200)
        self.positionLabels = config.get('postionLabels')
        
        self.fwDriver = thorFW102cDriver(self.port, self.baud)
        self.driverLock = Mutex(QtCore.QMutex.Recursive)  ## access to low level driver calls
        self.filterWheelLock = Mutex(QtCore.QMutex.Recursive)  ## access to self.attributes

        if len(self.positionLabels) != self.getPositionCount():
            raise Exception("Number of FilterWheel positions %s must correspond to number of labels!" % self.getPositionCount())
        
        self.maiTaiPower = 0.
        self.maiTaiWavelength = 0
        self.maiTaiHumidity = 0.
        self.maiTaiPumpPower = 0.
        self.maiTaiPulsing = False
        self.maiTaiP2Optimization = False
        self.maiTaiMode = None
        self.maiTaiHistory = None
        
        #self.mThread = MaiTaiThread(self, self.driver, self.driverLock)
        #self.mThread.sigPowerChanged.connect(self.powerChanged)
        #self.mThread.sigWLChanged.connect(self.wavelengthChanged)
        #self.mThread.sigRelHumidityChanged.connect(self.humidityChanged)
        #self.mThread.sigPPowerChanged.connect(self.pumpPowerChanged)
        #self.mThread.sigPulsingSChanged.connect(self.pulsingStateChanged)
        #self.mThread.sigMoChanged.connect(self.modeChanged)
        #self.mThread.sigP2OChanged.connect(self.p2OptimizationChanged)
        #self.mThread.sigHChanged.connect(self.historyBufferChanged)
        #self.mThread.start()
        
        #Laser.__init__(self, dm, config, name)
        
        #dm.sigAbortAll.connect(self.closeInternalShutter)
        
    def setTriggerMode(self, trigMode):
        with self.driverLock:
            self.driver.setTriggerMode(trigMode)
            self.sigFilterWheelTrigModeChanged.emit(pos)
    
    def getTriggerMode(self):
        with self.driverLock:
            return self.driver.getTriggerMode()
       
    def setSpeed(self, speed):
        with self.driverLock:
            self.driver.setSpeed(speed)
            self.sigFilterWheelSpeedChanged.emit(pos)
    
    def getSpeed(self):
        with self.driverLock:
            return self.driver.getSpeed()
        
    def setPosition(self, pos):
        with self.driverLock:
            self.driver.setPos(pos)
            self.sigFilterWheelPositionChanged.emit(pos)
            
    def getPosition(self):
        with self.driverLock:
            return self.driver.getPos()
        
    def getPositionCount(self):
        with self.driverLock:
            return self.driver.getPosCount()
        
    def createTask(self, cmd, parentTask):
        return FilterWheelTask(self, cmd, parentTask)

    def deviceInterface(self, win):
        return FilterWheelDevGui(self)
    
class FilterWheelTask(LaserTask):
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
    sigP2OChanged = QtCore.Signal(object)
    sigHChanged = QtCore.Signal(object)
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
    def adjustPumpPower(self,currentPower):
        """ keeps laser output power between alignmentPower value and  alignmentPower + 25%"""
        lastCommandedPP = self.driver.getLastCommandedPumpLaserPower()
        if self.dev.alignmentPower*1.25 < currentPower:
            newPP = round(lastCommandedPP*0.98,2) # decrease pump power by 2 % 
            self.driver.setPumpLaserPower(newPP)
        elif self.dev.alignmentPower > currentPower:
            newPP = round(lastCommandedPP*1.01,2) # increase pump power by 1 % 
            self.driver.setPumpLaserPower(newPP)
        #newCommandedPP = self.driver.getLastCommandedPumpLaserPower()
        #print 'pump laser power - before : new : after , ', lastCommandedPP, newPP, newCommandedPP
        #print 'laser output power : ', currentPower
        
        
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
                    p2Optimization = self.driver.getP2Status()
                    status = self.driver.getHistoryBuffer()
                    if self.alignmentMode:
                        self.adjustPumpPower(power)
                    
                self.sigPowerChanged.emit(power)
                self.sigWLChanged.emit(wl)
                self.sigRelHumidityChanged.emit(hum)
                self.sigPPowerChanged.emit(pumpPower)
                self.sigPulsingSChanged.emit(isPulsing)
                self.sigMoChanged.emit(mode)
                self.sigP2OChanged.emit(p2Optimization)
                self.sigHChanged.emit(status)
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
