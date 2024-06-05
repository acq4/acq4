import functools

import numpy as np
import scipy.ndimage
from typing import Optional, Union, Callable

from acq4.util import Qt, ptime
from acq4.util.imaging.background import remove_background_from_image

Ui_Form = Qt.importTemplate(".bg_subtract_template")


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

        self.backgroundFrame: Optional[np.ndarray] = None
        self.blurredBackgroundFrame = None
        self.lastFrameTime = None
        self.requestBgReset = False
        self._cachedDeferredSave = None

        # Connect Background Subtraction Dock
        self.ui.bgBlurSpin.valueChanged.connect(self.updateBackgroundBlur)
        self.ui.collectBgBtn.clicked.connect(self.collectBgClicked)
        self.ui.divideBgBtn.clicked.connect(self.divideClicked)
        self.ui.subtractBgBtn.clicked.connect(self.subtractClicked)
        self.ui.bgBlurSpin.valueChanged.connect(self.needFrameUpdate)

    def divideClicked(self):
        self.needFrameUpdate.emit()
        self.ui.subtractBgBtn.setChecked(False)
        self._cachedDeferredSave = None

    def subtractClicked(self):
        self.needFrameUpdate.emit()
        self.ui.divideBgBtn.setChecked(False)
        self._cachedDeferredSave = None

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
                self.bgStartTime = ptime.time()
            self.ui.collectBgBtn.setText("Collecting...")
        else:
            self.ui.collectBgBtn.setText("Collect Background")

    def includeNewFrame(self, frame):
        now = ptime.time()
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
            # stop collecting bg frames if we are in static mode and time is up
            timeLeft = self.ui.bgTimeSpin.value() - (ptime.time() - self.bgStartTime)
            if timeLeft > 0:
                self.ui.collectBgBtn.setText(f"Collecting... ({int(timeLeft + 1)})")
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
            self.backgroundFrame = x * self.backgroundFrame + (1 - x) * img
        self.blurredBackgroundFrame = None
        self._cachedDeferredSave = None

    def deferredSave(self) -> "None | Callable[[DirHandle], str]":
        if self.backgroundFrame is None:
            return None
        if self._cachedDeferredSave is None:
            info = {
                "subtract": self.ui.subtractBgBtn.isChecked(),
                "divide": self.ui.divideBgBtn.isChecked(),
                "blur": self.ui.bgBlurSpin.value(),
            }
            frame = self.backgroundFrame

            @functools.cache
            def do_save(dh: "DirHandle") -> str:
                fh = dh.writeFile(frame, "background.tif", info, fileType="ImageFile", autoIncrement=True)
                return fh.shortName()
            self._cachedDeferredSave = do_save
        return self._cachedDeferredSave

    def processImage(self, data: np.ndarray) -> np.ndarray:
        return remove_background_from_image(
            data,
            self.getBackgroundFrame(),
            self.ui.subtractBgBtn.isChecked(),
            self.ui.divideBgBtn.isChecked(),
            # we cache our blur, so don't also apply it here
            # self.ui.bgBlurSpin.value(),
        )


