# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.DAQGeneric import DAQGeneric, DAQGenericTask
from Mutex import Mutex
#from lib.devices.Device import *
from lib.devices.Microscope import Microscope
from PyQt4 import QtCore
import time
from numpy import *
from metaarray import *
from protoGUI import *
from deviceGUI import *
import ptime as ptime
from Mutex import Mutex, MutexLocker
from debug import *

class Camera(DAQGeneric):
    """Generic camera device class. All cameras should extend from this interface.
     - The class handles protocol tasks, scope integration, expose/trigger lines
     - Subclasses should handle the connection to the camera driver by overriding
        listParams, getParams, and setParams.
     - Subclasses may need to create their own AcquireThread

    The list/get/setParams functions should implement a few standard items:
    (Note: these number values are just examples, but the data types and strings must be the same.)
        triggerMode:     str, ['Normal', 'TriggerStart', 'Strobe', 'Bulb']
        exposure:        float, (0.0, 10.0)
        binning:         (int,int) , [[1,2,4,8,16], [1,2,4,8,16]]
        region:          (int, int, int, int), [(0, 511), (0, 511), (1, 512), (1, 512)] #[x, y, w, h]
        gain:            float, (0.1, 10.0)

    The configuration for these devices should look like:
    (Note that each subclass will add config options for identifying the camera)
        scopeDevice: 'Microscope'
        scaleFactor: (1.0, 1.0)  ## used for rectangular pixels
        exposeChannel: 'DAQ', '/Dev1/port0/line14'  ## Channel for recording expose signal
        triggerOutChannel: 'DAQ', '/Dev1/PFI5'  ## Channel the DAQ should trigger off of to sync with camera
        triggerInChannel: 'DAQ', '/Dev1/port0/line13'  ## Channel the DAQ should raise to trigger the camera
        params:
            GAIN_INDEX: 2
            CLEAR_MODE: 'CLEAR_PRE_SEQUENCE'  ## Overlap mode for QuantEM
    """

    sigCameraStopped = QtCore.Signal()
    sigCameraStarted = QtCore.Signal()
    sigShowMessage = QtCore.Signal(object)  # (string message)
    sigNewFrame = QtCore.Signal(object)  # (frame data)
    sigParamsChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):
        self.lock = Mutex(Mutex.Recursive)
        
        
        # Generate config to use for DAQ 
        daqConfig = {}
        if 'exposeChannel' in config:
            daqConfig['exposure'] = config['exposeChannel']
        if 'triggerInChannel' in config:
            daqConfig['trigger'] = config['triggerInChannel']
        DAQGeneric.__init__(self, dm, daqConfig, name)
        
        self.camConfig = config
        self.stateStack = []
        
        
        if 'scaleFactor' not in self.camConfig:
            self.camConfig['scaleFactor'] = [1., 1.]
        
        ## Default values for scope state. These will be used if there is no scope defined.
        self.scopeState = {
            'id': 0,
            #'scopePosition': [0, 0],   ## position of scope in global coords
            #'centerPosition': [0, 0],  ## position of objective in global coords (objective may be offset from center of scope)
            #'offset': [0, 0],
            #'objScale': 1,
            'pixelSize': (1, 1),
            'objective': '',
            'transform': None,
        }
        

        self.scopeDev = None
        p = self
        while p is not None:
            p = p.parentDevice()
            if isinstance(p, Microscope):
                self.scopeDev = p
                self.scopeDev.sigObjectiveChanged.connect(self.objectiveChanged)
                break
        
        #if 'scopeDevice' in config:
            #self.scopeDev = self.dm.getDevice(config['scopeDevice'])
            #self.scopeDev.sigPositionChanged.connect(self.positionChanged)
            ### Cache microscope state for fast access later
            #self.objectiveChanged()
            #self.positionChanged()
        #else:
            #self.scopeDev = None
        
        
        self.setupCamera() 
        #print "Camera: setupCamera returned, about to create acqThread"
        self.sensorSize = self.getParam('sensorSize')
        
        self.acqThread = AcquireThread(self)
        #print "Camera: acqThread created, about to connect signals."
        self.acqThread.finished.connect(self.acqThreadFinished)
        self.acqThread.started.connect(self.acqThreadStarted)
        self.acqThread.sigShowMessage.connect(self.showMessage)
        self.acqThread.sigNewFrame.connect(self.newFrame)
        #print "Camera: signals connected:"
        
        if config != None and 'params' in config:
            #print "Camera: setting configuration params."
            try:
                self.setParams(config['params'])
            except:
                printExc("Error default setting camera parameters:")
        #print "Camera: no config params to set."
        dm.declareInterface(name, ['camera'], self)
    
    def setupCamera(self):
        """Prepare the camera at least so that get/setParams will function correctly"""
        raise Exception("Function must be reimplemented in subclass.")
    
    def listParams(self, params=None):
        """Return a dictionary of parameter descriptions. By default, all parameters are listed.
        Each description is a tuple or list: (values, isWritable, isReadable, dependencies)
        
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
           params: a list or dict of (param, value) pairs to be set. Parameters are set in the order specified.
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
        
    def newFrames(self):
        """Returns a list of all new frames that have arrived since the last call. The list looks like:
            [{'id': 0, 'data': array, 'time': 1234678.3213}, ...]
        id is a unique integer representing the frame number since the start of the program.
        data should be a permanent copy of the image (ie, not directly from a circular buffer)
        time is the time of arrival of the frame. Optionally, 'exposeStartTime' and 'exposeDoneTime' 
            may be specified if they are available.
        """
        raise Exception("Function must be reimplemented in subclass.")
        
    def startCamera(self):
        """Calls the camera driver to start the camera's acquisition."""
        raise Exception("Function must be reimplemented in subclass.")
        
    def stopCamera(self):
        """Calls the camera driver to stop the camera's acquisition.
        Note that the acquisition may be _required_ to stop, since other processes
        may be preparing to synchronize with the camera's exposure signal."""
        raise Exception("Function must be reimplemented in subclass.")

    
    
    def pushState(self, name=None):
        #print "Camera: pushState", name
        params = self.listParams()
        for k in params.keys():    ## remove non-writable parameters
            if not params[k][1]:
                del params[k]
        params = self.getParams(params.keys())
        params['isRunning'] = self.isRunning()
        #print "Camera: pushState", name, params
        self.stateStack.append((name, params))
        
    def popState(self, name=None):
        #print "Camera: popState", name
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
        #print "Camera: popState", name, state
        nv, restart = self.setParams(state, autoRestart=False)
        #print "    run:", run, "isRunning:", self.isRunning(), "restart:", restart
        
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
        """Start camera and acquisition thread"""
        #print "Camera: start"
        #sys.stdout.flush()
        #time.sleep(0.1)
        self.acqThread.start()
        
    def stop(self, block=True):
        """Stop camera and acquisition thread"""
        #print "Camera: stop"
        #sys.stdout.flush()
        #time.sleep(0.1)
        self.acqThread.stop(block=block)
        
    def restart(self):
        if self.isRunning():
            self.stop()
            self.start()
    
    def quit(self):
        #print "quit() called from Camera"
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
            if self.camConfig['triggerOutChannel']['device'] != daq:
                return None
            return self.camConfig['triggerOutChannel']['channel']
        


    def protocolInterface(self, prot):
        return CameraProtoGui(self, prot)

    def deviceInterface(self, win):
        return CameraDeviceGui(self, win)
    
    ### Scope interface functions below

    #def getPosition(self, justScope=False):
        #"""Return the coordinate of the center of the sensor area
        #If justScope is True, return the scope position, uncorrected for the objective offset"""
        #with MutexLocker(self.lock):
            #if justScope:
                #return self.scopeState['scopePosition']
            #else:
                #return self.scopeState['centerPosition']

    #@ftrace
    #def getScale(self):
        #"""Return the dimensions of 1 pixel with signs if the image is flipped"""
        #with MutexLocker(self.lock):
            #return self.scopeState['scale']
        
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
            size = self.getParam('sensorSize')
            sx = size[0] * obj['scale'] * sf[0]
            sy = size[1] * obj['scale'] * sf[1]
            bounds = QtCore.QRectF(-sx * 0.5 + obj['offset'][0], -sy * 0.5 + obj['offset'][1], sx, sy)
            return bounds
        
    def getBoundaries(self):
        """Return a list of camera boundaries for all objectives"""
        objs = self.scopeDev.listObjectives(allObjs=False)
        return [self.getBoundary(objs[o]) for o in objs]
    
    def mapToSensor(self, pos):
        """Return the sub-pixel location on the sensor that corresponds to global position pos"""
        ss = self.getScopeState()
        boundary = self.getBoundary()
        boundary.translate(*ss['scopePosition'][:2])
        size = self.sensorSize
        x = (pos[0] - boundary.left()) * (float(size[0]) / boundary.width())
        y = (pos[1] - boundary.top()) * (float(size[1]) / boundary.height())
        return (x, y)
        
        
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
        
    #def getCamera(self):
        #return self.cam
        
        
    ### Proxy signals and functions for acqThread:
    ###############################################
    
    def acqThreadFinished(self):
        #self.emit(QtCore.SIGNAL('cameraStopped'))
        self.sigCameraStopped.emit()

    def acqThreadStarted(self):
        #self.emit(QtCore.SIGNAL('cameraStarted'))
        self.sigCameraStarted.emit()

    def showMessage(self, msg):
        #self.emit(QtCore.SIGNAL('showMessage'), msg)
        self.sigShowMessage.emit(msg)

    def newFrame(self, data):
        #self.emit(QtCore.SIGNAL('newFrame'), *args)
        self.sigNewFrame.emit(data)
        
    def isRunning(self):
        return self.acqThread.isRunning()

    #def isRunning(self):
        #with MutexLocker(self.lock):
            #return self.acqThread.isRunning()
    
    def wait(self, *args, **kargs):
        return self.acqThread.wait(*args, **kargs)

        
