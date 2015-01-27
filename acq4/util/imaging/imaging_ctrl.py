
from PyQt4 import QtGui, QtCore
from acq4 import pyqtgraph as pg
from .frame_display import FrameDisplay
from .imaging_template import Ui_Form
from .record_thread import RecordThread
from acq4.util.debug import printExc


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

    frameDisplayClass = FrameDisplay  # let subclasses override this class


    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        self.frameDisplay = self.frameDisplayClass()

        self.pinnedFrames = []

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
        self.ui.recordStackBtn.toggled.connect(self.toggleRecord)
        self.ui.saveFrameBtn.clicked.connect(self.saveFrameClicked)
        self.ui.pinFrameBtn.clicked.connect(self.addPinnedFrame)

    def newFrame(self, frame):
        self.ui.saveFrameBtn.setEnabled(True)
        self.ui.pinFrameBtn.setEnabled(True)

        fps = self.frameDisplay.acquireFps
        if fps is not None:
            self.ui.fpsLabel.setValue(fps)
        fps = self.frameDisplay.displayFps
        if fps is not None:
            self.ui.displayFpsLabel.setValue(fps)

        self.recordThread.newFrame(frame)
        self.ui.stackSizeLabel.setText('%d frames' % self.recordThread.stackSize)

    def saveFrameClicked(self):
        if self.ui.linkSavePinBtn.isChecked():
            self.addPinnedFrame()
        self.recordThread.saveFrame()

    def toggleRecord(self, b):
        if b:
            self.ui.recordStackBtn.setChecked(True)
            self.ui.recordXframesCheck.setEnabled(False)
            self.ui.recordXframesSpin.setEnabled(False)
            if self.ui.recordXframesCheck.isChecked():
                frameLimit = self.ui.recordXframesSpin.value()
            else:
                frameLimit = None
            self.recordThread.startRecording(frameLimit)
        else:
            self.ui.recordStackBtn.setChecked(False)
            self.ui.recordXframesCheck.setEnabled(True)
            self.ui.recordXframesSpin.setEnabled(True)
            self.recordThread.stopRecording()

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
            # self.recordThread.sigShowMessage.disconnect(self.showMessage)
            self.recordThread.finished.disconnect(self.recordThreadStopped)
            self.recordThread.sigRecordingFailed.disconnect(self.recordingFailed)
            self.recordThread.sigRecordingFinished.disconnect(self.recordFinished)
        except TypeError:
            pass

        self.recordThread.quit()
        if not self.recordThread.wait(10000):
            raise Exception("Timed out while waiting for rec. thread exit!")

    def acquisitionStopped(self):
        self.toggleRecord(False)
        self.ui.acquireVideoBtn.setChecked(False)
        self.ui.acquireVideoBtn.setEnabled(True)

    def acquisitionStarted(self):
        self.ui.acquireVideoBtn.setChecked(True)
        self.ui.acquireVideoBtn.setEnabled(True)

    def acquireVideoClicked(self):
        acq = self.ui.acquireVideoBtn.isChecked()
        self.sigAcquireVideoClicked.emit(acq)

    def acquireFrameClicked(self):
        self.sigAcquireFrameClicked.emit()

    def addPinnedFrame(self):
        """Make a copy of the current camera frame and pin it to the view background"""
        if self.ui.linkSavePinBtn.isChecked():
            self.saveFrameClicked()

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
        im.setTransform(self.frameDisplay.imageItem().globalTransform().as2D())

    def removePinnedFrame(self, fr):
        self.pinnedFrames.remove(fr)
        if fr.scene() is not None:
            fr.scene().removeItem(fr)
        fr.sigRemoveRequested.disconnect(self.removePinnedFrame)
        
    def threadSavedFrame(self, file):
        # Called when the recording thread saves a single frame
        if file is False:
            self.ui.saveFrameBtn.failure("Error.")
        else:            
            self.ui.saveFrameBtn.success("Saved.")









