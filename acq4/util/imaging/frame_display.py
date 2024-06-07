import pyqtgraph as pg
from acq4.util import Qt, ptime
from acq4.util.cuda import shouldUseCuda, cupy
from acq4.util.debug import printExc
from pyqtgraph.debug import Profiler
from .bg_subtract_ctrl import BgSubtractCtrl
from .contrast_ctrl import ContrastCtrl


class FrameDisplay(Qt.QObject):
    """Used with live imaging to hold the most recently acquired frame and allow
    user control of contrast, gain, and background subtraction.

    Provides:
    * frame rate limiting
    * contrast control widget
    * background subtraction control widget
    """

    # Allow subclasses to override these:
    contrastClass = ContrastCtrl
    bgSubtractClass = BgSubtractCtrl

    imageUpdated = Qt.Signal(object)  # emits frame when the image is redrawn
    sigDrawNewFrame = Qt.Signal(object)  # frame

    def __init__(self, maxFPS=30):
        Qt.QObject.__init__(self)

        self._maxFPS = maxFPS
        self._sPerFrame = 1.0 / maxFPS
        self._msPerFrame = int(self._sPerFrame * 1000)
        self._imageItem = pg.ImageItem()  # Implicitly depends on global setConfigOption state
        self._imageItem.setAutoDownsample(True)
        self.contrastCtrl = self.contrastClass()
        self.contrastCtrl.setImageItem(self._imageItem)
        self.bgCtrl = self.bgSubtractClass()
        self.bgCtrl.needFrameUpdate.connect(self.backgroundChanged)

        self.nextFrame = None
        self._updateFrame = False
        self.currentFrame = None
        self.lastDrawTime = None
        self.displayFps = None
        self.hasQuit = False

        # Check for new frame updates every 16ms
        # Some checks may be skipped even if there is a new frame waiting to avoid drawing more than
        # 60fps.
        self.frameTimer = Qt.QTimer()
        self.frameTimer.timeout.connect(self.checkForDraw)
        self.frameTimer.start(self._msPerFrame)  # draw frames no faster than 60Hz
        # Qt.QTimer.singleShot(1, self.drawFrame)
        # avoiding possible singleShot-induced crashes
        self.sigDrawNewFrame.connect(self._drawFrameInGui)

        self.contrastCtrl.sigOutputStateChanged.connect(self.contrastChanged)

    def backgroundChanged(self):
        """Background removal options have changed; redisplay and reset auto gain
        """
        self._updateFrame = True
        self.contrastCtrl.resetAutoGain()

    def contrastChanged(self):
        """Contrast controls have changed; redisplay
        """
        self._updateFrame = True

    def imageItem(self):
        return self._imageItem

    def contrastWidget(self):
        return self.contrastCtrl

    def backgroundWidget(self):
        return self.bgCtrl

    def visibleImage(self):
        """Return a copy of the image as it is currently visible in the scene.
        """
        if self.currentFrame is None:
            return
        return self.currentFrame.getImage()

    def newFrame(self, frame):
        # integrate new frame into background
        self.bgCtrl.includeNewFrame(frame)
        # possibly draw the frame and update auto gain (rate limited)
        self.checkForDraw(frame)
        # annotate frame with background and contrast info
        frame.addInfo(backgroundInfo=self.bgCtrl.deferredSave(), contrastInfo=self.contrastCtrl.saveState())

    def checkForDraw(self, frame=None):
        if self.hasQuit:
            return
        try:
            # If we last drew a frame < 1/30s ago, return.
            t = ptime.time()
            if (self.lastDrawTime is not None) and (t - self.lastDrawTime < self._sPerFrame):
                return
            # if there is no new frame and no controls have changed, just exit
            if frame is None and not self._updateFrame:
                return
            self._updateFrame = False

            prof = Profiler()
            prof()

            # If there are no new frames and no previous frames, then there is nothing to draw.
            if self.currentFrame is None and frame is None:
                return

            # Handle the next available frame, if there is one.
            if frame is not None:
                self.currentFrame = frame
            data = self.currentFrame.getImage()
            prof()

            # divide the background out of the current frame if needed
            data = self.bgCtrl.processImage(data)
            prof()

            # Set new levels if auto gain is enabled
            self.contrastCtrl.updateWithImage(data)
            prof()

            self.sigDrawNewFrame.emit(data)
            prof.finish()

        except Exception:
            printExc("Error while drawing new frames:")

    def _drawFrameInGui(self, data):
        # We will now draw a new frame (even if the frame is unchanged)
        t = ptime.time()
        if (self.lastDrawTime is not None) and (t - self.lastDrawTime < self._sPerFrame):
            return
        if self.lastDrawTime is not None:
            fps = 1.0 / (t - self.lastDrawTime)
            self.displayFps = fps
        self.lastDrawTime = t
        if shouldUseCuda():
            self._imageItem.updateImage(cupy.asarray(data))
        else:
            self._imageItem.updateImage(data.copy())

        self.imageUpdated.emit(self.currentFrame)

    def quit(self):
        self._imageItem = None
        self.hasQuit = True
