import numpy as np
import scipy.ndimage
from typing import Optional, Union

from acq4.util import Qt, ptime
from acq4.util.DataManager import DirHandle

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
        self._cachedSaveName = None

        # Connect Background Subtraction Dock
        self.ui.bgBlurSpin.valueChanged.connect(self.updateBackgroundBlur)
        self.ui.collectBgBtn.clicked.connect(self.collectBgClicked)
        self.ui.divideBgBtn.clicked.connect(self.divideClicked)
        self.ui.subtractBgBtn.clicked.connect(self.subtractClicked)
        self.ui.bgBlurSpin.valueChanged.connect(self.needFrameUpdate)

    def divideClicked(self):
        self.needFrameUpdate.emit()
        self.ui.subtractBgBtn.setChecked(False)
        self._cachedSaveName = None

    def subtractClicked(self):
        self.needFrameUpdate.emit()
        self.ui.divideBgBtn.setChecked(False)
        self._cachedSaveName = None

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

    def newFrame(self, frame):
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
        self._cachedSaveName = None

    def save(self, dh: DirHandle) -> Union[None, str]:
        if self._cachedSaveName is None:
            if self.backgroundFrame is None or not (
                    self.ui.subtractBgBtn.isChecked() or self.ui.divideBgBtn.isChecked()
            ):
                return None
            info = {
                "subtract": self.ui.subtractBgBtn.isChecked(),
                "divide": self.ui.divideBgBtn.isChecked(),
                "blur": self.ui.bgBlurSpin.value(),
            }
            fh = dh.writeFile(self.backgroundFrame, "background.tif", info, fileType="ImageFile", autoIncrement=True)
            self._cachedSaveName = fh.shortName()
        return self._cachedSaveName

    def processImage(self, data: np.ndarray) -> np.ndarray:
        return remove_background_from_image(
            data,
            self.getBackgroundFrame(),
            self.ui.subtractBgBtn.isChecked(),
            self.ui.divideBgBtn.isChecked(),
            # we cache our blur, so don't also do it here
            # self.ui.bgBlurSpin.value(),
        )


def remove_background_from_image(
    image: np.ndarray, bg: Optional[np.ndarray], subtract: bool = True, divide: bool = False, blur: float = 0.0
):
    if bg is None:
        return image
    if blur > 0.0:
        bg = scipy.ndimage.gaussian_filter(bg, (blur, blur))
    if divide:
        return image / bg
    if subtract:
        return image - bg
    return image
