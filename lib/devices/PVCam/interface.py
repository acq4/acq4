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

class PVCam(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.pvc = PVCDriver
        self.cam = None
        self.acqThread = AcquireThread(self)
        print "Created PVCam device. Cameras are:", self.pvc.listCameras()
        
        if 'params' in config:
            self.getCamera().setParams(config['params'])
    
    def quit(self):
        if hasattr(self, 'acqThread') and self.acqThread.isRunning():
            self.stopAcquire()
            self.acqThread.wait()
        
        
    def devName(self):
        return self.name
    
    def getCamera(self):
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
    
    def createTask(self, cmd):
        return Task(self, cmd)
    
    def getTriggerChannel(self):
        return self.config['triggerChannel'][1]
        
    def startAcquire(self):
        self.acqThread.start()
        
    def stopAcquire(self, block=True):
        self.acqThread.stop(block)

    def protocolInterface(self, prot):
        return PVCamProto(self, prot)

    def deviceInterface(self):
        return PVCamDevGui(self)

    def setParam(self, param, val):
        r = self.acqThread.isRunning()
        if r: 
            self.acqThread.stop(block=True)
        self.cam.setParam(param, val)
        if r: 
            self.acqThread.start()
        

class Task(DeviceTask):
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.recordHandle = None
        
        
    def configure(self, tasks, startOrder):
        ## If we are triggering, stop acquisition now and request that we start after the DAQ
        name = self.dev.devName()
        if self.cmd['trigger']:
            #print "Stopping camera before task start.."
            self.dev.stopAcquire(block=True)  
            #print "done"
            #print "running:", self.dev.acqThread.isRunning()
            daqName = self.dev.config['triggerChannel'][0]
            startOrder.remove(name)
            startOrder.insert(startOrder.index(daqName)+1, name)
            
        
        ## If we are not triggering, request that we start before everyone else
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
        self.dev.startAcquire()
        
    def isDone(self):
        ## should return false if recording is required to run for a specific time.
        return True
        
    def stop(self):
        self.recordHandle.stop()
        
    def getResult(self):
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
        self.state = {'binning': 1, 'exposure': .001, 'region': None}
        self.stopThread = False
        self.lock = QtCore.QMutex()
        self.acqBuffer = None
        self.frameId = 0
        self.bufferTime = 5.0
        self.ringSize = 15
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
        if 'maxBinning' in self.dev.config and binning > self.dev.config['maxBinning']:
            msg = "Requested binning %d exceeds maximum, using %d instead" % (binning, self.dev.config['maxBinning'])
            print msg
            self.emit(QtCore.SIGNAL("showMessage"), msg)
            binning = self.dev.config['maxBinning']
        
        exposure = self.state['exposure']
        region = self.state['region']
        lastFrame = None
        lastFrameTime = None
        #print "Lock for startup.."
        self.lock.lock()
        self.stopThread = False
        self.lock.unlock()
        #print "..unlocked from startup"
        self.fps = None
        
        try:
            #print self.ringSize, binning, exposure, region
            self.acqBuffer = self.cam.start(frames=self.ringSize, binning=binning, exposure=exposure, region=region)
            lastFrameTime = ptime.time() #time.clock()  # Use time.time() on Linux
            
            loopCount = 0
            while True:
                frame = self.cam.lastFrame()
                
                ## If a new frame is available, process it and inform other threads
                if frame is not None and frame != lastFrame:
                    now = ptime.time() #time.clock()
                    
                    if lastFrame is not None:
                        diff = ((frame + self.ringSize) - lastFrame) % self.ringSize
                        if diff > 1:
                            print "Dropped %d frames after %d" % (diff-1, self.frameId)
                            self.emit(QtCore.SIGNAL("showMessage"), "Acquisition thread dropped %d frame(s) after %d!" % (diff-1, self.frameId))
                    lastFrame = frame
                    
                    ## compute FPS
                    dt = now - lastFrameTime
                    if dt > 0.:
                        if self.fps is None:
                            self.fps = 1.0/dt
                        else:
                            self.fps = self.fps * 0.9 + 0.1 / dt
                    
                    ## Build meta-info for this frame
                    ## Use lastFrameTime because the current frame _began_ exposing when the previous frame arrived.
                    info = {'id': self.frameId, 'time': lastFrameTime, 'binning': binning, 'exposure': exposure, 'region': region, 'fps': self.fps}
                    
                    lastFrameTime = now
                    
                    ## Inform that new frame is ready
                    outFrame = (self.acqBuffer[frame].copy(), info)
                    self.emit(QtCore.SIGNAL("newFrame"), outFrame)
                    
                    ## Lock task array and copy before tinkering with it
                    #print "*Locking task array"
                    self.lock.lock()
                    tasks = self.tasks[:]
                    self.lock.unlock()
                    #print "*Unlocked task array"
                    
                    for t in tasks:
                        t.addFrame(outFrame)
                        
                    self.frameId += 1
                time.sleep(10e-6)
                
                #print "*Locking thread"
                if loopCount > 1000:
                    self.lock.lock()
                    if self.stopThread and frame is not None:
                        #print "Unlocking thread for exit"
                        self.lock.unlock()
                        #print "Camera acquisition thread stopping."
                        break
                    self.lock.unlock()
                    loopCount = 0
                
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
        #print "Requesting thread stop, acquiring lock first.."
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        #print "got lock, requested stop."
        l.unlock()
        #print "Unlocked, waiting for thread exit"
        if block:
          self.wait()
        #print "thread exited"

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
        #print "Add frame"
        l = QtCore.QMutexLocker(self.lock)
        self.frames.append(frame)
        if not self.recording:
            self.cam.removeTask(self)
    
    def data(self):
        l = QtCore.QMutexLocker(self.lock)
        return self.frames
    
    def stop(self):
        #print "Stop cam record"
        l = QtCore.QMutexLocker(self.lock)
        self.recording = False
    
