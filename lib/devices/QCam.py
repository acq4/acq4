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
        self.qcd = _QCamDriver()
        cams = self.pvc.listCameras()
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
        
        self.cam = self.qcd.getCamera(cams[0]) #open first camera  
        