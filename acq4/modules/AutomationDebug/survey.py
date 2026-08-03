"""Survey-region support for the autopatch demo: pack the camera field of view as
a grid over a user-defined rectangle and track which tiles have been imaged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyqtgraph as pg

from acq4.experiment.search_grid import count_covered, plan_grid, select_next

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow


class SurveyRegion:
    """A user-placed rectangle on the camera view that the autopatch demo surveys.

    Owns a resizable ROI in the Camera window (global coordinates) and remembers
    which field-of-view tiles have already been imaged, so ``nextTile`` hands out
    a fresh, unexamined location each time the demo grabs a z-stack.
    """

    def __init__(self, window: AutomationDebugWindow):
        self._window = window
        self._roi = None
        # Centers of tiles already imaged this run, in global (x, y).
        self._visited: list[tuple[float, float]] = []

    def _notify(self):
        """Refresh the window's survey stats readout on the GUI thread.

        Safe from any thread: nextTile runs on the GUI thread while the demo's
        reset() runs on a worker thread, and run_in_gui_thread calls inline when
        already on the GUI thread.
        """
        from acq4.util.task import run_in_gui_thread

        run_in_gui_thread(self._window._refreshSurveyStats)

    def _cameraWindow(self):
        return self._window.module.manager.getModule("Camera").window()

    def _fov(self) -> tuple[float, float]:
        """Current field-of-view width/height in global meters."""
        _, _, w, h = self._window.cameraDevice.getBoundary(globalCoords=True, mode="roi")
        return abs(w), abs(h)

    def hasRegion(self) -> bool:
        return self._roi is not None

    def addRegion(self):
        """Add a survey rectangle centered on the current FOV, ~3x3 tiles.

        Replaces any existing region and resets imaged-tile progress.
        """
        self.clearRegion()
        cam = self._window.cameraDevice
        fov_w, fov_h = self._fov()
        # Center in "roi" mode so the default rectangle matches the imaged field:
        # _fov() and detection use mode="roi", so this must too (globalCenterPosition
        # defaults to mode="sensor", which is off-center for a cropped camera ROI).
        cx, cy = cam.globalCenterPosition("roi")[:2]
        w, h = fov_w * 3, fov_h * 3
        pos = (cx - w / 2, cy - h / 2)
        roi = pg.RectROI(pos, (w, h), pen=pg.mkPen("y", width=2), removable=False)
        # Sit above the camera frame image so body drags translate the ROI
        # instead of falling through to the ViewBox and panning the whole view,
        # but below the pipette target and its arrows (z=5000) so those stay on
        # top.
        self._cameraWindow().addItem(roi, pos=pos, z=4000)
        roi.sigRegionChanged.connect(self._window._refreshSurveyStats)
        self._roi = roi
        self._notify()

    def clearRegion(self):
        """Remove the survey rectangle and forget imaged-tile progress."""
        if self._roi is not None:
            try:
                self._roi.sigRegionChanged.disconnect(self._window._refreshSurveyStats)
            except (TypeError, RuntimeError):
                pass
            self._cameraWindow().removeItem(self._roi)
            self._roi = None
        self._visited = []
        self._notify()

    def reset(self):
        """Forget imaged-tile progress while keeping the region, so a re-run
        surveys the same rectangle from scratch."""
        self._visited = []
        self._notify()

    def _bounds(self) -> tuple[float, float, float, float]:
        pos = self._roi.pos()
        size = self._roi.size()
        x0, y0 = float(pos.x()), float(pos.y())
        return x0, y0, x0 + float(size.x()), y0 + float(size.y())

    def _grid_and_threshold(self):
        """Return (grid, threshold) for the current ROI, camera FOV, and overlap."""
        fov_w, fov_h = self._fov()
        overlap = self._window.ui.surveyOverlapSpin.value()
        x0, y0, x1, y1 = self._bounds()
        grid = plan_grid(x0, y0, x1, y1, fov_w, fov_h, overlap)
        step = min(fov_w - overlap, fov_h - overlap)
        if step <= 0:
            step = min(fov_w, fov_h)
        return grid, step / 2

    def nextTile(self) -> tuple[float, float] | None:
        """Global (x, y) center of the next un-imaged tile, or None when the region
        is fully imaged. Marks the returned tile as imaged. GUI-thread only."""
        if self._roi is None:
            return None
        grid, threshold = self._grid_and_threshold()
        center = select_next(grid, self._visited, threshold)
        if center is not None:
            self._visited.append(center)
        self._notify()
        return center

    def stats(self) -> tuple[float, int, int, float] | None:
        """Survey progress for the current region, or None when none is set.

        Returns (area_m2, total_tiles, covered_tiles, percent_covered).
        """
        if self._roi is None:
            return None
        x0, y0, x1, y1 = self._bounds()
        area = abs(x1 - x0) * abs(y1 - y0)
        grid, threshold = self._grid_and_threshold()
        total = len(grid)
        covered = count_covered(grid, self._visited, threshold)
        percent = 100.0 * covered / total if total else 0.0
        return area, total, covered, percent
