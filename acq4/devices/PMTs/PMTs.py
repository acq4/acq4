# -*- coding: utf-8 -*-
from __future__ import with_statement
from acq4.devices.Device import *
#import serial, struct
from acq4.drivers.PMTController import *
from acq4.drivers.PMTController import PMTController as PMTDriver  ## name collision with device class
from acq4.util.Mutex import Mutex
import acq4.util.debug as debug
import os, time
#import pdb
import devTemplate
#import functions as fn
import acq4.pyqtgraph as pg
import numpy as np
from copy import deepcopy

class PMTs(Device):

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config
        self.configFile = os.path.join('devices', name + '_config.cfg')
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.port = config['port']  ## windows com ports start at COM1, pyserial ports start at 0
        # Interpret "COM1" as port 0
        if isinstance(self.port, basestring) and self.port.lower()[:3] == 'com':
            self.port = int(self.port[3:]) - 1
        
        self.baud = config.get('baud', 115200)   ## use fastest signaling 
        
        self.PMTs = PMTDriver(self.port, self.baud)  # access the PMT Controller
        self.driverLock = Mutex(QtCore.QMutex.Recursive)
        
        self.mThread = PMTThread(self, self.PMTs, self.driverLock)
        self.mThread.start()
        
        dm.declareInterface(name, ['PMTs'], self)

    def loadConfig(self):
        cfg = self.dm.readConfigFile(self.configFile)
        if 'vmax' in cfg:
            self.vmax = cfg['vmax']

    def storeConfig(self):
        cfg = {
            'vmax': self.vmax,
        }
        self.dm.writeConfigFile(cfg, self.configFile)



class PMTInterface(QtGui.QWidget):
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)
        self.ui = devTemplate.Ui_Form()
        self.ui.setupUi(self)
        
        self.win = win
        self.dev = dev
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('positionChanged'), self.update)
        self.ui.PMT1_Reset.clicked.connect(self.PMT1Reset)
        self.ui.PMT2_Reset.clicked.connect(self.PMT2Reset)
        self.getPMTTypes()
        self.update()
     
    def getPMTTypes(self):
        pmt1 = self.dev.getPMTID(0)
        self.ui.PMT1_type.setText(pmt1)   
        pmt2 = self.dev.getPMTID(1)
        self.ui.PMT2_type.setText(pmt2)

    def update(self):
        v0 = self.dev.getAnodeV(0)
        self.ui.PMT1_V.setText('%5.3f' % v0)
        v1 = self.dev.getAnodeV(0)
        self.ui.PMT1_V.setText('%5.3f' % v1)

    def PMT1Reset(self):
        self.dev.resetPMT(0)

    def PMT2Reset(self):
        self.dev.resetPMT(1)

    def updateClicked(self):
        self.dev.mThread.update()
        

class TimeoutError(Exception):
    pass

        
class PMTThread(QtCore.QThread):

    sigAnodeVChanged = QtCore.Signal(object)
    sigError = QtCore.Signal(object)

    def __init__(self, dev, driver, lock):
        QtCore.QThread.__init__(self)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.dev = dev
        self.driver = driver
        self.driverLock = lock
        self.cmds = {}
                        
    def resetPMT(self, devicenum):
        wait = QtCore.QWaitCondition()
        cmd = ['resetPMT', devicenum]
        with self.lock:
            self.cmds.append(cmd)

    def updatePMTs(self):
        with self.lock:
            self.update = True

    def run(self):
        self.stopThread = False
        with self.driverLock:
            self.sigAnodeV1Changed.emit(self.driver.getAnodeV(0))
            self.sigAnodeV2Changed.emit(self.driver.getAnodeV(1))
        while True:
            try:
                with self.driverLock:
                    anodev1 = self.driver.getAnodeV(1)
                    anodev2 = self.driver.getAnodeV(2)
                self.sigAnodeV1Changed.emit(anodev1)
                self.sigAnodeV2Changed.emit(anodev2)
                time.sleep(0.5)
            except:
                debug.printExc("Error in PMT communication thread:")
                
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
                raise Exception("Timed out while waiting for PMT thread exit!")

    def getCurrentAnodeV(self, devicenum):
        with self.driverLock:
            anodev = np.array(self.PMT.getAnodeV(devicenum=devicenum))
        return anodev
            
