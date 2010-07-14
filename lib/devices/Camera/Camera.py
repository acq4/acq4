# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.DAQGeneric import DAQGeneric, DAQGenericTask
#from lib.devices.Device import *
from PyQt4 import QtCore
import time
from numpy import *
from metaarray import *
from protoGUI import *
from deviceGUI import *
import lib.util.ptime as ptime
from lib.util.Mutex import Mutex, MutexLocker
from lib.util.debug import *

class Camera(DAQGeneric):
    """Generic camera device class. All cameras should extend from this interface.
     - The class handles protocol tasks, scope integration, expose/trigger lines
     - Subclasses should handle the connection to the camera driver by overriding
        listParams, getParams, and setParams.
     - Subclasses may need to create their own AcquireThread

    The list/get/setParams functions should implement a few standard items:
    (Note: these values are just examples, but the data types must be the same.)
        acquire:         bool
        triggerMode:     str, ['NoTrigger', 'TriggerStart', 'Strobe', 'Bulb']
        triggerType:     str, ['Software', 'Hardware']
        exposure:        float, (0.0, 10.0)
        exposureMode:    str, ['Exact', 'Maximize']
        binning:         int, [1,2,4,8,16]
        region:          dict, {
                            'x': (int, (0, 511)), 
                            'y': (int, (0, 511)), 
                            'w': (int, (1, 512)), 
                            'h': (int, (1, 512))  } 
        gain:            float, (0.1, 10.0)

    The configuration for these devices should look like:
    (Note that each subclass will add config options for identifying the camera)
        scopeDevice: 'Microscope'
        scaleFactor: (1.0, 1.0)  ## used for rectangular pixels
        exposeChannel: 'DAQ', '/Dev1/port0/line14'  ## Channel for recording expose signal
        triggerOutChannel: 'DAQ', '/Dev1/PFI5'  ## Channel the DAQ should trigger off of to sync with camera
        triggerInChannel: 'DAQ', '/Dev1/port0/line13'  ## Channel the DAQ should raise to trigger the camera
        paramLimits:
            binning:  [1,2,4,6,8,16]  ## set the limits for binning manually since the driver can't
        params:
            GAIN_INDEX: 2
            CLEAR_MODE: 'CLEAR_PRE_SEQUENCE'  ## Overlap mode for QuantEM
    """


    def __init__(self, dm, config, name):

        # Generate config to use for DAQ 
        daqConfig = {}
        if 'exposeChannel' in config:
            daqConfig['exposure'] = {'type': 'di', 'channel': config['exposeChannel']}
        if 'triggerInChannel' in config:
            daqConfig['trigger'] = {'type': 'do', 'channel': config['triggerInChannel']}
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        self.camConfig = config
        self.stateStack = []
        
        
        if 'scaleFactor' not in self.camConfig:
            self.camConfig['scaleFactor'] = [1., 1.]
        
        ## Default values for scope state. These will be used if there is no scope defined.
        self.scopeState = {
            'id': 0,
            'scale': self.camConfig['scaleFactor'],
            'scopePosition': [0, 0],
            'centerPosition': [0, 0],
            'offset': [0, 0],
            'objScale': 1,
            'pixelSize': filter(abs, self.camConfig['scaleFactor']),
            'objective': ''
        }
        
        
        if 'scopeDevice' in config:
            self.scopeDev = self.dm.getDevice(config['scopeDevice'])
            QtCore.QObject.connect(self.scopeDev, QtCore.SIGNAL('positionChanged'), self.positionChanged)
            QtCore.QObject.connect(self.scopeDev, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
            ## Cache microscope state for fast access later
            self.objectiveChanged()
            self.positionChanged()
        else:
            self.scopeDev = None
            
            
        self.setupCamera()  
            
        self.acqThread = AcquireThread(self)
        QtCore.QObject.connect(self.acqThread, QtCore.SIGNAL('finished()'), self.acqThreadFinished)
        QtCore.QObject.connect(self.acqThread, QtCore.SIGNAL('started()'), self.acqThreadStarted)
        QtCore.QObject.connect(self.acqThread, QtCore.SIGNAL('showMessage'), self.showMessage)
        QtCore.QObject.connect(self.acqThread, QtCore.SIGNAL('newFrame'), self.newFrame)
        
        if 'params' in config:
            self.setParams(config['params'])
            
    def setupCamera(self):
        """Prepare the camera at least so that get/setParams will function correctly"""
        raise Exception("Function must be reimplemented in subclass.")

    def listParams(self, params=None):
        """Return a dictionary of parameter descriptions. By default, all parameters are listed.
        Each description is a tuple: (values, isWritable, isReadable, dependencies)
        
        values may be any of:
          - Tuple of ints or floats indicating minimum and maximum values
          - List of int / float / string values
          - Tuple of strings, indicating that the parameter is made up of multiple sub-parameters
             (eg, 'region' should be ('regionX', 'regionY', 'regionW', 'regionH')
             
        dependencies is a list of other parameters which affect the allowable values of this parameter.
        
        eg:
        {  'paramName': ([list of values], True, False, []) }
        """
        raise Exception("Function must be reimplemented in subclass.")

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        """Set camera parameters. Options are:
           params: a list of (param, value) pairs to be set. Parameters are set in the order specified.
           autoRestart: If true, restart the camera if required to enact the parameter changes
           autoCorrect: If true, correct values that are out of range to their nearest acceptable value
        
        Return a tuple with: 
           0: dictionary of parameters and the values that were set.
              (note this may differ from requested values if autoCorrect is True)
           1: Boolean value indicating whether a restart is required to enact changes.
              If autoRestart is True, this value indicates whether the camera was restarted."""
        raise Exception("Function must be reimplemented in subclass.")
        
    def getParams(self, params=None):
        raise Exception("Function must be reimplemented in subclass.")
        
    def setParam(self, param, val, autoCorrect=True, autoRestart=True):
        return self.setParams([(param, val)], autoCorrect=autoCorrect, autoRestart=autoRestart)[0]
        
    def getParam(self, param):
        return self.getParams([param])[param]
        
    def pushState(self, name=None):
        print "Camera: pushState", name
        params = self.listParams()
        for k in params.keys():    ## remove non-writable parameters
            if not params[k][1]:
                del params[k]
        params = self.getParams(params.keys())
        params['isRunning'] = self.isRunning()
        
        self.stateStack.append((name, params))
        
    def popState(self, name=None):
        print "Camera: popState", name
        if name is None:
            state = self.stateStack.pop()[1]
        else:
            inds = [i for i in range(len(self.stateStack)) if self.stateStack[i][0] == name]
            if len(inds) == 0:
                raise Exception("Can not find camera state named '%s'" % name)
            state = self.stateStack[inds[-1]][1]
            self.stateStack = self.stateStack[:inds[-1]]
            
        run = state['isRunning']
        del state['isRunning']
        nv, restart = self.setParams(state, autoRestart=False)
        print "    run:", run, "isRunning:", self.isRunning(), "restart:", restart
        
        if self.isRunning():
            if run:
                if restart:
                    self.restart()
            else:
                self.stop()
        else:
            if run:
                self.start()
            
        
        #if not run and self.isRuning():
            #self.stop()
        
        #if run and (restart or (not self.isRunning()):
            #self.start()
        

    def start(self, block=True):
        print "Camera: start"
        self.acqThread.start()
        
    def stop(self, block=True):
        print "Camera: stop"
        self.acqThread.stop(block=block)
        
    def restart(self):
        if self.acqThread.isRunning():
            self.stop()
            self.start()
    
    def quit(self):
        if hasattr(self, 'acqThread') and self.isRunning():
            self.stop()
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
        #self.cam.close()
        DAQGeneric.quit(self)
        #print "Camera device quit."
        
        
    #@ftrace
    def devName(self):
        with MutexLocker(self.lock):
            return self.name
    
    
    #@ftrace
    def createTask(self, cmd):
        with MutexLocker(self.lock):
            return CameraTask(self, cmd)
    
    #@ftrace
    def getTriggerChannel(self, daq):
        with MutexLocker(self.lock):
            if not 'triggerOutChannel' in self.camConfig:
                return None
            if self.camConfig['triggerOutChannel'][0] != daq:
                return None
            return self.camConfig['triggerOutChannel'][1]
        

    def isRunning(self):
        with MutexLocker(self.lock):
            return self.acqThread.isRunning()

    def protocolInterface(self, prot):
        return CameraProtoGui(self, prot)

    def deviceInterface(self, win):
        return CameraDeviceGui(self, win)
    
    ### Scope interface functions below

    def getPosition(self, justScope=False):
        """Return the coordinate of the center of the sensor area
        If justScope is True, return the scope position, uncorrected for the objective offset"""
        with MutexLocker(self.lock):
            if justScope:
                return self.scopeState['scopePosition']
            else:
                return self.scopeState['centerPosition']

    #@ftrace
    def getScale(self):
        """Return the dimensions of 1 pixel with signs if the image is flipped"""
        with MutexLocker(self.lock):
            return self.scopeState['scale']
        
    #@ftrace
    def getPixelSize(self):
        """Return the absolute size of 1 pixel"""
        with MutexLocker(self.lock):
            return self.scopeState['pixelSize']
        
    #@ftrace
    def getObjective(self):
        with MutexLocker(self.lock):
            return self.scopeState['objective']

    def getScopeDevice(self):
        with MutexLocker(self.lock):
            return self.scopeDev
            
    def getBoundary(self, obj=None):
        """Return the boundaries of the camera in coordinates relative to the scope center.
        If obj is specified, then the boundary is computed for that objective."""
        if obj is None:
            obj = self.scopeDev.getObjective()
        if obj is None:
            return None
        
        with MutexLocker(self.lock):
            sf = self.camConfig['scaleFactor']
            size = self.cam.getParam('sensorSize')
            sx = size[0] * obj['scale'] * sf[0]
            sy = size[1] * obj['scale'] * sf[1]
            bounds = QtCore.QRectF(-sx * 0.5 + obj['offset'][0], -sy * 0.5 + obj['offset'][1], sx, sy)
            return bounds
        
    def getBoundaries(self):
        """Return a list of camera boundaries for all objectives"""
        objs = self.scopeDev.listObjectives(allObjs=False)
        return [self.getBoundary(objs[o]) for o in objs]
        
    def getScopeState(self):
        """Return meta information to be included with each frame. This function must be FAST."""
        with MutexLocker(self.lock):
            return self.scopeState
        
    def positionChanged(self, pos=None):
        if pos is None:
            pos = self.scopeDev.getPosition()
        else:
            pos = pos['abs']
        with MutexLocker(self.lock):
            self.scopeState['scopePosition'] = pos
            offset = self.scopeState['offset']
            self.scopeState['centerPosition'] = [pos[0] + offset[0], pos[1] + offset[1]]
            self.scopeState['id'] += 1
        #print self.scopeState
        
    def objectiveChanged(self, obj=None):
        if obj is None:
            obj = self.scopeDev.getObjective()
        else:
            obj = obj[0]
        with MutexLocker(self.lock):
            scale = obj['scale']
            offset = obj['offset']
            pos = self.scopeState['scopePosition']
            self.scopeState['objective'] = obj['name']
            self.scopeState['objScale'] = scale
            self.scopeState['offset'] = offset
            self.scopeState['centerPosition'] = [pos[0] + offset[0], pos[1] + offset[1]]
            sf = self.camConfig['scaleFactor']
            self.scopeState['scale'] = [sf[0] * scale, sf[1] * scale]
            self.scopeState['pixelSize'] = filter(abs, self.scopeState['scale'])
            self.scopeState['id'] += 1
        #print self.scopeState
        
    def getCamera(self):
        return self.cam
        
        
    ### Proxy signals and functions for acqThread:
    ###############################################
    
    def acqThreadFinished(self):
        self.emit(QtCore.SIGNAL('cameraStopped'))

    def acqThreadStarted(self):
        self.emit(QtCore.SIGNAL('cameraStarted'))

    def showMessage(self, *args):
        self.emit(QtCore.SIGNAL('showMessage'), *args)

    def newFrame(self, *args):
        self.emit(QtCore.SIGNAL('newFrame'), *args)
        
    def isRunning(self):
        return self.acqThread.isRunning()
    
    def wait(self, *args, **kargs):
        return self.acqThread.wait(*args, **kargs)

class CameraTask(DAQGenericTask):
    """Default implementation of camera protocol task.
    Some of these functions may need to be reimplemented for subclasses."""


    def __init__(self, dev, cmd):
        print "Camera task:", cmd
        daqCmd = {}
        if 'channels' in cmd:
            daqCmd = cmd['channels']
        DAQGenericTask.__init__(self, dev, daqCmd)
        
        self.camCmd = cmd
        self.lock = Mutex()
        self.recordHandle = None
        self.stopAfter = False
        self.stoppedCam = False
        self.returnState = {}
        self.frames = []
        self.recording = False
        self.stopRecording = False
        
        
    def configure(self, tasks, startOrder):
        ## Merge command into default values:
        print "CameraTask.configure"
        params = {
            'triggerMode': 'Normal',
            #'recordExposeChannel': False
        }
        
        print "pushState..."
        if 'pushState' in self.camCmd:
            stateName = self.camCmd['pushState']
            self.dev.pushState(stateName)
        time.sleep(0.5)
        
        nonCameraParams = ['channels', 'record', 'triggerProtocol', 'pushState', 'popState']
        for k in self.camCmd:
            if k not in nonCameraParams:
                params[k] = self.camCmd[k]
        #for k in defaults:
            #if k not in self.camCmd:
                #self.camCmd[k] = defaults[k]
        
        
        ## Determine whether to restart acquisition after protocol
        #self.stopAfter = (not self.dev.isRunning())

        ## are we requesting any parameter changes?
        #paramSet = False
        #for k in ['binning', 'exposure', 'region', 'params']:
            #if k in self.camCmd:
                #paramSet = True
                
        ## if the camera is being triggered by the daq or if there are parameters to be set, stop it now
        #if self.camCmd['triggerMode'] != 'No Trigger' or paramSet:
            #self.dev.stopAcquire(block=True)  

        ## If we are sending a one-time trigger to start the camera, then it must be restarted to arm the trigger        
        if self.camCmd['triggerMode'] == 'TriggerStart':
            restart = True
            
        #print params
        (newParams, restart) = self.dev.setParams(params, autoCorrect=True)
        
        ## If the camera is triggering the daq, stop acquisition now and request that it starts after the DAQ
        ##   (daq must be started first so that it is armed to received the camera trigger)
        name = self.dev.devName()
        if self.camCmd['triggerProtocol']:
            restart = True
            daqName = self.dev.camConfig['triggerOutChannel'][0]
            startOrder.remove(name)
            startOrder.insert(startOrder.index(daqName)+1, name)
        
        ## If we are not triggering the daq, request that we start before everyone else
        ## (no need to stop, we will simply record frames as they are collected)
        else:
            startOrder.remove(name)
            startOrder.insert(0, name)
            
        #if 'forceStop' in self.camCmd and self.camCmd['forceStop'] is True:
            #restart = True
            
            
        ## We want to avoid this if at all possible since it may be very expensive
        print "CameraTask: configure: restart camera:", restart
        if restart:
            self.dev.stop(block=False)  ## don't wait for the camera to stop; we'll check again later.
            self.stoppedCam = True
            
        ## connect using acqThread's connect method because there may be no event loop
        ## to deliver signals here.
        self.dev.acqThread.connect(self.newFrame)
        
        ## Call the DAQ configure
        DAQGenericTask.configure(self, tasks, startOrder)
            
    def newFrame(self, frame):
        disconnect = False
        with MutexLocker(self.lock):
            if self.recording:
                #print "New frame"
                #if self.stopRecording:
                    #print "Adding in last frame %d" % len(self.frames)
                self.frames.append(frame)
            if self.stopRecording:
                self.recording = False
                disconnect = True
        if disconnect:   ## Must be done only after unlocking mutex
            self.dev.acqThread.disconnect(self.newFrame)

        
    def start(self):
        ## arm recording
        self.frames = []
        self.stopRecording = False
        self.recording = True
        
        #print "CameraTask start"
        #time.sleep(0.5)
        #self.recordHandle = CameraTask(self.dev.acqThread)  #self.dev.acqThread.startRecord()
        ## start acquisition if needed
        #print "Camera start:", self.camCmd
        
        ## all extra parameters should be passed on to the camera..
        #camState = {'mode': self.camCmd['triggerMode']}
        #for k in ['binning', 'exposure', 'region']:
            #if k in self.camCmd:
                #camState[k] = self.camCmd[k]
        
        ## set special camera parameters
        #if 'params' in self.camCmd:
            #params = self.camCmd['params']
            #self.returnState = {}
            #for k in params:
                #self.returnState[k] = self.dev.getParam(k)
            ##print "Set camera params:", params
            #self.dev.setParams(params)
            ##print "   set done"
                
        
        if self.stoppedCam:
            #print "  waiting for camera to stop.."
            self.dev.wait()
            
        if not self.dev.isRunning():
            #print "  Starting camera again..", camState
            #self.dev.setParams(camState)
            self.dev.start(block=True)  ## wait until camera is actually ready to acquire
        
            ### If we requested a trigger mode, wait 300ms for the camera to get ready for the trigger
            ###   (Is there a way to ask the camera when it is ready instead?)
            #if self.camCmd['triggerMode'] != 'Normal':
                #time.sleep(0.3)
                
            
        ## Last I checked, this does nothing. It should be here anyway, though..
        #print "  start daq task"
        DAQGenericTask.start(self)
        #time.sleep(0.5)
        
        #print "  done"
        
        
    def isDone(self):
        ## should return false if recording is required to run for a specific time.
        if 'minFrames' in self.camCmd:
            with MutexLocker(self.lock):
                if len(self.frames) < self.camCmd['minFrames']:
                    return False
        return DAQGenericTask.isDone(self)  ## Should return True.
        
    def stop(self):
        ## Stop DAQ first
        DAQGenericTask.stop(self)
        
        with MutexLocker(self.lock):
            self.stopRecording = True
        #if self.stopAfter:
            #self.dev.stopAcquire()
        
        if 'popState' in self.camCmd:
            self.dev.popState(self.camCmd['popState'])  ## restores previous settings, stops/restarts camera if needed
                
            
        
        ## If this task made any changes to the camera state, return them now
        #for k in self.returnState:
            #self.dev.setParam(k, self.returnState[k])
            
        #if not self.stopAfter and (not self.dev.isRunning() or self.camCmd['triggerMode'] != 'No Trigger'):
            #self.dev.startAcquire({'mode': 'No Trigger'})
                
    def getResult(self):
        #print "get result from camera task.."
        #expose = None
        ## generate MetaArray of expose channel if it was recorded
        #if ('recordExposeChannel' in self.camCmd) and self.camCmd['recordExposeChannel']:
            #expose = self.daqTask.getData(self.dev.camConfig['exposeChannel'][1])
            #timeVals = linspace(0, float(expose['info']['numPts']-1) / float(expose['info']['rate']), expose['info']['numPts'])
            #info = [axis(name='Time', values=timeVals), expose['info']]
            #expose = MetaArray(expose['data'], info=info)
        daqResult = DAQGenericTask.getResult(self)
            
        ## generate MetaArray of images collected during recording
        #data = self.recordHandle.data()
        with MutexLocker(self.lock):
            data = self.frames
            if len(data) > 0:
                arr = concatenate([f[0][newaxis,...] for f in data])
                times = array([f[1]['time'] for f in data])
                times -= times[0]
                info = [axis(name='Time', units='s', values=times), axis(name='x'), axis(name='y'), data[0][1]]
                #print info
                marr = MetaArray(arr, info=info)
                #print "returning frames:", marr.shape
            else:
                #print "returning no frames"
                marr = None
            
        expose = None
        if daqResult is not None and daqResult.hasColumn('Channel', 'exposure'):
            expose = daqResult['Channel':'exposure']
            
        ## Correct times for each frame based on data recorded from exposure channel.
        if expose is not None and marr is not None: 
        
            ## Extract times from trace
            ex = expose.view(ndarray)
            exd = ex[1:] - ex[:-1]
            
            timeVals = expose.xvals('Time')
            inds = argwhere(exd > 0)[:, 0] + 1
            onTimes = timeVals[inds]
            #print "onTimes:", onTimes
            inds = argwhere(exd < 0)[:, 0] + 1
            offTimes = timeVals[inds]
            
            ## Determine average frame transfer time
            txLen = (offTimes[:len(times)] - times[:len(offTimes)]).mean()
            
            ## Determine average exposure time (excluding first frame, which is often shorter)
            expLen = (offTimes[1:len(onTimes)] - onTimes[1:len(offTimes)]).mean()
            
            
            if self.camCmd['triggerMode'] == 'Normal':
                ## Can we make a good guess about frame times even without having triggered the first frame?
                ## frames are marked with their arrival time. We will assume that a frame most likely 
                ## corresponds to the last complete exposure signal. 
                pass
                
            else:
                ## If we triggered the camera, then we know frame 0 occurred at the same time as the first expose signal.
                ## New times list is onTimes, any extra frames just increment by tx+exp time
                vals = marr.xvals('Time')
                #print "Original times:", vals
                vals[:len(onTimes)] = onTimes[:len(vals)]
                lastTime = onTimes[-1]
                for i in range(len(onTimes), len(vals)):
                    lastTime += txLen+expLen
                    #print "Guessing time for frame %d: %f" % (i, lastTime)
                    vals[i] = lastTime 
            
        ## Generate final result, incorporating data from DAQ
        return {'frames': marr, 'channels': daqResult}
        
    def storeResult(self, dirHandle):
        result = self.getResult()
        dh = dirHandle.mkdir(self.dev.name)
        for k in result:
            if result[k] is not None:
                dh.writeFile(result[k], k)
        
class AcquireThread(QtCore.QThread):
    def __init__(self, dev):
        QtCore.QThread.__init__(self)
        self.dev = dev
        self.cam = self.dev.getCamera()
        #size = self.cam.getSize()
        #self.state = {'binning': 1, 'exposure': .001, 'region': [0, 0, size[0]-1, size[1]-1], 'mode': 'No Trigger'}
        #self.state = self.dev.getParams(['binning', 'exposure', 'region', 'triggerMode'])
        self.stopThread = False
        self.lock = Mutex()
        self.acqBuffer = None
        self.frameId = 0
        self.bufferTime = 5.0
        self.ringSize = 30
        self.tasks = []
        
        ## This thread does not run an event loop,
        ## so we may need to deliver frames manually to some places
        self.connections = []
        self.connectMutex = Mutex()
    
    def __del__(self):
        if hasattr(self, 'cam'):
            self.cam.stop()
    
    def start(self, *args):
        self.lock.lock()
        self.stopThread = False
        self.lock.unlock()
        QtCore.QThread.start(self, *args)
        
    
    def connect(self, method):
        with MutexLocker(self.connectMutex):
            self.connections.append(method)
    
    def disconnect(self, method):
        with MutexLocker(self.connectMutex):
            self.connections.remove(method)
    #
    #def setParam(self, param, value):
    #    #print "PVCam:setParam", param, value
    #    start = False
    #    if self.isRunning():
    #        start = True
    #        #print "Camera.setParam: Stopping camera before setting parameter.."
    #        self.stop(block=True)
    #        #print "Camera.setParam: camera stopped"
    #    with self.lock:
    #        self.state[param] = value
    #    if start:
    #        #self.start(QtCore.QThread.HighPriority)
    #        self.start()
    #    
    
    def run(self):
        #print "Starting up camera acquisition thread."
        #binning = self.state['binning']
        
        ## Make sure binning value is acceptable (stupid driver problem)
        #if 'allowedBinning' in self.dev.camConfig and binning not in self.dev.camConfig['allowedBinning']:
        #    ab = self.dev.camConfig['allowedBinning'][:]
        #    ab.sort()
        #    if binning < ab[0]:
        #        binning = ab[0]
        #    while binning not in ab:
        #        binning -= 1
        #    msg = "Requested binning %d not allowed, using %d instead" % (self.state['binning'], binning)
        #    print msg
        #    self.emit(QtCore.SIGNAL("showMessage"), msg)
        #print "Will use binning", binning
        #exposure = self.state['exposure']
        #region = self.state['region']
        #mode = self.state['mode']
        size = self.cam.getParam('sensorSize')
        lastFrame = None
        lastFrameTime = None
        
        camState = dict(self.cam.getParams(['binning', 'exposure', 'region', 'triggerMode']))
        binning = camState['binning']
        exposure = camState['exposure']
        region = camState['region']
        mode = camState['triggerMode']
        
        #print "AcquireThread.run: Lock for startup.."
        #print "AcquireThread.run: ..unlocked from startup"
        #self.fps = None
        
        try:
            #print self.ringSize, binning, exposure, region
            #print "  AcquireThread.run: start camera.."
            
            ## Attempt camera start. If the driver complains that it can not allocate memory, reduce the ring size until it works. (Ridiculous driver bug)
            printRingSize = False
            while True:
                try:
                    #print "Starting camera: ", self.ringSize, binning, exposure, region
                    #self.acqBuffer = self.cam.start(frames=self.ringSize, binning=binning, exposure=exposure, region=region, mode=mode)
                    self.cam.setParam('ringSize', self.ringSize)
                    self.acqBuffer = self.cam.start()
                    #print "Camera started."
                    break
                except Exception, e:
                    if len(e.args) == 2 and e.args[1] == 15:
                        printRingSize = True
                        self.ringSize = int(self.ringSize * 0.9)
                        if self.ringSize < 2:
                            raise Exception("Will not reduce camera ring size < 2")
                    else:
                        raise
            if printRingSize:
                print "Reduced camera ring size to %d" % self.ringSize
            
            #print "  AcquireThread.run: camera started."
            lastFrameTime = lastStopCheck = ptime.time() #time.clock()  # Use time.time() on Linux
            #times = [0] * 15
            frameInfo = {}
            scopeState = None
            while True:
                ti = 0
                #times[ti] = ptime.time(); ti += 1
                now = ptime.time()
                frame = self.cam.lastFrame()
                #times[ti] = ptime.time(); ti += 1  ## +40us
                ## If a new frame is available, process it and inform other threads
                if frame is not None and frame != lastFrame:
                    #print 'frame', frame
                    if lastFrame is not None:
                        diff = (frame - lastFrame) % self.ringSize
                        if diff > (self.ringSize / 2):
                            print "Image acquisition buffer is at least half full (possible dropped frames)"
                            #self.emit(QtCore.SIGNAL("showMessage"), "Acquisition thread dropped %d frame(s) after frame %d. (%02g since last frame arrived)" % (diff-1, self.frameId, now-lastFrameTime))
                    else:
                        lastFrame = frame-1
                        diff = 1
                        
                    #print type(diff), type(frame), type(lastFrame), type(self.ringSize)
                    ## Build meta-info for this frame(s)
                    info = camState.copy()
                    
                    ## frameInfo includes pixelSize, objective, centerPosition, scopePosition, imagePosition
                    ss = self.dev.getScopeState()
                    #print ss
                    if ss['id'] != scopeState:
                        #print "scope state changed"
                        scopeState = ss['id']
                        ## regenerate frameInfo here
                        ps = ss['pixelSize']  ## size of CCD pixel
                        pos = ss['centerPosition']
                        pos2 = [pos[0] - size[0]*ps[0]*0.5 + region[0]*ps[0], pos[1] - size[1]*ps[1]*0.5 + region[1]*ps[1]]
                        
                        frameInfo = {
                            'pixelSize': [ps[0] * binning[0], ps[1] * binning[1]],  ## size of image pixel
                            'scopePosition': ss['scopePosition'],
                            'centerPosition': pos,
                            'objective': ss['objective'],
                            'imagePosition': pos2
                        }
                    ## Copy frame info to info array
                    for k in frameInfo:
                        info[k] = frameInfo[k]
                    
                    
                    
                    ## Process all waiting frames. If there is more than one frame waiting, guess the frame times.
                    dt = (now - lastFrameTime) / diff
                    for i in range(diff):
                        fInd = (i+lastFrame+1) % self.ringSize
                        
                        frameInfo = info.copy()
                        frameInfo['time'] = lastFrameTime + (dt * (i+1))
                        frameInfo['id'] = self.frameId
                        
                        ## Inform that new frame is ready
                        outFrame = (self.acqBuffer[fInd].copy(), frameInfo)
                        
                        with MutexLocker(self.connectMutex):
                            conn = self.connections[:]
                        for c in conn:
                            c(outFrame)
                        #print "new frame", frameInfo['time']
                        self.emit(QtCore.SIGNAL("newFrame"), outFrame)
                        #print "emit frame", self.frameId
                        
                        self.frameId += 1
                            
                    lastFrame = frame
                    lastFrameTime = now
                    
                    
                    ### mandatory sleep until 1ms before next expected frame
                    ### Otherwise the CPU is constantly tied up waiting for new frames.
                    #sleepTime = (now + exposure - 1e-3) - ptime.time()
                    #if sleepTime > 0:
                        ##print "Sleep %f sec"% sleepTime
                        #time.sleep(sleepTime)
                        
                    loopCount = 0
                    #times[ti] = ptime.time(); ti += 1
                #times[ti] = ptime.time(); ti += 1
                        
                time.sleep(100e-6)
                
                
                #now = ptime.time()
                ## check for stop request every 10ms
                if now - lastStopCheck > 10e-3: 
                    lastStopCheck = now
                    #print "stop check"
                    ## If no frame has arrived yet, do NOT allow the camera to stop (this can hang the driver)   << bug should be fixed in pvcam driver, not here.
                    diff = ptime.time()-lastFrameTime
                    if frame is not None or diff > 1:
                        #print "    AcquireThread.run: Locking thread to check for stop request"
                        self.lock.lock()
                        if self.stopThread:
                            #print "    AcquireThread.run: Unlocking thread for exit"
                            self.stopThread = False
                            self.lock.unlock()
                            #print "    AcquireThread.run: Camera acquisition thread stopping."
                            break
                        self.lock.unlock()
                        #print "    AcquireThread.run: Done with thread stop check"
                        
                        if diff > (10 + exposure):
                            if mode == 'Normal':
                                print "Camera acquisition thread has been waiting %02f sec but no new frames have arrived; shutting down." % diff
                                break
                            else:
                                pass  ## do not exit loop if there is a possibility we are waiting for a trigger
                                
                #times[ti] = ptime.time(); ti += 1 ## + 285us
                #print ",   ".join(['%03.2f' % ((times[i]-times[i-1]) * 1e6) for i in range(len(times)-1)])
                #times[-1] = ptime.time()
                
            #from debug import Profiler
            #prof = Profiler()
            self.cam.stop()
            #prof.mark('      camera stop:')
        except:
            try:
                self.cam.stop()
            except:
                pass
            printExc("Error starting camera acquisition:")
            self.emit(QtCore.SIGNAL("showMessage"), "ERROR starting acquisition (see console output)")
        finally:
            pass
            #print "Camera ACQ thread exited."
        
    def stop(self, block=False):
        print "AcquireThread.stop: Requesting thread stop, acquiring lock first.."
        with MutexLocker(self.lock):
            self.stopThread = True
        #print "AcquireThread.stop: got lock, requested stop."
        #print "AcquireThread.stop: Unlocked, waiting for thread exit (%s)" % block
        if block:
          if not self.wait(10000):
              raise Exception("Timed out waiting for thread exit!")
        print "AcquireThread.stop: thread exited"

    def reset(self):
        if self.isRunning():
            self.stop()
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
            #self.start(QtCore.QThread.HighPriority)
            self.start()

