# -*- coding: utf-8 -*-
from __future__ import print_function
import os, pickle 
import numpy as np
import acq4.pyqtgraph as pg
from acq4.devices.Device import *
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.Manager import logMsg, logExc
from acq4.util.Mutex import Mutex
from acq4.util.debug import *
import acq4.util.ptime as ptime
from acq4.util.HelpfulException import HelpfulException
from ..Stage import Stage
from .DeviceGui import ScannerDeviceGui
from .TaskGui import ScannerTaskGui
from .scan_program import ScanProgram 
from six.moves import range

class Scanner(Device, OptomechDevice):
    
    sigShutterChanged = Qt.Signal()
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        
        self.config = config
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.devGui = None
        self.lastRunTime = None
        self.calibrationIndex = None
        self.targetList = [1.0, {}]  ## stores the grids and points used by TaskGui so that they persist
        self.currentCommand = [0,0] ## The last requested voltage values (but not necessarily the current voltage applied to the mirrors)
        self.currentVoltage = [0, 0]
        self.shutterOpen = True ## indicates whether the virtual shutter is closed (the beam is steered to its 'off' position).
        if 'offVoltage' in config:
            self.setShutterOpen(False)
        dm.declareInterface(name, ['scanner'], self)
    
    #def quit(self):
        #Device.quit(self)
        ##if os.path.isfile(self.targetFileName):
            ##os.delete(self.targetFileName)
            
    def setCommand(self, vals):
        """Requests to set the command output to the mirrors.
        
        If the virtual shutter is closed, then the mirrors are not moved until
        the shutter is opened.
        """
        with self.lock:
            self.currentCommand = vals
            if self.getShutterOpen():
                self._setVoltage(vals)
            else:
                logMsg("Virtual shutter closed, not setting mirror position.", msgType='warning')

    def setPosition(self, pos, laser):
        """Set the position of the xy mirrors to a point in the image
        
        If the virtual shutter is closed, then the mirrors are not moved until
        the shutter is opened.
        """
        prof = Profiler('Scanner.setPosition', disabled=True)
        with self.lock:
            (x, y) = pos
            prof.mark()
            vals = self.mapToScanner(x, y, laser)
            prof.mark()
            self.setCommand(vals)
            prof.mark()
        prof.finish()
        
    def setShutterOpen(self, o):
        """Immediately move mirrors to the 'off' position or back.
        
        This method controls a "virtual" shutter that works by moving the scan 
        mirrors to a location outside the optical train (defined by the 
        `offVoltage` option in the scanner's configuration). While the virtual
        shutter is closed, all commands to set the mirror voltage are disabled. 
        When the virtual shutter is opened, the mirrors move to the most recent 
        position requested.
        """
        self.shutterOpen = o
        if o:
            self._setVoltage(self.getCommand())
        else:
            shVals = self.getShutterVals()
            if shVals is None:
                raise Exception("Scan mirrors are not configured for virtual shuttering; can not open.")
            self._setVoltage(shVals)
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
          3) Someone has called _setVoltage when they should have called setCommand"""
        vals = []
        with self.lock:
            vals = self.currentCommand[:]
        return vals
    
    def _setVoltage(self, vals):
        '''Immediately sets the voltage value on the mirrors.
        Does check virtual shutter state; most likely you want to use setCommand instead.'''
        with self.lock:
            ## make sure we have not requested a command outside the allowed limits
            (mn, mx) = self.config['commandLimits']
            for i in [0,1]:
                x = ['XAxis', 'YAxis'][i]
                daq = self.config[x]['device']
                chan = self.config[x]['channel']
                dev = self.dm.getDevice(daq)
                clipped = max(mn, min(mx, vals[i]))
                dev.setChannelValue(chan, clipped, block=True)
            self.currentVoltage = vals

    def getVoltage(self):
        with self.lock:
            return self.currentVoltage

    def getDaqName(self):
        return self.config['XAxis']['device']
        
    def mapToScanner(self, x, y, laser, opticState=None):
        """Convert global coordinates to voltages required to set scan mirrors
        *laser* and *opticState* are used to look up the correct calibration data.
        If *opticState* is not given, then the current optical state is used instead.
        """
        if opticState is None:
            opticState = self.getDeviceStateKey() ## this tells us about objectives, filters, etc
        cal = self.getCalibration(laser, opticState)
        
        if cal is None:
            raise HelpfulException("The scanner device '%s' is not calibrated for this combination of laser and objective (%s, %s)" % (self.name(), laser, str(opticState)))
            
        ## map from global coordinates to parent
        parentPos = self.mapGlobalToParent((x,y))
        if isinstance(parentPos, Qt.QPointF):
            x = parentPos.x()
            y = parentPos.y()
        else:
            x = parentPos[0]
            y = parentPos[1]
            
        ## map to voltages using calibration
        cal = cal['params']
        x2 = x**2
        y2 = y**2
        x1 = cal[0][0] + cal[0][1] * x + cal[0][2] * y + cal[0][3] * x2 + cal[0][4] * y2
        y1 = cal[1][0] + cal[1][1] * x + cal[1][2] * y + cal[1][3] * x2 + cal[1][4] * y2
        #print "voltage:", x1, y1
        return [x1, y1]
        
    def getCalibrationIndex(self):
        with self.lock:
            if self.calibrationIndex is None:
                index = self.readConfigFile('index')
                self.calibrationIndex = index
            return self.calibrationIndex
        
    def writeCalibrationDefaults(self, state):
        with self.lock:
            self.writeConfigFile(state, 'defaults')
        
    def loadCalibrationDefaults(self):
        with self.lock:
            state = self.readConfigFile('defaults')
            return state
        
    def writeCalibrationIndex(self, index):
        with self.lock:
            self.writeConfigFile(index, 'index')
            self.calibrationIndex = index

    def getCalibration(self, laser, opticState=None):
        with self.lock:
            index = self.getCalibrationIndex()
            
        if opticState is None:
            opticState = self.getDeviceStateKey() ## this tells us about objectives, filters, etc
        
        if laser in index:
            index1 = index[laser]
        else:
            logMsg("Warning: No calibration found for laser %s" % laser, msgType='warning')
            return None
            
        if opticState in index1:
            index2 = index1[opticState]
        else:
            logMsg("Warning: No calibration found for state: %s" % opticState, msgType='warning')
            return None
        
        return index2.copy()
        
    def storeCameraConfig(self, camera):
        """Store the configuration to be used when calibrating this camera"""
        camDev = self.dm.getDevice(camera)
        params = camDev.listParams()
        params = [p for p in params if params[p][1] and params[p][2]]  ## Select only readable and writable parameters
        state = camDev.getParams(params)
        self.writeConfigFile(state, camera+'Config.cfg')
        
    def getCameraConfig(self, camera):
        return self.readConfigFile(camera+'Config.cfg')
        
    def createTask(self, cmd, parentTask):
        with self.lock:
            return ScannerTask(self, cmd, parentTask)
    
    def taskInterface(self, taskRunner):
        with self.lock:
            return ScannerTaskGui(self, taskRunner)
    
    def deviceInterface(self, win):
        with self.lock:
            if self.devGui is None:
                self.devGui = ScannerDeviceGui(self, win)
            return self.devGui


class ScannerTask(DeviceTask):
    """
    Options for Scanner task:
        position:         (x,y) A calibrated position (in real physical coordinates) to set 
                          before starting the task. Requires 'camera' and 'laser' are
                          also specified.
        command:          (x,y) Voltage values to set before starting the task.
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
    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.cmd = cmd
        self.daqTasks = []
        self.spotSize = None
        
        # We use this flag to exit from the sleep loop in start() in case the 
        # task is aborted during that time.
        self.aborted = False
        self.abortLock = Mutex(recursive=True)
        
    def getConfigOrder(self):
        deps = []
        if self.cmd.get('simulateShutter', False):
            deps.append(self.cmd['laser'])

        if self.cmd.get('simulateShutter', False) or 'program' in self.cmd:
            deps.append(self.dev.getDaqName())
            
        return ([],deps)

    def configure(self):
        prof = Profiler('ScannerTask.configure', disabled=True)
        with self.dev.lock:
            prof.mark('got lock')
            ## If shuttering is requested, make sure the (virtual) shutter is closed now
            if self.cmd.get('simulateShutter', False):
                self.dev.setShutterOpen(False)
                
            ## Set position of mirrors now
            if 'command' in self.cmd:
                self.dev.setCommand(self.cmd['command'])
                prof.mark('set command')
            elif 'position' in self.cmd:  ## 'command' overrides 'position'
                #print " set position:", self.cmd['position']
                self.dev.setPosition(self.cmd['position'], self.cmd['laser'])
                prof.mark('set pos')

            ## record spot size from calibration data
            if 'laser' in self.cmd:
                cal = self.dev.getCalibration(self.cmd['laser'])
                if cal is None:
                    raise Exception("Scanner is not calibrated for: %s, %s" % (self.cmd['laser'], self.dev.getDeviceStateKey()))
                self.spotSize = cal['spot'][1]
                prof.mark('getSpotSize')
            
            ## If position arrays are given, translate into voltages
            if 'xPosition' in self.cmd or 'yPosition' in self.cmd:
                if 'xPosition' not in self.cmd or 'yPosition' not in self.cmd:
                    raise Exception('xPosition and yPosition must be given together or not at all.')
                self.cmd['xCommand'], self.cmd['yCommand'] = self.dev.mapToScanner(self.cmd['xPosition'], self.cmd['yPosition'], self.cmd['laser'])
                prof.mark('position arrays')
            
            # Deprecated - this should be done by the task creator instead.
            # The 'program' key is now ignored as meta-data.
            # elif 'program' in self.cmd:
            #     self.generateProgramArrays(self.cmd)    
            #     prof.mark('program')
                
            ## If shuttering is requested, generate proper arrays and shutter the laser now
            if self.cmd.get('simulateShutter', False):
                self.generateShutterArrays(tasks[self.cmd['laser']], self.cmd['duration'])
                prof.mark('shutter')
            prof.finish()
        
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
        for i in range(len(ons)):
            on = max(0, ons[i])
            mask[on:offs[i]] = True
        
        self.cmd['xCommand'][~mask] = offPos[0]
        self.cmd['yCommand'][~mask] = offPos[1]
        
    # Deprecated - this should be done by the task creator instead.
    # def generateProgramArrays(self, command):
    #     arr = ScanProgram.generateVoltageArray(self.dev, command)
    #     self.cmd['xCommand'] = arr[0] ## arrays of voltage values
    #     self.cmd['yCommand'] = arr[1]
        
    def createChannels(self, daqTask):
        ## make sure we have not requested a command outside the allowed limits
        (mn, mx) = self.dev.config['commandLimits']

        self.daqTasks = []
        with self.dev.lock:
            ## If buffered waveforms are requested in the command, configure them here.
            for cmdName, channel in [('xCommand', 'XAxis'), ('yCommand', 'YAxis')]:
                #cmdName = axis[0]
                #channel = axis[1]
                if cmdName not in self.cmd:
                    continue
                #print 'adding channel1: ', channel
                chConf = self.dev.config[channel]
                #if chConf[0] != daqTask.devName():
                if chConf['device'] != daqTask.devName():
                    continue
                #print 'adding channel2: ', channel
                
                daqTask.addChannel(chConf['channel'], 'ao')
                self.daqTasks.append(daqTask)  ## remember task so we can stop it later on
                clipped = np.clip(self.cmd[cmdName], mn, mx)
                daqTask.setWaveform(chConf['channel'], clipped)

    def stop(self, abort=False):
        if abort:
            with self.abortLock:
                print("Abort!")
                self.aborted = True
        with self.dev.lock:
            for t in self.daqTasks:
                t.stop(abort=abort)
            self.dev.lastRunTime = ptime.time()
            

    def start(self):
        #print "start"
        with self.dev.lock:
            lastRunTime = self.dev.lastRunTime
        if lastRunTime is None:
            #print "  no wait"
            return
        
        # Task specifies that we have a minimum wait from the end of the previous
        # task to the start of this one. This is used in photostimulation experiments
        # that require variable downtime depending on the proximity of subsequent
        # stimulations.
        if 'minWaitTime' in self.cmd:
            while True:
                now = ptime.time()
                wait = min(0.1, self.cmd['minWaitTime'] - (now - lastRunTime))
                if wait <= 0:
                    break
                with self.abortLock:
                    if self.aborted:
                        return
                time.sleep(wait)
            
    def getResult(self):
        #result = {}
        #for k in ['position', 'command']:
            #if k in self.cmd:
                #result[k] = self.cmd[k]

        result = self.cmd.copy()
        if self.spotSize is not None:
            result['spotSize'] = self.spotSize
        
        ### These arrays stick around and cause memory errors if we don't get rid of them. 
        ## For some reason, the top-level task command dict is not being collected (refcount=2, but gc.get_referrers=[])
        ## So until that issue is solved, we need to make sure that extra data is cleaned out.
        if 'xCommand' in self.cmd:
            self.cmd['xCommand'] = "deleted in ScannerTask.getResult()"
        if 'yCommand' in self.cmd:
            self.cmd['yCommand'] = "deleted in ScannerTask.getResult()"

        return result
    
    def storeResult(self, dirHandle):
        result = self.getResult()
        dirHandle.setInfo({self.dev.name(): result})
        
        
