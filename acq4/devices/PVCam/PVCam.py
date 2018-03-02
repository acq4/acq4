# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement
from acq4.devices.Camera import Camera, CameraTask
from acq4.drivers.pvcam import PVCam as PVCDriver
from acq4.util import Qt
import time, sys, traceback
from numpy import *
from acq4.util.metaarray import *
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex
from acq4.util.debug import *


class PVCam(Camera):
    def __init__(self, *args, **kargs):
        self.camLock = Mutex(Mutex.Recursive)  ## Lock to protect access to camera
        self.ringSize = 50
        Camera.__init__(self, *args, **kargs)  ## superclass will call setupCamera when it is ready.
        self.acqBuffer = None
        self.frameId = 0
        self.lastIndex = None
        self.lastFrameTime = None
        self.stopOk = False
    
    def setupCamera(self):
        self.pvc = PVCDriver
        cams = self.pvc.listCameras()
        print("Cameras:", cams)
        if len(cams) < 1:
            raise Exception('No cameras found by pvcam driver')
        
        if self.camConfig['serial'] is None:  ## Just pick first camera
            ind = 0
        else:
            if self.camConfig['serial'] in cams:
                ind = cams.index(self.camConfig['serial'])
            else:
                raise Exception('Can not find pvcam camera "%s". Options are: %s' % (str(self.camConfig['serial']), str(cams)))
        print("Selected camera:", cams[ind])
        self.cam = self.pvc.getCamera(cams[ind])
    
    def start(self, block=True):
        #print "PVCam: start"
        if not self.isRunning():
            self.lastIndex = None
            #print "  not running already; start camera"
            Camera.start(self, block)  ## Start the acquisition thread
            self.startTime = ptime.time()
            
        ## pvcams can take a long time 
        if block:
            tm = self.getParam('triggerMode')
            if tm != 'Normal':
                #print "  waiting for trigger to arm"
                waitTime = 0.3  ## trigger needs about 300ms to prepare (?)
            else:
                waitTime = 0
            
            sleepTime = (self.startTime + waitTime) - ptime.time()
            if sleepTime > 0:
                #print "  sleep for", sleepTime
                time.sleep(sleepTime)
        
    def startCamera(self):
        ## Attempt camera start. If the driver complains that it can not allocate memory, reduce the ring size until it works. (Ridiculous driver bug)
        #  Update: as of 2015.03 the bug is still present.
        self.stopOk = False
        while True:
            try:
                with self.camLock:
                    self.cam.setParam('ringSize', self.ringSize)
                    self.acqBuffer = self.cam.start()
                break
            except Exception as e:
                if len(e.args) == 2 and (e.args[1] in (15, 41)):
                    printRingSize = True
                    self.ringSize = int(self.ringSize * 0.9)
                    print("PVCam error: %r" % e)
                    print("Trying again with smaller ring size %d" % self.ringSize)
                    if self.ringSize < 2:
                        raise
                else:
                    raise
        
    def stopCamera(self):
        with self.camLock:
            if not self.stopOk:      ### If no frames have arrived since starting the camera, then 
                                ### it is not safe to stop the camera immediately--this can hang the (lame) driver
                time.sleep(1.0)
            self.cam.stop()
            self.acqBuffer = None

    def _acquireFrames(self, n=1):
        assert not self.isRunning(), "Camera must be stopped before calling acquireFrames."
        return self.cam.acquire(n)

    def noFrameWarning(self, time):
        # 2015.11: discovered that simply opening connections to multiple USB-serial devices on the same hub as the 
        # camera can cause it to fail to return frames, even if there is no data being sent to/from the serial devices.
        # 
        print("Camera acquisition thread has been waiting %02f sec but no new frames have arrived; shutting down." % diff)
        print("This can be caused by insufficient USB bandwidth; try moving the camera to its own exclusive USB hub.")
        print("Alternatively, reduce the bandwidth requirements of the camera by increasing the binning or decreasing the ROI size.")

    def newFrames(self):
        """Return a list of all frames acquired since the last call to newFrames."""
        
        with self.camLock:
            index = self.cam.lastFrame()
        now = ptime.time()
        if self.lastFrameTime is None:
            self.lastFrameTime = now
            
        if index is None:  ## no frames available yet
            return []
        
        if index == self.lastIndex:  ## no new frames since last check
            return []
        
        self.stopOk = True
        
        ## Determine how many new frames have arrived since last check
        if self.lastIndex is not None:
            diff = (index - self.lastIndex) % self.ringSize
            if diff > (self.ringSize / 2):
                print("Image acquisition buffer is at least half full (possible dropped frames)")
        else:
            self.lastIndex = index-1
            diff = 1
    
        dt = (now - self.lastFrameTime) / diff
        frames = []
        for i in range(diff):
            fInd = (i+self.lastIndex+1) % self.ringSize
            frame = {}
            frame['time'] = self.lastFrameTime + (dt * (i+1))
            frame['id'] = self.frameId
            frame['data'] = self.acqBuffer[fInd].copy()
            #print frame['data']
            frames.append(frame)
            self.frameId += 1
                
        self.lastFrame = frame
        self.lastFrameTime = now
        self.lastIndex = index
        return frames
        
                
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
        time.sleep(2)
        self.cam.close()
        #self.pvc.quit()
        
    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        with self.camLock:
            return self.cam.listParams(params)
        

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        #print "PVCam: setParams", params
        with self.camLock:
            if 'ringSize' in params:
                self.ringSize = params['ringSize']
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


    def setParam(self, param, value, autoRestart=True, autoCorrect=True):
        return self.setParams({param: value}, autoRestart=autoRestart, autoCorrect=autoCorrect)
        #with self.camLock:
            #newVal, restart = self.cam.setParam(param, value, autoCorrect=autoCorrect)
        ##restart = True  ## pretty much _always_ need a restart with these cameras.
        
        #if autoRestart and restart:
            #self.restart()
        #self.emit(Qt.SIGNAL('paramsChanged'), {param: newVal})
        #return (newVal, restart)

    def getParam(self, param):
        with self.camLock:
            return self.cam.getParam(param)

    def createTask(self, cmd, task):
        return PVCamTask(self, cmd, task)
    
    
class PVCamTask(CameraTask):
    def getPrepTimeEstimate(self):
        # if restart needed and triggering
        #return 0.5  # long time to prepare for trigger!
        return 0
    
    