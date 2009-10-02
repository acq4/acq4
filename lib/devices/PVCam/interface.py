# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.drivers.pvcam import PVCam as PVCDriver
from lib.devices.Device import *
from PyQt4 import QtCore
import time, sys, traceback
from numpy import *
from lib.util.MetaArray import *
from protoGUI import *
from deviceGUI import *
import lib.util.ptime as ptime
from lib.util.Mutex import Mutex, MutexLocker

def ftrace(func):
    def w(*args, **kargs):
        print "PVCam:" + func.__name__ + " start"
        rv = func(*args, **kargs)
        print "PVCam:" + func.__name__ + " done"
        return rv
    return w

class PVCam(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.camLock = Mutex(QtCore.QMutex.Recursive)
        self.pvc = PVCDriver
        self.cam = None
        self.acqThread = AcquireThread(self)
        #print "Created PVCam device. Cameras are:", self.pvc.listCameras()
        
        if 'scaleFactor' not in self.config:
            self.config['scaleFactor'] = [1, 1]
        
        ## Default values for scope state. These will be used if there is no scope defined.
        self.scopeState = {'id': 0, 'scale': self.config['scaleFactor'], 'scopePosition': [0, 0], 'centerPosition': [0, 0], 'offset': [0, 0], 'objScale': 1, 'pixelSize': filter(abs, self.config['scaleFactor'])}
        
        if 'params' in config:
            self.getCamera().setParams(config['params'])
            
        if 'exposeChannel' in config:
            ## create input channel in DAQGeneric
            pass
        if 'triggerInChannel' in config:
            ## create output channel in DAQGeneric
            pass
        
        if 'scopeDevice' in config:
            self.scopeDev = self.dm.getDevice(config['scopeDevice'])
            QtCore.QObject.connect(self.scopeDev, QtCore.SIGNAL('positionChanged'), self.positionChanged)
            QtCore.QObject.connect(self.scopeDev, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
            ## Cache microscope state for fast access later
            self.objectiveChanged()
            self.positionChanged()
        else:
            self.scopeDev = None
            
    def reconnect(self):
        print "Stopping acquisition.."
        try:
            self.stopAcquire(block=True)
        except:
            pass
        print "Closing camera.."
        try:
            self.cam.cose()
        except:
            pass
        self.cam.open()
        print "Re-opened camera."
        

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
            sf = self.config['scaleFactor']
            self.scopeState['scale'] = [sf[0] * scale, sf[1] * scale]
            self.scopeState['pixelSize'] = filter(abs, self.scopeState['scale'])
            self.scopeState['id'] += 1
        #print self.scopeState
    
    def quit(self):
        if hasattr(self, 'acqThread') and self.acqThread.isRunning():
            self.stopAcquire()
            if not self.acqThread.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
        self.cam.close()
        #print "Camera device quit."
        
        
    #@ftrace
    def devName(self):
        with MutexLocker(self.lock):
            return self.name
    
    #@ftrace
    def getCamera(self):
        with MutexLocker(self.lock):
            with MutexLocker(self.camLock):
                if self.cam is None:
                    cams = self.pvc.listCameras()
                    print "Cameras:", cams
                    if len(cams) < 1:
                        raise Exception('No cameras found by pvcam driver')
                    
                    if self.config['serial'] is None:  ## Just pick first camera
                        ind = 0
                    else:
                        if self.config['serial'] in cams:
                            ind = cams.index(self.config['serial'])
                        else:
                            raise Exception('Can not find pvcam camera "%s"' % str(self.config['serial']))
                    print "Selected camera:", cams[ind]
                    self.cam = self.pvc.getCamera(cams[ind])
                return self.cam
    
    #@ftrace
    def createTask(self, cmd):
        with MutexLocker(self.lock):
            return Task(self, cmd)
    
    #@ftrace
    def getTriggerChannel(self, daq):
        with MutexLocker(self.lock):
            if not 'triggerOutChannel' in self.config:
                return None
            if self.config['triggerOutChannel'][0] != daq:
                return None
            return self.config['triggerOutChannel'][1]
        
    def startAcquire(self, params=None):
        with MutexLocker(self.lock):
            at = self.acqThread
        
        if params is not None:
            for p in params:
                at.setParam(p, params[p])
        at.start()
        
    def stopAcquire(self, block=True):
        with MutexLocker(self.lock):
            at = self.acqThread
        
        at.stop(block)

    def isRunning(self):
        with MutexLocker(self.lock):
            return self.acqThread.isRunning()

    def protocolInterface(self, prot):
        return PVCamProto(self, prot)

    def deviceInterface(self):
        return PVCamDevGui(self)

    def setParam(self, param, val):
        with MutexLocker(self.lock):
            at = self.acqThread
        
        r = at.isRunning()
        if r: 
            at.stop(block=True)
            
        with MutexLocker(self.camLock):
            self.cam.setParam(param, val)
        
        self.emit(QtCore.SIGNAL('paramChanged'), param, val)
        if r: 
            at.start()
        
    def getParam(self, param):
        with MutexLocker(self.camLock):
            return self.cam.getParam(param)
        
    #@ftrace
    def listTriggerModes(self):
        with MutexLocker(self.camLock):
            return self.cam.listTriggerModes()
        
    #@ftrace
    def getPosition(self, justScope=False):
        """Return the coordinate of the center of the sensor area
        If justScope is True, return the scope position, uncorrected for the objective offset"""
        with MutexLocker(self.lock):
            if justScope:
                return self.scopeState['scopePosition']
            else:
                return self.scopeState['centerPosition']
            #if self.scopeDev is None:
                #return [0, 0]
            #else:
                #p = self.scopeDev.getPosition()
                #if not justScope:
                    #o = self.scopeDev.getObjective()
                    #off = o['offset']
                    #p = [p[0] + off[0], p[1] + off[1]]
                #return p

    #@ftrace
    def getScale(self):
        """Return the dimensions of 1 pixel with signs if the image is flipped"""
        with MutexLocker(self.lock):
            return self.scopeState['scale']
            #if 'scaleFactor' in self.config:
                #sf = self.config['scaleFactor']
            #else:
                #sf = [1, 1]
            #if self.scopeDev is None:
                #return sf
            #else:
                #obj = self.scopeDev.getObjective()
                #scale = obj['scale']
                #return (sf[0]*scale, sf[1]*scale)
        
    #@ftrace
    def getPixelSize(self):
        """Return the absolute size of 1 pixel"""
        with MutexLocker(self.lock):
            return self.scopeState['pixelSize']
        #s = self.getScale()
        #if s is None:
            #return None
        #return (abs(s[0]), abs(s[1]))
        
    #@ftrace
    def getObjective(self):
        with MutexLocker(self.lock):
            return self.scopeState['objective']
            #if self.scopeDev is None:
                #return None
            #else:
                #obj = self.scopeDev.getObjective()
                #return obj['name']

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
            sf = self.config['scaleFactor']
            size = self.cam.getSize()
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
        
        
        
        
        
       
        
        
        

class Task(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.lock = Mutex()
        self.recordHandle = None
        self.stopAfter = False
        self.returnState = {}
        self.frames = []
        self.recording = False
        self.stopRecording = False
        
        
    def configure(self, tasks, startOrder):
        ## Merge command into default values:
        defaults = {
            'record': True,
            'triggerProtocol': False,
            'triggerMode': 'Normal',
            'recordExposeChannel': False
        }
        for k in defaults:
            if k not in self.cmd:
                self.cmd[k] = defaults[k]
        
        ## Determine whether to restart acquisition after protocol
        self.stopAfter = (not self.dev.isRunning())
        
        ## if the camera is being triggered by the daq, stop it now
        if self.cmd['triggerMode'] != 'Normal':
            self.dev.stopAcquire(block=True)  
            
        ## If the camera is triggering the daq, stop acquisition now and request that it starts after the DAQ
        name = self.dev.devName()
        if self.cmd['triggerProtocol']:
            #print "Stopping camera before task start.."
            self.dev.stopAcquire(block=True)  
            #print "done"
            #print "running:", self.dev.acqThread.isRunning()
            daqName = self.dev.config['triggerOutChannel'][0]
            startOrder.remove(name)
            startOrder.insert(startOrder.index(daqName)+1, name)
        elif 'forceStop' in self.cmd and self.cmd['forceStop'] is True:
            self.dev.stopAcquire(block=True)  
            
            
        
        ## If we are not triggering the daq, request that we start before everyone else
        ## (no need to stop, we will simply record frames as they are collected)
        else:
            startOrder.remove(name)
            startOrder.insert(0, name)
            
        ## connect using acqThread's connect method because there may be no event loop
        ## to deliver signals here.
        self.dev.acqThread.connect(self.newFrame)
            
    def newFrame(self, frame):
        dis = False
        with MutexLocker(self.lock):
            if self.recording:
                self.frames.append(frame)
            if self.stopRecording:
                self.recording = False
                dis = True
        if dis:   ## Must be done only after unlocking mutex
            self.dev.acqThread.disconnect(self.newFrame)

    def createChannels(self, daqTask):
        ## Are we interested in recording the expose signal?
        if ('recordExposeChannel' not in self.cmd) or (not self.cmd['recordExposeChannel']):
            return
            
        ## Is this the correct DAQ device to record the expose signal? 
        if daqTask.devName() != self.dev.config['exposeChannel'][0]:
            return
        
        ## Then: create DI channel
        daqTask.addChannel(self.dev.config['exposeChannel'][1], 'di')
        
        self.daqTask = daqTask
        
    def start(self):
        ## arm recording
        self.frames = []
        self.stopRecording = False
        self.recording = True
        #self.recordHandle = CameraTask(self.dev.acqThread)  #self.dev.acqThread.startRecord()
        ## start acquisition if needed
        #print "stopAfter:", self.stopAfter
        
        #print "Camera start acquire: ", self.cmd['triggerMode']
        self.dev.startAcquire({'mode': self.cmd['triggerMode']})
        
        ## If we requested a trigger mode, wait 200ms for the camera to get ready for the trigger
        ##   (Is there a way to ask the camera when it is ready instead?)
        if self.cmd['triggerMode'] is not None:
            time.sleep(0.3)
        
    def isDone(self):
        ## should return false if recording is required to run for a specific time.
        if 'minFrames' in self.cmd:
            with MutexLocker(self.lock):
                if len(self.frames) < self.cmd['minFrames']:
                    return False
        return True
        
    def stop(self):
        #print "stop camera task"
        #self.recordHandle.stop()
        with MutexLocker(self.lock):
            self.stopRecording = True
        #print "stop camera task: done"
        #print "Stop camera acquisition"
        self.dev.stopAcquire()
        #print "done"
        
        ## If this task made any changes to the camera state, return them now
        for k in self.returnState:
            self.dev.setParam(k, self.returnState[k])
            
        if not self.stopAfter:
            #print "restart camera"
            self.dev.startAcquire({'mode': 'Normal'})
        #else:
            #print "no restaRT"
        #print "camera task stopped"
                
    def getResult(self):
        #print "get result from camera task.."
        expose = None
        ## generate MetaArray of expose channel if it was recorded
        if ('recordExposeChannel' in self.cmd) and self.cmd['recordExposeChannel']:
            expose = self.daqTask.getData(self.dev.config['exposeChannel'][1])
            timeVals = linspace(0, float(expose['info']['numPts']-1) / float(expose['info']['rate']), expose['info']['numPts'])
            info = [axis(name='Time', values=timeVals), expose['info']]
            expose = MetaArray(expose['data'], info=info)
            
        ## generate MetaArray of images collected during recording
        #data = self.recordHandle.data()
        with MutexLocker(self.lock):
            data = self.frames
            if len(data) > 0:
                arr = concatenate([f[0][newaxis,...] for f in data])
                times = array([f[1]['time'] for f in data])
                times -= times[0]
                info = [axis(name='Time', units='s', values=times), axis(name='x'), axis(name='y'), data[0][1]]
                marr = MetaArray(arr, info=info)
                #print "returning frames:", marr.shape
            else:
                #print "returning no frames"
                marr = None
            
        ## If exposure channel was recorded, update frame times to match.
        if expose is not None and marr is not None:
            ## Extract times from trace
            ex = expose.view(ndarray)
            exd = ex[1:] - ex[:-1]
            
            inds = argwhere(exd > 0)[:, 0] + 1
            onTimes = timeVals[inds]
            #print "onTimes:", onTimes
            inds = argwhere(exd < 0)[:, 0] + 1
            offTimes = timeVals[inds]
            
            ## Cut all arrays back to the same length
            #onTimes = onTimes[:len(times)]
            #offTimes = offTimes[:len(times)]
            #times = times[:len(onTimes)]
            
            ## Determine average frame transfer time
            txLen = (offTimes[:len(times)] - times[:len(offTimes)]).mean()
            
            ## Determine average exposure time (excluding first frame)
            expLen = (offTimes[1:len(onTimes)] - onTimes[1:len(offTimes)]).mean()
            
            ## New times list is onTimes, any extra frames use their original time offset by txLen and expLen
            vals = marr.xvals('Time')
            #print "Original times:", vals
            vals[:len(onTimes)] = onTimes[:len(vals)]
            vals[len(onTimes):] -= txLen + expLen
            #print "New times:", vals
            
            
            
        return {'frames': marr, 'expose': expose}
        
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
        size = self.cam.getSize()
        self.state = {'binning': 1, 'exposure': .001, 'region': [0, 0, size[0]-1, size[1]-1], 'mode': 'Normal'}
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
    
    def setParam(self, param, value):
        #print "PVCam:setParam", param, value
        start = False
        if self.isRunning():
            start = True
            #print "Camera.setParam: Stopping camera before setting parameter.."
            self.stop(block=True)
            #print "Camera.setPAram: camera stopped"
        with MutexLocker(self.lock):
            self.state[param] = value
        if start:
            #self.start(QtCore.QThread.HighPriority)
            self.start()
        
    
    def run(self):
        #print "Starting up camera acquisition thread."
        binning = self.state['binning']
        
        ## Make sure binning value is acceptable (stupid driver problem)
        if 'allowedBinning' in self.dev.config and binning not in self.dev.config['allowedBinning']:
            ab = self.dev.config['allowedBinning'][:]
            ab.sort()
            if binning < ab[0]:
                binning = ab[0]
            while binning not in ab:
                binning -= 1
            msg = "Requested binning %d not allowed, using %d instead" % (self.state['binning'], binning)
            print msg
            self.emit(QtCore.SIGNAL("showMessage"), msg)
        #print "Will use binning", binning
        exposure = self.state['exposure']
        region = self.state['region']
        mode = self.state['mode']
        size = self.cam.getSize()
        lastFrame = None
        lastFrameTime = None
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
                    self.acqBuffer = self.cam.start(frames=self.ringSize, binning=binning, exposure=exposure, region=region, mode=mode)
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
                frame = self.cam.lastFrame()
                #times[ti] = ptime.time(); ti += 1  ## +40us
                ## If a new frame is available, process it and inform other threads
                if frame is not None and frame != lastFrame:
                    #print 'frame'
                    now = ptime.time() #time.clock()
                    if lastFrame is not None:
                        diff = ((frame + self.ringSize) - lastFrame) % self.ringSize
                        if diff > 1:
                            print "Dropped %d frames after %d" % (diff-1, self.frameId)
                            self.emit(QtCore.SIGNAL("showMessage"), "Acquisition thread dropped %d frame(s) after frame %d. (%02g since last frame arrived)" % (diff-1, self.frameId, now-lastFrameTime))
                    lastFrame = frame
                    #times[ti] = ptime.time(); ti += 1  # +130us
                    
                    ## Build meta-info for this frame
                    ## Use lastFrameTime because the current frame _began_ exposing when the previous frame arrived.
                    info = {'id': self.frameId, 'time': now, 'binning': binning, 'exposure': exposure, 'region': region}
                    
                    #ps = self.dev.getPixelSize()
                    #if ps is not None:
                        #ps2 = (ps[0] * binning, ps[1] * binning)
                        #info['pixelSize'] = ps2
                    #obj = self.dev.getObjective()
                    #if obj is not None:
                        #info['objective'] = obj
                    #pos = self.dev.getPosition()  ## pos is the position of the center of the sensor
                    #if pos is not None:
                        #info['centerPosition'] = pos
                        #if ps is not None and size is not None:
                            ##print pos, size, ps, region
                            #pos2 = [pos[0] - size[0]*ps[0]*0.5 + region[0]*ps[0], pos[1] - size[1]*ps[1]*0.5 + region[1]*ps[1]]
                            #info['imagePosition'] = pos2
                    #sPos = self.dev.getPosition(justScope=True)
                    #if sPos is not None:
                        #info['scopePosition'] = sPos
                        
                    ## frameInfo includes pixelSize, objective, centerPosition, scopePosition, imagePosition
                    ss = self.dev.getScopeState()
                    #print ss
                    if ss['id'] != scopeState:
                        #print "scope state changed"
                        scopeState = ss['id']
                        ## regenerate frameInfo here
                        ps = ss['pixelSize']
                        pos = ss['centerPosition']
                        pos2 = [pos[0] - size[0]*ps[0]*0.5 + region[0]*ps[0], pos[1] - size[1]*ps[1]*0.5 + region[1]*ps[1]]
                        
                        frameInfo = {
                            'pixelSize': [ps[0] * binning, ps[1] * binning],
                            'scopePosition': ss['scopePosition'],
                            'centerPosition': pos,
                            'objective': ss['objective'],
                            'imagePosition': pos2
                        }
                    ## Copy frame info to info array
                    for k in frameInfo:
                        info[k] = frameInfo[k]
                    #times[ti] = ptime.time(); ti += 1   ## + 3600us

                    lastFrameTime = now
                    
                    ## Inform that new frame is ready
                    outFrame = (self.acqBuffer[frame].copy(), info)
                    #times[ti] = ptime.time(); ti += 1  ## +1130us
                    
                    with MutexLocker(self.connectMutex):
                        conn = self.connections[:]
                    for c in conn:
                        c(outFrame)
                    #times[ti] = ptime.time(); ti += 1  ## + 169us
                    self.emit(QtCore.SIGNAL("newFrame"), outFrame)
                    #times[ti] = ptime.time(); ti += 1  ## + 26us
                    
                    ## Lock task array and copy before tinkering with it
                    #print "lock", self.lock.depth()
                    #self.lock.lock(id="PVCam/interface.py AcquireThread.run near 465")
                    #print "locked", self.lock.depth()
                    #try:
                        ##tasks = self.tasks[:]
                        #for t in self.tasks:
                            #t.addFrame(outFrame)
                    #finally:
                        #self.lock.unlock()
                    #print "unlock", self.lock.depth()

                    self.frameId += 1
                    
                    ## mandatory sleep until 1ms before next expected frame
                    ## Otherwise the CPU is constantly tied up waiting for new frames.
                    sleepTime = (lastFrameTime + exposure - 1e-3) - ptime.time()
                    if sleepTime > 0:
                        #print "Sleep %f sec"% sleepTime
                        time.sleep(sleepTime)
                    loopCount = 0
                    #times[ti] = ptime.time(); ti += 1
                #times[ti] = ptime.time(); ti += 1
                        
                time.sleep(100e-6)
                
                
                now = ptime.time()
                ## check for stop request every 10ms
                if now - lastStopCheck > 10e-3: 
                    lastStopCheck = now
                    #print "stop check"
                    ## If no frame has arrived yet, do NOT stop the camera (this can hang the driver)
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
                            print "Camera acquisition thread has been waiting %02f sec but no new frames have arrived; shutting down." % diff
                            break
                #times[ti] = ptime.time(); ti += 1 ## + 285us
                #print ",   ".join(['%03.2f' % ((times[i]-times[i-1]) * 1e6) for i in range(len(times)-1)])
                #times[-1] = ptime.time()
            self.cam.stop()
        except:
            try:
                self.cam.stop()
            except:
                pass
            msg = "ERROR Starting acquisition:", sys.exc_info()[0], sys.exc_info()[1]
            print traceback.print_exception(*sys.exc_info())
            self.emit(QtCore.SIGNAL("showMessage"), msg)
            
        
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


#class CameraTask(QObject):
    #def __init__(self, cam, maxTime=None):
        #self.cam = cam
        #self.maxTime = maxTime
        #self.lock = Mutex()
        #self.frames = []
        #self.recording = True
        #QtCore.QObject.connect(self.cam, QtCore.SIGNAL('newFrame'), self.newFrame)
    
    ##def addFrame(self, frame):
        ###print "CameraTask.Add frame"
        ##with MutexLocker(self.lock):
            ##self.frames.append(frame)
            ##rec = self.recording
        ##if not rec:
            ##self.cam.removeTask(self)
            ###print "CameraTask.Add frame done"
        
    #def newFrame(self, frame):
        #self.frames.append(frame)
        #if not self.recording:
            #QtCore.QObject.disconnect(self.cam, QtCore.SIGNAL('newFrame'), self.newFrame)


    #def data(self):
        ##with MutexLocker(self.lock):
        #return self.frames
    
    #def stop(self):
        ##print "Stop cam record"
        ##with MutexLocker(self.lock):
        #self.recording = False
    
