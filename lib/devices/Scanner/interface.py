# -*- coding: utf-8 -*-
from lib.devices.Device import *
from lib.util.Mutex import Mutex, MutexLocker
import lib.util.configfile as configfile
from DeviceGui import ScannerDeviceGui
from ProtocolGui import ScannerProtoGui
import os 

class Scanner(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.devGui = None
        
    def setPosition(self, x, y, camera, laser):
        """Set the position of the xy mirrors to a point in the image"""
        vals = self.mapToScanner(x, y)
        
        for i in [0,1]:
            x = ['XAxis', 'YAxis'][i]
            (daq, chan) = self.config[x]
            dev = self.dm.getDevice(daq)
            dev.setChannelValue(chan, vals[i], block=True)
    
    def getObjective(self, camera):
        camDev = self.dm.getDevice(camera)
        scope = camDev.scopeDev
        return scope.getObjective()['name']
    
    def mapToScanner(self, x, y, camera, laser):
        """Convert coordinate in camera space to voltages required to set scan mirrors"""
        obj = self.getObjective(camera)
        cal = self.getCalibration(camera, laser, obj)
        
        if cal is None:
            raise Exception("No calibration found for this combination of laser, camera, and objective:\n  %s\n  %s\n  %s" % (laser, camera, obj))
        
        if x < 0 or x >= cal.shape[0]:
            raise Exception("Requested point out of camera range 0 <= %f < %d" % (x, cal.shape[0]))
        if y < 0 or y >= cal.shape[1]:
            raise Exception("Requested point out of camera range 0 <= %f < %d" % (y, cal.shape[1]))
        
        return cal[x, y]
        
    def getCalibrationIndex(self):
        calDir = self.config['calibrationDir']
        fileName = os.path.join(calDir, 'index')
        try:
            index = configfile.readConfigFile(fileName)
        except:
            index = {}
        return index
        
    def writeCalibrationIndex(self, index):
        calDir = self.config['calibrationDir']
        fileName = os.path.join(calDir, 'index')
        configfile.writeConfigFile(index, fileName)
        
    def getCalibration(self, camera, laser, objective):
        index = self.getCalibrationIndex()
        
        try:
            index1 = index[camera]
        except:
            return None
            
        try:
            index2 = index1[laser]
        except:
            return None
            
        try:
            index3 = index2[objective]
        except:
            return None
        
        calFile = os.path.join(calDir, index3['fileName'])
        
        try:
            cal = MetaArray(file=calFile)
        except:
            print "Error loading calibration file for:\n  %s\n  %s\n  %s" % (laser, camera, obj)
            raise
        
        return cal
        
    
    def createTask(self, cmd):
        with MutexLocker(self.lock):
            return Task(self, cmd)
    
    def protocolInterface(self, prot):
        with MutexLocker(self.lock):
            return ScannerProtoGui(self, prot)
    
    def deviceInterface(self):
        with MutexLocker(self.lock):
            if self.devGui is None:
                self.devGui = ScannerDeviceGui(self)
            return self.devGui
    
    
class ScannerTask(DeviceTask):
    def configure(self, tasks, startOrder):
        ## Set position of mirrors now
        pass
        
        
    #def getResult(self):
        #return None