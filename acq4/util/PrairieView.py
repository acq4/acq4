import time, socket
import numpy as np
from acq4.Manager import getManager
from acq4.devices.Stage import Stage, MoveFuture
from acq4.util.Thread import Thread
import acq4.pyqtgraph as pg
from acq4.pyqtgraph.Qt import QtGui, QtCore
from acq4.util.Mutex import Mutex
import win32com.client
import pythoncom
import os

class PrairieView(QtCore.QObject):

    sigDataReady = QtCore.Signal(object)
    sigMarkPointsRun = QtCore.Signal(object)

    def __init__(self, ipaddress):

        QtCore.QObject.__init__(self)
        self.prairieRigIP = ipaddress #Wayne Rig
        self.pl_socket = None
        self.connected = False
        self.lock = Mutex()
        self.publicFilePath = 'M:'


    def connect_to_prairie(self):
 
        if not self.connected:

            try:
                self.pl_socket = socket.create_connection((self.prairieRigIP, 1236))
            except:
                raise Exception("Could not connect to PrairieView software.")

            self.connected = True


    def quit(self):

        closed = self.call_pl('-Exit')

        self.pl_socket.close() 
        print('===PROPER DISCONNECT FROM PRAIRIE OCCURED===') 


    def call_pl(self, cmd):

        if not self.connected:
            self.connect_to_prairie()

        orig_cmd = cmd
        cmd = cmd.replace(' ', '\1') + '\r\n'

        with self.lock:
            self.pl_socket.send(cmd)
            response = ''
            while True:
                response += self.pl_socket.recv(1000)
                if response.endswith('DONE\r\n'):
                    break
                time.sleep(0.005)
        parts = response.split('\r\n')


        self.sigDataReady.emit(orig_cmd)

        if 'MarkPoints' in orig_cmd:
            if '-LoadMarkPoints' not in orig_cmd:
                self.sigMarkPointsRun.emit(orig_cmd)

        #elif 'TSeries' in orig_cmd:
            #self.sigTSeriesRun.emit(orig_cmd)

        return parts[1:-1]

    def getPos(self):
        #if not self.connected:
        #    self.connect_to_prairie()

        x = float(self.call_pl('-GetMotorPosition X')[0])
        y = float(self.call_pl('-GetMotorPosition Y')[0])
        z = float(self.call_pl('-GetMotorPosition Z')[0])

        pos = np.array([x, y, z]) 

        return pos

    def getZPos(self):
         z = float(self.call_pl('-GetMotorPosition Z')[0])
         return z

    def move(self, axis, pos):
        ## position in microns
        ## axis one of X, Y, Z 
        #cmd = "-MoveMotor %s %i" % (axis, distance)
        cmd = "-SetMotorPosition %s %f" % (axis, pos) 
        self.call_pl(cmd)

    def setImageName(self, name, iterationNum, addDateTime=False):

        if addDateTime:
            adt = 'addDateTime'
        else:
            adt = ''
        
        self.call_pl('-SetFileName Singlescan %s %s' % (name, adt))
        self.call_pl('-SetFileIteration Singlescan %i' % iterationNum)

    def saveImage(self, name, iterationNum):

        self.setImageName(name, iterationNum)
        self.call_pl('-SingleScan')

    def setSaveDirectory(self, dirPath):
        self.call_pl('-SetSavePath %s' % dirPath)

    def markPoints(self, pos, laserPower, duration, spiralSize, revolutions, nPulses, intervals):
        intervals.append('')
        cmd = "-MarkPoints "
        for i in range(nPulses):
            cmd += "%f %f %f Fidelity %f True %f %f %s"%(pos[0], pos[1], duration[i], laserPower[i], spiralSize, revolutions, str(intervals[i]))

        self.call_pl(cmd)

    
    def loadMarkPoints(self, filename=None):
        if filename is None:
            filename = os.path.join(self.publicFilePath, 'acq4_MarkPoints.xml')
        self.call_pl("-LoadMarkPoints %s" %filename)

    def openShutter(self):
        self.call_pl("-OverrideHardShutter Fidelity open")

    def resetShutter(self):
        self.call_pl("-OverrideHardShutter Fidelity auto")





