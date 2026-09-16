"""Collect labelled pipette-tip imagery for training tip-detection models.

One run writes a directory of z-stacks: a fine reference stack of the tip, then
repeated *pairs* of sample stacks. The pair is what makes the data useful --
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
SAMPLE_FILE_NAME = "pipette_sample.ma"
MOVED_FILE_BASE = "pipette_sample_moved"

# Reference stack: fine and tall, since it is taken only once per run.
REFERENCE_Z_BELOW = 10e-6
REFERENCE_Z_ABOVE = 30e-6
REFERENCE_Z_STEP = 1e-6

# Sample stacks are specified as a frame count either side of the tip rather than
# a distance, so whatever step is drawn, the tip lands exactly on frame
# SAMPLE_FRAMES_BELOW of the stack.
SAMPLE_FRAMES_BELOW = 3
SAMPLE_FRAMES_ABOVE = 6

# Random displacement applied between the two stacks of a pair.
AXIAL_RANGE = (-15e-6, 5e-6)  # along the pipette axis; negative retracts
LATERAL_SIGMA = 3e-6  # 2D gaussian in the plane orthogonal to the axis

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
            frames = acquire_z_stack(
                cam,
                tip[2] - REFERENCE_Z_BELOW,
                tip[2] + REFERENCE_Z_ABOVE,
                REFERENCE_Z_STEP,
                name="pipette reference stack",
            )
            self._saveStack(frames, storage, REFERENCE_FILE_NAME, pip)

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

    def _collectSamplePair(self, pip: Pipette, cam: Camera, storage: DirHandle):
        """Acquire and save one clicked stack and its displaced counterpart.

        Raises _Skip if the operator abandons the location part-way through, having
        first removed anything already written for it.
        """
        self._skipRequested.clear()
        written: list[FileHandle] = []
        try:
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
            start = tip[2] - SAMPLE_FRAMES_BELOW * step
            stop = tip[2] + SAMPLE_FRAMES_ABOVE * step

            # Name the pair up front so both halves carry the same index.
            base = SAMPLE_FILE_NAME[: -len(".ma")]
            sampleName = storage.incrementFileName(SAMPLE_FILE_NAME)
            movedName = MOVED_FILE_BASE + sampleName[len(base) :]

            set_state("sample stack")
            self.sigStatus.emit(f"Acquiring {sampleName}")
            frames = acquire_z_stack(cam, start, stop, step, name="pipette sample stack")
            self._checkSkip()
            written.append(self._saveStack(frames, storage, sampleName, pip))

            set_state("displacing pipette")
            self._randomNudge(pip)

            set_state("moved stack")
            self.sigStatus.emit(f"Acquiring {movedName}")
            # Deliberately the same absolute z range as above: the two stacks differ
            # only by the pipette's known displacement, not by where the scope looked.
            frames = acquire_z_stack(cam, start, stop, step, name="pipette sample stack (moved)")
            self._checkSkip()
            written.append(self._saveStack(frames, storage, movedName, pip))
        except _Skip:
            # A skipped location contributes nothing, so a half-written pair is
            # removed rather than left with an unpaired sample. The index is freed
            # along with it, so the next pair reuses it and the run stays gapless.
            for fh in written:
                fh.delete()
            raise

    def _randomNudge(self, pip: Pipette):
        """Displace the tip by a small, known random amount.

        The axial component runs from a 15 um retraction to a 5 um advance along
        the pipette axis; the lateral component is a 2D gaussian in the plane
        orthogonal to it.
        """
        axis = pip.globalDirection()
        # Any vector not parallel to the axis yields a first basis vector; +z is
        # parallel only for a perfectly vertical pipette, which does not occur.
        u = np.cross(axis, [0, 0, 1.0])
        u = u / np.linalg.norm(u)
        v = np.cross(axis, u)  # already unit: axis and u are orthogonal unit vectors
        offset = (
            axis * np.random.uniform(*AXIAL_RANGE)
            + u * np.random.normal(0, LATERAL_SIGMA)
            + v * np.random.normal(0, LATERAL_SIGMA)
        )
        pip.moveToGlobalNoPlanning(
            pip.globalPosition() + offset, NUDGE_SPEED, name="pipette training displacement"
        ).wait()

    @staticmethod
    def _saveStack(frames, storage: DirHandle, fileName: str, pip: Pipette) -> FileHandle:
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
        fh.setInfo(
            pipetteYaw=pip.yawAngle(),
            pipettePitch=pip.pitchAngle(),
            pipetteGlobalPosition=list(pip.globalPosition()),
        )
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
