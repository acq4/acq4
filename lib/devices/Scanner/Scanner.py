# -*- coding: utf-8 -*-
from lib.devices.Device import *
from Mutex import Mutex, MutexLocker
from DeviceGui import ScannerDeviceGui
from ProtocolGui import ScannerProtoGui
import os, pickle 
import ptime
from debug import *

class Scanner(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.devGui = None
        self.lastRunTime = None
        self.calibrationIndex = None
        self.targetList = [1.0, {}]  ## stores the grids and points used by ProtocolGui so that they persist
        self._configDir = os.path.join('devices', self.name + '_config')
        
        #if not os.path.isdir(config['calibrationDir']):
            #print "Calibration directory '%s' does not exist, creating.." % config['calibrationDir']
            #os.mkdir(config['calibrationDir'])
        #self.targetFileName = os.path.join(self.config['calibrationDir'], 'targetList.pickle')
        #if os.path.isfile(self.targetFileName):
            #fd = open(self.targetFileName)
            #self.targetList = pickle.load(fd)
            #fd.close()
    
    #def quit(self):
        #Device.quit(self)
        ##if os.path.isfile(self.targetFileName):
            ##os.delete(self.targetFileName)
    
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
            #cam = self.dm.getDevice(camera)
            #camPos = cam.getPosition()
            #vals = self.mapToScanner(x - camPos[0], y - camPos[1], camera, laser)
            vals = self.mapToScanner(x, y, camera, laser)
            #print "Setting position", pos, " values are", vals
            
            self.setCommand(vals)
    
    def getObjective(self, camera):
        with MutexLocker(self.lock):
            camDev = self.dm.getDevice(camera)
        scope = camDev.scopeDev
        return scope.getObjective()['name']
    
    def mapToScanner(self, x, y, camera, laser):
        """Convert global coordinates to voltages required to set scan mirrors"""
        obj = self.getObjective(camera)
        cam = self.dm.getDevice(camera)
        camPos = cam.getPosition()
        
        ## first convert position to sensor coords
        (x, y) = cam.mapToSensor((x, y))
        
        cal = self.getCalibration(camera, laser, obj)['params']
        
        if cal is None:
            raise Exception("No calibration found for this combination of laser, camera, and objective:\n  %s\n  %s\n  %s" % (laser, camera, obj))
        x1 = cal[0][0] + cal[0][1] * x + cal[0][2] * y + cal[0][3] * x**2 + cal[0][4] * y**2
        y1 = cal[1][0] + cal[1][1] * x + cal[1][2] * y + cal[1][3] * x**2 + cal[1][4] * y**2
        return [x1, y1]
        
    def getCalibrationIndex(self):
        with MutexLocker(self.lock):
            if self.calibrationIndex is None:
                calDir = self.configDir()
                fileName = os.path.join(calDir, 'index')
                index = self.dm.readConfigFile(fileName)
                #if os.path.isfile(fileName):
                    #try:
                        #index = configfile.readConfigFile(fileName)
                    #except:
                        #index = {}
                        #printExc("===== Warning: Error while reading scanner calibration index:")
                        #print "    calDir: %s  fileName: %s" % (calDir, fileName)
                        #print "    self.config:", self.config
                #else:
                    #index = {}
                self.calibrationIndex = index
            return self.calibrationIndex
        
    def writeCalibrationDefaults(self, state):
        with MutexLocker(self.lock):
            calDir = self.configDir()
            fileName = os.path.join(calDir, 'defaults')
            self.dm.writeConfigFile(state, fileName)
        
    def loadCalibrationDefaults(self):
        with MutexLocker(self.lock):
            calDir = self.configDir()
            fileName = os.path.join(calDir, 'defaults')
            state = self.dm.readConfigFile(fileName)
            return state
        
    def writeCalibrationIndex(self, index):
        with MutexLocker(self.lock):
            calDir = self.configDir()
            fileName = os.path.join(calDir, 'index')
            self.dm.writeConfigFile(index, fileName)
            #configfile.writeConfigFile(index, fileName)
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
        
    def storeCameraConfig(self, camera):
        """Store the configuration to be used when calibrating this camera"""
        camDev = self.dm.getDevice(camera)
        params = camDev.listParams()
        params = [p for p in params if params[p][1] and params[p][2]]  ## Select only readable and writable parameters
        state = camDev.getParams(params)
        fileName = os.path.join(self.configDir(), camera+'Config.cfg')
        self.dm.writeConfigFile(state, fileName)
        
    def getCameraConfig(self, camera):
        fileName = os.path.join(self.configDir(), camera+'Config.cfg')
        return self.dm.readConfigFile(fileName)
        
        
    def configDir(self):
        """Return the name of the directory where configuration/calibration data should be stored"""
        return self._configDir
        
    
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
    
    def updateTarget(self, name, info):
        """Inform the device that a target or grid of targets has been changed. This allows new instances of ProtocolGui to share targets with previous ones."""
        if info is None:
            del self.targetList[1][name]
        else:
            self.targetList[1][name] = info
            
        #fd = open(self.targetFileName)
        #pickle.dump(fd, self.targetList)
        #fd.close()
        
    def updateTargetPacking(self, p):
        self.targetList[0] = p
        #fd = open(self.targetFileName)
        #pickle.dump(fd, self.targetList)
        #fd.close()
        
        
    def getTargetList(self):
        """Return the full list of targets generated by previous ProtocolGuis"""
        return self.targetList


class ScannerTask(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.daqTasks = []
        self.spotSize = None

    def configure(self, tasks, startOrder):
        with MutexLocker(self.dev.lock):
            ## Set position of mirrors now
            if 'command' in self.cmd:
                self.dev.setCommand(self.cmd['command'])
            elif 'position' in self.cmd:
                self.dev.setPosition(self.cmd['position'], self.cmd['camera'], self.cmd['laser'])
                
            ## record spot size from calibration data
            if 'camera' in self.cmd and 'laser' in self.cmd:
                self.spotSize = self.dev.getCalibration(self.cmd['camera'], self.cmd['laser'])['spot'][1]
                
            ## If program is specified, generate the command arrays now
            if 'program' in self.cmd:
                self.generateProgramArrays(self.cmd['program'])
        
    def generateProgramArrays(self, prg):
        """LASER LOGO
        Turn a list of movement commands into arrays of x and y values.
        prg looks like:
        { 
            numPts: 10000,
            duration: 1.0,
            commands: [
               ('step', 0.0, None),           ## start with step to "off" position 
               ('step', 0.2, (1.3e-6, 4e-6)), ## step to the given location after 200ms
               ('line', (0.2, 0.205), (1.3e-6, 4e-6))  ## 5ms sweep to the new position 
               ('step', 0.205, None),           ## finish step to "off" position at 205ms
           ]
        }
        
        Commands we might add in the future:
          - circle
          - spiral
        """
        dt = prg['duration'] / prg['numPts']
        arr = numpy.empty((2, prg['numPts']))
        cmds = prg['commands']
        lastPos = None
        for i in range(len(cmds)):
            cmd = cmds[i]
            if cmd[0] == 'step':
                ## determine when to end the step
                if i+1 < len(cmds):
                    nextTime = cmds[i+1][1]
                    if type(nextTime) is tuple:
                        nextTime = nextTime[0]
                    stopInd = nextTime / dt
                else:
                    stopInd = -1
                
                startInd = cmd[1] / dt
                
                pos = cmd[2]
                if pos == None:
                    pos = self.dev.getOffPosition()
                lastPos = pos
                
                arr[0, startInd:stopInd] = pos[0]
                arr[1, startInd:stopInd] = pos[1]
            elif cmd[0] == 'line':
                if lastPos is None:
                    raise Exception("'line' command with no defined starting position")
                startInd = cmd[1][0] / dt
                stopInd = cmd[1][1] / dt
                pos = cmd[2]
                arr[0, startInd:stopInd] = linspace(lastPos[0], pos[0], stopInd-startInd)
                arr[1, startInd:stopInd] = linspace(lastPos[1], pos[1], stopInd-startInd)
                lastPos = pos
        self.cmd['xCommand'] = arr[0]
        self.cmd['yCommand'] = arr[1]
        
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

    def stop(self, abort=False):
        with MutexLocker(self.dev.lock):
            for t in self.daqTasks:
                t.stop(abort=abort)
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
        #print "  >> GO"
            
    def getResult(self):
        result = {}
        for k in ['position', 'command']:
            if k in self.cmd:
                result[k] = self.cmd[k]
        if self.spotSize is not None:
            result['spotSize'] = self.spotSize
        return result
    
    def storeResult(self, dirHandle):
        result = self.getResult()
        dirHandle.setInfo({self.dev.name: result})
        
        