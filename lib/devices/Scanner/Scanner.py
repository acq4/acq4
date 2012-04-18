# -*- coding: utf-8 -*-
from lib.devices.Device import *
from lib.Manager import logMsg, logExc
from Mutex import Mutex, MutexLocker
from DeviceGui import ScannerDeviceGui
from ProtocolGui import ScannerProtoGui
import os, pickle 
import ptime
from debug import *
import numpy as np
from HelpfulException import HelpfulException

class Scanner(Device):
    
    sigShutterChanged = QtCore.Signal()
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.devGui = None
        self.lastRunTime = None
        self.calibrationIndex = None
        self.targetList = [1.0, {}]  ## stores the grids and points used by ProtocolGui so that they persist
        self._configDir = os.path.join('devices', self.name + '_config')
        self.currentCommand = [0,0] ## The last requested voltage values (but not necessarily the current voltage applied to the mirrors)
        self.currentVoltage = [0, 0]
        self.shutterOpen = True ## indicates whether the virtual shutter is closed (the beam is steered to its 'off' position).
        if 'offVoltage' in config:
            self.setShutterOpen(False)
        #if not os.path.isdir(config['calibrationDir']):
            #print "Calibration directory '%s' does not exist, creating.." % config['calibrationDir']
            #os.mkdir(config['calibrationDir'])
        #self.targetFileName = os.path.join(self.config['calibrationDir'], 'targetList.pickle')
        #if os.path.isfile(self.targetFileName):
            #fd = open(self.targetFileName)
            #self.targetList = pickle.load(fd)
            #fd.close()
        dm.declareInterface(name, ['scanner'], self)
    
    #def quit(self):
        #Device.quit(self)
        ##if os.path.isfile(self.targetFileName):
            ##os.delete(self.targetFileName)
            
    def setCommand(self, vals):
        """Requests to set the command output to the mirrors.
        (The request is denied if the virtual shutter is closed)"""
        with self.lock:
            self.currentCommand = vals
            if self.getShutterOpen():
                ## make sure we have not requested a command outside the allowed limits
                (mn, mx) = self.config['commandLimits']
                v0 = max(mn, min(mx, vals[0]))
                v1 = max(mn, min(mx, vals[1]))
                self.setVoltage([v0, v1])
            else:
                logMsg("Virtual shutter closed, not setting mirror position.", msgType='warning')

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
        
    def setShutterOpen(self, o):
        """Immediately move mirrors 'off' position or back."""
        self.shutterOpen = o
        if o:
            self.setVoltage(self.getCommand())
        else:
            shVals = self.getShutterVals()
            if shVals is None:
                raise Exception("Scan mirrors are not configured for virtual shuttering; can not open.")
            self.setVoltage(shVals)
        self.sigShutterChanged.emit()
        
    def getShutterOpen(self):
        """Return whether the virtual shutter is currently open"""
        if 'offVoltage' not in self.config:
            return True
        return self.shutterOpen

    def getShutterVals(self):
        '''Return the voltage settings required to steer the beam to its 'off' position.'''
        return self.config.get('offVoltage', None)
            
    def getCommand(self):
        """Return the last command value that was requested.
        This is also the current output voltage to the mirrors, unless:
          1) The virtual shutter is closed
          2) The current command is outside the allowed limits
          3) Someone has called setVoltage when they should have called setCommand"""
        vals = []
        with MutexLocker(self.lock):
            vals = self.currentCommand[:]
            #for x in ['XAxis', 'YAxis']:
                #(daq, chan) = self.config[x]
                #dev = self.dm.getDevice(daq)
                #vals.append(dev.getChannelValue(chan))
        return vals
    
    def setVoltage(self, vals):
        '''Immediately sets the voltage value on the mirrors.
        Does NOT do shutter or limit checking; most likely you want to use setCommand instead.'''
        with MutexLocker(self.lock):
            for i in [0,1]:
                x = ['XAxis', 'YAxis'][i]
                daq = self.config[x]['device']
                chan = self.config[x]['channel']
                dev = self.dm.getDevice(daq)
                dev.setChannelValue(chan, vals[i], block=True)
            self.currentVoltage = vals

    def getVoltage(self):
        with self.lock:
            return self.currentVoltage

    
    def getObjective(self, camera):
        """Return the objective currently in use for camera"""
        with MutexLocker(self.lock):
            camDev = self.dm.getDevice(camera)
        scope = camDev.scopeDev
        return scope.getObjective()['name']
    
    def getDaqName(self):
        return self.config['XAxis']['device']
        
    def mapToScanner(self, x, y, camera, laser):
        """Convert global coordinates to voltages required to set scan mirrors"""
        obj = self.getObjective(camera)
        cam = self.dm.getDevice(camera)
        camPos = cam.getPosition()
        
        ## first convert position to sensor coords
        #print "global:", x, y
        (x, y) = cam.mapToSensor((x, y))
        
        #print "camera:", x, y
        cal = self.getCalibration(camera, laser, obj)
        
        if cal is None:
            raise HelpfulException("The scanner device '%s' is not calibrated for this combination of laser, objective, and camera (%s, %s, %s)" % (self.name, laser, obj, camera))
            #raise Exception("No calibration found for this combination of laser, camera, and objective:\n  %s\n  %s\n  %s" % (laser, camera, obj))
            
        cal = cal['params']
        x1 = cal[0][0] + cal[0][1] * x + cal[0][2] * y + cal[0][3] * x**2 + cal[0][4] * y**2
        y1 = cal[1][0] + cal[1][1] * x + cal[1][2] * y + cal[1][3] * x**2 + cal[1][4] * y**2
        #print "voltage:", x1, y1
        return [x1, y1]
    
    #def mapToScanner(self, x, y, cam, laser=None, cal=None):
        #"""Convert global coordinates to voltages required to set scan mirrors"""
        #if cal is None:
            #cal = self.getCalibration(cam, laser)['params']
        #if cal is None:
            #raise Exception("No calibration found for this combination of laser, camera, and objective:\n  %s\n  %s\n  %s" % (laser, camera, obj))
        
        
        ### first convert position to sensor coords
        #(x, y) = cam.mapToSensor((x, y))
        #x1 = cal[0][0] + cal[0][1] * x + cal[0][2] * y + cal[0][3] * x**2 + cal[0][4] * y**2
        #y1 = cal[1][0] + cal[1][1] * x + cal[1][2] * y + cal[1][3] * x**2 + cal[1][4] * y**2
        ##print "voltage:", x1, y1
        #return [x1, y1]
    
    
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
            logMsg("Warning:No calibration found for camera %s" % camera, msgType='warning')
            return None
            
        if laser in index1:
            index2 = index1[laser]
        else:
            print "Warning: No calibration found for laser %s" % laser
            logMsg("Warning:No calibration found for laser %s" % laser, msgType='warning')
            return None
            
        if objective in index2:
            index3 = index2[objective]
        else:
            print "Warning: No calibration found for objective %s" % objective
            logMsg("Warning:No calibration found for objective %s" % objective, msgType='warning')
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
    
    #def updateTarget(self, name, info):
        #"""Inform the device that a target or grid of targets has been changed. This allows new instances of ProtocolGui to share targets with previous ones."""
        #if info is None:
            #del self.targetList[1][name]
        #else:
            #self.targetList[1][name] = info
            
        ##fd = open(self.targetFileName)
        ##pickle.dump(fd, self.targetList)
        ##fd.close()
        
    #def updateTargetDisplaySize(self, s):
        
        #self.targetList[0] = s
        ##fd = open(self.targetFileName)
        ##pickle.dump(fd, self.targetList)
        ##fd.close()
        
        
    #def getTargetList(self):
        #"""Return the full list of targets generated by previous ProtocolGuis"""
        #return self.targetList


