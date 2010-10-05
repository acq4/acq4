#!/usr/bin/env python
from __future__ import with_statement
#from lib.devices.DAQGeneric.interface import DAQGeneric, DAQGenericTask
from lib.devices.Camera import Camera
from lib.drivers.QImaging.QImagingDriver import *
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

class QCam(Camera):
    def __init__(self, *args, **kargs):
        self.camLock = Mutex(Mutex.Recursive)  ## Lock to protect access to camera
        Camera.__init__(self, *args, **kargs)  ## superclass will call setupCamera when it is ready.
        
    def setupCamera(self):
        self.qcd = QCamDriverClass()
        cams = self.qcd.listCameras()
        print "Cameras:", cams
        if len(cams) < 1:
            raise Exception('No cameras found by QCam driver')
        
        #if self.camConfig['serial'] is None:  ## Just pick first camera
        #    ind = 0
        #else:
        #    if self.camConfig['serial'] in cams:
        #        ind = cams.index(self.camConfig['serial'])
        #    else:
        #        raise Exception('Can not find pvcam camera "%s"' % str(self.camConfig['serial']))
        #print "Selected camera:", cams[ind]
        #self.cam = self.pvc.getCamera(cams[ind])
        print "QCam: Opening camera ...."
        self.cam = self.qcd.getCamera(cams[0]) #open first camera
        print "QCam: Camera opened."
        
    #def start(self, block=True):
        #if not self.isRunning():
            ##print "  not running already; start camera"
            #Camera.start(self, block)
            #self.startTime = ptime.time()
            
        #if block:
            #tm = self.getParam('triggerMode')
            #if tm != 'Normal':
                ##print "  waiting for trigger to arm"
                #waitTime = 0.3  ## trigger needs about 300ms to prepare (?)
            #else:
                #waitTime = 0
            
            #sleepTime = (self.startTime + waitTime) - ptime.time()
            #if sleepTime > 0:
                ##print "  sleep for", sleepTime
                #time.sleep(sleepTime)
            
    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        with self.camLock:
            return self.cam.listParams(params)
            
    def setParams(self, params, autoRestart=True, autoCorrect=True):
        #params: a list of (param, value) pairs to be set
        #print "PVCam: setParams", params
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


    #def setParam(self, param, value, autoRestart=True, autoCorrect=True):
        #return self.setParams({param: value}, autoRestart=autoRestart, autoCorrect=autoCorrect)
        
    #def getParam(self, param):
        #with self.camLock:
            #return self.cam.getParam(param)
            
    #def quit(self):
        #Camera.quit(self)
        #self.qcd.quit()
        