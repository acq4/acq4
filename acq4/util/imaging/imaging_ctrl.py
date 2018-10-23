from __future__ import print_function

from acq4.util import Qt
from acq4 import pyqtgraph as pg
from .frame_display import FrameDisplay
from .imaging_template import Ui_Form
from .record_thread import RecordThread
from acq4.util.debug import printExc


class ImagingCtrl(Qt.QWidget):
    """Control widget used to interact with imaging devices. 

    Provides:

    * Acquire frame / video controls
    * Save frame, pin frame
    * Record stack
    * FPS display
    * Internal FrameDisplay that handles image display, contrast, and
      background subtraction.

    Basic usage:
    
    * Place self.frameDisplay.imageItem() in a ViewBox.
    * Display this widget along with self.frameDisplay.contrastCtrl and .bgCtrl
      to provide the user interface.
    * Connect to sigAcquireVideoClicked and sigAcquireFrameClicked to handle
      user requests for acquisition.
    * Call acquisitionStarted() and acquisitionStopped() to provide feedback
    * Call newFrame(Frame) whenever a new frame is available from the imaging
      device.
    * Connect to self.frameDisplay.imageUpdated to set image transform whenever
      the image is updated. (Note that not all calls to newFrame() will result
      in an image update)

    """

    sigStartVideoClicked = Qt.Signal(object)  # mode
    sigStopVideoClicked = Qt.Signal()
    sigAcquireFrameClicked = Qt.Signal(object)  # mode

    frameDisplayClass = FrameDisplay  # let subclasses override this class


    def __init__(self, parent=None):
        Qt.QWidget.__init__(self, parent)

        self.frameDisplay = self.frameDisplayClass()

        self.pinnedFrames = []
        self.stackShape = None
        self.lastFrameTime = None

        # User-added buttons for specific acquisition modes
        # (frame buttons, video buttons)
        self.customButtons = ([], [])

        self.ui = Ui_Form()
        self.ui.setupUi(self)

        ## format labels
        self.ui.fpsLabel.setFormatStr('{avgValue:.1f} fps')
        self.ui.fpsLabel.setAverageTime(2.0)
        self.ui.displayFpsLabel.setFormatStr('{avgValue:.1f} fps')
        self.ui.displayFpsLabel.setAverageTime(2.0)
        self.ui.displayPercentLabel.setFormatStr('({avgValue:.1f}%)')
        self.ui.displayPercentLabel.setAverageTime(4.0)

        # disabled until first frame arrives
        self.ui.saveFrameBtn.setEnabled(False)
        self.ui.pinFrameBtn.setEnabled(False)

        ## set up recording thread
        self.recordThread = RecordThread(self)
        self.recordThread.start()
        # self.recordThread.sigShowMessage.connect(self.showMessage)
        self.recordThread.finished.connect(self.recordThreadStopped)
        self.recordThread.sigRecordingFinished.connect(self.recordFinished)
        self.recordThread.sigRecordingFailed.connect(self.recordingFailed)
        self.recordThread.sigSavedFrame.connect(self.threadSavedFrame)

        ## connect UI signals
        self.ui.acquireVideoBtn.clicked.connect(self.acquireVideoClicked)
        self.ui.acquireFrameBtn.clicked.connect(self.acquireFrameClicked)
        self.ui.recordStackBtn.toggled.connect(self.recordStackToggled)
        self.ui.saveFrameBtn.clicked.connect(self.saveFrameClicked)
        self.ui.pinFrameBtn.clicked.connect(self.pinFrameClicked)
        self.ui.clearPinnedFramesBtn.clicked.connect(self.clearPinnedFramesClicked)

    def addFrameButton(self, name):
        """Add a new button below the original "Acquire Frame" button.

        When this button is clicked, the sigAcquireFrameClicked signal is emitted
        with *name* as the first argument.
        """
        btn = Qt.QPushButton(name)
        self.customButtons[0].append(btn)
        self.ui.acqBtnLayout.addWidget(btn, len(self.customButtons[0]), 0)
        btn.clicked.connect(lambda: self.sigAcquireFrameClicked.emit(name))

    def addVideoButton(self, name):
        """Add a new button below the original "Acquire Video" button.

        When this button is clicked, the sigAcquireVideoClicked signal is emitted
        with *name* as the first argument.
        """
        btn = Qt.QPushButton(name)
        self.customButtons[1].append(btn)
        self.ui.acqBtnLayout.addWidget(btn, len(self.customButtons[1]), 1)
        btn.clicked.connect(lambda: self.acquireVideoClicked(None, name))

    def newFrame(self, frame):
        self.ui.saveFrameBtn.setEnabled(True)
        self.ui.pinFrameBtn.setEnabled(True)

        # update acquisition frame rate
        now = frame.info()['time']
        if self.lastFrameTime is not None:
            dt = now - self.lastFrameTime
            if dt > 0:
                fps = 1.0 / dt
                self.ui.fpsLabel.setValue(fps)
        self.lastFrameTime = now

        # update display frame rate
        fps = self.frameDisplay.displayFps
        if fps is not None:
            self.ui.displayFpsLabel.setValue(fps)

        if self.recordingStack():
            frameShape = frame.getImage().shape
            if self.stackShape is None:
                self.stackShape = frameShape
            elif self.stackShape != frameShape:
                # new iamge does not match stack shape; need to stop recording.
                self.endStack()

        queued = self.recordThread.newFrame(frame)
        if self.ui.recordStackBtn.isChecked():
            self.ui.stackSizeLabel.setText('%d frames' % self.recordThread.stackSize)

        self.frameDisplay.newFrame(frame)

    def saveFrameClicked(self):
        if self.ui.linkSavePinBtn.isChecked():
            self.addPinnedFrame()
        self.recordThread.saveFrame()

    def recordStackToggled(self, b):
        if b:
            self.startStack()
        else:
            self.endStack()

    def startStack(self):
        """Begin recording a new stack. 

        Raises an exception if a stack is already in progress.
        """
        if self.recordingStack():
            raise RuntimeError("Cannot start stack record; stack already in progress.")
        self.ui.stackSizeLabel.setText('0 frames')
        self.ui.recordStackBtn.setChecked(True)
        self.ui.recordXframesCheck.setEnabled(False)
        self.ui.recordXframesSpin.setEnabled(False)
        if self.ui.recordXframesCheck.isChecked():
            frameLimit = self.ui.recordXframesSpin.value()
        else:
            frameLimit = None
        self.recordThread.startRecording(frameLimit)
        self.stackShape = None

    def endStack(self):
        """Finish recording the current stack.

        Does nothing if no stack is currently in progress.
        """
        self.ui.recordStackBtn.setChecked(False)
        self.ui.recordXframesCheck.setEnabled(True)
        self.ui.recordXframesSpin.setEnabled(True)
        self.recordThread.stopRecording()

    def recordingStack(self):
        """Return True if a stack is currently being recorded.
        """
        return self.recordThread.recording

    def recordFinished(self, fh, numFrames):
        # called by recording thread when it completes a stack recording
        # self.endStack()
        pass

    def recordThreadStopped(self):
        self.endStack()
        self.ui.recordStackBtn.setEnabled(False)  ## Recording thread has stopped, can't record anymore.
        printExc("Recording thread died! See console for error message.")

    def recordingFailed(self):
        self.endStack()
        printExc("Recording failed! See console for error message.")

    def quit(self):
        try:
            self.recordThread.finished.disconnect(self.recordThreadStopped)
        except TypeError:
            pass
        try:
            self.recordThread.sigRecordingFailed.disconnect(self.recordingFailed)
        except TypeError:
            pass
        try:
            self.recordThread.sigRecordingFinished.disconnect(self.recordFinished)
        except TypeError:
            pass
        try:
            self.recordThread.finished.disconnect(self.recordThreadStopped)
        except TypeError:
            pass

        self.recordThread.quit()
        self.frameDisplay.quit()
        if not self.recordThread.wait(10000):
            raise Exception("Timed out while waiting for rec. thread exit!")

    def acquisitionStopped(self):
        # self.toggleRecord(False)
        self.ui.acquireVideoBtn.setChecked(False)
        self.ui.acquireVideoBtn.setEnabled(True)
        for btn in [self.ui.acquireFrameBtn] + self.customButtons[0]:
            btn.setEnabled(True)

    def acquisitionStarted(self):
        self.ui.acquireVideoBtn.setChecked(True)
        self.ui.acquireVideoBtn.setEnabled(True)
        for btn in [self.ui.acquireFrameBtn] + self.customButtons[0]:
            btn.setEnabled(False)

    def acquireVideoClicked(self, b, name=None):
        if name is not None or self.ui.acquireVideoBtn.isChecked():
            self.sigStartVideoClicked.emit(name)
        else:
            self.sigStopVideoClicked.emit()

    def acquireFrameClicked(self):
        self.sigAcquireFrameClicked.emit(None)

    def pinFrameClicked(self):
        if self.ui.linkSavePinBtn.isChecked():
            self.recordThread.saveFrame()
        self.addPinnedFrame()

    def addPinnedFrame(self):
        """Make a copy of the current camera frame and pin it to the view background"""

        data = self.frameDisplay.visibleImage()
        if data is None:
            return

        hist = self.frameDisplay.contrastCtrl.ui.histogram
        im = pg.ImageItem(data, levels=hist.getLevels(), lut=hist.getLookupTable(img=data), removable=True)
        im.sigRemoveRequested.connect(self.removePinnedFrame)
        if len(self.pinnedFrames) == 0:
            z = -10000
        else:
            z = self.pinnedFrames[-1].zValue() + 1
        im.setZValue(z)

        self.pinnedFrames.append(im)
        view = self.frameDisplay.imageItem().getViewBox()
        if view is not None:
            view.addItem(im)
        im.setTransform(self.frameDisplay.currentFrame.globalTransform().as2D())

    def removePinnedFrame(self, fr):
        self.pinnedFrames.remove(fr)
        if fr.scene() is not None:
            fr.scene().removeItem(fr)
        fr.sigRemoveRequested.disconnect(self.removePinnedFrame)
        
    def clearPinnedFramesClicked(self):
        if Qt.QMessageBox.question(self, "Really?", "Clear all pinned frames?", Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel) == Qt.QMessageBox.Ok:
            self.clearPinnedFrames()

    def clearPinnedFrames(self):
        for frame in self.pinnedFrames[:]:
            self.removePinnedFrame(frame)

    def threadSavedFrame(self, file):
        # Called when the recording thread saves a single frame
        if file is False:
            self.ui.saveFrameBtn.failure("Error.")
        else:            
            self.ui.saveFrameBtn.success("Saved.")









