"""Collect labelled pipette-tip imagery for training tip-detection models.

One run writes a directory of z-stacks: a fine reference stack of the tip and a
matching background stack taken with the pipette retracted clear of the field
(so the reference can have its background subtracted), then repeated *pairs* of
sample stacks. The pair is what makes the data useful --
the operator clicks the tip for the first stack of a pair, the pipette is then
displaced by a small random amount, and the second stack is taken over exactly
the same z range. The tip position in the second stack is therefore known
analytically from the commanded displacement, without a second click.

The run loops until the operator stops it.
"""

from __future__ import annotations

import threading

import numpy as np

import pyqtgraph as pg
from acq4.devices.Camera import Camera
from acq4.devices.Microscope import Microscope
from acq4.devices.Pipette import Pipette
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.DataManager import DirHandle, FileHandle
from acq4.util.InterfaceCombo import InterfaceCombo
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4.util.task import (
    FutureButton,
    asynch_with_qt_signals,
    check_stop,
    poll,
    run_in_gui_thread,
    set_state,
)

DATA_DIR_NAME = "pipette_training_data"
REFERENCE_FILE_NAME = "pipette_reference.ma"
BACKGROUND_FILE_NAME = "pipette_reference_background.ma"
SAMPLE_FILE_NAME = "pipette_sample.ma"
MOVED_FILE_BASE = "pipette_sample_moved"

# Reference stack: fine and tall, since it is taken only once per run.
REFERENCE_Z_BELOW = 10e-6
REFERENCE_Z_ABOVE = 30e-6
REFERENCE_Z_STEP = 1e-6

# Retraction for the reference background stack. Derived from the field of view
# rather than fixed, since the field changes by an order of magnitude between
# objectives. The cap is a sanity limit on how far the pipette will be driven;
# exceeding it is an error rather than a clamp, since a clamped retraction would
# leave the pipette in frame and quietly write a useless background stack.
BACKGROUND_RETRACT_MARGIN = 100e-6
BACKGROUND_RETRACT_MAX = 3e-3

# Sample stacks are specified as a frame count either side of the tip rather than
# a distance, so whatever step is drawn, the tip lands exactly on a frame.
DEFAULT_FRAMES_BELOW = 3
DEFAULT_FRAMES_ABOVE = 6

# Random displacement applied between the two stacks of a pair. The axial default
# is a gaussian roughly spanning the 15 um retraction to 5 um advance the axial
# motion was originally drawn uniformly from.
DEFAULT_AXIAL_MEAN = -5e-6  # along the pipette axis; negative retracts
DEFAULT_AXIAL_SIGMA = 5e-6
DEFAULT_LATERAL_SIGMA = 3e-6  # 2D gaussian in the plane orthogonal to the axis

# The two stacks of a pair are only usable together if their frames sit at the
# same focal depths; more disagreement than this is a bug worth surfacing.
Z_ALIGNMENT_TOLERANCE = 1e-6

MOVE_SPEED = "fast"
NUDGE_SPEED = "slow"

# Above the camera frame image, so a drag on the ROI body moves it rather than
# panning the view, but below the pipette target marker and its arrows (z=5000).
REGION_ROI_Z = 4000


class _Skip(Exception):
    """Raised inside a sample pair when the operator skips the current location.

    Caught by the run loop, which moves straight on to a fresh random target.
    """


