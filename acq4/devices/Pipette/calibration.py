import numpy as np
import scipy.interpolate

import pyqtgraph as pg
from acq4.devices.Camera import Camera
from acq4.util import Qt
from acq4.util.future import future_wrap
from acq4.util.imaging.sequencer import acquire_z_stack
from .pipette import Pipette
from .planners import PipetteMotionPlanner


_z_stack_detection_window = None


class ZStackDetectionWidget(Qt.QWidget):
    """Widget showing a z-stack with per-frame ML pipette detection results.

    The ROI plot at the bottom shows predicted z-offset (red, left axis) and
    confidence (green, right axis) vs frame index. Dragging the timeline
    updates a crosshair on the image to the predicted tip position.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Z-Stack Pipette Detection")
        self.resize(900, 700)

        layout = Qt.QVBoxLayout(self)
        self.imageView = pg.ImageView()
        layout.addWidget(self.imageView)

        from pyqtgraph.graphicsItems.TargetItem import TargetItem
        self._target = TargetItem(size=20, movable=False, pen=pg.mkPen('r', width=2))
        self.imageView.getView().addItem(self._target)
        self._target.setVisible(False)

        self._image_positions = None
        self._z_curve = None
        self._conf_curve = None
        self._conf_vb = None

        self.imageView.sigTimeChanged.connect(self._on_time_changed)

    def setData(self, frames, image_positions, z_um, confidences):
        """Update the widget with new detection results.

        Parameters
        ----------
        frames : list of Frame
        image_positions : ndarray, shape (n, 2)
            Per-frame tip position in image pixel coordinates.
        z_um : ndarray, shape (n,)
            Per-frame predicted z offset from focal plane in µm.
        confidences : ndarray, shape (n,)
            Per-frame detection confidence (0-1).
        """
        self._image_positions = image_positions

        stack = np.stack([f.data() for f in frames], axis=0)
        self.imageView.setImage(stack)

        roi_plot = self.imageView.ui.roiPlot
        if self._z_curve is not None:
            roi_plot.removeItem(self._z_curve)
        if self._conf_curve is not None and self._conf_vb is not None:
            self._conf_vb.removeItem(self._conf_curve)

        x = np.arange(len(z_um))
        self._z_curve = roi_plot.plot(x, z_um, pen=pg.mkPen('r', width=2))
        roi_plot.setLabel('left', 'predicted z', units='µm')
        roi_plot.setLabel('bottom', 'frame index')
        roi_plot.showAxis('left')

        if self._conf_vb is None:
            self._conf_vb = pg.ViewBox()
            roi_plot.scene().addItem(self._conf_vb)
            roi_plot.showAxis('right')
            roi_plot.getAxis('right').linkToView(self._conf_vb)
            roi_plot.getAxis('right').setLabel('confidence')
            self._conf_vb.setXLink(roi_plot)
            roi_plot.getViewBox().sigResized.connect(self._update_conf_vb_geometry)

        self._conf_vb.clear()
        self._conf_curve = pg.PlotDataItem(x, confidences, pen=pg.mkPen('g', width=2))
        self._conf_vb.addItem(self._conf_curve)
        self._conf_vb.setRange(yRange=[0, 1])
        self._update_conf_vb_geometry()

        self._target.setVisible(True)
        self._on_time_changed(0, 0)
        self.show()
        self.raise_()

    def _update_conf_vb_geometry(self):
        if self._conf_vb is not None:
            roi_plot = self.imageView.ui.roiPlot
            self._conf_vb.setGeometry(roi_plot.getViewBox().sceneBoundingRect())
            self._conf_vb.linkedViewChanged(roi_plot.getViewBox(), self._conf_vb.XAxis)

    def _on_time_changed(self, ind, time):
        if self._image_positions is None:
            return
        idx = max(0, min(int(round(ind)), len(self._image_positions) - 1))
        pos = self._image_positions[idx]
        # image_pos_rc axes match frame.data() axis order: pos[0] → axis-0 (x in pg), pos[1] → axis-1 (y in pg)
        self._target.setPos(float(pos[0]), float(pos[1]))


def scan_pipette_z_stack(pipette, imager=None, z_range=50e-6, z_step=5e-6, show=False):
    """Acquire a z-stack and run ML pipette detection on every frame.

    Parameters
    ----------
    pipette : Pipette
        Pipette device whose tip will be detected in each frame.
    imager : Camera, optional
        Imaging device to use. Defaults to ``pipette.imagingDevice()``.
    z_range : float, optional
        Distance above and below current focus depth to scan in meters. Default ±50 µm.
    z_step : float
        Distance between planes in meters. Default 5 µm.
    show : bool
        If True, display the stack and detection results in a
        ``ZStackDetectionWidget`` (created once and reused on subsequent calls).

    Returns
    -------
    frames : list of Frame
    global_positions : ndarray, shape (n, 3)
        Predicted global (x, y, z) tip position per frame.
    z_predictions_um : ndarray, shape (n,)
        Predicted z offset of tip from focal plane in µm per frame.
    confidences : ndarray, shape (n,)
        Detection confidence (0–1) per frame.
    """
    from acq4_automation.object_detection import do_pipette_tip_detection

    if imager is None:
        imager = pipette.imagingDevice()

    current_z = imager.getFocusDepth()
    z_start = current_z - z_range
    z_end = current_z + z_range

    frames = acquire_z_stack(
        imager, z_start, z_end, z_step, block=True, name="ML pipette detection stack"
    ).getResult()

    pipette_dir = pipette.globalDirection()
    global_positions = []
    z_predictions_um = []
    confidences = []
    image_positions = []

    for frame in frames:
        img = frame.data()
        image_dir = np.array(
            frame.mapFromGlobalToFrame(pipette_dir) - frame.mapFromGlobalToFrame([0, 0, 0])
        )[:2]
        image_dir = image_dir / np.linalg.norm(image_dir)
        pipette_angle = np.arctan2(-image_dir[0], image_dir[1]) * 180 / np.pi
        px_size = frame.info()["pixelSize"][0]

        image_pos_rc, z_um, confidence, _ = do_pipette_tip_detection(img, pipette_angle, px_size, show=False)

        tip_pos = frame.mapFromFrameToGlobal(pg.Vector(image_pos_rc))
        global_positions.append((tip_pos.x(), tip_pos.y(), tip_pos.z() + z_um * 1e-6))
        z_predictions_um.append(float(z_um))
        confidences.append(float(confidence))
        image_positions.append([float(image_pos_rc[0]), float(image_pos_rc[1])])

    global_positions = np.array(global_positions)
    z_predictions_um = np.array(z_predictions_um)
    confidences = np.array(confidences)
    image_positions = np.array(image_positions)

    if show:
        from acq4.util.threadrun import runInGuiThread
        runInGuiThread(_show_z_stack_detection_widget, frames, image_positions, z_predictions_um, confidences)

    return frames, global_positions, z_predictions_um, confidences


def _show_z_stack_detection_widget(frames, image_positions, z_um, confidences):
    global _z_stack_detection_window
    if _z_stack_detection_window is None or not _z_stack_detection_window.isVisible():
        _z_stack_detection_window = ZStackDetectionWidget()
    _z_stack_detection_window.setData(frames, image_positions, z_um, confidences)


@future_wrap
def findNewPipette(pipette: Pipette, imager: Camera, scopeDevice, searchSpeed=0.4e-3, _future=None):
    """
    Find the tip of a new pipette by moving it across the objective while recording from the imager.
    """

    try:
        # focus 2mm above surface
        surfaceZ = scopeDevice.getSurfaceDepth()
        startDepth = surfaceZ + 2e-3
        _future.waitFor(imager.setFocusDepth(startDepth))

        # move pipette to search position
        center = imager.globalCenterPosition(mode='roi')
        pipVector = pipette.globalDirection()
        pipY = np.cross(pipVector, [0, 0, 1])
        pipY /= np.linalg.norm(pipY)
        searchPos1 = center + pipVector * 1.5e-3 + pipY * 2e-3
        searchPos2 = center + pipVector * 1.5e-3 - pipY * 2e-3
        # using a planner avoids possible collisions with the objective
        planner = PipetteMotionPlanner(pipette, searchPos1, speed='fast')
        _future.waitFor(planner.move())

        # collect background images, analyze noise
        with imager.ensureRunning():
            bgFrames = _future.waitFor(imager.acquireFrames(10)).getResult()
            bgFrameArray = np.stack([f.data() for f in bgFrames], axis=0)
            bgFrame = bgFrameArray.mean(axis=0)

        # record from imager and pipette position while moving pipette across the objecive
        frames, posEvents = watchMovingPipette(pipette, imager, searchPos2, speed=searchSpeed, _future=_future)
        framesArray = np.stack([f.data() for f in frames])

        # analyze frames for center point
        # avg should be mostly flat with a symmetrical bumpy thing in the middle
        avg = np.array([((frame.data() - bgFrame) ** 2).mean() for frame in frames])
        # avg = ((framesArray - bgFrame[None, ...])**2).mean(axis=1).mean(axis=1)

        # Find the center of the bump
        cs = np.cumsum(avg - avg.min())
        centerIndex = np.searchsorted(cs, cs.max() / 2, 'left')

        # get time of the frame with the center point
        centerTime = frames[centerIndex].info()['time']
        # get position of pipette at center time
        centerPipPos = getPipettePositionAtTime(posEvents, centerTime)

        # move back to center position
        _future.waitFor(pipette._moveToGlobal(centerPipPos, speed='fast'))

        # todo: at this point we could compare the current image to the previously collected video
        # to see whether we made it back to the desired position (and if not, apply
        # a correction as well as remember the apparent time delay between camera images and
        # position updates)
        compareFrame = _future.waitFor(imager.acquireFrames(1)).getResult()[0].data().astype(float)
        comparisonError = ((framesArray.astype(float) - compareFrame[None, ...])**2).sum(axis=1).sum(axis=1)
        mostSimilarFrame = np.argmin(comparisonError)
        pipetteCameraDelay = frames[mostSimilarFrame].info()['time'] - frames[centerIndex].info()['time']
        correctedCenterTime = frames[centerIndex].info()['time'] - pipetteCameraDelay
        correctedCenterPipPos = getPipettePositionAtTime(posEvents, correctedCenterTime)
        _future.waitFor(pipette._moveToGlobal(correctedCenterPipPos, speed='fast'))

        # record from imager and pipette position while retracting pipette out of frame
        retractPos = centerPipPos - pipVector * 2e-3
        frames2, posEvents2 = watchMovingPipette(pipette, imager, retractPos, speed=searchSpeed, _future=_future)
        frames2Array = np.stack([f.data() for f in frames2])

        # measure image intensity at a line perpendicular to the pipette that crosses the center of the frame        
        profile, interpCoords = interpolate_orthogonal_line(frames2, bgFrame, pipVector)
        # avg should be drifting at the beginning and flat at the end
        # the point where we transition from drifting to flat should be where the pipette tip crosses
        # the center of the frame
        avg2 = np.abs(profile).mean(axis=1)
        avg2End = avg2[-10:]
        avg2 -= avg2End.mean()
        avg2End = avg2[-10:]  # technically not needed

        # find where we reach 10% of max value
        profileMin = profile.min(axis=1)
        profileMin -= profileMin[-10:].mean()
        threshold = profileMin.min() / 10
        endIndex = np.argwhere(profileMin > threshold).min()

        endTime = frames2[endIndex].info()['time'] - pipetteCameraDelay

        # find pipette position at end time
        endPipPos = getPipettePositionAtTime(posEvents2, endTime)

        # find center of mass when the pipette crossed the center of the frame
        cs2 = np.cumsum(np.abs(profile[endIndex]))
        centerIndex2 = np.searchsorted(cs2, cs2.max() / 2, 'left')
        # centerPos = frames2[0].globalTransform().map(list(centerPosPx) + [0])
        yDistPx = centerIndex2 - len(interpCoords) // 2
        yDist = frames2[0].info()['pixelSize'][0] * yDistPx

        # # add 1/2 width of fov
        # halfFrameWidth = frames2[0].info()['pixelSize'][0] * (frames2[0].data().shape[0] //2)
        # centerPipPos2 = endPipPos + pipVector * halfFrameWidth
        centerPipPos2 = endPipPos + np.array([0, yDist, 0])

        # move to new center
        _future.waitFor(pipette._moveToGlobal(centerPipPos2, speed='fast'))

        # autofocus
        z_range = (startDepth - 500e-6, startDepth + 500e-6, 20e-6)
        zStack = _future.waitFor(acquire_z_stack(imager, *z_range, block=True, max_dz_per_frame=np.inf, name="finding pipette depth")).getResult()
        zStackArray = np.stack([frame.data() for frame in zStack])
        zDiff = np.abs(np.diff(zStackArray.astype(float), axis=0))
        zProfile = zDiff.max(axis=2).max(axis=1)  # most-changed pixel in each frame
        zProfile -= scipy.stats.scoreatpercentile(zProfile, 20)
        zThreshold = 0.75 * zProfile.max()
        # most in-focus z index toward the tip; pipette tip should be near here
        zIndex = np.argwhere(zProfile > zThreshold)[0, 0]


        # find tip by looking for most-in-focusest point of largest object, in the direction of the tip
        tipFrame = zStack[zIndex]
        tipImg = zDiff[zIndex]
        smoothTipImg = scipy.ndimage.gaussian_filter(tipImg, 2)
        tipThreshold = scipy.stats.scoreatpercentile(smoothTipImg, 98)
        # tipThreshold = 0.5 * (smoothTipImg.max() + smoothTipImg.min())
        tipMask = scipy.ndimage.binary_erosion(smoothTipImg > tipThreshold)

        # find largest object, hope this is the pipette
        label = scipy.ndimage.label(tipMask)[0]
        objects = scipy.ndimage.find_objects(label)
        largest = None
        for i, obj in enumerate(objects):
            size = (obj[0].stop - obj[0].start) * (obj[1].stop - obj[1].start)
            if largest is None or size > largest[0]:
                largest = (size, i+1)

        # location of all pixels in largest object
        tipPixels = np.argwhere(label == largest[1])

        # find the pixel that is farthest in the direction the pipette points
        imgVector = frame_pipette_direction(zStack[0], pipVector)[:2]
        tipPixelDistanceAlongPipette = np.dot(tipPixels, imgVector)
        tippestPixel = tipPixels[np.argmax(tipPixelDistanceAlongPipette)]

        # this is our best guess as to the global position of the pipette tip
        globalPos = tipFrame.mapFromFrameToGlobal([tippestPixel[0], tippestPixel[1], 0])

        # do initial coarse registration: reset offset to detected position, center in frame
        pipette.resetGlobalPosition(globalPos)
        _future.waitFor(pipette._moveToGlobal(imager.globalCenterPosition(), 'fast'))

        # iteratively refine tip position until convergence
        _future.waitFor(pipette.iterativelyFindTip(30), timeout=None)
    finally:
        _future.l = locals().copy()


def frame_pipette_direction(frame, pipVector):
    """Return the direction a pipette points in image coordinates for a frame"""
    frame_tr = frame.globalTransform().inverse
    imgVector = frame_tr.map(pipVector) - frame_tr.map([0, 0, 0])
    imgVector /= np.linalg.norm(imgVector)
    return imgVector


def interpolate_orthogonal_line(frames, bgFrame, pipVector):
    """Given a video in *frames* and a background frame to subtract, return
    a 2D slice of the video data across all frames and along the diagonal line that is
    orthogonal to the pipette x axis and passes through the center of the frame
    
    This is a cheaper way of measuring the cross-section of the pipette
    without having to rotate the entire video relative to the pipette yaw angle.

    Returns
    -------
        profile : ndarray of shape (n_frames, n_points)
            The 2D profile (frames, points) sliced from the video
        interpCoords : ndarray of shape (n_points, 2)
            The (row,col) image coordinates chosen to slice values from the video.
            len(interpCoords) == profile.shape[1]
    """
    center = np.array(frames[0].shape) // 2
    imgVector = frame_pipette_direction(frames[0], pipVector)
    orthoVector = np.array([imgVector[1], -imgVector[0]])  # 90 deg CW

    radiusPx = (center**2).sum()**0.5
    start = center - radiusPx * orthoVector
    interpCoords = start + np.arange(int(radiusPx*2))[:, np.newaxis] * orthoVector[np.newaxis, :]

    profile = np.empty((len(frames), interpCoords.shape[0]))
    for i,frame in enumerate(frames):
        profile[i] = scipy.interpolate.interpn(
            points=(np.arange(frame.shape[0]), np.arange(frame.shape[1])),
            values=frame.data() - bgFrame,
            xi=interpCoords,
            method='nearest',
            bounds_error=False,
            fill_value=0,
        )
    return profile, interpCoords


def watchMovingPipette(pipette: Pipette, imager: Camera, pos, speed, _future):
    with imager.ensureRunning():
        pipRecorder = None
        imgFuture = None
        try:
            imgFuture = imager.acquireFrames()
            pipRecorder = pipette.startRecording()
            pipFuture = pipette._moveToGlobal(pos, speed=speed)
            _future.waitFor(pipFuture, timeout=40)  # for some reason one of these moves takes a long time to finish..
        finally:
            if pipRecorder is not None:
                pipRecorder.stop()
            if imgFuture is not None:
                imgFuture.stop()    

    # return only position change events
    events = [ev for ev in pipRecorder.events if ev['event'] == 'position_change']

    return imgFuture.getResult(), events


def getPipettePositionAtTime(events, time):
    pipTimes = [ev['event_time'] for ev in events]
    pipIndex = np.searchsorted(pipTimes, time, 'left')
    return events[pipIndex]['position']


@future_wrap
def calibrate_manipulator_axes(
    pipette: Pipette,
    n_steps: int = 10,
    step_size: float = 50e-6,
    z_search_range: float = 100e-6,
    _future=None,
):
    """Automatically collect axis calibration data for a manipulator using the pipette tip finder.

    Moves the manipulator along each axis in incremental steps, using ML-based z-stack detection
    to locate the tip after each move. Returns calibration points suitable for use with
    ManipulatorAxesCalibrationWindow.

    Pre-conditions:
      - Pipette tip is in focus and visible in the camera frame.
      - Manipulator scale (meters per device unit) is correctly configured.
      - Stage and focus device are calibrated.

    Parameters
    ----------
    pipette : Pipette
        The pipette device whose manipulator axes are being calibrated.
    n_steps : int
        Number of steps to take per axis. Total points collected per axis = n_steps + 1.
    step_size : float
        Distance to move per step, in meters. Should be small enough that the tip stays
        within the camera field of view (50 µm is a typical starting value).
    z_search_range : float
        Half-range of the z-scan used to locate the tip after each move, in meters.
        Should be at least as large as the expected z displacement per step.

    Returns
    -------
    list of (device_pos, parent_pos) pairs
        Each pair contains the raw device position and the corresponding tip position in
        the parent device coordinate system. Pass these directly to
        ManipulatorAxesCalibrationWindow as calibration points.
    """
    # Movement and position queries go to the parent manipulator (a Stage); the pipette
    # itself is only used for tip detection and focus control.
    manipulator = pipette.parentStage
    imager = pipette.imagingDevice()
    scale = manipulator.getAxisScale()  # meters per device unit, shape (nAxes,)
    parent_dev = manipulator.parentDevice()

    calibration_points = []

    # Accurately locate the tip before starting the sweep.
    _future.waitFor(pipette.iterativelyFindTip(10))

    for axis in range(manipulator.nAxes):
        axis_start_pos = list(manipulator.getPosition())

        # Record the initial point; tip is already accurately located from iterativelyFindTip.
        device_pos = list(manipulator.getPosition())
        global_pos = list(pipette.globalPosition())
        parent_pos = list(parent_dev.mapFromGlobal(global_pos)) if parent_dev is not None else global_pos
        calibration_points.append((device_pos, parent_pos))

        for step_idx in range(1, n_steps + 1):
            # Move along this axis to the next absolute position.
            target_pos = list(axis_start_pos)
            target_pos[axis] = axis_start_pos[axis] + step_idx * (step_size / scale[axis])
            _future.waitFor(manipulator.move(target_pos, 'slow'))

            # Locate the tip via z-stack scan; this handles unknown axis orientation by
            # searching a range of focal depths around the current focus.
            _, global_positions, _, confidences = scan_pipette_z_stack(
                pipette, imager, z_range=z_search_range
            )
            best = int(np.argmax(confidences))
            detected_pos = global_positions[best]

            # Update the tip position without the normal validation prompt, since
            # we expect the tip to have moved during calibration.
            pipette.resetGlobalPosition(detected_pos)
            _future.waitFor(pipette.focusTip())

            device_pos = list(manipulator.getPosition())
            global_pos = list(pipette.globalPosition())
            parent_pos = list(parent_dev.mapFromGlobal(global_pos)) if parent_dev is not None else global_pos
            calibration_points.append((device_pos, parent_pos))

        # Return to the starting position before sweeping the next axis.
        _future.waitFor(manipulator.move(axis_start_pos, 'slow'))
        # Re-locate tip at start before recording the first point of the next axis.
        _future.waitFor(pipette.iterativelyFindTip(10))

    return calibration_points
