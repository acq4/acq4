
from .frame_display import FrameDisplay
from .imaging_template import Ui_Form
from .record_thread import RecordThread


class ImagingCtrl(QtGui.QWidget):
    """Control widget used to interact with imaging devices. 

    Provides:

    * Acquire frame / video controls
    * Save frame, pin frame
    * Record stack
    * FPS display
    """

    sigAcquireVideoClicked = QtCore.Signal(object)  # bool
    sigAcquireFrameClicked = QtCore.Signal()

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        self.pinnedFrames = []

        self.ui = Ui_Form()
        self.ui.setupUi(selr)

        ## format labels
        self.ui.fpsLabel.setFormatStr('{avgValue:.1f} fps')
        self.ui.fpsLabel.setAverageTime(2.0)
        self.ui.displayFpsLabel.setFormatStr('{avgValue:.1f} fps')
        self.ui.displayFpsLabel.setAverageTime(2.0)
        self.ui.displayPercentLabel.setFormatStr('({avgValue:.1f}%)')
        self.ui.displayPercentLabel.setAverageTime(4.0)

        ## set up recording thread
        self.recordThread = RecordThread(self)
        self.recordThread.start()
        self.recordThread.sigShowMessage.connect(self.showMessage)
        self.recordThread.finished.connect(self.recordThreadStopped)
        self.recordThread.sigRecordingFinished.connect(self.recordFinished)
        self.recordThread.sigRecordingFailed.connect(self.recordingFailed)

        ## connect UI signals
        self.ui.acquireVideoBtn.clicked.connect(self.toggleAcquire)
        self.ui.recordStackBtn.toggled.connect(self.toggleRecord)
        self.ui.pinFrameBtn.clicked.connect(self.addPinnedFrame)

    def newFrame(self, frame):
        fps = self.frameDisplay.acquireFps
        if fps is not None:
            self.ui.fpsLabel.setValue(fps)
        fps = self.frameDisplay.displayFps
        if fps is not None:
            self.ui.displayFpsLabel.setValue(fps)

    def toggleRecord(self, b):
        if b:
            self.ui.recordStackBtn.setChecked(True)
            self.ui.recordXframesCheck.setEnabled(False)
            self.ui.recordXframesSpin.setEnabled(False)
        else:
            self.ui.recordStackBtn.setChecked(False)
            self.ui.recordXframesCheck.setEnabled(True)
            self.ui.recordXframesSpin.setEnabled(True)

    def recordFinished(self):
        self.toggleRecord(False)

    def recordThreadStopped(self):
        self.toggleRecord(False)
        self.ui.recordStackBtn.setEnabled(False)  ## Recording thread has stopped, can't record anymore.
        printExc("Recording thread died! See console for error message.")

    def recordingFailed(self):
        self.toggleRecord(False)
        printExc("Recording failed! See console for error message.")


    def quit(self):
        try:
            self.recordThread.sigShowMessage.disconnect(self.showMessage)
            self.recordThread.finished.disconnect(self.recordThreadStopped)
            self.recordThread.sigRecordingFailed.disconnect(self.recordingFailed)
            self.recordThread.sigRecordingFinished.disconnect(self.recordFinished)
        except TypeError:
            pass

        if self.recordThread.isRunning():
            self.recordThread.stop()
            if not self.recordThread.wait(10000):
                raise Exception("Timed out while waiting for rec. thread exit!")
        del self.recordThread  ## Required due to cyclic reference

    def acquisitionStopped(self):
        self.toggleRecord(False)
        self.ui.acquireVideoBtn.setChecked(False)
        self.ui.acquireVideoBtn.setEnabled(True)

    def acquisitionStarted(self):
        self.ui.acquireVideoBtn.setChecked(True)
        self.ui.acquireVideoBtn.setEnabled(True)

    def toggleAcquire(self):
        acq self.ui.acquireVideoBtn.isChecked()
        self.sigAcquireClicked.emit(acq)

    def addPinnedFrame(self):
        """Make a copy of the current camera frame and pin it to the view background"""
        data = self.frameDisplay.visibleImage()
        if data is None:
            return

        im = pg.ImageItem(data, levels=self.ui.histogram.getLevels(), lut=self.ui.histogram.getLookupTable(img=data), removable=True)
        im.sigRemoveRequested.connect(self.removePinnedFrame)
        if len(self.pinnedFrames) == 0:
            z = -10000
        else:
            z = self.pinnedFrames[-1].zValue() + 1

        self.pinnedFrames.append(im)
        self.module.addItem(im, z=z)
        im.setTransform(self.currentFrame.globalTransform().as2D())

    def removePinnedFrame(self, fr):
        self.pinnedFrames.remove(fr)
        self.module.removeItem(fr)
        fr.sigRemoveRequested.disconnect(self.removePinnedFrame)
        
