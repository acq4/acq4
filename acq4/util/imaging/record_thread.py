from __future__ import print_function
import time
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.util import Qt
import acq4.util.debug as debug
from acq4.util.metaarray import MetaArray
import numpy as np
import acq4.util.ptime as ptime
import acq4.Manager
from acq4.util.DataManager import FileHandle, DirHandle
try:
    from acq4.filetypes.ImageFile import *
    HAVE_IMAGEFILE = True
except ImportError:
    HAVE_IMAGEFILE = False


class RecordThread(Thread):
    """Class for offloading image recording to a worker thread.
    """
    # sigShowMessage = Qt.Signal(object)
    sigRecordingFailed = Qt.Signal()
    sigRecordingFinished = Qt.Signal(object, object)  # file handle, num frames
    sigSavedFrame = Qt.Signal(object)
    
    def __init__(self, ui):
        Thread.__init__(self)
        self.m = acq4.Manager.getManager()
        
        self._stackSize = 0  # size of currently recorded stack
        self._recording = False
        self.currentFrame = None
        self.frameLimit = None
        
        # Interaction with worker thread:
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.newFrames = []  # list of frames and the files they should be sored / appended to.

        # Attributes private to worker thread:
        self.currentStack = None  # file handle of currently recorded stack
        self.startFrameTime = None
        self.lastFrameTime = None
        self.currentFrameNum = 0

    def startRecording(self, frameLimit=None):
        """Ask the recording thread to begin recording a new image stack.

        *frameLimit* may specify the maximum number of frames in the stack before
        the recording will stop.
        """
        if self.recording:
            raise Exception("Already recording; cannot start a new stack.")

        self.frameLimit = frameLimit
        self._stackSize = 0
        self._recording = True

    def stopRecording(self):
        """Ask the recording thread to stop recording new images to the image
        stack.
        """
        self.frameLimit = None
        self._stackSize = 0
        self._recording = False
        with self.lock:
            self.newFrames.append(False)

    @property
    def recording(self):
        """Bool indicating whether the thread is currently recording new frames
        to an image stack.
        """
        return self._recording

    def saveFrame(self):
        """Ask the recording thread to save the most recently acquired frame.
        """
        with self.lock:
            self.newFrames.append({'frame': self.currentFrame, 'dir': self.m.getCurrentDir(), 'stack': False})

    def newFrame(self, frame=None):
        """Inform the recording thread that a new frame has arrived.

        Returns the number of frames currently waiting to be written.
        """
        if frame is None:
            return

        self.currentFrame = frame
        with self.lock:
            if self.recording:
                self.newFrames.append({'frame': self.currentFrame, 'dir': self.m.getCurrentDir(), 'stack': True})
                self._stackSize += 1
            framesLeft = len(self.newFrames)
        if self.recording:
            if self.frameLimit is not None and self._stackSize >= self.frameLimit:
                self.frameLimit = None
                self.stopRecording()
        return framesLeft

    @property
    def stackSize(self):
        """The total number of frames requested for storage in the current
        image stack.
        """
        return self._stackSize

    def quit(self):
        """Stop the recording thread.

        No new frames will be written after the thread exits.
        """
        with self.lock:
            self.stopThread = True
            self.newFrames = []
            self.currentFrame = None
    
    def run(self):
        # run is invoked in the worker thread automatically after calling start()
        self.stopThread = False
        
        while True:
            with self.lock:
                if self.stopThread:
                    break
                newFrames = self.newFrames[:]
                self.newFrames = []
            
            try:
                self.handleFrames(newFrames)
            except:
                debug.printExc('Error in image recording thread:')
                self.sigRecordingFailed.emit()
                
            time.sleep(100e-3)

    def handleFrames(self, frames):
        # Write as many frames into the stack as possible.
        # If False appears in the list of frames, it indicates the end of a stack
        # and any further frames are written to a new stack.

        recFrames = []
        for frame in frames:

            if frame is False:
                # stop current recording
                if len(recFrames) > 0:
                    ## write prior frames now
                    self.writeFrames(recFrames, dh)
                    recFrames = []

                if self.currentStack is not None:
                    dur = self.lastFrameTime - self.startFrameTime
                    if dur > 0:
                        fps = (self.currentFrameNum+1) / dur
                    else:
                        fps = 0
                    self.currentStack.setInfo({'frames': self.currentFrameNum, 'duration': dur, 'averageFPS': fps})
                    # self.showMessage('Finished recording %s - %d frames, %02f sec' % (self.currentStack.name(), self.currentFrameNum, dur)) 
                    self.sigRecordingFinished.emit(self.currentStack, self.currentFrameNum)
                    self.currentStack = None
                    self.currentFrameNum = 0
                continue


            data = frame['frame'].getImage()
            info = frame['frame'].info()
            dh = frame['dir']
            stack = frame['stack']

            if stack is False:
                # Store single frame to new file
                try:
                    if HAVE_IMAGEFILE:
                        fileName = 'image.tif'
                        fh = dh.writeFile(data, fileName, info, fileType="ImageFile", autoIncrement=True)
                    else:
                        fileName = 'image.ma'
                        fh = dh.writeFile(data, fileName, info, fileType="MetaArray", autoIncrement=True)

                    self.sigSavedFrame.emit(fh.name())
                except:
                    self.sigSavedFrame.emit(False)
                    raise
                continue

            # Store frame to current (or new) stack
            recFrames.append((data, info))
            self.lastFrameTime = info['time']
            
        if len(recFrames) > 0:
            self.writeFrames(recFrames, dh)
            self.currentFrameNum += len(recFrames)

    def writeFrames(self, frames, dh):
        newRec = self.currentStack is None

        if newRec:
            self.startFrameTime = frames[0][1]['time']

        times = [f[1]['time'] for f in frames]
        translations = np.array([f[1]['transform'].getTranslation() for f in frames])
        arrayInfo = [
            {'name': 'Time', 'values': array(times) - self.startFrameTime, 'units': 's', 'translation': translations},
            {'name': 'X'},
            {'name': 'Y'}
        ]
        imgs = [f[0][np.newaxis,...] for f in frames]
        
        data = MetaArray(np.concatenate(imgs, axis=0), info=arrayInfo)
        if newRec:
            self.currentStack = dh.writeFile(data, 'video', autoIncrement=True, info=frames[0][1], appendAxis='Time', appendKeys=['translation'])
        else:
            data.write(self.currentStack.name(), appendAxis='Time', appendKeys=['translation'])
