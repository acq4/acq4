from __future__ import print_function
import scipy.ndimage
import numpy as np
from acq4.util import Qt

from acq4 import pyqtgraph as pg
from .bg_subtract_template import Ui_Form


class BgSubtractCtrl(Qt.QWidget):
    """Widget for controlling background subtraction for live imaging.

    Provides:
    * background collection / averaging
    * subtract / divide background
    * background blur for unsharp masking
    * continuous averaging
    """
    needFrameUpdate = Qt.Signal()

    def __init__(self, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self.backgroundFrame = None
        self.blurredBackgroundFrame = None
        self.lastFrameTime = None
        self.requestBgReset = False

        ## Connect Background Subtraction Dock
        self.ui.bgBlurSpin.valueChanged.connect(self.updateBackgroundBlur)
        self.ui.collectBgBtn.clicked.connect(self.collectBgClicked)
        self.ui.divideBgBtn.clicked.connect(self.divideClicked)
        self.ui.subtractBgBtn.clicked.connect(self.subtractClicked)
        self.ui.bgBlurSpin.valueChanged.connect(self.needFrameUpdate)

    def divideClicked(self):
        self.needFrameUpdate.emit()
        self.ui.subtractBgBtn.setChecked(False)

    def subtractClicked(self):
        self.needFrameUpdate.emit()
        self.ui.divideBgBtn.setChecked(False)

    def getBackgroundFrame(self):
        if self.backgroundFrame is None:
            return None
        if self.blurredBackgroundFrame is None:
            self.updateBackgroundBlur()
        return self.blurredBackgroundFrame

    def updateBackgroundBlur(self):
        b = self.ui.bgBlurSpin.value()
        if b > 0.0:
            self.blurredBackgroundFrame = scipy.ndimage.gaussian_filter(self.backgroundFrame, (b, b))
        else:
            self.blurredBackgroundFrame = self.backgroundFrame

    def collectBgClicked(self, checked):
        if checked:
            if not self.ui.contAvgBgCheck.isChecked():
                # don't reset the background frame just yet; anyone may call processImage()
                # before the next frame arrives.
                self.requestBgReset = True
                self.bgFrameCount = 0
                self.bgStartTime = pg.ptime.time()
            self.ui.collectBgBtn.setText("Collecting...")
        else:
            self.ui.collectBgBtn.setText("Collect Background")

    def newFrame(self, frame):
        now = pg.ptime.time()
        if self.lastFrameTime is None:
            dt = 0
        else:
            dt = now - self.lastFrameTime
        self.lastFrameTime = now
        if not self.ui.collectBgBtn.isChecked():
            return
        
        # integrate new frame into background
        if self.ui.contAvgBgCheck.isChecked():
            x = np.exp(-dt * 5 / max(self.ui.bgTimeSpin.value(), 0.01))
        else:
            ## stop collecting bg frames if we are in static mode and time is up
            timeLeft = self.ui.bgTimeSpin.value() - (pg.ptime.time()-self.bgStartTime)
            if timeLeft > 0:
                self.ui.collectBgBtn.setText("Collecting... (%d)" % int(timeLeft+1))
            else:
                self.ui.collectBgBtn.setChecked(False)
                self.ui.collectBgBtn.setText("Collect Background")

            x = float(self.bgFrameCount) / (self.bgFrameCount + 1)
            self.bgFrameCount += 1
    
        img = frame.getImage().astype(np.float32)
        if self.requestBgReset or self.backgroundFrame is None or self.backgroundFrame.shape != img.shape:
            self.requestBgReset = False
            self.backgroundFrame = img
            self.needFrameUpdate.emit()
        else:
            self.backgroundFrame = x * self.backgroundFrame + (1-x) * img
        self.blurredBackgroundFrame = None
        
    def processImage(self, data):
        if self.ui.divideBgBtn.isChecked():
            bg = self.getBackgroundFrame()
            if bg is not None and bg.shape == data.shape:
                data = data / bg
        elif self.ui.subtractBgBtn.isChecked():
            bg = self.getBackgroundFrame()
            if bg is not None and bg.shape == data.shape:
                data = data - bg

        return data