class Frame(object):
    def __init__(self, data, info):
        object.__init__(self)
        self._data = data
        self._info = info
        
    def data(self):
        return self._data
    
    def info(self):
        return self._info
        
    def mapFromFrameToScope(obj):
        """
        Map from the frame's data coordinates to scope coordinates
        """
        pass
    
    
    def mapFromFrameToGlobal(obj):
        """
        Map from the frame's data coordinates to global coordinates
        """
        pass
    
    
    def mapFromFrameToSensor(obj):
        """
        Map from the frame's data coordinates to the camera's sensor coordinates
        """
        pass
    
    
        
class CameraTask(DAQGenericTask):
    """Default implementation of camera protocol task.
    Some of these functions may need to be reimplemented for subclasses."""


    def __init__(self, dev, cmd):
        #print "Camera task:", cmd
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
        prof = Profiler('Camera.CameraTask.configure', disabled=True)
        #print "CameraTask.configure"
        
        ## set default parameters, load params from command
        params = {
            'triggerMode': 'Normal',
            #'recordExposeChannel': False
        }
        params.update(self.camCmd['params'])
        
        #print "pushState..."
        if 'pushState' in self.camCmd:
            stateName = self.camCmd['pushState']
            self.dev.pushState(stateName)
        #time.sleep(0.5)
        
        #nonCameraParams = ['channels', 'record', 'triggerProtocol', 'pushState', 'popState', 'minFrames']
        #for k in self.camCmd:
            #if k not in nonCameraParams:
                #params[k] = self.camCmd[k]
        #for k in defaults:
            #if k not in self.camCmd:
                #self.camCmd[k] = defaults[k]
        
        prof.mark('collect params')
                
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
        if params['triggerMode'] == 'TriggerStart':
            restart = True
            
        #print params
        #print "Camera.configure: setParams"
        (newParams, restart) = self.dev.setParams(params, autoCorrect=True, autoRestart=False)  ## we'll restart in a moment if needed..
        #print "restart:", restart
        
        prof.mark('set params')
        ## If the camera is triggering the daq, stop acquisition now and request that it starts after the DAQ
        ##   (daq must be started first so that it is armed to received the camera trigger)
        name = self.dev.devName()
        if self.camCmd.get('triggerProtocol', False):
            #print "Camera triggering protocol; restart needed"
            restart = True
            daqName = self.dev.camConfig['triggerOutChannel']['device']
            startOrder.remove(name)
            startOrder.insert(startOrder.index(daqName)+1, name)
            prof.mark('conf 1')
        
        ## If we are not triggering the daq, request that we start before everyone else
        ## (no need to stop, we will simply record frames as they are collected)
        else:
            startOrder.remove(name)
            startOrder.insert(0, name)
            prof.mark('conf 2')
            
            
        #if 'forceStop' in self.camCmd and self.camCmd['forceStop'] is True:
            #restart = True
            
            
        ## We want to avoid this if at all possible since it may be very expensive
        #print "CameraTask: configure: restart camera:", restart
        if restart:
            self.dev.stop(block=True)
            #self.stoppedCam = True
        prof.mark('stop')
            
        ## connect using acqThread's connect method because there may be no event loop
        ## to deliver signals here.
        self.dev.acqThread.connectCallback(self.newFrame)
        
        ## Call the DAQ configure
        DAQGenericTask.configure(self, tasks, startOrder)
        prof.mark('DAQ configure')
        prof.finish()
            
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
            self.dev.acqThread.disconnectCallback(self.newFrame)

        
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
                
        
        #if self.stoppedCam:
            #print "  CameraTask start: waiting for camera to stop.."
            #self.dev.wait()
            
        if not self.dev.isRunning():
            #print "  CameraTask start: Starting camera.."
            #self.dev.setParams(camState)
            self.dev.start(block=True)  ## wait until camera is actually ready to acquire
                
            
        ## Last I checked, this does nothing. It should be here anyway, though..
        #print "  start daq task"
        DAQGenericTask.start(self)
        #time.sleep(0.5)
        
        #print "  done"
        
        
    def isDone(self):
        ## If camera stopped, then probably there was a problem and we are finished.
        if not self.dev.isRunning():
            return True    
        
        ## should return false if recording is required to run for a specific time.
        if 'minFrames' in self.camCmd:
            with MutexLocker(self.lock):
                if len(self.frames) < self.camCmd['minFrames']:
                    return False
        return DAQGenericTask.isDone(self)  ## Should return True.
        
    def stop(self, abort=False):
        ## Stop DAQ first
        #print "Stop camera task"
        DAQGenericTask.stop(self)
        
        with MutexLocker(self.lock):
            self.stopRecording = True
        #if self.stopAfter:
            #self.dev.stopAcquire()
        
        if 'popState' in self.camCmd:
            #print "  pop state"
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
        times = None
        with MutexLocker(self.lock):
            data = self.frames
            if len(data) > 0:
                arr = concatenate([f.data()[newaxis,...] for f in data])
                try:
                    times = array([f.info()['time'] for f in data])
                except:
                    print f
                    raise
                times -= times[0]
                info = [axis(name='Time', units='s', values=times), axis(name='x'), axis(name='y'), data[0].info()]
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
            ex = expose.view(ndarray).astype(int32)
            exd = ex[1:] - ex[:-1]

            
            timeVals = expose.xvals('Time')
            inds = argwhere(exd > 0.5)[:, 0] + 1
            onTimes = timeVals[inds]
            
            ## If camera triggered DAQ, then it is likely we missed the first 0->1 transition
            if self.camCmd.get('triggerProtocol', False) and ex[0] > 0.5:
                onTimes = array([timeVals[0]] + list(onTimes))
            
            #print "onTimes:", onTimes
            inds = argwhere(exd < 0.5)[:, 0] + 1
            offTimes = timeVals[inds]
            
            ## Determine average frame transfer time
            txLen = (offTimes[:len(times)] - times[:len(offTimes)]).mean()
            
            ## Determine average exposure time (excluding first frame, which is often shorter)
            expLen = (offTimes[1:len(onTimes)] - onTimes[1:len(offTimes)]).mean()
            
            
            if self.camCmd['params']['triggerMode'] == 'Normal' and not self.camCmd.get('triggerProtocol', False):
                ## Can we make a good guess about frame times even without having triggered the first frame?
                ## frames are marked with their arrival time. We will assume that a frame most likely 
                ## corresponds to the last complete exposure signal. 
                pass
                
            elif len(onTimes) > 0:
                ## If we triggered the camera (or if the camera triggered the DAQ), 
                ## then we know frame 0 occurred at the same time as the first expose signal.
                ## New times list is onTimes, any extra frames just increment by tx+exp time
                vals = marr.xvals('Time')
                #print "Original times:", vals
                vals[:len(onTimes)] = onTimes[:len(vals)]
                lastTime = onTimes[-1]
                if len(onTimes) > 1:
                    framePeriod = (onTimes[-1] - onTimes[0]) / (len(onTimes) - 1)
                elif times is not None:
                    framePeriod = (times[-1] - times[0]) / (len(times) - 1)
                else:
                    framePeriod = None
                    
                if framePeriod is not None:
                    for i in range(len(onTimes), len(vals)):
                        lastTime += framePeriod
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
    
    sigNewFrame = QtCore.Signal(object)
    sigShowMessage = QtCore.Signal(object)
    
    def __init__(self, dev):
        QtCore.QThread.__init__(self)
        self.dev = dev
        #self.cam = self.dev.getCamera()
        self.camLock = self.dev.camLock
        #size = self.cam.getSize()
        #self.state = {'binning': 1, 'exposure': .001, 'region': [0, 0, size[0]-1, size[1]-1], 'mode': 'No Trigger'}
        #self.state = self.dev.getParams(['binning', 'exposure', 'region', 'triggerMode'])
        self.stopThread = False
        self.lock = Mutex()
        self.acqBuffer = None
        #self.frameId = 0
        self.bufferTime = 5.0
        #self.ringSize = 30
        self.tasks = []
        
        ## This thread does not run an event loop,
        ## so we may need to deliver frames manually to some places
        self.connections = set()
        self.connectMutex = Mutex()
    
    def __del__(self):
        if hasattr(self, 'cam'):
            #self.cam.stop()
            self.dev.stopCamera()
    
    def start(self, *args):
        self.lock.lock()
        self.stopThread = False
        self.lock.unlock()
        QtCore.QThread.start(self, *args)
        
    
    def connectCallback(self, method):
        with MutexLocker(self.connectMutex):
            self.connections.add(method)
    
    def disconnectCallback(self, method):
        with MutexLocker(self.connectMutex):
            if method in self.connections:
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
        size = self.dev.getParam('sensorSize')
        lastFrame = None
        lastFrameTime = None
        lastFrameId = None
        fps = None
        
        camState = dict(self.dev.getParams(['binning', 'exposure', 'region', 'triggerMode']))
        binning = camState['binning']
        exposure = camState['exposure']
        region = camState['region']
        mode = camState['triggerMode']
        
        try:
            #self.dev.setParam('ringSize', self.ringSize, autoRestart=False)
            self.dev.startCamera()
            
            lastFrameTime = lastStopCheck = ptime.time()
            frameInfo = {}
            scopeState = None
            while True:
                ti = 0
                now = ptime.time()
                frames = self.dev.newFrames()
                
                #with self.camLock:
                    #frame = self.cam.lastFrame()
                ## If a new frame is available, process it and inform other threads
                if len(frames) > 0:
                    if lastFrameId is not None:
                        drop = frames[0]['id'] - lastFrameId - 1
                        if drop > 0:
                            print "WARNING: Camera dropped %d frames" % drop
                        
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
                        #pos = ss['centerPosition']
                        #pos2 = [pos[0] - size[0]*ps[0]*0.5 + region[0]*ps[0], pos[1] - size[1]*ps[1]*0.5 + region[1]*ps[1]]
                        
                        transform = pg.Transform(ss['transform'])
                        transform.scale(*ps)
                        transform.translate(0,0)  ## correct for ROI here
                        
                        frameInfo = {
                            'pixelSize': [ps[0] * binning[0], ps[1] * binning[1]],  ## size of image pixel
                            #'scopePosition': ss['scopePosition'],
                            #'centerPosition': pos,
                            'objective': ss['objective'],
                            #'imagePosition': pos2
                            'cameraTransform': ss['transform'],
                            'transform': transform,
                        }
                        
                    ## Copy frame info to info array
                    info.update(frameInfo)
                    #for k in frameInfo:
                        #info[k] = frameInfo[k]
                    
                    ## Process all waiting frames. If there is more than one frame waiting, guess the frame times.
                    dt = (now - lastFrameTime) / len(frames)
                    if dt > 0:
                        info['fps'] = 1.0/dt
                    else:
                        info['fps'] = None
                    
                    for frame in frames:
                        frameInfo = info.copy()
                        data = frame['data']
                        #print data
                        del frame['data']
                        frameInfo.update(frame)
                        out = Frame(data, frameInfo)
                        with MutexLocker(self.connectMutex):
                            conn = list(self.connections)
                        for c in conn:
                            c(out)
                        #self.emit(QtCore.SIGNAL("newFrame"), out)
                        self.sigNewFrame.emit(out)
                        
                    lastFrameTime = now
                    lastFrameId = frames[-1]['id']
                    loopCount = 0
                        
                time.sleep(100e-6)
                
                ## check for stop request every 10ms
                if now - lastStopCheck > 10e-3: 
                    lastStopCheck = now
                    
                    ## If no frame has arrived yet, do NOT allow the camera to stop (this can hang the driver)   << bug should be fixed in pvcam driver, not here.
                    self.lock.lock()
                    if self.stopThread:
                        self.stopThread = False
                        self.lock.unlock()
                        break
                    self.lock.unlock()
                    
                    diff = ptime.time()-lastFrameTime
                    if diff > (10 + exposure):
                        if mode == 'Normal':
                            print "Camera acquisition thread has been waiting %02f sec but no new frames have arrived; shutting down." % diff
                            break
                        else:
                            pass  ## do not exit loop if there is a possibility we are waiting for a trigger
                                
                
            #from debug import Profiler
            #prof = Profiler()
            with self.camLock:
                #self.cam.stop()
                self.dev.stopCamera()
            #prof.mark('      camera stop:')
        except:
            try:
                with self.camLock:
                    #self.cam.stop()
                    self.dev.stopCamera()
            except:
                pass
            printExc("Error starting camera acquisition:")
            #self.emit(QtCore.SIGNAL("showMessage"), "ERROR starting acquisition (see console output)")
            self.sigShowMessage.emit("ERROR starting acquisition (see console output)")
        finally:
            pass
            #print "Camera ACQ thread exited."
        
    def stop(self, block=False):
        #print "AcquireThread.stop: Requesting thread stop, acquiring lock first.."
        with MutexLocker(self.lock):
            self.stopThread = True
        #print "AcquireThread.stop: got lock, requested stop."
        #print "AcquireThread.stop: Unlocked, waiting for thread exit (%s)" % block
        if block:
            if not self.wait(10000):
                raise Exception("Timed out waiting for thread exit!")
        #print "AcquireThread.stop: thread exited"

    def reset(self):
        if self.isRunning():
            self.stop()
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
            #self.start(QtCore.QThread.HighPriority)
            self.start()

