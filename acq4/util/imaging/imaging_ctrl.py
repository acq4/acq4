import pyqtgraph as pg

from acq4.util import Qt, ptime
from acq4.util.debug import printExc
from .frame_display import FrameDisplay
from .record_thread import RecordThread

Ui_Form = Qt.importTemplate(".imaging_template")


class ImagingCtrl(Qt.QWidget):
    """Control widget used to interact with imaging devices. 

    Provides:

    * Acquire frame / video controls
    * Save frame, pin frame
    * Record stack
    * FPS display
    * Internal FrameDisplay that handles rendering the image.
    * Contrast controls
    * Background subtraction controls

    Basic usage:
    
    * Place self.frameDisplay.imageItem() in a ViewBox.
    * Display this widget along with self.contrastCtrl and .bgCtrl to provide
      the user interface.
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
    sigUpdateUi = Qt.Signal()

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

        # format labels
        self._fps = 0
        self._lastDrawTime = ptime.time()
        self.ui.fpsLabel.setFormatStr("{avgValue:.1f} fps")
        self.ui.fpsLabel.setAverageTime(2.0)
        self.ui.displayFpsLabel.setFormatStr("{avgValue:.1f} fps")
        self.ui.displayFpsLabel.setAverageTime(2.0)
        self.ui.displayPercentLabel.setFormatStr("({avgValue:.1f}%)")
        self.ui.displayPercentLabel.setAverageTime(4.0)

        # disabled until first frame arrives
        self.ui.saveFrameBtn.setEnabled(False)
        self.ui.pinFrameBtn.setEnabled(False)

        # set up recording thread
        self.recordThread = RecordThread(self)
        self.recordThread.start()
        # self.recordThread.sigShowMessage.connect(self.showMessage)
        self.recordThread.finished.connect(self.recordThreadStopped)
        self.recordThread.sigRecordingFinished.connect(self.recordFinished)
        self.recordThread.sigRecordingFailed.connect(self.recordingFailed)
        self.recordThread.sigSavedFrame.connect(self.threadSavedFrame)

        # connect UI signals
        self.ui.acquireVideoBtn.clicked.connect(self.acquireVideoClicked)
        self.ui.acquireFrameBtn.clicked.connect(self.acquireFrameClicked)
        self.ui.recordStackBtn.toggled.connect(self.recordStackToggled)
        self.ui.saveFrameBtn.clicked.connect(self.saveFrameClicked)
        self.ui.pinFrameBtn.clicked.connect(self.pinFrameClicked)
        self.ui.clearPinnedFramesBtn.clicked.connect(self.clearPinnedFramesClicked)
        self.sigUpdateUi.connect(self.updateUi)

    def addFrameButton(self, name):
        """Add a new button below the original "Acquire Frame" button.

        When this button is clicked, the sigAcquireFrameClicked signal is emitted
        with *name* as the first argument.
        """
        btn = Qt.QPushButton(name)
        btn.setObjectName(name)
        self.customButtons[0].append(btn)
        self.ui.acqBtnLayout.addWidget(btn, len(self.customButtons[0]), 0)
        btn.clicked.connect(self._onNamedFrameButtonClick)

    def _onNamedFrameButtonClick(self, checked):
        btn = self.sender()
        self.sigAcquireFrameClicked.emit(btn.objectName())

    def addVideoButton(self, name):
        """Add a new button below the original "Acquire Video" button.

        When this button is clicked, the sigAcquireVideoClicked signal is emitted
        with *name* as the first argument.
        """
        btn = Qt.QPushButton(name)
        btn.setObjectName(name)
        self.customButtons[1].append(btn)
        self.ui.acqBtnLayout.addWidget(btn, len(self.customButtons[1]), 1)
        btn.clicked.connect(self._handleNamedVideoButtonClick)

    def newFrame(self, frame):
        # update acquisition frame rate
        now = frame.info()["time"]
        if self.lastFrameTime is not None:
            dt = now - self.lastFrameTime
            if dt > 0:
                fps = 1.0 / dt
                self._fps = fps
        self.lastFrameTime = now

        if self.recordingStack():
            frameShape = frame.getImage().shape
            if self.stackShape is None:
                self.stackShape = frameShape
            elif self.stackShape != frameShape:
                # new image does not match stack shape; need to stop recording.
                self.endStack()

        self.recordThread.newFrame(frame)
        if self.ui.recordStackBtn.isChecked():
            self.ui.stackSizeLabel.setText("%d frames" % self.recordThread.stackSize)

        self.frameDisplay.newFrame(frame)
        self.sigUpdateUi.emit()

    def updateUi(self):
        now = ptime.time()
        if (now - self._lastDrawTime) < 0.5:
            return
        self._lastDrawTime = now
        self.ui.saveFrameBtn.setEnabled(True)
        self.ui.pinFrameBtn.setEnabled(True)
        self.ui.fpsLabel.setValue(self._fps)
        fps = self.frameDisplay.displayFps
        if fps is not None:
            self.ui.displayFpsLabel.setValue(fps)

    def saveFrameClicked(self):
        if self.ui.linkSavePinBtn.isChecked():
            self.pinCurrentFrame()
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
        self.ui.stackSizeLabel.setText("0 frames")
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
        self.ui.recordStackBtn.setEnabled(False)  # Recording thread has stopped, can't record anymore.
        printExc("Recording thread died! See console for error message.")

    def recordingFailed(self):
        self.endStack()
        printExc("Recording failed! See console for error message.")

    def quit(self):
        Qt.disconnect(self.recordThread.finished, self.recordThreadStopped)
        Qt.disconnect(self.recordThread.sigRecordingFailed, self.recordingFailed)
        Qt.disconnect(self.recordThread.sigRecordingFinished, self.recordFinished)
        Qt.disconnect(self.recordThread.finished, self.recordThreadStopped)

        self.recordThread.quit()
        self.frameDisplay.quit()
        if not self.recordThread.wait(10000):
            raise TimeoutError("Timed out while waiting for rec. thread exit!")

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

    def acquireVideoClicked(self, checked):
        if checked:
            self.sigStartVideoClicked.emit(None)
        else:
            self.sigStopVideoClicked.emit()

    def _handleNamedVideoButtonClick(self, checked):
        btn = self.sender()
        self.sigStartVideoClicked.emit(btn.objectName())

    def acquireFrameClicked(self):
        self.sigAcquireFrameClicked.emit(None)

    def pinFrameClicked(self):
        if self.ui.linkSavePinBtn.isChecked():
            self.recordThread.saveFrame()
        self.pinCurrentFrame()

    def pinCurrentFrame(self):
        """Make a copy of the current camera frame and pin it to the view background"""

        data = self.frameDisplay.visibleImage()
        if data is None:
            return

        hist = self.frameDisplay.contrastCtrl.ui.histogram
        im = pg.ImageItem(data, levels=hist.getLevels(), lut=hist.getLookupTable(img=data), removable=True)
        im.setTransform(self.frameDisplay.currentFrame.globalTransform().as2D())

        self.addPinnedFrame(im)

    def addPinnedFrame(self, im: pg.ImageItem):
        if len(self.pinnedFrames) == 0:
            z = -10000
        else:
            z = self.pinnedFrames[-1].zValue() + 1
        im.setZValue(z)
        im.sigRemoveRequested.connect(self.removePinnedFrame)
        self.pinnedFrames.append(im)
        view = self.frameDisplay.imageItem().getViewBox()
        if view is not None:
            view.addItem(im)

    def removePinnedFrame(self, fr):
        self.pinnedFrames.remove(fr)
        if fr.scene() is not None:
            fr.scene().removeItem(fr)
        fr.sigRemoveRequested.disconnect(self.removePinnedFrame)

    def clearPinnedFramesClicked(self):
        query = Qt.QMessageBox.question(
            self, "Really?", "Clear all pinned frames?", Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel)
        if query == Qt.QMessageBox.Ok:
            self.clearPinnedFrames()

    def clearPinnedFrames(self):
        for frame in self.pinnedFrames[:]:
            self.removePinnedFrame(frame)

    def threadSavedFrame(self, filename):
        # Called when the recording thread saves a single frame
        if filename is False:
            self.ui.saveFrameBtn.failure("Error.")
        else:
            self.ui.saveFrameBtn.success("Saved.")
