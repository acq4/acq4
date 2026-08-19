from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from acq4 import getManager
from acq4.devices.Pipette.calibration import findNewPipette
from acq4.logging_config import get_logger
from acq4.util.model_config import segmenter_path
from acq4.util.task import Stopped, Task, asynch_with_qt_signals, sleep, synch
from acq4_automation.feature_tracking.cell import Cell
from coorx import Point

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow

logger = get_logger(__name__)

# Ridge weight for the affine flow fit that picks a tracked cell's focal plane. None
# keeps the dispersion metric and its calibrated quality thresholds. Values around
# 0 to 1 tolerate the smooth deformation an approaching pipette causes; the useful
# range was measured as roughly [0, 1]. See the acq4-automation design doc
# docs/superpowers/specs/2026-07-28-smooth-vector-field-z-design.md
DEFORMATION_TOLERANCE = 1


def _hasHistoryWorthSaving(tracker) -> bool:
    """Whether `tracker` holds anything save_history would actually write.

    It writes two things: the list of tracking results, and every reference
    ObjectStack the motion estimator has taken. Either alone is a history worth
    keeping, so both are asked about here.

    Read through getattr because this is reached with test doubles and, in
    principle, with trackers from other implementations; an attribute this
    cannot find is one save_history would not have found either.
    """
    if getattr(tracker, "tracking_results", None):
        return True
    estimator = getattr(tracker, "motion_estimator", None)
    return bool(getattr(estimator, "object_stacks", None))


def saveTrackingHistory(cell, dir_handle, autoIncrement=False) -> None:
    """Save a cell's tracking history to an .acqtrack file in dir_handle.

    Written whenever the tracker holds anything worth reading: tracking results,
    or reference stacks on its motion estimator, or both. The second of those is
    the case that used to be dropped. A cell detected in a tile, seeded with a
    reference cube cut from that tile's stack, queued, and then abandoned before
    a single tracking frame has no results at all -- so no file was written, and
    the ~1 MB cube that shows what the detector actually saw went with it.
    save_history is perfectly happy to write a history of zero results: it
    records n_results = 0 and its loop over the results simply does not run. The
    file that comes out opens in the replay visualizer showing the reference
    stack and nothing else, which is precisely the truth about that cell.

    A tracker holding neither is still skipped, and that is a different case
    rather than a smaller one. It is a tracker that was constructed and never
    initialized -- tracking genuinely never happened -- and the file recording
    it would be an empty container in every cell directory of every run, saying
    nothing that an absent file does not say more clearly.

    Silently skips when there is no cell or no tracker at all. Exceptions from
    the save are logged and swallowed so a failed save never aborts the caller.
    """
    if cell is None:
        return
    tracker = getattr(cell, "_tracker", None)
    if tracker is None or not _hasHistoryWorthSaving(tracker):
        return
    try:
        # writeFile, not a raw path write: it records the file's type in the index
        # and emits the 'children' change that puts it in the Data Manager tree.
        fh = dir_handle.writeFile(
            tracker, "tracking_history", fileType="AcqTrackFile", autoIncrement=autoIncrement
        )
        logger.info(f"Saved tracking history to {fh.name()}")
    except Exception:
        logger.exception("Failed to save tracking history")


class FeatureTracker:
    def __init__(self, window: AutomationDebugWindow):
        self._window = window

    @asynch_with_qt_signals
    def doPipetteCalibrationTest(self):
        win = self._window
        win.sigWorking.emit(win.ui.testPipetteBtn)
        camera = win.cameraDevice
        pipette = win.pipetteDevice
        true_tip_position = pipette.globalPosition()
        fake_tip_position = true_tip_position + np.random.uniform(-100e-6, 100e-6, 3)
        pipette.resetGlobalPosition(fake_tip_position)
        pipette.moveTo("home", "fast")
        while True:
            try:
                synch(findNewPipette)(pipette, camera, camera.scopeDev)
                error = np.linalg.norm(pipette.globalPosition() - true_tip_position)
                win.sigLogMessage.emit(
                    f"Calibration complete: {error * 1e6:.2g}µm error"
                )
                if error > 50e-6:
                    win.failedCalibrations.append(error)
                    i = len(win.failedCalibrations) - 1
                    win.sigLogMessage.emit(
                        f'....so bad. Why? Check man.getModule("AutomationDebug").failedCalibrations[{i}]'
                    )
            except Stopped:
                win.sigLogMessage.emit("Calibration interrupted by user request")
                break

    @asynch_with_qt_signals
    def doFeatureTracking(self):
        win = self._window
        win.sigWorking.emit(win.ui.trackFeaturesBtn)
        pipette = win.pipetteDevice
        target = Point(pipette.targetPosition(), "global")
        cell = win._cell = Cell(target)
        cell.initializeTracker(win.cameraDevice, use_cellpose=True, deformation_tolerance=DEFORMATION_TOLERANCE, segmenter=segmenter_path())  # pipette=win.pipetteDevice,
        cell.enableTracking()
        cell.sigPositionChanged.connect(self._updatePipetteTarget)
        win.sigWorking.emit(win.ui.trackFeaturesBtn)
        try:
            while cell.isTracking():
                sleep(1)
        except Exception:
            cell.enableTracking(False)
            cell.sigPositionChanged.disconnect(self._updatePipetteTarget)
            raise

    def _visualizeTracking(self):
        win = self._window
        cell = win.patchPipetteDevice.cell or win._cell
        if cell is None or cell._tracker is None:
            logger.error("No cell tracking available to visualize.")
            return
        from acq4_automation.feature_tracking.visualization import LiveTrackerVisualizer
        visualizer = LiveTrackerVisualizer(cell._tracker)
        win._visualizers.append(visualizer)
        visualizer.show()

    def _saveLastTrackingLog(self):
        """Save the most recent tracker's history into the current storage directory.

        Names the file with an incrementing suffix so repeated saves don't clobber
        each other.
        """
        win = self._window
        ppip = win.patchPipetteDevice
        cell = (ppip.cell if ppip is not None else None) or win._cell
        if cell is None:
            logger.error("No cell tracking available to save.")
            return
        saveTrackingHistory(cell, getManager().getCurrentDir(), autoIncrement=True)

    def _updatePipetteTarget(self, pos):
        self._window.pipetteDevice.setTarget(pos)
        self._window.sigLogMessage.emit(f"Updated target to {pos}")

    def _handleFeatureTrackingFinish(self, fut: Task):
        self._window.sigWorking.emit(False)

    def _handleCalibrationFinish(self, fut: Task):
        self._window.sigWorking.emit(False)