class PipetteTrainingWindow(Qt.QWidget):
    # Status text is set from the acquisition thread; the signal marshals it to the GUI.
    sigStatus = Qt.Signal(str)

    def __init__(self, module: "PipetteTraining"):
        super().__init__()
        self.module = module
        self.setWindowTitle("Pipette Training Data")
        self._roi = None
        self._clickedPos = None
        # Set from the GUI thread, read from the acquisition thread.
        self._skipRequested = threading.Event()
        self._buildUi()
        self.sigStatus.connect(self.statusLabel.setText)
        self.show()

    def _buildUi(self):
        layout = Qt.QGridLayout()
        self.setLayout(layout)
        row = 0

        layout.addWidget(Qt.QLabel("Pipette:"), row, 0)
        self.pipetteSelector = InterfaceCombo(types=["pipette"])
        layout.addWidget(self.pipetteSelector, row, 1)
        layout.addWidget(Qt.QLabel("Camera:"), row, 2)
        self.cameraSelector = InterfaceCombo(types=["camera"])
        layout.addWidget(self.cameraSelector, row, 3)
        row += 1

        self.addRegionBtn = Qt.QPushButton("Add sample region")
        self.clearRegionBtn = Qt.QPushButton("Clear region")
        layout.addWidget(self.addRegionBtn, row, 0, 1, 2)
        layout.addWidget(self.clearRegionBtn, row, 2, 1, 2)
        row += 1

        layout.addWidget(Qt.QLabel("Depth below surface:"), row, 0)
        self.minDepthSpin = pg.SpinBox(value=30e-6, suffix="m", siPrefix=True, step=5e-6)
        self.maxDepthSpin = pg.SpinBox(value=80e-6, suffix="m", siPrefix=True, step=5e-6)
        layout.addWidget(self.minDepthSpin, row, 1)
        layout.addWidget(Qt.QLabel("to"), row, 2, alignment=Qt.Qt.AlignCenter)
        layout.addWidget(self.maxDepthSpin, row, 3)
        row += 1

        layout.addWidget(Qt.QLabel("Sample z step:"), row, 0)
        self.minStepSpin = pg.SpinBox(
            value=1e-6, suffix="m", siPrefix=True, step=1e-6, bounds=(1e-7, None)
        )
        self.maxStepSpin = pg.SpinBox(
            value=5e-6, suffix="m", siPrefix=True, step=1e-6, bounds=(1e-7, None)
        )
        layout.addWidget(self.minStepSpin, row, 1)
        layout.addWidget(Qt.QLabel("to"), row, 2, alignment=Qt.Qt.AlignCenter)
        layout.addWidget(self.maxStepSpin, row, 3)
        row += 1

        layout.addWidget(Qt.QLabel("Frames below tip:"), row, 0)
        self.framesBelowSpin = Qt.QSpinBox()
        self.framesBelowSpin.setRange(0, 200)
        self.framesBelowSpin.setValue(DEFAULT_FRAMES_BELOW)
        layout.addWidget(self.framesBelowSpin, row, 1)
        layout.addWidget(Qt.QLabel("above tip:"), row, 2)
        self.framesAboveSpin = Qt.QSpinBox()
        self.framesAboveSpin.setRange(0, 200)
        self.framesAboveSpin.setValue(DEFAULT_FRAMES_ABOVE)
        layout.addWidget(self.framesAboveSpin, row, 3)
        row += 1

        layout.addWidget(Qt.QLabel("Axial motion mean:"), row, 0)
        self.axialMeanSpin = pg.SpinBox(
            value=DEFAULT_AXIAL_MEAN, suffix="m", siPrefix=True, step=1e-6
        )
        self.axialMeanSpin.setToolTip("Along the pipette axis; negative retracts")
        layout.addWidget(self.axialMeanSpin, row, 1)
        layout.addWidget(Qt.QLabel("stdev:"), row, 2)
        self.axialSigmaSpin = pg.SpinBox(
            value=DEFAULT_AXIAL_SIGMA, suffix="m", siPrefix=True, step=1e-6, bounds=(0, None)
        )
        layout.addWidget(self.axialSigmaSpin, row, 3)
        row += 1

        layout.addWidget(Qt.QLabel("Lateral motion stdev:"), row, 0)
        self.lateralSigmaSpin = pg.SpinBox(
            value=DEFAULT_LATERAL_SIGMA, suffix="m", siPrefix=True, step=1e-6, bounds=(0, None)
        )
        self.lateralSigmaSpin.setToolTip(
            "2D gaussian in the plane orthogonal to the pipette axis; mean is zero"
        )
        layout.addWidget(self.lateralSigmaSpin, row, 1)
        row += 1

        # FeedbackButton (FutureButton's base) is already checkable and manages its
        # own checked state, so this is the start/stop toggle.
        self.runBtn = FutureButton(
            self._run, "Start collecting", stoppable=True, processing="Stop collecting"
        )
        layout.addWidget(self.runBtn, row, 0, 1, 2)

        # Only meaningful mid-run, so it stays disabled until the loop is going.
        self.skipBtn = Qt.QPushButton("Skip location")
        self.skipBtn.setToolTip(
            "Abandon the current location without writing data and move to the next one"
        )
        self.skipBtn.setEnabled(False)
        layout.addWidget(self.skipBtn, row, 2, 1, 2)
        row += 1

        self.statusLabel = Qt.QLabel("Idle")
        self.statusLabel.setWordWrap(True)
        layout.addWidget(self.statusLabel, row, 0, 1, 4)

        self.addRegionBtn.clicked.connect(self.addRegion)
        self.clearRegionBtn.clicked.connect(self.clearRegion)
        self.skipBtn.clicked.connect(self._skipRequested.set)

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    @property
    def pipetteDevice(self) -> Pipette:
        return self.module.manager.getDevice(self.pipetteSelector.currentText())

    @property
    def cameraDevice(self) -> Camera:
        return self.module.manager.getDevice(self.cameraSelector.currentText())

    @property
    def scopeDevice(self) -> Microscope:
        return self.cameraDevice.scopeDev

    # ------------------------------------------------------------------
    # Sample region
    # ------------------------------------------------------------------

    def _cameraWindow(self):
        return self.module.manager.getModule("Camera").window()

    def addRegion(self):
        """Put a rectangle on the camera view bounding where samples are taken."""
        self.clearRegion()
        cam = self.cameraDevice
        # "roi" mode throughout: the field the camera actually images is what the
        # default rectangle should match, and it is off-center for a cropped
        # camera ROI.
        _, _, fov_w, fov_h = cam.getBoundary(globalCoords=True, mode="roi")
        w, h = abs(fov_w) * 0.8, abs(fov_h) * 0.8
        cx, cy = cam.globalCenterPosition("roi")[:2]
        pos = (cx - w / 2, cy - h / 2)
        roi = pg.RectROI(pos, (w, h), pen=pg.mkPen("c", width=2), removable=False)
        self._cameraWindow().addItem(roi, pos=pos, z=REGION_ROI_Z)
        self._roi = roi

    def clearRegion(self):
        if self._roi is not None:
            self._cameraWindow().removeItem(self._roi)
            self._roi = None

    def randomTarget(self) -> np.ndarray:
        """A random global position inside the region and the configured depth range.

        GUI-thread only; the acquisition thread reaches it via run_in_gui_thread so
        it never samples an ROI mid-drag.
        """
        if self._roi is None:
            raise RuntimeError("No sample region defined; click 'Add sample region' first.")
        pos = self._roi.pos()
        size = self._roi.size()
        # An ROI dragged past its own origin reports a negative size, so these
        # corners are not necessarily min/max.
        x0, x1 = sorted((float(pos.x()), float(pos.x()) + float(size.x())))
        y0, y1 = sorted((float(pos.y()), float(pos.y()) + float(size.y())))
        surface = self.scopeDevice.getSurfaceDepth()
        if surface is None:
            raise RuntimeError("Surface depth is not set; cannot choose a target depth.")
        d0, d1 = sorted((self.minDepthSpin.value(), self.maxDepthSpin.value()))
        return np.array(
            [
                np.random.uniform(x0, x1),
                np.random.uniform(y0, y1),
                surface - np.random.uniform(d0, d1),
            ]
        )

    def randomZStep(self) -> float:
        """Draw a z step for one sample pair. GUI-thread only."""
        lo, hi = sorted((self.minStepSpin.value(), self.maxStepSpin.value()))
        return np.random.uniform(lo, hi)

    def frameCounts(self) -> tuple[int, int]:
        """Frames to take below and above the tip. GUI-thread only."""
        return self.framesBelowSpin.value(), self.framesAboveSpin.value()

    def randomDisplacement(self, axis: np.ndarray) -> np.ndarray:
        """Draw a displacement vector for the configured motion distribution.

        Gaussian along *axis*, plus an isotropic gaussian in the orthogonal plane.
        GUI-thread only, since it reads the motion spinboxes.
        """
        # Any vector not parallel to the axis yields a first basis vector; +z is
        # parallel only for a perfectly vertical pipette, which does not occur.
        u = np.cross(axis, [0, 0, 1.0])
        u = u / np.linalg.norm(u)
        v = np.cross(axis, u)  # already unit: axis and u are orthogonal unit vectors
        lateralSigma = self.lateralSigmaSpin.value()
        return (
            axis * np.random.normal(self.axialMeanSpin.value(), self.axialSigmaSpin.value())
            + u * np.random.normal(0, lateralSigma)
            + v * np.random.normal(0, lateralSigma)
        )

    # ------------------------------------------------------------------
    # Waiting for the operator to click the tip
    # ------------------------------------------------------------------

    def _awaitTipClick(self, message: str) -> np.ndarray:
        """Block until the operator left-clicks the tip in the Camera window.

        Returns the clicked global position, taking z from the camera's current
        focus depth. Called from the acquisition thread; raises Stopped if the run
        is stopped while waiting, or _Skip if the operator skips the location.
        """
        self._clickedPos = None
        self.sigStatus.emit(message)
        run_in_gui_thread(self._connectClicks)
        try:
            poll(
                lambda: self._clickedPos is not None or self._skipRequested.is_set(),
                interval=0.05,
            )
        finally:
            run_in_gui_thread(self._disconnectClicks)
        self._checkSkip()
        return self._clickedPos

    def _checkSkip(self):
        """Raise _Skip if the operator has asked to abandon this location."""
        if self._skipRequested.is_set():
            raise _Skip()

    def _connectClicks(self):
        self._cameraWindow().getView().scene().sigMouseClicked.connect(self._cameraClicked)

    def _disconnectClicks(self):
        pg.disconnect(self._cameraWindow().getView().scene().sigMouseClicked, self._cameraClicked)

    def _cameraClicked(self, ev):
        if ev.button() != Qt.Qt.LeftButton:
            return
        pos = self._cameraWindow().getView().mapSceneToView(ev.scenePos())
        self._clickedPos = np.array([pos.x(), pos.y(), self.cameraDevice.getFocusDepth()])

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    @asynch_with_qt_signals
    def _run(self):
        pip = self.pipetteDevice
        cam = self.cameraDevice
        # Fail before creating a directory if there is nothing to sample over.
        run_in_gui_thread(self.randomTarget)

        storage = self.module.manager.getCurrentDir().mkdir(DATA_DIR_NAME, autoIncrement=True)
        try:
            set_state("reference stack")
            # Fine search with distance 0 centers the tip in the field and puts the
            # scope above the surface, which is where the reference stack belongs.
            pip.goSearch(MOVE_SPEED, distance=0).wait()
            tip = self._awaitTipClick("Click the pipette tip for the reference stack.")
            pip.resetGlobalPosition(tip)
            self.sigStatus.emit(f"Acquiring reference stack in {storage.shortName()}")
            start = tip[2] - REFERENCE_Z_BELOW
            stop = tip[2] + REFERENCE_Z_ABOVE
            reference = acquire_z_stack(
                cam, start, stop, REFERENCE_Z_STEP, name="pipette reference stack"
            )
            referencePose = self._pipettePose(pip)

            background, backgroundPose = self._collectReferenceBackground(
                pip, cam, tip, start, stop
            )

            # Verified before either is written, so a misaligned pair never lands
            # in the dataset.
            self._assertStacksAligned(
                reference, background, REFERENCE_FILE_NAME, BACKGROUND_FILE_NAME
            )
            self._saveStack(reference, storage, REFERENCE_FILE_NAME, referencePose)
            self._saveStack(background, storage, BACKGROUND_FILE_NAME, backgroundPose)

            run_in_gui_thread(self.skipBtn.setEnabled, True)
            while True:
                check_stop()
                try:
                    self._collectSamplePair(pip, cam, storage)
                except _Skip:
                    self.sigStatus.emit("Location skipped.")
        finally:
            run_in_gui_thread(self.skipBtn.setEnabled, False)
            self.sigStatus.emit(f"Idle. Last run: {storage.shortName()}")

    def _collectReferenceBackground(
        self, pip: Pipette, cam: Camera, tip: np.ndarray, start: float, stop: float
    ) -> tuple[list, dict]:
        """Retract the pipette clear of the field and repeat the reference stack.

        Same z range, same step, no pipette -- which is what makes the pair
        subtractable. The tip goes back to *tip* afterwards, so the loop starts from
        the position the reference stack was taken at.

        Returns the frames and the pose they were taken at, which is the retracted
        one -- the truth about where the pipette was while they were acquired.
        """
        set_state("reference background stack")
        distance = self._backgroundRetractDistance(pip, cam)
        pip.moveToGlobalNoPlanning(
            tip - pip.globalDirection() * distance,
            NUDGE_SPEED,
            name="retract for reference background stack",
        ).wait()
        try:
            self.sigStatus.emit("Acquiring reference background stack")
            frames = acquire_z_stack(
                cam, start, stop, REFERENCE_Z_STEP, name="pipette reference background stack"
            )
            return frames, self._pipettePose(pip)
        finally:
            pip.moveToGlobalNoPlanning(
                tip, NUDGE_SPEED, name="return from reference background stack"
            ).wait()

    @staticmethod
    def _backgroundRetractDistance(pip: Pipette, cam: Camera) -> float:
        """Axial distance that takes the pipette entirely out of the camera field.

        Retracting drags the tip backwards along the axis and the shank follows it,
        so clearing the tip past the far corner of the field clears the whole
        pipette. Only the axis's lateral component moves the tip towards the edge,
        hence dividing by cos(pitch): a steeply pitched pipette has to travel much
        further along its axis to leave the field.
        """
        _, _, width, height = cam.getBoundary(globalCoords=True, mode="roi")
        diagonal = np.hypot(width, height)
        reach = diagonal / 2 + BACKGROUND_RETRACT_MARGIN
        lateral = abs(np.cos(pip.pitchRadians()))
        distance = float("inf") if lateral == 0 else reach / lateral
        if distance > BACKGROUND_RETRACT_MAX:
            raise RuntimeError(
                f"{pip.name()} is pitched at {pip.pitchAngle():.1f} deg, so clearing a field "
                f"{diagonal * 1e6:.0f} um across the diagonal would take a "
                f"{distance * 1e3:.1f} mm retraction (limit "
                f"{BACKGROUND_RETRACT_MAX * 1e3:.1f} mm). Use a higher-magnification objective "
                f"or a shallower pipette for the reference background stack."
            )
        return distance

    def _collectSamplePair(self, pip: Pipette, cam: Camera, storage: DirHandle):
        """Acquire and save one clicked stack and its displaced counterpart.

        Both stacks are acquired and checked against each other before either is
        written, so a skipped or misaligned location leaves nothing behind.

        Raises _Skip if the operator abandons the location part-way through.
        """
        self._skipRequested.clear()
        set_state("moving to target")
        target = run_in_gui_thread(self.randomTarget)
        pip.setTarget(target)
        pip.goTarget(MOVE_SPEED).wait()
        pip.focusTip(MOVE_SPEED).wait()
        self._checkSkip()

        tip = self._awaitTipClick("Click the pipette tip.")
        pip.resetGlobalPosition(tip)

        # One step for both halves of the pair, drawn fresh each time so the
        # training set spans a range of z resolutions.
        step = run_in_gui_thread(self.randomZStep)
        below, above = run_in_gui_thread(self.frameCounts)
        start = tip[2] - below * step
        stop = tip[2] + above * step

        # Name the pair up front so both halves carry the same index.
        base = SAMPLE_FILE_NAME[: -len(".ma")]
        sampleName = storage.incrementFileName(SAMPLE_FILE_NAME)
        movedName = MOVED_FILE_BASE + sampleName[len(base) :]

        set_state("sample stack")
        self.sigStatus.emit(f"Acquiring {sampleName}")
        sample = acquire_z_stack(cam, start, stop, step, name="pipette sample stack")
        samplePose = self._pipettePose(pip)
        self._checkSkip()

        set_state("displacing pipette")
        self._randomNudge(pip)

        set_state("moved stack")
        self.sigStatus.emit(f"Acquiring {movedName}")
        # Deliberately the same absolute z range as above: the two stacks differ
        # only by the pipette's known displacement, not by where the scope looked.
        moved = acquire_z_stack(cam, start, stop, step, name="pipette sample stack (moved)")
        movedPose = self._pipettePose(pip)
        self._checkSkip()

        self._assertStacksAligned(sample, moved, sampleName, movedName)
        self._saveStack(sample, storage, sampleName, samplePose)
        self._saveStack(moved, storage, movedName, movedPose)

    def _randomNudge(self, pip: Pipette):
        """Displace the tip by a small, known random amount.

        Drawn from the configured motion distribution: gaussian along the pipette
        axis, plus an isotropic gaussian in the plane orthogonal to it.
        """
        offset = run_in_gui_thread(self.randomDisplacement, pip.globalDirection())
        pip.moveToGlobalNoPlanning(
            pip.globalPosition() + offset, NUDGE_SPEED, name="pipette training displacement"
        ).wait()

    @staticmethod
    def _pipettePose(pip: Pipette) -> dict:
        """The pipette metadata stamped onto a stack, sampled at acquisition time.

        Captured when the frames are taken rather than when they are written, since
        the pipette moves between the two for a background or displaced stack.
        """
        return {
            "pipetteYaw": pip.yawAngle(),
            "pipettePitch": pip.pitchAngle(),
            "pipetteGlobalPosition": list(pip.globalPosition()),
        }

    @staticmethod
    def _assertStacksAligned(first: list, second: list, firstName: str, secondName: str):
        """Raise unless frame i of one stack was exposed at frame i's depth in the other.

        Both halves of a pair are only usable together if frame i of one sits at the
        same focal depth as frame i of the other -- that is what background
        subtraction and the displacement label both assume.

        Frame depths are *measured*, not commanded, and the two stacks of a pair are
        acquired minutes apart with a pipette move in between. Stage drift, or a focus
        device that does not return to the same place twice, puts the same plane index
        at two different depths and mislabels the pair. The count is guaranteed by the
        identical bounds; the depths are not, so they are measured.
        """
        assert len(first) == len(second), (
            f"Stack length mismatch: {firstName} has {len(first)} frames, "
            f"{secondName} has {len(second)}; identical bounds must give identical counts."
        )
        firstZ = np.array([f.depth for f in first])
        secondZ = np.array([f.depth for f in second])
        deltas = secondZ - firstZ
        worst = int(np.argmax(np.abs(deltas)))
        if abs(deltas[worst]) > Z_ALIGNMENT_TOLERANCE:
            raise RuntimeError(
                f"Stack z mismatch between {firstName} and {secondName}: frame {worst} "
                f"differs by {deltas[worst] * 1e6:.3f} um "
                f"({firstZ[worst] * 1e6:.3f} vs {secondZ[worst] * 1e6:.3f} um), "
                f"tolerance {Z_ALIGNMENT_TOLERANCE * 1e6:.3f} um. "
                f"Per-frame differences (um): {np.round(deltas * 1e6, 3).tolist()}"
            )

    @staticmethod
    def _saveStack(frames, storage: DirHandle, fileName: str, pose: dict) -> FileHandle:
        """Write *frames* as one .ma and stamp it with the pipette's pose.

        Per-frame geometry rides along for free: saveImage stores the first frame's
        info (its global transform and pixelSize, with the z scale already filled in
        by acquire_z_stack), and each appendImage adds that frame's globalPosition to
        the MetaArray's Time axis.
        """
        fh = None
        for frame in frames:
            if fh is None:
                fh = frame.saveImage(storage, fileName, autoIncrement=False)
            else:
                fh = frame.appendImage(fh)
        fh.setInfo(**pose)
        return fh

    def quit(self):
        self.clearRegion()
        self.close()

    def closeEvent(self, ev):
        self.module.quit(fromUi=True)
        super().closeEvent(ev)


class PipetteTraining(Module):
    moduleDisplayName = "Pipette Training Data"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = PipetteTrainingWindow(self)

    def window(self):
        return self.ui

    def quit(self, fromUi=False):
        if not fromUi:
            self.ui.quit()
        else:
            self.ui.clearRegion()
        super().quit()
