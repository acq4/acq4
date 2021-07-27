from __future__ import print_function

import pyqtgraph as pg

from acq4.util import Qt
from acq4.util.cuda import shouldUseCuda, cupy
from acq4.util.debug import printExc
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
        self.bgCtrl.needFrameUpdate.connect(self.updateFrame)

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
        self.frameTimer.timeout.connect(self.drawFrame)
        self.frameTimer.start(self._msPerFrame)  # draw frames no faster than 60Hz
        # Qt.QTimer.singleShot(1, self.drawFrame)
        # avoiding possible singleShot-induced crashes

    def updateFrame(self):
        """Redisplay the current frame.
        """
        self._updateFrame = True
        self.contrastCtrl.resetAutoGain()

    def imageItem(self):
        return self._imageItem

    def contrastWidget(self):
        return self.contrastCtrl

    def backgroundWidget(self):
        return self.bgCtrl

    def backgroundFrame(self):
        """Return the currently active background image or None if background
        subtraction is disabled.
        """
        return self.bgCtrl.backgroundFrame()

    def visibleImage(self):
        """Return a copy of the image as it is currently visible in the scene.
        """
        if self.currentFrame is None:
            return
        return self.currentFrame.getImage()

    def newFrame(self, frame):
        # lf = None
        # if self.nextFrame is not None:
        #     lf = self.nextFrame
        # elif self.currentFrame is not None:
        #     lf = self.currentFrame

        # self.nextFrame gets picked up by drawFrame() at some point
        self.nextFrame = frame

        self.bgCtrl.newFrame(frame)

    def drawFrame(self):
        if self.hasQuit:
            return
        try:
            # If we last drew a frame < 1/30s ago, return.
            t = pg.ptime.time()
            if (self.lastDrawTime is not None) and (t - self.lastDrawTime < self._sPerFrame):
                return
            # if there is no new frame and no controls have changed, just exit
            if not self._updateFrame and self.nextFrame is None:
                return
            self._updateFrame = False

            # If there are no new frames and no previous frames, then there is nothing to draw.
            if self.currentFrame is None and self.nextFrame is None:
                return

            prof = pg.debug.Profiler()
            # We will now draw a new frame (even if the frame is unchanged)
            if self.lastDrawTime is not None:
                fps = 1.0 / (t - self.lastDrawTime)
                self.displayFps = fps
            self.lastDrawTime = t
            prof()

            # Handle the next available frame, if there is one.
            if self.nextFrame is not None:
                self.currentFrame = self.nextFrame
                self.nextFrame = None

            data = self.currentFrame.getImage()
            # if we got a stack of frames, just display the first one. (not sure what else we could do here..)
            if data.ndim == 3:
                data = data[0]
            prof()

            # divide the background out of the current frame if needed
            data = self.bgCtrl.processImage(data)
            prof()

            # Set new levels if auto gain is enabled
            self.contrastCtrl.processImage(data)
            prof()

            if shouldUseCuda():
                self._imageItem.updateImage(cupy.asarray(data))
            else:
                self._imageItem.updateImage(data.copy())
            prof()

            self.imageUpdated.emit(self.currentFrame)
            prof()

            prof.finish()

        except Exception:
            printExc("Error while drawing new frames:")

    def quit(self):
        self._imageItem = None
        self.hasQuit = True
