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
    def __init__(self, *args, **kargs):
        self.camLock = Mutex()  ## Lock to protect access to camera
        Camera.__init__(self, *args, **kargs)  ## superclass will call setupCamera when it is ready.
    
    def setupCamera(self):
        self.pvc = PVCDriver
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
        
    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        with self.camLock:
            return self.cam.listParams(params)
        

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        with self.camLock:
            newVals, restart = self.cam.setParams(params, autoCorrect=autoCorrect)
        #restart = True  ## pretty much _always_ need a restart with these cameras.
        
        if autoRestart and restart:
            self.restart()
        self.emit(QtCore.SIGNAL('paramsChanged'), newVals)
        return (newVals, restart)

    def getParams(self, params=None):
        if params is None:
            params = self.listParams().keys()
        with self.camLock:
            return self.cam.getParams(params)


    def setParam(self, param, value, autoRestart=True, autoCorrect=True):
        with self.camLock:
            newVal, restart = self.cam.setParam(param, value, autoCorrect=autoCorrect)
        #restart = True  ## pretty much _always_ need a restart with these cameras.
        
        if autoRestart and restart:
            self.restart()
        self.emit(QtCore.SIGNAL('paramsChanged'), {param: newVal})
        return (newVal, restart)

    def getParam(self, param):
        with self.camLock:
            return self.cam.getParam(param)

