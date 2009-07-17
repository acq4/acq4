# -*- coding: utf-8 -*-
from lib.drivers.pvcam import PVCam as PVCDriver
from lib.devices.Device import *
from PyQt4 import QtCore
import time, sys, traceback
from numpy import *
from lib.util.MetaArray import *
from protoGUI import *
from deviceGUI import *
import lib.util.ptime as ptime

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
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.pvc = PVCDriver
        self.cam = None
        self.acqThread = AcquireThread(self)
        print "Created PVCam device. Cameras are:", self.pvc.listCameras()
        
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
            #QtCore.QObject.connect(self.scopeDev, QtCore.SIGNAL('positionChanged'), self.positionChanged)
            #QtCore.QObject.connect(self.scopeDev, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
        else:
            self.scopeDev = None
        
    
    def quit(self):
        if hasattr(self, 'acqThread') and self.acqThread.isRunning():
            self.stopAcquire()
            self.acqThread.wait()
        
        
    #@ftrace
    def devName(self):
        l = QtCore.QMutexLocker(self.lock)
        return self.name
    
    #@ftrace
    def getCamera(self):
        l = QtCore.QMutexLocker(self.lock)
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
        l = QtCore.QMutexLocker(self.lock)
        return Task(self, cmd)
    
    #@ftrace
    def getTriggerChannel(self, daq):
        l = QtCore.QMutexLocker(self.lock)
        if not 'triggerOutChannel' in self.config:
            return None
        if self.config['triggerOutChannel'][0] != daq:
            return None
        return self.config['triggerOutChannel'][1]
        
    def startAcquire(self, params=None):
        #l = QtCore.QMutexLocker(self.lock)
        if params is not None:
            for p in params:
                self.acqThread.setParam(p, params[p])
        self.acqThread.start()
        
    def stopAcquire(self, block=True):
        #l = QtCore.QMutexLocker(self.lock)
        self.acqThread.stop(block)

    def isRunning(self):
        l = QtCore.QMutexLocker(self.lock)
        return self.acqThread.isRunning()

    def protocolInterface(self, prot):
        return PVCamProto(self, prot)

    def deviceInterface(self):
        return PVCamDevGui(self)

    def setParam(self, param, val):
        #l = QtCore.QMutexLocker(self.lock)
        r = self.acqThread.isRunning()
        if r: 
            self.acqThread.stop(block=True)
        self.cam.setParam(param, val)
        self.emit(QtCore.SIGNAL('paramChanged'), param, val)
        if r: 
            self.acqThread.start()
        
    def getParam(self, param):
        #l = QtCore.QMutexLocker(self.lock)
        return self.cam.getParam(param)
        
    #@ftrace
    def listTriggerModes(self):
        #l = QtCore.QMutexLocker(self.lock)
        return self.cam.listTriggerModes()
        
    #@ftrace
    def getPosition(self):
        #print "PVCam: getPosition"
        l = QtCore.QMutexLocker(self.lock)
        #print "PVCam: getPosition: locked"
        if self.scopeDev is None:
            #print "   none"
            #print "PVCam: getPosition done"
            return None
        else:
            #print "PVCam:getPosition: scopeDev.getPosition"
            p = self.scopeDev.getPosition()
            #print "PVCam:getPosition: scopeDev.getPosition done"
            #print "   ", p
            #print "PVCam: getPosition done"
            return p

    #@ftrace
    def getScale(self):
        """Return the dimensions of 1 pixel with signs if the image is flipped"""
        l = QtCore.QMutexLocker(self.lock)
        #print "PVCam: getScale locked"
        
        if self.scopeDev is None:
            #print "   none"
            return None
        else:
            #print "PVCam: getScale getObj"
            obj = self.scopeDev.getObjective()
            #print "PVCam: getScale getObj done"
            scale = obj['scale']
            #print "   ", p
            sf = self.config['scaleFactor']
            return (sf[0]/scale, sf[1]/scale)
        
    #@ftrace
    def getPixelSize(self):
        """Return the absolute size of 1 pixel"""
        s = self.getScale()
        return (abs(s[0]), abs(s[1]))
        
    #@ftrace
    def getObjective(self):
        l = QtCore.QMutexLocker(self.lock)
        #print "PVCam:getObjective: locked"
        if self.scopeDev is None:
            #print "   none"
            return None
        else:
            #print "PVCam:getObjective: scopeDev.getObjective"
            obj = self.scopeDev.getObjective()
            #print "PVCam:getObjective: scopeDev.getObjective done"
            return obj['name']

    def getScopeDevice(self):
        l = QtCore.QMutexLocker(self.lock)
        return self.scopeDev
        

