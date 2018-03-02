from __future__ import print_function
import time
import pickle
import time
import numpy as np
import scipy.optimize, scipy.ndimage
from acq4.util import Qt
import acq4.pyqtgraph as pg
from acq4.Manager import getManager


class PipetteTracker(object):
    """Provides functionality for automated tracking and recalibration of pipette tip position
    based on camera feedback.

    The current implementation uses normalized cross-correlation to do template matching against
    a stack of reference images collected with `takeReferenceFrames()`. 

    """
    def __init__(self, pipette):
        self.dev = pipette
        fileName = self.dev.configFileName('ref_frames.pk')
        try:
            self.reference = pickle.load(open(fileName, 'rb'))
        except Exception:
            self.reference = {}

    def takeFrame(self, imager=None):
        """Acquire one frame from an imaging device.

        This method guarantees that the frame is exposed *after* this method is called.
        """
        imager = self._getImager(imager)

        restart = False
        if imager.isRunning():
            restart = True
            imager.stop()
        frame = imager.acquireFrames(1)
        if restart:
            imager.start()
        return frame

    def getNextFrame(self, imager=None):
        """Return the next frame available from the imager. 

        Note: the frame may have been exposed before this method was called.
        """
        imager = self._getImager(imager)
        self.__nextFrame = None
        def newFrame(newFrame):
            self.__nextFrame = newFrame
        imager.sigNewFrame.connect(newFrame)
        try:
            start = pg.ptime.time()
            while pg.ptime.time() < start + 5.0:
                Qt.QApplication.processEvents()
                frame = self.__nextFrame
                if frame is not None:
                    self.__nextFrame = None
                    return frame
                time.sleep(0.01)
            raise RuntimeError("Did not receive frame from imager.")
        finally:
            pg.disconnect(imager.sigNewFrame, newFrame)

    def _getImager(self, imager=None):
        if imager is None:
            imager = 'Camera'
        if isinstance(imager, str):
            man = getManager()
            imager = man.getDevice('Camera')
        return imager

    def getTipImageArea(self, frame, padding, pos=None, tipLength=None):
        """Generate coordinates needed to clip a camera frame to include just the
        tip of the pipette and some padding.

        By default, images will include the tip of the pipette to a length of 100 pixels.

        Return a tuple (minImgPos, maxImgPos, tipRelPos), where the first two
        items are (x,y) coordinate pairs giving the corners of the image region to 
        be extracted, and tipRelPos is the subpixel location of the pipette tip
        within this region.
        """
        img = frame.data()
        if img.ndim == 3:
            img = img[0]

        if tipLength is None:
            tipLength = self.suggestTipLength(frame)

        # determine bounding rectangle that we would like to acquire from the tip
        if pos is not None:
            tipPos = pos
        else:
            tipPos = self.dev.globalPosition()
        tipPos = np.array([tipPos[0], tipPos[1]])
        angle = self.dev.getYawAngle() * np.pi / 180.
        da = 10 * np.pi / 180  # half-angle of the tip
        pxw = frame.info()['pixelSize'][0]
        # compute back points of a triangle that circumscribes the tip
        backPos1 = np.array([-tipLength * np.cos(angle+da), -tipLength * np.sin(angle+da)])
        backPos2 = np.array([-tipLength * np.cos(angle-da), -tipLength * np.sin(angle-da)])

        # convert to image coordinates
        tr = frame.globalTransform().inverted()[0]
        originImgPos = tr.map(pg.Vector([0, 0]))
        backImgPos1 = tr.map(pg.Vector(backPos1)) - originImgPos
        backImgPos2 = tr.map(pg.Vector(backPos2)) - originImgPos
        backImgPos1 = np.array([backImgPos1.x(), backImgPos1.y()])
        backImgPos2 = np.array([backImgPos2.x(), backImgPos2.y()])

        # Pixel positions of bounding corners in the image relative to tip, including padding.
        # Note this is all calculated without actual tip position; this ensures the image
        # size is constant even as the tip moves.
        allPos = np.vstack([[0, 0], backImgPos1, backImgPos2]).astype('int')
        padding = int(padding / pxw)
        minRelPos = allPos.min(axis=0) - padding
        maxRelPos = allPos.max(axis=0) + padding

        # Get absolute pixel position of tip within image
        tipImgPos = tr.map(pg.Vector(tipPos))
        tipImgPos = np.array([tipImgPos.x(), tipImgPos.y()])
        tipImgPx = tipImgPos.astype('int')

        # clip bounding coordinates
        minRelPos = [np.clip(minRelPos[0], -tipImgPx[0], img.shape[0]-1-tipImgPx[0]), 
                     np.clip(minRelPos[1], -tipImgPx[1], img.shape[1]-1-tipImgPx[1])]
        maxRelPos = [np.clip(maxRelPos[0], -tipImgPx[0], img.shape[0]-1-tipImgPx[0]), 
                     np.clip(maxRelPos[1], -tipImgPx[1], img.shape[1]-1-tipImgPx[1])]

        # absolute image coordinates of bounding rect
        minImgPos = tipImgPx + minRelPos
        maxImgPos = tipImgPx + maxRelPos

        if np.any(maxImgPos - minImgPos < 1):
            raise RuntimeError("No part of tip overlaps with camera frame.")

        # subpixel location of tip within image
        tipRelPos = tipImgPos - tipImgPx - minRelPos

        return minImgPos, maxImgPos, tipRelPos

    def takeTipImage(self, padding=50e-6):
        """Acquire an image of the pipette tip plus some padding.

        Return a tuple (image, tipPosition).
        """
        frame = self.takeFrame()

        minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(frame, padding)

        # clipped image region
        subimg = frame.data()[0, minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]

        return subimg, tipRelPos

    def suggestTipLength(self, frame):
        # return a suggested tip length to image, given the image resolution
        # currently just returns the length of 100 pixels in the frame
        return frame.info()['pixelSize'][0] * 100

    def takeReferenceFrames(self, zRange=None, zStep=None, imager=None, average=8, tipLength=None):
        """Collect a series of images of the pipette tip at various focal depths.

        The collected images are used as reference templates for determining the most likely location 
        and focal depth of the tip after the calibration is no longer valid.

        The focus first is moved in +z by half of *zRange*, then stepped downward by *zStep* until the
        entire *zRange* is covered. Images of the pipette tip are acquired and stored at each step.

        This method assumes that the tip is in focus near the center of the camera frame, and that its
        position is well-calibrated. Ideally, the illumination is flat and the area surrounding the tip
        is free of any artifacts.

        Images are filtered using `self.filterImage` before they are stored.
        """
        imager = self._getImager(imager)

        # Take an initial frame with the tip in focus.
        centerFrame = self.takeFrame()

        if tipLength is None:
            tipLength = self.suggestTipLength(centerFrame)

        if zRange is None:
            zRange = tipLength*1.5
        if zStep is None:
            zStep = zRange / 30.


        minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(centerFrame, padding=tipLength*0.15, tipLength=tipLength)
        center = centerFrame.data()[0, minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]
        center = self.filterImage(center)

        # Decide how many frames to collect and at what z depths
        nFrames = (int(zRange / zStep) // 2) * 2
        pos = self.dev.globalPosition()
        zStart = pos[2] + zStep * (nFrames // 2)
        frames = []
        bg_frames = []
        corr = []

        print("Collecting %d frames of %0.2fum tip length at %0.2fum resolution." % (nFrames, tipLength*1e6, zStep*1e6))

        # Stop camera if it is currently running
        restart = False
        if imager.isRunning():
            restart = True
            imager.stop()

        try:
            with pg.ProgressDialog('Acquiring reference frames...', 0, nFrames*2+1) as dlg:
                # collect 2 stacks of images (second stack is for background subtraction)
                for j in range(2):
                    # Set initial focus above start point to reduce hysteresis in focus mechanism
                    scope = self.dev.scopeDevice()
                    scope.setFocusDepth(zStart + 10e-6)

                    # Acquire multiple frames at different depths
                    for i in range(nFrames):
                        #pos[2] = zStart - zStep * i
                        # self.dev._moveToGlobal(pos, 'slow').wait()
                        scope.setFocusDepth(zStart - zStep * i).wait()
                        frame = imager.acquireFrames(average)
                        img = frame.data()[:, minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]].astype(float).mean(axis=0)
                        img = self.filterImage(img)
                        if j == 0:
                            frames.append(img)
                            corr.append(self._matchTemplateSingle(img, center)[1])
                        else:
                            bg_frames.append(img)
                        dlg += 1
                        if dlg.wasCanceled():
                            return

                    if j == 0:
                        # move tip out-of-frame to collect background images
                        self.dev._moveToLocal([-tipLength*3, 0, 0], 'slow').wait()
                    else:
                        self.dev._moveToLocal([tipLength*3, 0, 0], 'slow')

        finally:
            # restart camera if it was running
            if restart:
                imager.start()
            scope.setFocusDepth(pos[2])

        # find the index of the frame that most closely matches the initial, tip-focused frame
        maxInd = np.argmax(corr)

        # stack all frames into a 3D array
        frames = np.dstack(frames).transpose((2, 0, 1))
        bg_frames = np.dstack(bg_frames).transpose((2, 0, 1))

        # subtract background
        # frames -= bg_frame.data()

        # generate downsampled frame versions
        # (for now we generate these on the fly..)
        # ds = [frames] + [pg.downsample(pg.downsample(frames, n, axis=1), n, axis=2) for n in [2, 4, 8]]

        key = imager.getDeviceStateKey()
        self.reference[key] = {
            'frames': frames - bg_frames,
            'zStep': zStep,
            'centerInd': maxInd,
            'centerPos': tipRelPos,
            'pixelSize': frame.info()['pixelSize'],
            'tipLength': tipLength,
            # 'downsampledFrames' = ds,
        }

        # Store with pickle because configfile does not support arrays
        pickle.dump(self.reference, open(self.dev.configFileName('ref_frames.pk'), 'wb'))

    def measureTipPosition(self, padding=50e-6, threshold=0.7, frame=None, pos=None, tipLength=None, show=False):
        """Find the pipette tip location by template matching within a region surrounding the
        expected tip position.

        Return `((x, y, z), corr)`, where *corr* is the normalized cross-correlation value of
        the best template match.

        If the strength of the match is less than *threshold*, then raise RuntimeError.
        """
        # Grab one frame (if it is not already supplied) and crop it to the region around the pipette tip.
        if frame is None:
            frame = self.takeFrame()
        elif frame == 'next':
            frame = self.getNextFrame()

        # load up template images
        reference = self._getReference()

        if tipLength is None:
            # select a tip length similar to template images
            tipLength = reference['tipLength']

        minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(frame, padding, pos=pos, tipLength=tipLength)
        img = frame.data()
        if img.ndim == 3:
            img = img[0]
        img = img[minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]
        img = self.filterImage(img)

        # resample acquired image to match template pixel size
        pxr = frame.info()['pixelSize'][0] / reference['pixelSize'][0]
        if pxr != 1.0:
            img = scipy.ndimage.zoom(img, pxr)

        # run template match against all template frames, find the frame with the strongest match
        match = [self.matchTemplate(img, t) for t in reference['frames']]

        if show:
            pg.plot([m[0][0] for m in match], title='x match vs z')
            pg.plot([m[0][1] for m in match], title='y match vs z')
            pg.plot([m[1] for m in match], title='match correlation vs z')

        maxInd = np.argmax([m[1] for m in match])
        if match[maxInd][1] < threshold:
            raise RuntimeError("Unable to locate pipette tip (correlation %0.2f < %0.2f)" % (match[maxInd][1], threshold))

        # measure z error
        zErr = (maxInd - reference['centerInd']) * reference['zStep']

        # measure xy position
        offset = match[maxInd][0]
        tipImgPos = (minImgPos[0] + (offset[0] + reference['centerPos'][0]) / pxr, 
                     minImgPos[1] + (offset[1] + reference['centerPos'][1]) / pxr)
        tipPos = frame.mapFromFrameToGlobal(pg.Vector(tipImgPos))
        return (tipPos.x(), tipPos.y(), tipPos.z() + zErr), match[maxInd][1]

    def measureError(self, padding=50e-6, threshold=0.7, frame=None, pos=None):
        """Return an (x, y, z) tuple indicating the error vector from the calibrated tip position to the
        measured (actual) tip position.
        """
        if pos is None:
            expectedTipPos = self.dev.globalPosition()
        else:
            expectedTipPos = pos

        measuredTipPos, corr = self.measureTipPosition(padding, threshold, frame, pos=pos)
        return tuple([measuredTipPos[i] - expectedTipPos[i] for i in (0, 1, 2)])

    def _getReference(self):
        key = self._getImager().getDeviceStateKey()
        try:
            return self.reference[key]
        except KeyError:
            raise Exception("No reference frames found for this pipette / objective combination.")

    def autoCalibrate(self, **kwds):
        """Automatically calibrate the pipette tip position using template matching on a single camera frame.

        Return the offset in pipette-local coordinates and the normalized cross-correlation value of the template match.

        All keyword arguments are passed to `measureTipPosition()`.
        """
        # If no image padding is given, then use the template tip length as a first guess
        if 'padding' not in kwds:
            ref = self._getReference()
            kwds['padding'] = ref['tipLength']
        if 'frame' not in kwds:
            kwds['frame'] = 'next'
        try:
            tipPos, corr = self.measureTipPosition(**kwds)
        except RuntimeError:
            kwds['padding'] *= 2
            tipPos, corr = self.measureTipPosition(**kwds)

        localError = self.dev.mapFromGlobal(tipPos)
        tr = self.dev.deviceTransform()
        tr.translate(pg.Vector(localError))
        self.dev.setDeviceTransform(tr)
        return localError, corr

    def filterImage(self, img):
        """Return a filtered version of an image to be used in template matching.

        Currently, no filtering is applied.
        """
        # Sobel should reduce background artifacts, but it also seems to increase the noise in the signal
        # itself--two images with slightly different focus can have a very bad match.
        # import skimage.feature
        # return skimage.filter.sobel(img)
        img = scipy.ndimage.morphological_gradient(img, size=(3, 3))
        return img

    def matchTemplate(self, img, template, dsVals=(4, 2, 1)):
        """Match a template to image data.

        Return the (x, y) pixel offset of the template and a value indicating the strength of the match.

        For efficiency, the input images are downsampled and matched at low resolution before
        iteratively re-matching at higher resolutions. The *dsVals* argument lists the downsampling values
        that will be used, in order. Each value in this list must be an integer multiple of
        the value that follows it.
        """
        # Recursively match at increasing image resolution

        imgDs = [pg.downsample(pg.downsample(img, n, axis=0), n, axis=1) for n in dsVals]
        tmpDs = [pg.downsample(pg.downsample(template, n, axis=0), n, axis=1) for n in dsVals]
        offset = np.array([0, 0])
        for i, ds in enumerate(dsVals):
            pos, val = self._matchTemplateSingle(imgDs[i], tmpDs[i])
            pos = np.array(pos)
            if i == len(dsVals) - 1:
                offset += pos
                # [pg.image(imgDs[j], title=str(j)) for j in range(len(dsVals))]
                return offset, val
            else:
                scale = ds // dsVals[i+1]
                assert scale == ds / dsVals[i+1], "dsVals must satisfy constraint: dsVals[i] == dsVals[i+1] * int(x)"
                offset *= scale
                offset += np.clip(((pos-1) * scale), 0, imgDs[i+1].shape)
                end = offset + np.array(tmpDs[i+1].shape) + 3
                end = np.clip(end, 0, imgDs[i+1].shape)
                imgDs[i+1] = imgDs[i+1][offset[0]:end[0], offset[1]:end[1]]

    def _matchTemplateSingle(self, img, template, show=False, unsharp=3):
        import skimage.feature
        if img.shape[0] < template.shape[0] or img.shape[1] < template.shape[1]:
            raise ValueError("Image must be larger than template.  %s %s" % (img.shape, template.shape))
        cc = skimage.feature.match_template(img, template)
        # high-pass filter; we're looking for a fairly sharp peak.
        if unsharp is not False:
            cc_filt = cc - scipy.ndimage.gaussian_filter(cc, (unsharp, unsharp))
        else:
            cc_filt = cc

        if show:
            pg.image(cc)

        ind = np.argmax(cc_filt)
        pos = np.unravel_index(ind, cc.shape)
        val = cc[pos[0], pos[1]]
        return pos, val

    def mapErrors(self, nSteps=(5, 5, 7), stepSize=(50e-6, 50e-6, 50e-6),  padding=60e-6,
                  threshold=0.4, speed='slow', show=False, intermediateDist=60e-6):
        """Move pipette tip randomly to locations in a grid and measure the position error
        at each location.

        All tip locations must be within the field of view.
        """
        startTime = time.time()
        start = np.array(self.dev.globalPosition())
        npts = nSteps[0] * nSteps[1] * nSteps[2]
        inds = np.mgrid[0:nSteps[0], 0:nSteps[1], 0:nSteps[2]].reshape((3, npts)).transpose()
        order = np.arange(npts)
        np.random.shuffle(order)

        err = np.zeros(nSteps + (3,))

        stepSize = np.array(stepSize)

        if show:
            imv = pg.image()
            mark1 = Qt.QGraphicsEllipseItem(Qt.QRectF(-5, -5, 10, 10))
            mark1.setBrush(pg.mkBrush(255, 255, 0, 100))
            mark1.setZValue(100)
            imv.addItem(mark1)
            mark2 = Qt.QGraphicsEllipseItem(Qt.QRectF(-5, -5, 10, 10))
            mark2.setBrush(pg.mkBrush(255, 0, 0, 100))
            mark2.setZValue(100)
            imv.addItem(mark2)

        # loop over all points in random order, and such that we do heavy computation while
        # pipette is moving.
        images = []
        offsets = []
        try:
            with pg.ProgressDialog("Acquiring error map...", 0, len(order)) as dlg:
                for i in range(len(order)+1):
                    if i > 0:
                        lastPos = pos
                    if i < len(order):
                        ind = inds[order[i]]
                        pos = start.copy() + (stepSize * ind)

                        # Jump to position + a random 20um offset to avoid hysteresis
                        offset = np.random.normal(size=3)
                        offset *= intermediateDist / (offset**2).sum()**0.5
                        offsets.append(offset)

                        mfut = self.dev._moveToGlobal(pos + offset, speed)
                        ffut = self.dev.scopeDevice().setFocusDepth(pos[2], speed)
                    if i > 0:
                        ind = inds[order[i-1]]

                        print("Frame: %d %s" % (i-1, lastPos))
                        err[tuple(ind)] = self.measureError(padding=padding, threshold=threshold, frame=frame, pos=lastPos)
                        print("    error: %s" % err[tuple(ind)])
                        dlg += 1

                        if show:
                            imv.setImage(frame.data()[0])
                            p1 = frame.globalTransform().inverted()[0].map(pg.Vector(lastPos))
                            p2 = frame.globalTransform().inverted()[0].map(pg.Vector(lastPos + err[tuple(ind)]))
                            mark1.setPos(p1.x(), p1.y())
                            mark2.setPos(p2.x(), p2.y())

                    # wait for previous moves to complete
                    mfut.wait(updates=True)
                    ffut.wait(updates=True)

                    # step back to actual target position
                    self.dev._moveToGlobal(pos, speed).wait(updates=True)

                    frame = self.takeFrame()

                    if dlg.wasCanceled():
                        return None
        finally:
            self.dev._moveToGlobal(start, 'fast')
            self.dev.scopeDevice().setFocusDepth(start[2], 'fast')

        self.errorMap = {
            'err': err,
            'nSteps': nSteps,
            'stepSize': stepSize,
            'order': order,
            'inds': inds,
            'offsets': offsets,
            'time': time.time() - startTime,
        }

        filename = self.dev.configFileName('error_map.np')
        np.save(open(filename, 'wb'), self.errorMap)

        return self.errorMap

    def showErrorAnalysis(self):
        if not hasattr(self, 'errorMap'):
            filename = self.dev.configFileName('error_map.np')
            self.errorMap = np.load(open(filename, 'rb'))[np.newaxis][0]

        err = self.errorMap
        imx = pg.image(err['err'][..., 0].transpose(1, 0, 2), title='X error')
        imy = pg.image(err['err'][..., 1], title='Y error')
        imz = pg.image(err['err'][..., 2], title='Z error')

        # get N,3 array of offset values used to randomize hysteresis
        off = np.vstack(err['offsets'])
        sh = err['err'].shape

        # Get N,3 array of measured position errors
        errf = err['err'].reshape(sh[0]*sh[1]*sh[2], 3)[err['order']]

        # Display histogram of errors
        win = pg.GraphicsWindow(title="%s error" % self.dev.name())
        # subtract out slow drift
        normErr = errf - scipy.ndimage.gaussian_filter(errf, (20, 0))
        # calculate magnitude of error
        absErr = (normErr**2).sum(axis=1)**0.5
        # errPlot.plot(absErr)
        title = "Error Histogram (mean=%s)" % pg.siFormat(absErr.mean(), suffix='m')
        errPlot = win.addPlot(row=0, col=0, title=title, labels={'bottom': ('Position error', 'm')})
        hist = np.histogram(absErr, bins=50)
        errPlot.plot(hist[1], hist[0], stepMode=True)

        # display drift and hysteresis plots
        driftPlot = win.addPlot(row=0, col=1, rowspan=1, colspan=2, title="Pipette Drift",
                                labels={'left': ('Position error', 'm'), 'bottom': ('Time', 's')})
        driftPlot.plot(np.linspace(0, err['time'], errf.shape[0]), errf[:, 0], pen='r')
        driftPlot.plot(np.linspace(0, err['time'], errf.shape[0]), errf[:, 1], pen='g')
        driftPlot.plot(np.linspace(0, err['time'], errf.shape[0]), errf[:, 2], pen='b')

        xhplot = win.addPlot(row=1, col=0, title='X Hysteresis',
                             labels={'left': ('Position error', 'm'), 'bottom': ('Last pipette movement', 'm')})
        xhplot.plot(-off[:, 0], errf[:, 0], pen=None, symbol='o')

        yhplot = win.addPlot(row=1, col=1, title='Y Hysteresis',
                             labels={'left': ('Position error', 'm'), 'bottom': ('Last pipette movement', 'm')})
        yhplot.plot(-off[:, 1], errf[:, 1], pen=None, symbol='o')

        zhplot = win.addPlot(row=1, col=2, title='Z Hysteresis',
                             labels={'left': ('Position error', 'm'), 'bottom': ('Last pipette movement', 'm')})
        zhplot.plot(-off[:, 2], errf[:, 2], pen=None, symbol='o')

        # Print best fit for manipulator axes
        expPos = err['inds'] * err['stepSize']
        measPos = expPos + off
        guess = np.array([[1, 0, 0, 0],
                          [0, 1, 0, 0],
                          [0, 0, 1, 0]], dtype='float')
        def errFn(v):
            return ((measPos - np.dot(expPos, v.reshape(3,4))[:,:3])**2).sum()

        fit = scipy.optimize.minimize(errFn, guess)
        print("Pipette position transform:", fit)

        self.errorMapAnalysis = (imx, imy, imz, win)



class DriftMonitor(Qt.QWidget):
    def __init__(self, trackers):
        self.trackers = trackers
        self.nextFrame = None

        Qt.QWidget.__init__(self)
        self.timer = Qt.QTimer()
        self.timer.timeout.connect(self.update)

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        self.gv = pg.GraphicsLayoutWidget()
        self.layout.addWidget(self.gv, 0, 0)

        self.plot = self.gv.addPlot(labels={'left': ('Drift distance', 'm'), 'bottom': ('Time', 's')})
        self.plot.addLegend()
        self.xplot = self.gv.addPlot(labels={'left': ('X position', 'm')}, row=1, col=0)
        self.yplot = self.gv.addPlot(labels={'left': ('Y position', 'm')}, row=2, col=0)
        self.zplot = self.gv.addPlot(labels={'left': ('Z position', 'm'), 'bottom': ('Time', 's')}, row=3, col=0)
        for plt in [self.xplot, self.yplot, self.zplot]:
            plt.setYRange(-10e-6, 10e-6)

        self.pens = [(i, len(trackers)) for i in range(len(trackers))]
        self.lines = [self.plot.plot(pen=self.pens[i], name=trackers[i].dev.name()) for i in range(len(trackers))]
        # self.errors = [[] for i in range(len(trackers))]
        # self.cumulative = np.zeros((len(trackers), 3))
        self.positions = []
        self.times = []

        self.timer.start(2000)
        trackers[0]._getImager().sigNewFrame.connect(self.newFrame)
        self.show()

    def newFrame(self, frame):
        self.nextFrame = frame

    def update(self):
        try:
            if self.nextFrame is None:
                return
            frame = self.nextFrame
            self.nextFrame = None

            self.times.append(time.time())
            x = np.array(self.times)
            x -= x[0]

            pos = []
            for i, t in enumerate(self.trackers):
                try:
                    err, corr = t.autoCalibrate(frame=frame, padding=50e-6)
                    # err = np.array(err)
                    # self.cumulative[i] += err
                    # err = (self.cumulative[i]**2).sum()**0.5
                    pos.append(t.dev.globalPosition())
                except RuntimeError:
                    pos.append([np.nan]*3)
                # self.errors[i].append(err)
            self.positions.append(pos)
            pos = np.array(self.positions)
            pos -= pos[0]
            err = (pos**2).sum(axis=2)**0.5
            for i, t in enumerate(self.trackers):
                self.lines[i].setData(x, err[:, i])
            for ax, plt in enumerate([self.xplot, self.yplot, self.zplot]):
                plt.clear()
                for i, t in enumerate(self.trackers):
                    plt.plot(x, pos[:, i, ax], pen=self.pens[i])

        except Exception:
            self.timer.stop()
            raise

    def closeEvent(self, event):
        self.timer.stop()
        return Qt.QWidget.closeEvent(self, event)
