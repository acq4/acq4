import scipy.ndimage
from PyQt4 import QtCore, QtGui
from acq4 import pyqtgraph as pg
from .bg_subtract_template import Ui_Form


class BgSubtractCtrl(QtGui.QWidget):
    """Widget for controlling background subtraction for live imaging.

    Provides:
    * background collection / averaging
    * subtract / divide background
    * background blur for unsharp masking
    * continuous averaging
    """
    needFrameUpdate = QtCore.Signal()

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self.backgroundFrame = None
        self.blurredBackgroundFrame = None

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
                self.backgroundFrame = None ## reset background frame
                self.bgFrameCount = 0
                self.bgStartTime = pg.ptime.time()
            self.ui.collectBgBtn.setText("Collecting...")
        else:
            self.ui.collectBgBtn.setText("Collect Background")

    def newFrame(self, frame):
        ## stop collecting bg frames if we are in static mode and time is up
        if self.ui.collectBgBtn.isChecked() and not self.ui.contAvgBgCheck.isChecked():
            timeLeft = self.ui.bgTimeSpin.value() - (pg.ptime.time()-self.bgStartTime)
            if timeLeft > 0:
                self.ui.collectBgBtn.setText("Collecting... (%d)" % int(timeLeft+1))
            else:
                self.ui.collectBgBtn.setChecked(False)
                self.ui.collectBgBtn.setText("Collect Background")
        
        if self.ui.collectBgBtn.isChecked():
            if self.ui.contAvgBgCheck.isChecked():
                x = 1.0 - 1.0 / (self.ui.bgTimeSpin.value()+1.0)
            else:
                x = float(self.bgFrameCount)/(self.bgFrameCount + 1)
                self.bgFrameCount += 1
            
            if self.backgroundFrame == None or self.backgroundFrame.shape != frame.data().shape:
                self.backgroundFrame = frame.data().astype(float)
            else:
                self.backgroundFrame = x * self.backgroundFrame + (1-x)*frame.data().astype(float)
        
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
