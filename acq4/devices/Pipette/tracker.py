import pickle
import time

import numpy as np
import scipy
import scipy.ndimage as ndi

import pyqtgraph as pg
from acq4.Manager import getManager
from acq4.util import Qt
from acq4.util.future import Future, future_wrap
from acq4.util.image_registration import imageTemplateMatch
from acq4.util.imaging.sequencer import acquire_z_stack
from .pipette_detection import TemplateMatchPipetteDetector
from ...logging_config import get_logger

logger = get_logger(__name__)


class PipetteTracker:
    def __init__(self, pipette):
        self.pipette = pipette

    def takeFrame(self, imager=None, ensureFreshFrames=True):
        """Acquire one frame from an imaging device.

        This method guarantees that the frame is exposed *after* this method is called.
        """
        imager = self._getImager(imager)
        with imager.ensureRunning(ensureFreshFrames=True):
            return imager.acquireFrames(1).getResult()[0]

    def _getImager(self, imager=None):
        if imager is None:
            imager = "Camera"
        if isinstance(imager, str):
            man = getManager()
            imager = man.getDevice("Camera")
        return imager

    def findTipInFrame(self, threshold=0.15, **kwds):
        """Automatically find the pipette tip position.

        Return the tip position in global coordinates.

        Parameters
        ----------
        threshold : float
            Minimum confidence value required. If the detection confidence is below this
            threshold, a RuntimeError is raised. Default is 0.5.
        **kwds
            All other keyword arguments are passed to `measureTipPosition()`.

        Returns
        -------
        tipPos : array-like
            (x, y, z) position of pipette tip in global coordinates

        Raises
        ------
        RuntimeError
            If the detection confidence is below threshold.
        """
        if "frame" not in kwds:
            kwds['frame'] = self.takeFrame(ensureFreshFrames=False)
        tipPos, confidence = self.measureTipPosition(**kwds)
        if confidence < threshold:
            raise RuntimeError(f"Unable to locate pipette tip (confidence {confidence:.2f} < {threshold:.2f})")
        return tipPos

    def measureTipPosition(self, frame, **kwds):
        """Measure the position of the pipette tip in global coordinates based on the provided camera frame.

        This method must be implemented by subclasses to provide specific algorithms for determining the tip position.

        Parameters
        -----------
        frame : Frame
            A frame acquired from an imager (e.g. using tracker.takeFrame() or imager.acquireFrames(1))
            Note that the frame must be acquired under simliar conditions to those used previously to collect a reference image set (same objective, filter, lighting, etc.).
        **kwds : dict
            Additional keyword arguments that may be used by specific implementations of this method.

        Returns
        -------
        tipPos : array-like
            (x, y, z) predicted location of pipette tip in global coordinates
        confidence : float
            Indicates prediction confidence. Arbitrary units, but usually values below about 0.5 will be rejected by the caller.
        """
        raise NotImplementedError()


