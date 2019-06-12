from __future__ import print_function
import numpy as np
#from acq4.Manager import getManager
#from acq4.devices.Stage import Stage, MoveFuture
#from acq4.util.Thread import Thread
import acq4.pyqtgraph as pg
from acq4.pyqtgraph.Qt import QtGui, QtCore
from acq4.util.Mutex import Mutex
#import win32com.client
#import pythoncom
import os

class MockPrairieView():

    def getPos(self):
        return np.array([0,0,0])

    def saveImage(self, name, iterationNum):
        pass

    def setSaveDirectory(self, dirPath):
        pass

    def markPoints(self, pos, laserPower, duration, spiralSize, revolutions, nPulses, intervals):
        intervals.append('')
        cmd = "-MarkPoints "
        for i in range(nPulses):
            cmd += "%f %f %f Fidelity %f True %f %f %s"%(pos[0], pos[1], duration[i], laserPower[i], spiralSize, revolutions, str(intervals[i]))

        print("CMD: ", cmd)
        print("   pos:", pos,
              "   laserPower:", laserPower,
              "   duration:", duration,
              "   spiralSize:", spiralSize,
              "   revolutions:", revolutions,
              "   nPulses:", nPulses,
              "   intervals:", intervals)

    def openShutter(self):
        pass

    def resetShutter(self):
        pass