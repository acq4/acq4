from __future__ import print_function
import numpy as np
import acq4.pyqtgraph as pg
from .component import ScanProgramComponent



#class StepScanComponent(ScanProgramComponent):
    #"""
    #Steps the laser once to a specific position.    
    #"""
    #name = 'step'
    
    #def generateVoltageArray(self, arr, startInd, stopInd):
        #pos = cmd['pos']
        #if pos == None:
            #pos = self.dev.getOffVoltage()
        #else:
            #pos = self.mapToScanner(pos[0], pos[1])
        #lastPos = pos
        
        #arr[0, startInd] = pos[0]
        #arr[1, startInd] = pos[1]
        #return startInd