class ResnetPipetteTracker(PipetteTracker):
    def measureTipPosition(self, frame, **kwds):
        return self.findPipette(frame)

    def findPipette(self, frame):
        img = frame.data()

        # find pipette direction in image
        pipetteAngle = self.pipetteAngleFromFrame(frame)

        pxSize = frame.info()["pixelSize"][0]

        # measure image pixel offset and z error to pipette tip
        xyOffset, zErr, confidence = self.estimateOffset(img, pipetteAngle, pxSize)

        # map pixel offsets back to physical coordinates
        tipPos = frame.mapFromFrameToGlobal(pg.Vector(xyOffset))

        return (tipPos.x(), tipPos.y(), tipPos.z() + zErr * 1e-6), confidence

    def pipetteAngleFromFrame(self, frame):
        """Calculate the angle of the pipette in the image frame, in degrees CCW from pointing right."""
        pipetteDir = self.pipette.globalDirection()
        imageDir = np.array(frame.mapFromGlobalToFrame(pipetteDir) - frame.mapFromGlobalToFrame([0, 0, 0]))[:2]
        imageDir = imageDir / np.linalg.norm(imageDir)
        pipetteAngle = np.arctan2(-imageDir[0], imageDir[1]) * 180 / np.pi
        return pipetteAngle

    def estimateOffset(self, img, pipetteAngle, pxSize):
        from acq4_automation.object_detection import do_pipette_tip_detection
        self.result = do_pipette_tip_detection(img, pipetteAngle, pxSize, show=False)
        return self.result[:3]

    def estimatePositionFromStack(
        self,
        z_range: float = 15e-6,
        z_step: float = 1e-6,
        confidence_threshold: float = 0.97,
        xy_stability_threshold_px: float = 3.0,
        stability_filter_size: int = 5,
    ) -> tuple[float, float, float] | None:
        """Find the global pipette tip position by scanning a z-stack and detecting the tip in each frame.

        Takes a z-stack centered on the current estimated tip position, runs ML-based pipette
        detection on every frame, and returns the global (x, y, z) position of the tip based
        on the first frame where both confidence is high and the detected XY position is stable.

        Assumes the pipette tip is already close (within ~10 µm) to its current estimated position.

        Parameters
        ----------
        z_range : float
            Half-range of the z-stack in meters (stack spans tip_z ± z_range). Default 15 µm.
        z_step : float
            Step size between z-stack frames in meters. Default 1 µm.
        confidence_threshold : float
            Minimum model confidence to accept a frame. Default 0.97.
        xy_stability_threshold_px : float
            Maximum allowed distance (pixels) from median position to consider XY stable. Default 3 px.
        stability_filter_size : int
            Size of median filter applied to confidence and stability masks. Default 5 frames.

        Returns
        -------
        (x, y, z) global position of the tip in meters, or None if detection failed.
        """
        from acq4_automation.object_detection import do_pipette_tip_detection
        pipette = self.pipette
        imager = self._getImager()

        tip_pos = pipette.globalPosition()
        z_center = tip_pos[2]

        # Scan from above the tip downward (+Z is up in global coords, so z_center+z_range is shallower).
        # enforce_linear_z_stack always returns frames sorted low-z to high-z (deep to shallow).
        frames = acquire_z_stack(
            imager,
            start=z_center + z_range,
            stop=z_center - z_range,
            step=z_step,
        ).getResult()

        px_size = frames[0].info()['pixelSize'][0]

        # Compute pipette angle in image frame: angle is measured CCW from pointing right
        pipette_angle = self.pipetteAngleFromFrame(frames[0])

        # Linearize z positions: the stage reports z in bursts so many consecutive frames share
        # the same z value. Fit a line to recover evenly-spaced depths.
        z_raw = np.array([f.depth for f in frames])
        z_fit = np.poly1d(np.polyfit(np.arange(len(z_raw)), z_raw, 1))
        z_positions = z_fit(np.arange(len(z_raw)))

        # Run detection on every frame. Frames where the focal plane is below the tip
        # (low z, deep) will have low confidence and unstable XY. Confidence rises when
        # the focal plane reaches the tip and remains high for shallower frames that show
        # the shaft — but the tip itself is only directly imaged at the lowest accepted z.
        confidences = []
        detection_results = []
        rows = []
        cols = []
        for frame in frames:
            img = frame.data()
            result = do_pipette_tip_detection(
                img, pipette_angle, px_size, show=False
            )
            detection_results.append(result)
            pos_rc, _z_um, confidence, _extras = result
            confidences.append(float(confidence))
            rows.append(float(pos_rc[0]))
            cols.append(float(pos_rc[1]))

        confidences = np.array(confidences)
        rows = np.array(rows)
        cols = np.array(cols)

        # XY stability: large frame-to-frame jumps indicate the tip is not yet in focus.
        # Median-filter the positions first to get a robust reference, then measure deviation.
        med_rows = ndi.median_filter(rows, size=stability_filter_size, mode='nearest')
        med_cols = ndi.median_filter(cols, size=stability_filter_size, mode='nearest')
        distances = np.sqrt((rows - med_rows) ** 2 + (cols - med_cols) ** 2)
        filt_distances = ndi.median_filter(distances, size=stability_filter_size, mode='nearest')

        # Build acceptance mask, then median-filter it to reject isolated spurious frames.
        good_confidence = confidences > confidence_threshold
        stable_xy = filt_distances < xy_stability_threshold_px
        accepted = ndi.median_filter(
            (good_confidence & stable_xy).astype(float),
            size=stability_filter_size,
            mode='nearest',
        ) > 0.5

        accepted_indices = np.where(accepted)[0]
        if len(accepted_indices) == 0:
            return None

        # The tip is the deepest focusable part of the pipette. Because frames are sorted
        # deep-to-shallow (low z first), accepted_indices[0] is the deepest accepted frame —
        # the one where the focal plane first reaches the tip level. Higher accepted frames
        # show the shaft above the tip and should not be used for z.
        best_idx = accepted_indices[0]
        best_frame = frames[best_idx]

        # Use the median-filtered XY position (more robust than the single-frame detection).
        tip_pixel = np.array([med_rows[best_idx], med_cols[best_idx]])
        tip_global = best_frame.mapFromFrameToGlobal(tip_pixel)

        return float(tip_global.x()), float(tip_global.y()), float(z_positions[best_idx])


