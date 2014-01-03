import time
from acq4.util.Mutex import Mutex
from PyQt4 import QtGui, QtCore
import acq4.util.debug as debug
from acq4.util.metaarray import MetaArray
import numpy as np
import acq4.util.ptime as ptime
import acq4.Manager
try:
    from acq4.filetypes.ImageFile import *
    HAVE_IMAGEFILE = True
except ImportError:
    HAVE_IMAGEFILE = False


class RecordThread(QtCore.QThread):
    """
    Thread class used by camera module for storing data to disk.
    """
    sigShowMessage = QtCore.Signal(object)
    sigRecordingFailed = QtCore.Signal()
    sigRecordingFinished = QtCore.Signal()
    
    def __init__(self, ui):
        QtCore.QThread.__init__(self)
        self.ui = ui
        self.m = acq4.Manager.getManager()
        self.ui.cam.sigNewFrame.connect(self.newCamFrame)
        
        ui.ui.recordStackBtn.toggled.connect(self.toggleRecord)
        ui.ui.saveFrameBtn.clicked.connect(self.snapClicked)
        self.recording = False
        self.recordStart = False
        self.recordStop = False
        self.takeSnap = False
        self.currentRecord = None
        self.frameLimit = None
        
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.camLock = Mutex()
        self.newCamFrames = []
        
    def newCamFrame(self, frame=None):
        if frame is None:
            return
        with self.lock:
            newRec = self.recordStart
            
            if self.frameLimit is not None:
                self.frameLimit -= 1
                if self.frameLimit < 0:
                    self.recordStop = True
                    self.frameLimit = None
                    self.sigRecordingFinished.emit()
            lastRec = self.recordStop and self.recording
            if self.recordStop:
                self.recording = False
                self.recordStop = False
            if self.recordStart:
                self.recordStart = False
                self.recording = True
            recording = self.recording or lastRec
            takeSnap = self.takeSnap
            self.takeSnap = False
            recFile = self.currentRecord
        if recording or takeSnap:
            with self.camLock:
                ## remember the record/snap/storageDir states since they might change 
                ## before the write thread gets to this frame
                self.newCamFrames.append({'frame': frame, 'record': recording, 'snap': takeSnap, 'newRec': newRec, 'lastRec': lastRec})
                if self.currentRecord is not None:
                    self.showMessage("Recording %s - %d" % (self.currentRecord.name(), self.currentFrameNum))
    
    def run(self): ### run is called indirectly (by C somewhere) by calling start() from the parent thread; DO NOT call directly
        self.stopThread = False
        
        while True:
            try:
                with self.camLock:
                    handleCamFrames = self.newCamFrames[:]
                    self.newCamFrames = []
            except:
                debug.printExc('Error in camera recording thread:')
                break
            
            try:
                self.handleCamFrames(handleCamFrames)
                #while len(handleCamFrames) > 0:
                    #self.handleCamFrame(handleCamFrames.pop(0))
            except:
                debug.printExc('Error in camera recording thread:')
                self.toggleRecord(False)
                #self.emit(QtCore.SIGNAL('recordingFailed'))
                self.sigRecordingFailed.emit()
                
            time.sleep(10e-3)
            
            #print "  RecordThread run: stop check"
            with self.lock as l:
                #print "  RecordThread run:   got lock"
                if self.stopThread:
                    #print "  RecordThread run:   stop requested, exiting loop"
                    break
            #print "  RecordThread run:   unlocked"

    def handleCamFrames(self, frames):
        recFrames = []
        newRec = False
        for frame in frames:
            data = frame['frame'].data()
            info = frame['frame'].info()
            if frame['record']:
                recFrames.append((data, info))
                if frame['newRec']:
                    self.startFrameTime = info['time']
                    newRec = True
                
                
                if frame['lastRec']:
                    dur = info['time'] - self.startFrameTime
                    self.currentRecord.setInfo({'frames': self.currentFrameNum, 'duration': dur, 'averageFPS': ((self.currentFrameNum-1)/dur)})
                    self.showMessage('Finished recording %s - %d frames, %02f sec' % (self.currentRecord.name(), self.currentFrameNum, dur)) 
            else:
                if len(recFrames) > 0:
                    ## do recording
                    self.writeFrames(recFrames, newRec)
                    recFrames = []
                    newRec = False
                
            
            if frame['snap']:
                try:
                    if HAVE_IMAGEFILE:
                        fileName = 'image.tif'
                        fh = self.m.getCurrentDir().writeFile(data, fileName, info, fileType="ImageFile", autoIncrement=True)
                    else:
                        fileName = 'image.ma'
                        fh = self.m.getCurrentDir().writeFile(data, fileName, info, fileType="MetaArray", autoIncrement=True)

                    fn = fh.name()
                    self.showMessage("Saved image %s" % fn)
                    with self.lock:
                        self.takeSnap = False
                    self.ui.ui.saveFrameBtn.success("Saved.")
                except:
                    self.ui.ui.saveFrameBtn.failure("Error.")
                    raise
                    
        if len(recFrames) > 0:
            self.writeFrames(recFrames, newRec)
            

    def writeFrames(self, frames, newRec):
        times = [f[1]['time'] for f in frames]
        arrayInfo = [
            {'name': 'Time', 'values': array(times) - self.startFrameTime, 'units': 's'},
            {'name': 'X'},
            {'name': 'Y'}
        ]
        #import random
        #if random.random() < 0.01:
            #raise Exception("TEST")
        imgs = [f[0][np.newaxis,...] for f in frames]
        
        data = MetaArray(np.concatenate(imgs, axis=0), info=arrayInfo)
        if newRec:
            self.currentRecord = self.m.getCurrentDir().writeFile(data, 'video', autoIncrement=True, info=frames[0][1], appendAxis='Time')
            self.currentFrameNum = 0
        else:
            data.write(self.currentRecord.name(), appendAxis='Time')
            s = 1.0/self.currentFrameNum
            
        #self.showMessage("Recording %s - %d" % (self.currentRecord.name(), self.currentFrameNum))
        
        self.currentFrameNum += len(frames)

    #def handleCamFrame(self, frame):
        #(data, info) = frame['frame']
        
        #if frame['record']:
            #if frame['newRec']:
                #self.startFrameTime = info['time']
                
            #arrayInfo = [
                #{'name': 'Time', 'values': array([info['time'] - self.startFrameTime]), 'units': 's'},
                #{'name': 'X'},
                #{'name': 'Y'}
            #]
            ##import random
            ##if random.random() < 0.01:
                ##raise Exception("TEST")
            #data = MetaArray(data[np.newaxis], info=arrayInfo)
            #if frame['newRec']:
                #self.currentRecord = self.m.getCurrentDir().writeFile(data, 'video', autoIncrement=True, info=info, appendAxis='Time')
                #self.currentFrameNum = 0
            #else:
                #now = ptime.time()
                #data.write(self.currentRecord.name(), appendAxis='Time')
                #print "Frame write: %0.2gms" % (1000*(ptime.time()-now))
                #s = 1.0/self.currentFrameNum
                
            #self.showMessage("Recording %s - %d" % (self.currentRecord.name(), self.currentFrameNum))
            
            #self.currentFrameNum += 1
            
            #if frame['lastRec']:
                #dur = info['time'] - self.startFrameTime
                #self.currentRecord.setInfo({'frames': self.currentFrameNum, 'duration': dur, 'averageFPS': ((self.currentFrameNum-1)/dur)})
                #self.showMessage('Finished recording %s - %d frames, %02f sec' % (self.currentRecord.name(), self.currentFrameNum, dur)) 
                
            
        
        #if frame['snap']:
            #fileName = 'image.tif'
            
            #fh = self.m.getCurrentDir().writeFile(data, fileName, info, fileType="ImageFile", autoIncrement=True)
            #fn = fh.name()
            #self.showMessage("Saved image %s" % fn)
            #with self.lock:
                #self.takeSnap = False
    
    def showMessage(self, msg):
        #self.emit(QtCore.SIGNAL('showMessage'), msg)
        self.sigShowMessage.emit(msg)
    
    def snapClicked(self):
        with self.lock:
            self.takeSnap = True

    def toggleRecord(self, b):
        with self.lock:
            if b: ### Only the GUI thread is allowed to initiate recording
                self.recordStart = True
                self.frameLimit = None
                if self.ui.ui.recordXframesCheck.isChecked():
                    self.frameLimit = self.ui.ui.recordXframesSpin.value()
            else:
                if self.recording:
                    self.recordStop = True

    def stop(self):
        #QtCore.QObject.disconnect(self.ui.cam, QtCore.SIGNAL('newFrame'), self.newCamFrame)
        self.ui.cam.sigNewFrame.disconnect(self.newCamFrame)
        #print "RecordThread stop.."    
        with self.lock:
        #print "  RecordThread stop: locked"
            self.stopThread = True
        #print "  RecordThread stop: done"
        