class ScannerTask(DeviceTask):
    """
    Options for Scanner task:
        position:         (x,y) A calibrated position (in real physical coordinates) to set 
                          before starting the protocol. Requires 'camera' and 'laser' are
                          also specified.
        command:          (x,y) Voltage values to set before starting the protocol.
                          This option overrides 'position'.
        xPosition:        Array of x positions. (requires yPosition)
        yPosition:        Array of y positions. (requires xPosition)
        xCommand:         Array of x voltages. Overrides x/yPosition.
        xCommand:         Array of y voltages. Overrides x/yPosition.
        camera:           The camera to use for calibrated positions
        laser:            The laser to use for calibrated positions
        simulateShutter:  auto-generate position commands such that the mirrors are 
                          in 'off' position except when laser is active
        program:          A list of high-level directives for generating position commands
    """
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.cmd = cmd
        self.daqTasks = []
        self.spotSize = None
        #print "Scanner task:", cmd
        
    def getConfigOrder(self):
        if self.cmd.get('simulateShutter', False) or 'program' in self.cmd:
            return ([], [self.cmd['laser'], self.dev.getDaqName()]) ### need to do this so we can get the waveform from the laser later
        else:
            return ([],[])

    def configure(self, tasks, startOrder):
        with MutexLocker(self.dev.lock):
            ## If shuttering is requested, make sure the (virtual) shutter is closed now
            if self.cmd.get('simulateShutter', False):
                self.dev.setShutterOpen(False)
                
            ## Set position of mirrors now
            if 'command' in self.cmd:
                self.dev.setCommand(self.cmd['command'])
            elif 'position' in self.cmd:  ## 'command' overrides 'position'
                #print " set position:", self.cmd['position']
                self.dev.setPosition(self.cmd['position'], self.cmd['camera'], self.cmd['laser'])

            ## record spot size from calibration data
            if 'camera' in self.cmd and 'laser' in self.cmd:
                self.spotSize = self.dev.getCalibration(self.cmd['camera'], self.cmd['laser'])['spot'][1]
            
            ## If position arrays are given, translate into voltages
            if 'xPosition' in self.cmd or 'yPosition' in self.cmd:
                if 'xPosition' not in self.cmd or 'yPosition' not in self.cmd:
                    raise Exception('xPosition and yPosition must be given together or not at all.')
                self.cmd['xCommand'], self.cmd['yCommand'] = self.dev.mapToScanner(self.cmd['xPosition'], self.cmd['yPosition'], self.cmd['camera'], self.cmd['laser'])
            ## Otherwise if program is specified, generate the command arrays now
            elif 'program' in self.cmd:
                self.generateProgramArrays(self.cmd)    
                
            ## If shuttering is requested, generate proper arrays and shutter the laser now
            if self.cmd.get('simulateShutter', False):
                self.generateShutterArrays(tasks[self.cmd['laser']], self.cmd['duration'])
        
    def generateShutterArrays(self, laserTask, duration):
        """In the absence of a shutter, use this to direct the beam 'off-screen' when shutter would normally be closed."""
        ##get waveform from laser
        laser = laserTask.cmd['QSwitch']['command']
        offPos = self.dev.getShutterVals()
        
        if 'xCommand' not in self.cmd:   ## If no command was specified, then we just use the current command values whenever the shutter is open
            x, y = self.dev.getCommand()
            self.cmd['xCommand'] = np.empty(len(laser), dtype=float)
            self.cmd['yCommand'] = np.empty(len(laser), dtype=float)
            self.cmd['xCommand'][:] = x
            self.cmd['yCommand'][:] = y
        
        ## Find all regions where the laser is activated, make sure the shutter opens 10ms before each
        shutter = np.zeros(len(laser), dtype=bool)
        dif = laser[1:] - laser[:-1]
        ons = np.argwhere(dif==1)[:,0]
        offs = np.argwhere(dif==-1)[:,0]
        dt = duration / len(laser)
        npts = int(10e-3 / dt)
        ons -= npts
        mask = np.zeros(len(laser), dtype=bool)
        for i in xrange(len(ons)):
            on = max(0, ons[i])
            mask[on:offs[i]] = True
        
        self.cmd['xCommand'][~mask] = offPos[0]
        self.cmd['yCommand'][~mask] = offPos[1]
        
    def generateProgramArrays(self, command):
        """LASER LOGO
        Turn a list of movement commands into arrays of x and y values.
        prg looks like:
        { 
            numPts: 10000,
            duration: 1.0,
            commands: [
               {'type': 'step', 'time': 0.0, 'pos': None),           ## start with step to "off" position 
               ('type': 'step', 'time': 0.2, 'pos': (1.3e-6, 4e-6)), ## step to the given location after 200ms
               ('type': 'line', 'time': (0.2, 0.205), 'pos': (1.3e-6, 4e-6))  ## 5ms sweep to the new position 
               ('type': 'step', 'time': 0.205, 'pos': None),           ## finish step to "off" position at 205ms
           ]
        }
        
        Commands we might add in the future:
          - circle
          - spiral
        """
        dt = command['duration'] / command['numPts']
        arr = np.empty((2, command['numPts']))
        cmds = command['program']
        lastPos = None
                
        lastValue = np.array(self.dev.getVoltage())
        lastStopInd = 0
        for i in range(len(cmds)):
            cmd = cmds[i]
            startInd = cmd['startTime'] / dt
            stopInd = cmd['endTime'] / dt
            arr[:,lastStopInd:startInd] = lastValue[:,np.newaxis]
            if cmd['type'] == 'step':
                ## determine when to end the step
                #if i+1 < len(cmds):
                    #nextTime = cmds[i+1]['time']
                    #if type(nextTime) is tuple:
                        #nextTime = nextTime[0]
                    #stopInd = nextTime / dt
                #else:
                    #stopInd = -1
                
                pos = cmd['pos']
                if pos == None:
                    pos = self.dev.getOffVoltage()
                else:
                    pos = self.dev.mapToScanner(pos[0], pos[1], self.cmd['camera'], self.cmd['laser'])
                lastPos = pos
                
                arr[0, startInd] = pos[0]
                arr[1, startInd] = pos[1]
                
            elif cmd['type'] == 'line':
                if lastPos is None:
                    raise Exception("'line' command with no defined starting position")
                pos = cmd['pos']
                
                xPos = linspace(lastPos[0], pos[0], stopInd-startInd)
                yPos = linspace(lastPos[1], pos[1], stopInd-startInd)
                x, y = self.dev.mapToScanner(xPos, yPos, self.cmd['camera'], self.cmd['laser'])
                arr[0, startInd:stopInd] = x
                arr[1, startInd:stopInd] = y
                lastPos = pos
                
            elif cmd['type'] == 'lineScan':
                startPos = cmd['points'][0]                
                stopPos = cmd['points'][1]               
                scanLength = (stopInd - startInd)/cmd['nScans'] # in point indices, not time.
                
                xPos = np.linspace(startPos.x(), stopPos.x(), scanLength)
                yPos = np.linspace(startPos.y(), stopPos.y(), scanLength)
                x, y = self.dev.mapToScanner(xPos, yPos, self.cmd['camera'], self.cmd['laser'])
                x = np.tile(x, cmd['nScans'])
                y = np.tile(y, cmd['nScans'])
                arr[0, startInd:startInd + len(x)] = x
                arr[1, startInd:startInd + len(y)] = y
                arr[0, startInd + len(x):stopInd] = arr[0, startInd + len(x)-1]
                arr[1, startInd + len(y):stopInd] = arr[1, startInd + len(y)-1]
                lastPos = (x[-1], y[-1])

            elif cmd['type'] == 'rectScan':
                startPos = cmd['points'][0] # lower left corner or so               
                stopPos = cmd['points'][1]  # diagonal opposite corner

                ylen = stopPos.y() - startPos.y()
                yDir = 1;
                if ylen < 0:
                    ylen = 1
                    yDir = -1
                nYScans = int(ylen/cmd['lineSpacing'])
                scanLength = (stopInd - startInd)/(cmd['nScans']*nYScans) # in point indices, not time.
                xPos = np.linspace(startPos.x(), stopPos.x(), scanLength)
                yPos = np.linspace(startPos.y(), startPos.y(), scanLength)
                yStep = yDir*cmd['lineSpacing']
                for nsc in range(0, cmd['nScans']):
                    for yp in range(0,nYScans):
                        yPos = yPos + yStep
                        #yPos = np.linspace(startPos.y(), stopPos.y(), scanLength)
                        xl, yl = self.dev.mapToScanner(xPos, yPos, self.cmd['camera'], self.cmd['laser'])
                        if nsc == 0 and yp == 0:
                            y = yl
                            x = xl
                        else:
                            y = np.append(y, yl)
                            x = np.append(x, xl)
                #x = np.tile(x, cmd['nScans']*nYScans)
                #y = np.tile(y, cmd['nScans'])
                print x.shape
                print y.shape
                arr[0, startInd:startInd + len(x)] = x
                arr[1, startInd:startInd + len(y)] = y
                arr[0, startInd + len(x):stopInd] = arr[0, startInd + len(x)-1]
                arr[1, startInd + len(y):stopInd] = arr[1, startInd + len(y)-1]
                lastPos = (x[-1], y[-1])

            lastValue = arr[:,stopInd-1]
            lastStopInd = stopInd
        arr[:,lastStopInd:] = lastValue[:,np.newaxis]             
        self.dev.dm.somename = arr

        self.cmd['xCommand'] = arr[0] ## arrays of voltage values
        self.cmd['yCommand'] = arr[1]

        
    def createChannels(self, daqTask):
        self.daqTasks = []
        with MutexLocker(self.dev.lock):
            ## If buffered waveforms are requested in the command, configure them here.
            for cmdName, channel in [('xCommand', 'XAxis'), ('yCommand', 'YAxis')]:
                #cmdName = axis[0]
                #channel = axis[1]
                if cmdName not in self.cmd:
                    continue
                print 'adding channel1: ', channel
                chConf = self.dev.config[channel]
                #if chConf[0] != daqTask.devName():
                if chConf['device'] != daqTask.devName():
                    continue
                print 'adding channel2: ', channel
                
                daqTask.addChannel(chConf['channel'], 'ao')
                self.daqTasks.append(daqTask)  ## remember task so we can stop it later on
                daqTask.setWaveform(chConf['channel'], self.cmd[cmdName])

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
    
        ### These arrays stick around and cause memory errors if we don't get rid of them. 
        ## For some reason, the top-level protocol command dict is not being collected (refcount=2, but gc.get_referrers=[])
        ## So until that issue is solved, we need to make sure that extra data is cleaned out.
        if 'xCommand' in self.cmd:
            self.cmd['xCommand'] = "dedeted in ScannerTask.getResult()"
        if 'yCommand' in self.cmd:
            self.cmd['yCommand'] = "dedeted in ScannerTask.getResult()"

        return result
    
    def storeResult(self, dirHandle):
        result = self.getResult()
        dirHandle.setInfo({self.dev.name: result})
        
        