class CorrelationPipetteTracker(PipetteTracker):
    """Provides functionality for automated tracking and recalibration of pipette tip position
    based on camera feedback.

    The current implementation uses normalized cross-correlation to do template matching against
    a stack of reference images collected with `takeReferenceFrames()`. 

    """

    detectorClass = TemplateMatchPipetteDetector

    def __init__(self, pipette):
        PipetteTracker.__init__(self, pipette)
        fileName = self.pipette.configFileName("ref_frames.pk")
        try:
            with open(fileName, "rb") as fh:
                self.reference = pickle.load(fh)
        except Exception:
            self.reference = {}

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
            tipPos = self.pipette.globalPosition()
        tipPos = np.array([tipPos[0], tipPos[1]])
        angle = self.pipette.yawRadians()
        da = 10 * np.pi / 180  # half-angle of the tip
        pxw = frame.info()["pixelSize"][0]
        # compute back points of a triangle that circumscribes the tip
        backPos1 = np.array([-tipLength * np.cos(angle + da), -tipLength * np.sin(angle + da)])
        backPos2 = np.array([-tipLength * np.cos(angle - da), -tipLength * np.sin(angle - da)])

        # convert to image coordinates
        tr = frame.globalTransform().inverse
        originImgPos = tr.map(pg.Vector([0, 0]))
        backImgPos1 = tr.map(pg.Vector(backPos1)) - originImgPos
        backImgPos2 = tr.map(pg.Vector(backPos2)) - originImgPos
        backImgPos1 = np.array([backImgPos1.x(), backImgPos1.y()])
        backImgPos2 = np.array([backImgPos2.x(), backImgPos2.y()])

        # Pixel positions of bounding corners in the image relative to tip, including padding.
        # Note this is all calculated without actual tip position; this ensures the image
        # size is constant even as the tip moves.
        allPos = np.vstack([[0, 0], backImgPos1, backImgPos2]).astype("int")
        padding = int(padding / pxw)
        minRelPos = allPos.min(axis=0) - padding
        maxRelPos = allPos.max(axis=0) + padding

        # Get absolute pixel position of tip within image
        tipImgPos = tr.map(pg.Vector(tipPos))
        tipImgPos = np.array([tipImgPos.x(), tipImgPos.y()])
        tipImgPx = tipImgPos.astype("int")

        # clip bounding coordinates
        minRelPos = [
            np.clip(minRelPos[0], -tipImgPx[0], img.shape[0] - 1 - tipImgPx[0]),
            np.clip(minRelPos[1], -tipImgPx[1], img.shape[1] - 1 - tipImgPx[1]),
        ]
        maxRelPos = [
            np.clip(maxRelPos[0], -tipImgPx[0], img.shape[0] - 1 - tipImgPx[0]),
            np.clip(maxRelPos[1], -tipImgPx[1], img.shape[1] - 1 - tipImgPx[1]),
        ]

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
        subimg = frame.data()[minImgPos[0] : maxImgPos[0], minImgPos[1] : maxImgPos[1]]

        return subimg, tipRelPos

    def suggestTipLength(self, frame):
        # return a suggested tip length to image, given the image resolution
        # currently just returns the length of 100 pixels in the frame
        return frame.info()["pixelSize"][0] * 100

    @future_wrap
    def takeReferenceFrames(
        self, zRange=None, zStep=None, imager=None, tipLength=None, _future: Future = None
    ):
        """Collect a series of images of the pipette tip at various focal depths.

        The collected images are used as reference templates for determining the most likely location 
        and focal depth of the tip after the calibration is no longer valid.

        This method assumes that the tip is in focus near the center of the camera frame, and that its
        position is well-calibrated. Ideally, the illumination is flat and the area surrounding the tip
        is free of any artifacts.
        """
        imager = self._getImager(imager)
        centerFrame = self.takeFrame()

        if tipLength is None:
            tipLength = self.suggestTipLength(centerFrame)

        minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(centerFrame, padding=tipLength * 0.15, tipLength=tipLength)
        center = centerFrame.data()[minImgPos[0]: maxImgPos[0], minImgPos[1]: maxImgPos[1]]
        if zRange is None:
            zRange = tipLength * 1.5
        zStart = self.pipette.globalPosition()[2] + zRange / 2
        zEnd = self.pipette.globalPosition()[2] - zRange / 2
        if zStep is None:
            zStep = zRange / 30

        # collect pipette stack
        frames = acquire_z_stack(
            imager, zStart, zEnd, zStep, block=True, name="pipette reference stack"
        ).getResult()
        pxSize = frames[0].info()["pixelSize"]
        frames = np.stack([f.data()[minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]] for f in frames], axis=0).astype(float)

        # collect background stack
        _future.waitFor(self.pipette._moveToLocal([-tipLength * 3, 0, 0], "slow"))
        bg_frames = acquire_z_stack(
            imager, zStart, zEnd, zStep, block=True, name="background for subtracting"
        ).getResult()
        bg_frames = np.stack([f.data()[minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]] for f in bg_frames], axis=0).astype(float)

        # return pipette to original position
        self.pipette._moveToLocal([tipLength * 3, 0, 0], "slow")

        # find frame that most closely matches center frame
        maxInd = np.argmax([imageTemplateMatch(f, center)[1] for f in frames])

        key = imager.getDeviceStateKey()
        self.reference[key] = {
            "frames": frames - bg_frames.mean(axis=0),
            "zStep": zStep,
            "centerInd": maxInd,
            "centerPos": tipRelPos,
            "pixelSize": pxSize,
            "tipLength": tipLength,
        }

        # Store with pickle because configfile does not support arrays
        with open(self.pipette.configFileName("ref_frames.pk"), "wb") as fh:
            pickle.dump(self.reference, fh)

    def measureTipPosition(
        self, frame, searchRegion="near_tip", padding=50e-6, pos=None, movePipette=False
    ):
        """Find the pipette tip location by template matching within a region surrounding the
        expected tip position.

        Parameters
        -----------
        frame : Frame
            A frame acquired from an imager (e.g. using tracker.takeFrame() or imager.acquireFrames(1))
            Note that the frame must be acquired under simliar conditions to those used previously to collect
            a reference image set (same objective, filter, lighting, etc.).
        searchRegion : str
            May be "near_tip" to search near the expected position of the pipette, or "full_frame"
            to search the entire camera field of view.
        padding : float
            Distance (m) around expected tip position to search. Applies only when searchRegion=="near_tip".
        pos : array-like
            Expected position of tip in global coordinates
        movePipette : bool
            If True, then take two frames with the pipette moved away for the second frame to allow background subtraction

        Returns
        -------
        tipPos : array-like
            (x, y, z) predicted location of pipette tip in global coordinates
        confidence : float
            Indicates confidence in tipPos (arbitrary units)
        """
        detector = self.detectorClass(tracker=self, pipette=self.pipette)

        tipLength = detector.suggestTipLength()
        if padding is None:
            padding = tipLength

        if movePipette:
            # move pipette and take a background frame
            if pos is None:
                pos = self.pipette.globalPosition()
            self.pipette._moveToLocal([-tipLength * 3, 0, 0], "fast").wait()
            bg_frame = self.takeFrame()
        else:
            bg_frame = None

        if searchRegion == 'near_tip':
            # generate suggested crop and pipette position
            minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(frame, padding, pos=pos, tipLength=tipLength)
            # apply machine vision algorithm
            tipPos, performance = detector.findPipette(frame, bg_frame, minImgPos, maxImgPos, pos)
        elif searchRegion == 'entire_frame':
            tipPos, performance = detector.findPipette(frame, bg_frame)
        else:
            raise ValueError("searchRegion must be 'near_tip' or 'entire_frame'")

        return tipPos, performance

    def measureError(self, padding=50e-6, threshold=0.7, frame=None, pos=None, movePipette=False):
        """Return an (x, y, z) tuple indicating the error vector from the calibrated tip position to the
        measured (actual) tip position.

        Raises RuntimeError if confidence is below threshold.
        """
        if pos is None:
            expectedTipPos = self.pipette.globalPosition()
        else:
            expectedTipPos = pos

        measuredTipPos, confidence = self.measureTipPosition(frame, padding=padding, pos=pos, movePipette=movePipette)
        if confidence < threshold:
            raise RuntimeError(f"Unable to locate pipette tip (confidence {confidence:.2f} < {threshold:.2f})")
        return tuple([measuredTipPos[i] - expectedTipPos[i] for i in (0, 1, 2)])

    def getReference(self):
        key = self._getImager().getDeviceStateKey()
        try:
            return self.reference[key]
        except KeyError:
            raise Exception(
                "No reference frames found for this pipette / objective / filter combination: %s" % repr(key)
            )

    def mapErrors(
        self,
        nSteps=(5, 5, 7),
        stepSize=(50e-6, 50e-6, 50e-6),
        padding=60e-6,
        threshold=0.4,
        speed="slow",
        show=False,
        intermediateDist=60e-6,
        moveStageXY=True,
    ):
        """Move pipette tip randomly to locations in a grid and measure the position error
        at each location.

        All tip locations must be within the field of view.

        If *show* is True, then a window is displayed showing each test image as it is acquired,
        with a yellow marker showing the _target_ position of the pipette, a red marker showing
        the _detected_ position of the pipette, and a blue marker showing the _reported_ position
        of the pipette.
        """
        imager = self._getImager()
        startTime = time.time()
        start = np.array(self.pipette.globalPosition())
        npts = nSteps[0] * nSteps[1] * nSteps[2]
        inds = np.mgrid[0 : nSteps[0], 0 : nSteps[1], 0 : nSteps[2]].reshape((3, npts)).transpose()
        order = np.arange(npts)
        np.random.shuffle(order)
        misses = 0
        err = np.zeros(nSteps + (3,))

        stepSize = np.array(stepSize)

        if show:
            imv = pg.image()
            # target marker
            mark1 = Qt.QGraphicsEllipseItem(Qt.QRectF(-8, -8, 16, 16))
            mark1.setBrush(pg.mkBrush(255, 255, 0, 100))
            mark1.setZValue(100)
            imv.addItem(mark1)
            # visually detected marker
            mark2 = Qt.QGraphicsEllipseItem(Qt.QRectF(-5, -5, 10, 10))
            mark2.setBrush(pg.mkBrush(255, 0, 0, 100))
            mark2.setZValue(100)
            imv.addItem(mark2)
            # manipulator reported marker
            mark3 = Qt.QGraphicsEllipseItem(Qt.QRectF(-5, -5, 10, 10))
            mark3.setBrush(pg.mkBrush(0, 0, 255, 200))
            mark3.setZValue(100)
            imv.addItem(mark3)

        # loop over all points in random order, and such that we do heavy computation while
        # pipette is moving.
        images = []
        offsets = []
        try:
            with pg.ProgressDialog("Acquiring error map...", 0, len(order)) as dlg:
                for i in range(len(order) + 1):
                    print("Iteration %d/%d" % (i, len(order)))
                    if i > 0:
                        lastPos = pos
                    if i < len(order):
                        ind = inds[order[i]]
                        pos = start.copy() + (stepSize * ind)

                        # Jump to position + a random 20um offset to avoid hysteresis
                        offset = np.random.normal(size=3)
                        offset *= intermediateDist / (offset ** 2).sum() ** 0.5
                        offsets.append(offset)

                        # move manipulator
                        mfut = self.pipette._moveToGlobal(pos + offset, speed)

                        # move camera
                        if moveStageXY:
                            cpos = pos
                        else:
                            cpos = imager.globalCenterPosition("roi")
                            cpos[2] = pos[2]
                        ffut = imager.moveCenterToGlobal(cpos, speed, center="roi")
                    if i > 0:
                        ind = inds[order[i - 1]]

                        print("Frame: %d/%d %s" % (i - 1, len(order), lastPos))
                        try:
                            err[tuple(ind)] = self.measureError(
                                padding=padding, threshold=threshold, frame=frame, pos=lastPos
                            )
                        except RuntimeError:
                            print("Could not detect pipette here.")
                            err[tuple(ind)] = (np.nan, np.nan, np.nan)
                        print("    error: %s" % err[tuple(ind)])
                        dlg += 1

                        if show:
                            imv.setImage(frame.data())
                            p1 = frame.globalTransform().inverse.map(pg.Vector(lastPos))
                            p2 = frame.globalTransform().inverse.map(pg.Vector(lastPos + err[tuple(ind)]))
                            p3 = frame.globalTransform().inverse.map(pg.Vector(reportedPos))
                            mark1.setPos(p1.x(), p1.y())
                            mark2.setPos(p2.x(), p2.y())
                            mark3.setPos(p3.x(), p3.y())

                    # wait for previous moves to complete
                    try:
                        mfut.wait(updates=True)
                    except:
                        logger.exception("Manipulator missed intermediate target:")

                    try:
                        ffut.wait(updates=True)
                    except:
                        logger.exception("Stage missed target:")

                    # step back to actual target position
                    try:
                        self.pipette._moveToGlobal(pos, speed).wait(updates=True)
                    except RuntimeError as exc:
                        misses += 1
                        logger.exception("Manipulator missed target:")

                    time.sleep(0.2)

                    frame = self.takeFrame()
                    reportedPos = self.pipette.globalPosition()

                    if dlg.wasCanceled():
                        return None
        finally:
            self.pipette._moveToGlobal(start, "fast")
            self.pipette.scopeDevice().setFocusDepth(start[2], "fast")

        self.errorMap = {
            "err": err,
            "nSteps": nSteps,
            "stepSize": stepSize,
            "order": order,
            "inds": inds,
            "offsets": offsets,
            "time": time.time() - startTime,
            "misses": misses,
        }

        print("Manipulator missed target %d times" % misses)

        filename = self.pipette.configFileName("error_map.np")
        np.save(filename, self.errorMap)

        return self.errorMap

    def showErrorAnalysis(self):
        if not hasattr(self, "errorMap"):
            filename = self.pipette.configFileName("error_map.np")
            self.errorMap = np.load(filename)[np.newaxis][0]

        err = self.errorMap
        imx = pg.image(err["err"][..., 0].transpose(2, 0, 1), title="X error", axes={"t": 0, "x": 1, "y": 2})
        imy = pg.image(err["err"][..., 1].transpose(2, 0, 1), title="Y error", axes={"t": 0, "x": 1, "y": 2})
        imz = pg.image(err["err"][..., 2].transpose(2, 0, 1), title="Z error", axes={"t": 0, "x": 1, "y": 2})

        # get N,3 array of offset values used to randomize hysteresis
        off = np.vstack(err["offsets"])
        sh = err["err"].shape

        # Get N,3 array of measured position errors
        errf = err["err"].reshape(sh[0] * sh[1] * sh[2], 3)[err["order"]]

        # Display histogram of errors
        win = pg.GraphicsWindow(title="%s error" % self.pipette.name())
        # subtract out slow drift
        normErr = errf - scipy.ndimage.gaussian_filter(errf, (20, 0))
        # calculate magnitude of error
        absErr = (normErr ** 2).sum(axis=1) ** 0.5
        # errPlot.plot(absErr)
        title = "Error Histogram (mean=%s)" % pg.siFormat(absErr.mean(), suffix="m")
        errPlot = win.addPlot(row=0, col=0, title=title, labels={"bottom": ("Position error", "m")})
        hist = np.histogram(absErr, bins=50)
        errPlot.plot(hist[1], hist[0], stepMode=True)

        # display drift and hysteresis plots
        driftPlot = win.addPlot(
            row=0,
            col=1,
            rowspan=1,
            colspan=2,
            title="Pipette Drift",
            labels={"left": ("Position error", "m"), "bottom": ("Time", "s")},
        )
        driftPlot.plot(np.linspace(0, err["time"], errf.shape[0]), errf[:, 0], pen="r")
        driftPlot.plot(np.linspace(0, err["time"], errf.shape[0]), errf[:, 1], pen="g")
        driftPlot.plot(np.linspace(0, err["time"], errf.shape[0]), errf[:, 2], pen="b")

        xhplot = win.addPlot(
            row=1,
            col=0,
            title="X Hysteresis",
            labels={"left": ("Position error", "m"), "bottom": ("Last pipette movement", "m")},
        )
        xhplot.plot(-off[:, 0], errf[:, 0], pen=None, symbol="o")

        yhplot = win.addPlot(
            row=1,
            col=1,
            title="Y Hysteresis",
            labels={"left": ("Position error", "m"), "bottom": ("Last pipette movement", "m")},
        )
        yhplot.plot(-off[:, 1], errf[:, 1], pen=None, symbol="o")

        zhplot = win.addPlot(
            row=1,
            col=2,
            title="Z Hysteresis",
            labels={"left": ("Position error", "m"), "bottom": ("Last pipette movement", "m")},
        )
        zhplot.plot(-off[:, 2], errf[:, 2], pen=None, symbol="o")

        # Print best fit for manipulator axes
        expPos = err["inds"] * err["stepSize"]
        measPos = expPos + off
        guess = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], dtype="float")

        def errFn(v):
            return ((measPos - np.dot(expPos, v.reshape(3, 4))[:, :3]) ** 2).sum()

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
        self.gv.setObjectName("PipetteTracker_graphicsLayoutWidget")
        self.layout.addWidget(self.gv, 0, 0)

        self.plot = self.gv.addPlot(labels={"left": ("Drift distance", "m"), "bottom": ("Time", "s")})
        self.plot.addLegend()
        self.xplot = self.gv.addPlot(labels={"left": ("X position", "m")}, row=1, col=0)
        self.yplot = self.gv.addPlot(labels={"left": ("Y position", "m")}, row=2, col=0)
        self.zplot = self.gv.addPlot(labels={"left": ("Z position", "m"), "bottom": ("Time", "s")}, row=3, col=0)
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
                    err = t.findTipInFrame(frame=frame, padding=50e-6)
                    t.pipette.setTipOffset(err)
                    # err = np.array(err)
                    # self.cumulative[i] += err
                    # err = (self.cumulative[i]**2).sum()**0.5
                    pos.append(t.dev.globalPosition())
                except RuntimeError:
                    pos.append([np.nan] * 3)
                # self.errors[i].append(err)
            self.positions.append(pos)
            pos = np.array(self.positions)
            pos -= pos[0]
            err = (pos ** 2).sum(axis=2) ** 0.5
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
