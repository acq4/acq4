# -*- coding: utf-8 -*-
from lib.devices.Device import *
from lib.util.Mutex import Mutex, MutexLocker
import lib.util.configfile as configfile
from DeviceGui import ScannerDeviceGui
from ProtocolGui import ScannerProtoGui
import os 
from lib.util import ptime
from lib.util.debug import *

class Scanner(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.devGui = None
        self.lastRunTime = None
        self.calibrationIndex = None
        if not os.path.isdir(config['calibrationDir']):
            print "Calibration directory '%s' does not exist, creating.." % config['calibrationDir']
            os.mkdir(config['calibrationDir'])
    
    def setCommand(self, vals):
        with MutexLocker(self.lock):
            (mn, mx) = self.config['commandLimits']
            for i in [0,1]:
                x = ['XAxis', 'YAxis'][i]
                (daq, chan) = self.config[x]
                dev = self.dm.getDevice(daq)
                v = max(mn, min(mx, vals[i]))
                dev.setChannelValue(chan, v, block=True)
    
    def setPosition(self, pos, camera, laser):
        """Set the position of the xy mirrors to a point in the image"""
        with MutexLocker(self.lock):
            (x, y) = pos
            cam = self.dm.getDevice(camera)
            camPos = cam.getPosition()
            vals = self.mapToScanner(x - camPos[0], y - camPos[1], camera, laser)
            #print "Setting position", pos, " values are", vals
            
            self.setCommand(vals)
    
    def getObjective(self, camera):
        with MutexLocker(self.lock):
            camDev = self.dm.getDevice(camera)
        scope = camDev.scopeDev
        return scope.getObjective()['name']
    
    def mapToScanner(self, x, y, camera, laser):
        """Convert coordinate in camera space to voltages required to set scan mirrors"""
        obj = self.getObjective(camera)
        cal = self.getCalibration(camera, laser, obj)['params']
        
        if cal is None:
            raise Exception("No calibration found for this combination of laser, camera, and objective:\n  %s\n  %s\n  %s" % (laser, camera, obj))
        x1 = cal[0][0] + cal[0][1] * x + cal[0][2] * y + cal[0][3] * x**2 + cal[0][4] * y**2
        y1 = cal[1][0] + cal[1][1] * x + cal[1][2] * y + cal[1][3] * x**2 + cal[1][4] * y**2
        return [x1, y1]
        
    def getCalibrationIndex(self):
        with MutexLocker(self.lock):
            if self.calibrationIndex is None:
                calDir = self.config['calibrationDir']
                fileName = os.path.join(calDir, 'index')
                if os.path.isfile(fileName):
                    try:
                        index = configfile.readConfigFile(fileName)
                    except:
                        index = {}
                        printExc("===== Warning: Error while reading scanner calibration index:")
                        print "    calDir: %s  fileName: %s" % (calDir, fileName)
                        print "    self.config:", self.config
                else:
                    index = {}
                self.calibrationIndex = index
            return self.calibrationIndex
        
    def writeCalibrationIndex(self, index):
        with MutexLocker(self.lock):
            calDir = self.config['calibrationDir']
            fileName = os.path.join(calDir, 'index')
            configfile.writeConfigFile(index, fileName)
            self.calibrationIndex = index
        
    def getCalibration(self, camera, laser, objective=None):
        with MutexLocker(self.lock):
            index = self.getCalibrationIndex()
            
        if objective is None:
            objective = self.getObjective(camera)
        
        if camera in index:
            index1 = index[camera]
        else:
            print "Warning: No calibration found for camera %s" % camera
            return None
            
        if laser in index1:
            index2 = index1[laser]
        else:
            print "Warning: No calibration found for laser %s" % laser
            return None
            
        if objective in index2:
            index3 = index2[objective]
        else:
            print "Warning: No calibration found for objective %s" % objective
            return None
        
        #calFile = os.path.join(calDir, index3['fileName'])
        
        #try:
            #cal = MetaArray(file=calFile)
        #except:
            #print "Error loading calibration file for:\n  %s\n  %s\n  %s" % (laser, camera, obj)
            #raise
        
        return index3.copy()
        
    
    def createTask(self, cmd):
        with MutexLocker(self.lock):
            return ScannerTask(self, cmd)
    
    def protocolInterface(self, prot):
        with MutexLocker(self.lock):
            return ScannerProtoGui(self, prot)
    
    def deviceInterface(self, win):
        with MutexLocker(self.lock):
            if self.devGui is None:
                self.devGui = ScannerDeviceGui(self, win)
            return self.devGui
    
    
class ScannerTask(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.daqTasks = []

    def configure(self, tasks, startOrder):
        with MutexLocker(self.dev.lock):
            ## Set position of mirrors now
            if 'command' in self.cmd:
                self.dev.setCommand(self.cmd['command'])
            elif 'position' in self.cmd:
                self.dev.setPosition(self.cmd['position'], self.cmd['camera'], self.cmd['laser'])
        
    def createChannels(self, daqTask):
        self.daqTasks = []
        with MutexLocker(self.dev.lock):
            ## If buffered waveforms are requested in the command, configure them here.
            for axis in [('xCommand', 'XAxis'), ('yCommand', 'YAxis')]:
                cmdName = axis[0]
                channel = axis[1]
                if cmdName not in self.cmd:
                    continue
                chConf = self.dev.config[channel]
                if chConf[0] != daqTask.devName():
                    continue
                
                daqTask.addChannel(chConf[1], 'ao')
                self.daqTasks.append(daqTask)  ## remember task so we can stop it later on
                daqTask.setWaveform(chConf[1], self.cmd[cmdName])

    def stop(self):
        with MutexLocker(self.dev.lock):
            for t in self.daqTasks:
                t.stop()
            self.dev.lastRunTime = ptime.time()
            #for ch in self.cmd:
                #if 'holding' in self.cmd[ch]:
                    #self.dev.setHolding(ch, self.cmd[ch]['holding'])

    def start(self):
        #print "start"
        with MutexLocker(self.dev.lock):
            lastRunTime = self.dev.lastRunTime
        if lastRunTime is None:
            #print "  no wait"
            return
        now = ptime.time()
        if 'minWaitTime' in self.cmd:
            
            wait = self.cmd['minWaitTime'] - (now - lastRunTime)
            #print "  min wait is ", self.cmd['minWaitTime'], "; sleep", wait
            if wait > 0:
                time.sleep(wait)
            
    def getResult(self):
        result = {}
        for k in ['position', 'command']:
            if k in self.cmd:
                result[k] = self.cmd[k]
        return result
    
    def storeResult(self, dirHandle):
        result = self.getResult()
        dirHandle.setInfo({self.dev.name: result})
        
        