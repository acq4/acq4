from __future__ import print_function

import pyqtgraph as pg

from acq4.util import Qt
from acq4.util.Thread import Thread
from acq4.util.debug import printExc
from .bg_subtract_ctrl import BgSubtractCtrl
from .contrast_ctrl import ContrastCtrl

MAX_FPS = 30
MS_PER_FRAME = int((1.0 / MAX_FPS) * 1000)


class _FrameDrawThread(Thread):
    def __init__(self, drawFunc):
        super(_FrameDrawThread, self).__init__()
        self._timer = Qt.QTimer()
        self._timer.timeout.connect(drawFunc)
        self._timer.moveToThread(self)

    def run(self):
        self._timer.start(MS_PER_FRAME)
        Qt.QEventLoop().exec_()


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

    def __init__(self):
        Qt.QObject.__init__(self)

        self._imageItem = pg.ImageItem()
        self._imageItem.setAutoDownsample(True)
        self.contrastCtrl = self.contrastClass()
        self.contrastCtrl.setImageItem(self._imageItem)
        self.contrastCtrl.payAttentionToNewImageData(self.imageUpdated)
        self.bgCtrl = self.bgSubtractClass()
        self.bgCtrl.needFrameUpdate.connect(self.updateFrame)

        self.nextFrame = None
        self._updateFrame = False
        self.currentFrame = None
        self.lastDrawTime = None
        self.displayFps = None
        self.hasQuit = False

        # Check for new frame updates repeatedly
        # Some checks may be skipped even if there is a new frame waiting to avoid drawing too quickly
        self._drawingThread = _FrameDrawThread(self.drawFrame)
        self._drawingThread.start()
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
            if (self.lastDrawTime is not None) and (t - self.lastDrawTime < MS_PER_FRAME / 1000.0):
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

            # Set alpha from auto gain
            self.contrastCtrl.processImage(data)
            prof()

            # update image in viewport
            # The data used to be copy()ed in this line, with a vague comment about crashing.
            self._imageItem.updateImage(data)
            prof()

            self.imageUpdated.emit(self.currentFrame)
            prof()

            prof.finish()

        except Exception:
            printExc("Error while drawing new frames:")

    def quit(self):
        self._imageItem = None
        self.hasQuit = True
