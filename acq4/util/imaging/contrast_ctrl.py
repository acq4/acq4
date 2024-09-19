import numpy as np

from acq4.util import Qt

Ui_Form = Qt.importTemplate(".contrast_ctrl_template")


class ContrastCtrl(Qt.QWidget):
    """Widget for controlling contrast with rapidly updating image content.

    Provides:
    * image histogram
    * contrast control
    * color lookup table
    * automatic gain control
    * center weighted gain control
    * zoom-to-image button
    """

    sigAutoGainChanged = Qt.Signal()
    sigOutputStateChanged = Qt.Signal()

    def __init__(self, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self.imageItem = None
        self.lastMinMax = None  # Records most recently measured maximum/minimum image values
        self.autoGainLevels = [0.0, 1.0]
        self.ignoreLevelChange = False
        self.alpha = 1.0
        self._cached_state = None
        self.centerAutoGainWeight = 1
        self.autoGainSpeed = 0
        self.lastAGCMax = None
        self.lastLevels = None
        self.useAutoGain = True
        self.uiValuesChanged()

        # Connect DisplayGain dock
        self.ui.histogram.sigLookupTableChanged.connect(self.lutChanged)
        self.ui.histogram.sigLevelsChanged.connect(self.levelsChanged)
        self.ui.btnAutoGain.toggled.connect(self.toggleAutoGain)
        self.ui.btnAutoGain.setChecked(True)
        self.ui.zoomLiveBtn.clicked.connect(self.zoomToImage)
        self.ui.alphaSlider.valueChanged.connect(self.alphaChanged)
        self.sigAutoGainChanged.connect(self._updateGuiAutoGainLevels)
        self.ui.spinAutoGainCenterWeight.valueChanged.connect(self.uiValuesChanged)
        self.ui.spinAutoGainSpeed.valueChanged.connect(self.uiValuesChanged)

    def uiValuesChanged(self):
        # leave these to be picked up by other threads
        self._cached_state = None
        self.centerAutoGainWeight = self.ui.spinAutoGainCenterWeight.value()
        self.autoGainSpeed = self.ui.spinAutoGainSpeed.value()

    def setImageItem(self, item):
        """Sets the ImageItem that will be affected by the contrast / color controls
        """
        self.imageItem = item
        self.ui.histogram.setImageItem(item)
        self.ui.histogram.fillHistogram(False)  # for speed

    def zoomToImage(self):
        """Zoom the image's view such that the image fills most of the view.
        """
        self.imageItem.getViewBox().autoRange(items=[self.imageItem])

    def lutChanged(self):
        self._cached_state = None
        self.sigOutputStateChanged.emit()

    def levelsChanged(self):
        if self.lastMinMax is None or not self.ui.btnAutoGain.isChecked() or self.ignoreLevelChange:
            return
        bl, wl = self.getLevels()
        mn, mx = self.lastMinMax
        rng = float(mx - mn)
        if rng == 0:
            return
        newLevels = [(bl - mn) / rng, (wl - mn) / rng]
        self.autoGainLevels = newLevels
        self._cached_state = None
        self.sigOutputStateChanged.emit()

    def alphaChanged(self, val):
        self.alpha = val / self.ui.alphaSlider.maximum()  # slider only works in integers, and we need a 0 to 1 value
        self._cached_state = None
        self.imageItem.setOpacity(self.alpha)

    def getLevels(self):
        return self.ui.histogram.getLevels()

    def saveState(self):
        if self._cached_state is None:
            self._cached_state = {
                'levels': self.getLevels(),
                'gradient': self.ui.histogram.gradient.saveState()
            }
        return self._cached_state

    def toggleAutoGain(self, b):
        self.useAutoGain = b
        if b:
            self.lastAGCMax = None
            self.ui.histogram.vb.setMouseEnabled(x=False, y=False)
        else:
            self.ui.histogram.vb.setMouseEnabled(x=False, y=True)

    def resetAutoGain(self):
        """Causes the AGC to immediately scale to the next frame that arrives. This is called
        when a sudden change in the image values is expected.
        """
        self.lastMinMax = None

    def updateWithImage(self, data: np.ndarray) -> None:
        # Thread safe function! We expect this to be called from a non-gui thread.

        # Update auto gain for new image
        # Note that histogram is linked to image item; this is what determines
        # the final appearance of the image.

        if not self.useAutoGain:
            return
        cw = self.centerAutoGainWeight
        (w, h) = data.shape
        center = data[w // 2 - w // 6 : w // 2 + w // 6, h // 2 - h // 6 : h // 2 + h // 6]

        reduced = data
        while reduced.size > 2 ** 16:
            ax = np.argmax(reduced.shape)
            sl = [slice(None, None)] * data.ndim
            sl[ax] = slice(None, None, 2)
            reduced = reduced[tuple(sl)]

        minVal = reduced.min() * (1.0 - cw) + center.min() * cw
        maxVal = reduced.max() * (1.0 - cw) + center.max() * cw

        # If there is inf/nan in the image, strip it out before computing min/max
        if any([np.isnan(minVal), np.isinf(minVal), np.isnan(minVal), np.isinf(minVal)]):
            nanMask = np.isnan(reduced)
            infMask = np.isinf(reduced)
            valid = reduced[~nanMask * ~infMask]
            minVal = valid.min() * (1.0 - cw) + center.min() * cw
            maxVal = valid.max() * (1.0 - cw) + center.max() * cw

        # Smooth min/max range to avoid noise
        if self.lastMinMax is None:
            minVal = minVal
            maxVal = maxVal
        else:
            s = 1.0 - 1.0 / (self.autoGainSpeed + 1.0)
            minVal = self.lastMinMax[0] * s + minVal * (1.0 - s)
            maxVal = self.lastMinMax[1] * s + maxVal * (1.0 - s)

        self.lastMinMax = [minVal, maxVal]

        # and convert fraction of previous range into new levels
        bl = self.autoGainLevels[0] * (maxVal - minVal) + minVal
        wl = self.autoGainLevels[1] * (maxVal - minVal) + minVal
        self.lastLevels = [bl, wl]

        self.ignoreLevelChange = True
        self._cached_state = None
        self.sigAutoGainChanged.emit()  # ask GUI to update for new levels

    def _updateGuiAutoGainLevels(self):
        # Called by signal when processing a new frame causes auto gain levels to change
        bl, wl = self.lastLevels
        minVal, maxVal = self.lastMinMax
        try:
            self.ui.histogram.setLevels(bl, wl)
            self.ui.histogram.setHistogramRange(minVal, maxVal, padding=0.05)
        finally:
            self.ignoreLevelChange = False

        self.imageItem.setOpacity(self.alpha)
