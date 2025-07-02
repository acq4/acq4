#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement

import time

from acq4.devices.Camera import Camera
from acq4.drivers.QImaging.QImagingDriver import QCamDriverClass
from acq4.util.Mutex import Mutex


class QCam(Camera):
    """
    Camera driver for QImaging cameras using the QCam library.
    
    QCam-specific configuration options:
    
    * **serial** (str, optional): Camera serial number string
      If not specified, the first available camera will be used.
      Use incorrect serial to see available options in error message.
    
    Standard Camera configuration options (see Camera base class):
    
    * **parentDevice** (str, optional): Name of parent optical device (microscope, etc.)
    
    * **transform** (dict, optional): Spatial transform relative to parent device
        - pos: Position offset [x, y]
        - scale: Scale factors [x, y] in m/pixel
        - angle: Rotation angle in radians
    
    * **exposeChannel** (dict, optional): DAQ channel for exposure signal recording
    
    * **triggerInChannel** (dict, optional): DAQ channel for triggering camera
    
    * **params** (dict, optional): Camera parameters to set at startup
    
    Example configuration::
    
        Camera:
            driver: 'QCam'
            parentDevice: 'Microscope'
            transform:
                pos: [0, 0]
                scale: [1, 1]
                angle: 0
    """
    def setupCamera(self):
        self.qcd = QCamDriverClass()
        cams = self.qcd.listCameras()
        if len(cams) < 1:
            raise Exception('No cameras found by QCam driver')
        
        # If no camera is specified, choose the first
        serial = self.camConfig.get('serial', list(cams.keys())[0])
        
        if serial not in cams:
            raise Exception('QCam camera "%s" not found. Options are: %s' % (serial, list(cams.keys())))
        self.cam = self.qcd.getCamera(cams[serial]) #open first camera
            
    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        with self.camLock:
            return self.cam.listParams(params)
            
    def setParams(self, params, autoRestart=True, autoCorrect=True):
        """Set camera parameters. Options are:
           params: a list or dict of (param, value) pairs to be set. Parameters are set in the order specified.
           autoRestart: If true, restart the camera if required to enact the parameter changes
           autoCorrect: If true, correct values that are out of range to their nearest acceptable value
        
        Return a tuple with: 
           0: dictionary of parameters and the values that were set.
              (note this may differ from requested values if autoCorrect is True)
           1: Boolean value indicating whether a restart is required to enact changes.
              If autoRestart is True, this value indicates whether the camera was restarted."""
        #params: a list of (param, value) pairs to be set
        #print "PVCam: setParams", params
        with self.camLock:
            newVals, restart = self.cam.setParams(params, autoCorrect=autoCorrect)
        #restart = True  ## pretty much _always_ need a restart with these cameras.
        
        if autoRestart and restart:
            self.restart()
        #self.emit(Qt.SIGNAL('paramsChanged'), newVals)
        self.sigParamsChanged.emit(newVals)
        return (newVals, restart)
        
    def getParams(self, params=None):
        if params is None:
            params = list(self.listParams().keys())
        with self.camLock:
            return self.cam.getParams(params)


    #def setParam(self, param, value, autoRestart=True, autoCorrect=True):
        #return self.setParams({param: value}, autoRestart=autoRestart, autoCorrect=autoCorrect)
        
    def getParam(self, param):
        with self.camLock:
            return self.cam.getParam(param)

        
    def quit(self):
        #print "quit() called from QCamDevice."
        Camera.quit(self)
        self.qcd.quit()
        
    def newFrames(self):
        with self.camLock:
            a = self.cam.newFrames()
        return a
      
    
    def startCamera(self):
        with self.camLock:
            #sys.stdout.flush()
            #time.sleep(0.1)
            #print "QCam: Start camera"
            self.cam.start()
            
    def stopCamera(self):
        with self.camLock:
            #sys.stdout.flush()
            #time.sleep(0.1)
            #print "QCam: Stop camera"
            self.cam.stop()
            time.sleep(0.06)

        