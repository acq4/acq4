# -*- coding: utf-8 -*-
from __future__ import with_statement
from acq4.devices.Camera import Camera, CameraTask
from PyQt4 import QtCore
import time, sys, traceback
from numpy import *
from acq4.util.metaarray import *
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex
from acq4.util.debug import *

try:
    import MMCorePy
    HAVE_MM = True
except ImportError:
    HAVE_MM = False


class MicroManager(Camera):
    """Camera device that uses MicroManager to provide imaging.

    Configuration keys:

    * mmAdapterName
    * mmDeviceName
    """
    def __init__(self, *args, **kargs):
        assert HAVE_MM, "MicroManager module (MMCorePy) is not importable."
        self.camLock = Mutex(Mutex.Recursive)  ## Lock to protect access to camera
        Camera.__init__(self, *args, **kargs)  ## superclass will call setupCamera when it is ready.
        self.acqBuffer = None
        self.frameId = 0
        self.lastIndex = None
        self.lastFrameTime = None
    
    def setupCamera(self):
        self.mmc = MMCorePy.CMMCore()

        # sanity check for MM adapter and device name
        adapterName = self.config['mmAdapterName']
        allAdapters = self.mmc.getDeviceAdapterNames()
        if adapterName not in allAdapters:
            raise ValueError("Adapter name '%s' is not valid. Options are: %s" % (adapterName, allAdapters))
        deviceName = self.config['mmDeviceName']
        allDevices = self.mmc.getAvailableDevices(adapterName)
        if deviceName not in allDevices:
            raise ValueError("Device name '%s' is not valid for adapter '%s'. Options are: %s" % (deviceName, adapterName, allDevices))

        self.mmc.loadDevice(self.name(), adapterName, deviceName)
        self.mmc.initializeDevice(self.name())
        
    def startCamera(self):
        with self.camLock:
            self.mmc.startContinuousSequenceAcquisition(0)
            
    def stopCamera(self):
        with self.camLock:
            self.mmc.stopSequenceAcquisition()
            self.acqBuffer = None

    def _acquireFrames(self, n=1):
        assert n == 1, "MMC only supports single-frame or continuous acquisition (requested %d frames)" % n
        self.mmc.snapImage()
        return self.mmc.getImage()

    def newFrames(self):
        """Return a list of all frames acquired since the last call to newFrames."""
        
        with self.camLock:
            nFrames = mmc.getRemainingImageCount()
            if nFrames == 0:
                return []

        now = ptime.time()
        if self.lastFrameTime is None:
            self.lastFrameTime = now
        
        ## Determine how many new frames have arrived since last check
    
        dt = (now - self.lastFrameTime) / nFrames
        frames = []
        with self.camLock:
            for i in range(nFrames):
                fInd = (i+self.lastIndex+1) % self.ringSize
                frame = {}
                frame['time'] = self.lastFrameTime + (dt * (i+1))
                frame['id'] = self.frameId
                frame['data'] = self.mmc.popNextFrame()
                frames.append(frame)
                self.frameId += 1
                
        self.lastFrame = frame
        self.lastFrameTime = now
        self.lastIndex = index
        return frames
        
    def quit(self):
        mmc.stopSequenceAcquisition()
        mmc.unloadDevice(self.name())

    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        with self.camLock:
            properties = self.mmc.getDevicePropertyNames(self.name())
            vals = [self.mmc.getDevicePropertyValues(self.name(), prop) for prop in properties]
            readonly = [self.mmc.isPropertyReadOnly(self.name(), prop) for prop in properties]
            # make sure device names are coerced into our standard names:
            params = {
                'triggerMode': (value, writable, readable, deps),
                'exposure': (value, writable, readable, deps),
                'binningX': (value, writable, readable, deps),
                'binningY': (value, writable, readable, deps),
                'regionX': (value, writable, readable, deps),
                'regionY': (value, writable, readable, deps),
                'regionW': (value, writable, readable, deps),
                'regionH': (value, writable, readable, deps),
            }

        

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        #print "PVCam: setParams", params
        with self.camLock:
            if 'ringSize' in params:
                self.ringSize = params['ringSize']
            newVals, restart = self.cam.setParams(params, autoCorrect=autoCorrect)
        #restart = True  ## pretty much _always_ need a restart with these cameras.
        
        if autoRestart and restart:
            self.restart()
        
        #self.emit(QtCore.SIGNAL('paramsChanged'), newVals)
        self.sigParamsChanged.emit(newVals)
        return (newVals, restart)

    def getParams(self, params=None):
        if params is None:
            params = self.listParams().keys()
        with self.camLock:
            pass

    def setParam(self, param, value, autoRestart=True, autoCorrect=True):
        with self.camLock:
            if param == 'exposure':
                self.mmc.setExposure(exposure)  # scaling?
            else:
                self.mmc.setProperty(self.name(), param, value)

    def getParam(self, param):
        with self.camLock:
            return self.mmc.getProperty(self.name(), name)

