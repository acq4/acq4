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
        
        self.driver = filterWheelDriver(self.port, self.baud)
        self.driverLock = Mutex(QtCore.QMutex.Recursive)  ## access to low level driver calls
        self.filterWheelLock = Mutex(QtCore.QMutex.Recursive)  ## access to self.attributes

        if len(self.positionLabels) != self.getPositionCount():
            raise Exception("Number of FilterWheel positions %s must correspond to number of labels!" % self.getPositionCount())
        
        with self.driverLock:
            self.position = self.driver.getPos()

        self.fwThread = FilterWheelThread(self, self.driver, self.driverLock)
        self.fwThread.fwPosChanged.connect(self.positionChanged)
        self.fwThread.start()
        
    def setTriggerMode(self, trigMode):
        with self.driverLock:
            self.driver.setTriggerMode(trigMode)
            self.sigFilterWheelTrigModeChanged.emit(trigMode)
    
    def getTriggerMode(self):
        with self.driverLock:
            return self.driver.getTriggerMode()
       
    def setSpeed(self, speed):
        with self.driverLock:
            self.driver.setSpeed(speed)
            self.sigFilterWheelSpeedChanged.emit(speed)
    
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
    
    def positionChanged(self,newPos):
        with self.filterWheelLock:
            self.position = newPos
            self.sigFilterWheelPositionChanged.emit(newPos)
        
    #def createTask(self, cmd, parentTask):
    #    return FilterWheelTask(self, cmd, parentTask)

    def deviceInterface(self, win):
        return FilterWheelDevGui(self)
    
#class FilterWheelTask(LaserTask):
    #pass
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
        
class FilterWheelThread(Thread):

    fwPosChanged = QtCore.Signal(object)

    def __init__(self, dev, driver, lock):
        Thread.__init__(self)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.dev = dev
        self.driver = driver
        self.driverLock = lock
        self.cmds = {}

        
    def run(self):
        self.stopThread = False
        with self.driverLock:
            self.fwPosChanged.emit(self.driver.getPos())
        while True:
            try:
                with self.driverLock:
                    pos = self.driver.getPos()
                self.fwPosChanged.emit(pos)
                time.sleep(0.5)
            except:
                debug.printExc("Error in Filter Wheel communication thread:")
                
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
                raise Exception("Timed out while waiting for Filter Wheel thread exit!")