class Task(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.recordHandle = None
        self.stopAfter = False
        self.returnState = {}
        
        
    def configure(self, tasks, startOrder):
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
            
        
        ## If we are not triggering the daq, request that we start before everyone else
        ## (no need to stop, we will simply record frames as they are collected)
        else:
            startOrder.remove(name)
            startOrder.insert(0, name)
            
        
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
        self.recordHandle = self.dev.acqThread.startRecord()
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
        return True
        
    def stop(self):
        #print "stop camera task"
        self.recordHandle.stop()
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
        data = self.recordHandle.data()
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
        self.state = {'binning': 1, 'exposure': .001, 'region': None, 'mode': 'Normal'}
        self.stopThread = False
        self.lock = QtCore.QMutex()
        self.acqBuffer = None
        self.frameId = 0
        self.bufferTime = 5.0
        self.ringSize = 30
        self.tasks = []
    
    def __del__(self):
        if hasattr(self, 'cam'):
            self.cam.stop()
    
    def setParam(self, param, value):
        start = False
        if self.isRunning():
            start = True
            self.stop(block=True)
        l = QtCore.QMutexLocker(self.lock)
        self.state[param] = value
        l.unlock()
        if start:
            self.start()
        
    def startRecord(self, maxTime=None):
        rec = CameraTask(self, maxTime)
        #print "lock to create task"
        l = QtCore.QMutexLocker(self.lock)
        self.tasks.append(rec)
        #print "..unlock from create task"
        return rec
        
    def removeTask(self, task):
        #print "Lock to remove task"
        l = QtCore.QMutexLocker(self.lock)
        if task in self.tasks:
            self.tasks.remove(task)
        #print "..unlock from remove task"
    
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
        
        exposure = self.state['exposure']
        region = self.state['region']
        mode = self.state['mode']
        lastFrame = None
        lastFrameTime = None
        #print "AcquireThread.run: Lock for startup.."
        self.lock.lock()
        self.stopThread = False
        self.lock.unlock()
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
            lastFrameTime = ptime.time() #time.clock()  # Use time.time() on Linux
            
            loopCount = 0
            while True:
                frame = self.cam.lastFrame()
                ## If a new frame is available, process it and inform other threads
                if frame is not None and frame != lastFrame:
                    #print "      AcquireThread.run: frame"
                    now = ptime.time() #time.clock()
                    #print "      AcquireThread.run: frame 2"
                    if lastFrame is not None:
                        diff = ((frame + self.ringSize) - lastFrame) % self.ringSize
                        if diff > 1:
                            print "Dropped %d frames after %d" % (diff-1, self.frameId)
                            self.emit(QtCore.SIGNAL("showMessage"), "Acquisition thread dropped %d frame(s) after %d!" % (diff-1, self.frameId))
                    lastFrame = frame
                    #print "      AcquireThread.run: frame 3"
                    
                    ### compute FPS
                    #dt = now - lastFrameTime
                    #if dt > 0.:
                        #if self.fps is None:
                            #self.fps = 1.0/dt
                        #else:
                            #self.fps = self.fps * 0.9 + 0.1 / dt
                    
                    ## Build meta-info for this frame
                    ## Use lastFrameTime because the current frame _began_ exposing when the previous frame arrived.
                    ps = self.dev.getPixelSize()
                    ps = (ps[0] * binning, ps[1] * binning)
                    info = {'id': self.frameId, 'time': lastFrameTime, 'binning': binning, 'exposure': exposure, 'region': region, 'position': self.dev.getPosition(), 'pixelSize': ps, 'objective': self.dev.getObjective()}
                    
                    lastFrameTime = now
                    #print "      AcquireThread.run: frame 4"
                    
                    ## Inform that new frame is ready
                    outFrame = (self.acqBuffer[frame].copy(), info)
                    self.emit(QtCore.SIGNAL("newFrame"), outFrame)
                    
                    ## Lock task array and copy before tinkering with it
                    #print "AcquireThread.run: *Locking task array"
                    self.lock.lock()
                    tasks = self.tasks[:]
                    self.lock.unlock()
                    #print "AcquireThread.run: *Unlocked task array"
                    
                    #print "AcquireThread.run: Adding frame to tasks"
                    for t in tasks:
                        t.addFrame(outFrame)
                    #print "AcquireThread.run: done"
                        
                    self.frameId += 1
                time.sleep(10e-6)
                
                if loopCount > 1000: 
                    ## If no frame has arrived yet, do NOT stop the camera (this can hang the driver)
                    if frame is not None or (ptime.time()-lastFrameTime > 1):
                        #print "    AcquireThread.run: Locking thread to check for stop request"
                        self.lock.lock()
                        if self.stopThread:
                            #print "    AcquireThread.run: Unlocking thread for exit"
                            self.lock.unlock()
                            #print "    AcquireThread.run: Camera acquisition thread stopping."
                            break
                        self.lock.unlock()
                        #print "    AcquireThread.run: Done with thread stop check"
                    loopCount = 0
                
                #if loopCount % 10000 == 0:
                    #print "    AcquireThread.run: loop"
                loopCount += 1
                #print "*Unlocking thread"
            ## Inform that we have stopped (?)
            #self.ui.stop()
            self.cam.stop()
            #print "camera stopped"
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
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        #print "AcquireThread.stop: got lock, requested stop."
        l.unlock()
        #print "AcquireThread.stop: Unlocked, waiting for thread exit (%s)" % block
        if block:
          self.wait()
        #print "AcquireThread.stop: thread exited"

    def reset(self):
        if self.isRunning():
            self.stop()
            self.wait()
            self.start()


class CameraTask:
    def __init__(self, cam, maxTime=None):
        self.cam = cam
        self.maxTime = maxTime
        self.lock = QtCore.QMutex()
        self.frames = []
        self.recording = True
    
    def addFrame(self, frame):
        #print "CameraTask.Add frame"
        l = QtCore.QMutexLocker(self.lock)
        self.frames.append(frame)
        if not self.recording:
            self.cam.removeTask(self)
        #print "CameraTask.Add frame done"
    
    def data(self):
        l = QtCore.QMutexLocker(self.lock)
        return self.frames
    
    def stop(self):
        #print "Stop cam record"
        l = QtCore.QMutexLocker(self.lock)
        self.recording = False
    
