# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.devices.Laser import *
#import serial, struct
from acq4.drivers.Coherent import *
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
import acq4.util.debug as debug
import time

class CoherentLaser(Laser):

    def __init__(self, dm, config, name):
        self.port = config['port']-1  ## windows com ports start at COM1, pyserial ports start at 0
        self.baud = config.get('baud', 19200)
        self.driver = Coherent(self.port, self.baud)
        self.driverLock = Mutex(Qt.QMutex.Recursive)  ## access to low level driver calls
        
        self.coherentLock = Mutex(Qt.QMutex.Recursive)  ## access to self.attributes
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
        with self.driverLock:
            self.driver.setWavelength(wl*1e9)
            
    def getWavelengthRange(self):
        with self.driverLock:
            bounds = self.driver.getWavelengthRange()
        return bounds[0]*1e-9, bounds[1]*1e-9
    
    
    def getGDDMinMax(self):
        with self.driverLock:
            gddlims = self.driver.getGDDMinMax()
        return gddlims
    
    def setGDD(self, value):
        with self.driverLock:
            self.driver.setGDD(value)
           # print 'comp is %s' % self.driver.getComp()
            #print 'Gdd set to %s, reading back gives %s' % (value, self.driver.getGDD())
       # with self.driverLock:
       #     print 'Gdd set to %s, reading back gives %s' % (value, self.driver.getGDD())

            
            
    def clearGDD(self):
        with self.driverLock:
            self.driver.clearGDD()
        
    ## Shutter functions are disabled because coherent lasers are not really designed to 
    ## operate their shutters this way. Use an external shutter instead.
    ## (excessive shutter activity can damage the shutter)
    #def openShutter(self):
        #with self.driverLock:
            #self.driver.setShutter(True)
        #Laser.openShutter(self)
        
    #def closeShutter(self):
        #with self.driverLock:
            #self.driver.setShutter(False)
        #Laser.closeShutter(self)
        
    #def getShutter(self):
        #with self.driverLock:
            #return self.driver.getShutter()
        
    def createTask(self, cmd, parentTask):
        return CoherentTask(self, cmd, parentTask)
        
class CoherentTask(LaserTask):
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
        
class CoherentThread(Thread):

    sigPowerChanged = Qt.Signal(object)
    sigWavelengthChanged = Qt.Signal(object)
    sigError = Qt.Signal(object)

    def __init__(self, dev, driver, lock):
        Thread.__init__(self)
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.dev = dev
        self.driver = driver
        self.driverLock = lock
        self.cmds = {}
        
    def setWavelength(self, wl):
        pass
        
    def setShutter(self, opened):
        wait = Qt.QWaitCondition()
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
                self.sigPowerChanged.emit(power)
                self.sigWavelengthChanged.emit(wl)
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
