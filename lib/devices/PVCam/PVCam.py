# -*- coding: utf-8 -*-
from __future__ import with_statement
#from lib.devices.DAQGeneric.interface import DAQGeneric, DAQGenericTask
from lib.devices.Camera import Camera
from lib.drivers.pvcam import PVCam as PVCDriver
#from lib.devices.Device import *
from PyQt4 import QtCore
import time, sys, traceback
from numpy import *
from metaarray import *
#from protoGUI import *
#from deviceGUI import *
import lib.util.ptime as ptime
from lib.util.Mutex import Mutex, MutexLocker
from lib.util.debug import *

class PVCam(Camera):
    def __init__(self, ):
        Camera.__init__(self)
        
        self.camLock = Mutex()  ## Lock to protect access to camera
        
        cams = self.pvc.listCameras()
        print "Cameras:", cams
        if len(cams) < 1:
            raise Exception('No cameras found by pvcam driver')
        
        if self.camConfig['serial'] is None:  ## Just pick first camera
            ind = 0
        else:
            if self.camConfig['serial'] in cams:
                ind = cams.index(self.camConfig['serial'])
            else:
                raise Exception('Can not find pvcam camera "%s"' % str(self.camConfig['serial']))
        print "Selected camera:", cams[ind]
        self.cam = self.pvc.getCamera(cams[ind])
    
    #def reconnect(self):
        #print "Stopping acquisition.."
        #try:
            #self.stopAcquire(block=True)
        #except:
            #printExc("Error while stopping camera:")
        #print "Closing camera.."
        #try:
            #self.cam.close()
        #except:
            #printExc("Error while closing camera:")
            
        #print "Re-initializing pvcam driver"
        #self.pvc.reloadDriver()
            
        #print "Cameras are:", self.pvc.listCameras()
            
        #self.cam.open()
        #print "Re-opened camera."
        
    def quit(self):
        Camera.quit(self)
        self.pvc.quit()
        
    def listParams(self):
        with self.camLock:
            return self.cam.listParams()
        

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        with self.camLock:
            (newVals, restart) = self.cam.setParams(params)
        
        self.emit(QtCore.SIGNAL('paramsChanged'), newVals)

        if autoRestart and restart:
            self.restart()
        return (newVals, restart)

    def getParams(self, params=None):
        if params is None:
            params = self.listParams().keys()
        with self.camLock:
            return self.cam.getParams(params)
