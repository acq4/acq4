# -*- coding: utf-8 -*-
import numpy as np
import acq4.pyqtgraph as pg
from acq4.util.HelpfulException import HelpfulException
from collections import OreredDict


# Keep track of all available scan program components
COMPONENTS = OrderedDict()

def registerScanComponent(component):
    COMPONENTS[component.name] = component

for cType in ['step', 'line', 'rect', 'loop', 'ellipse', 'spiral']:
    mod = __import__(cType)
    clsName = cType.capitalize() + "ScanComponent"
    registerScanComponent(mod[clsName])



class ScanProgram:
    """
    ScanProgram encapsulates one or more laser scanning operations that are
    executed in sequence. 
    
    It provides the foillowing services:
    
    * GUI for generating task commands and interactive representation of 
      command in camera module
    * Convert task command to mirror voltage command
    * Save / restore functionality
    * Masking arrays for controlling laser power
    * Extraction and analysis of imaging data generated during a scan
    
    Note that most of the functionality of ScanProgram is provided through 
    subclasses of ScanProgramComponent.
    """
    def __init__(self, dev, command):
        self.dev = dev
        self.cmd = command 

    def mapToScanner(self, x, y):
        return self.dev.mapToScanner(x, y, self.cmd['laser'])
    
    def generate(self):
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
        command = self.cmd
        dt = command['duration'] / command['numPts']
        arr = np.zeros((2, command['numPts']))        
        cmds = command['program']
        lastPos = None     
        lastValue = np.array(self.dev.getVoltage())
        lastStopInd = 0
        for i in range(len(cmds)):
            cmd = cmds[i]
            if cmd['active'] is False:
                continue
            
            startInd = int(cmd['startTime'] / dt)
            stopInd = int(cmd['endTime'] / dt)
            if stopInd >= arr.shape[1]:
                raise HelpfulException('Scan Program duration is longer than protocol duration') 
            arr[:,lastStopInd:startInd] = lastValue[:,np.newaxis]
            cmd['startStopIndices'] = (startInd, stopInd)
            
            if cmd['type'] not in COMPONENTS:
                raise Exception('No registered scan component class named "%s".' % cmd['type'])
            
            component = COMPONENTS[cmd['type']](self, cmd)
            compStopInd = component.generateVoltageArray(arr)
            
            assert compStopInd <= stopInd
            stopInd = compStopInd
            
            lastValue = arr[:,stopInd-1]
            lastStopInd = stopInd
            
            
        arr[:,lastStopInd:] = lastValue[:,np.newaxis]
        
        return arr
