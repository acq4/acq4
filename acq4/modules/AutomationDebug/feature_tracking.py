from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from acq4.devices.Pipette.calibration import findNewPipette
from acq4.logging_config import get_logger
from acq4.util.future import Future, Stopped, sleep
from acq4_automation.feature_tracking.cell import Cell
from coorx import Point

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow

logger = get_logger(__name__)


class FeatureTracker:
    def __init__(self, window: AutomationDebugWindow):
        self._window = window

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
                findNewPipette(pipette, camera, camera.scopeDev)
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

    def doFeatureTracking(self):
        win = self._window
        win.sigWorking.emit(win.ui.trackFeaturesBtn)
        pipette = win.pipetteDevice
        target = Point(pipette.targetPosition(), "global")
        cell = win._cell = Cell(target)
        cell.initializeTracker(win.cameraDevice).wait()
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

    def _updatePipetteTarget(self, pos):
        self._window.pipetteDevice.setTarget(pos)
        self._window.sigLogMessage.emit(f"Updated target to {pos}")

    def _handleFeatureTrackingFinish(self, fut: Future):
        self._window.sigWorking.emit(False)

    def _handleCalibrationFinish(self, fut: Future):
        self._window.sigWorking.emit(False)
