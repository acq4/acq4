"""Survey-region support for the autopatch demo: pack the camera field of view as
a grid over a user-defined rectangle and track which tiles have been imaged.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pyqtgraph as pg

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow


def _axis_centers(lo: float, hi: float, fov: float, overlap: float) -> list[float]:
    """Tile centers along one axis whose union covers [lo, hi].

    Step between tiles is ``fov - overlap``; the tile count is the smallest that
    spans the extent, and the tiles are centered over it so the union fully
    covers [lo, hi] (the outermost tiles may extend past the edges).
    """
    extent = hi - lo
    step = fov - overlap
    if step <= 0:
        # Degrade gracefully if the overlap swallows the whole FOV.
        step = fov
    if extent <= fov:
        return [(lo + hi) / 2.0]
    n = math.ceil((extent - fov) / step) + 1
    covered = fov + (n - 1) * step
    extra = covered - extent
    start = lo + fov / 2.0 - extra / 2.0
    return [start + i * step for i in range(n)]


def plan_grid(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    fov_w: float,
    fov_h: float,
    overlap: float,
) -> list[tuple[float, float]]:
    """Serpentine-ordered tile centers whose union fully covers the rectangle.

    The step between adjacent tiles is ``fov - overlap`` (an absolute distance).
    The grid is centered over the rectangle so no part of it is left uncovered;
    the outermost tiles may extend past the edges. A single tile at the rect
    center is returned when the rect is smaller than one FOV. Rows alternate
    direction (boustrophedon) to minimize stage travel.
    """
    xs = _axis_centers(min(x0, x1), max(x0, x1), fov_w, overlap)
    ys = _axis_centers(min(y0, y1), max(y0, y1), fov_h, overlap)
    grid: list[tuple[float, float]] = []
    for j, cy in enumerate(ys):
        row = xs if j % 2 == 0 else list(reversed(xs))
        for cx in row:
            grid.append((cx, cy))
    return grid


def select_next(
    grid: list[tuple[float, float]],
    visited: list[tuple[float, float]],
    threshold: float,
) -> tuple[float, float] | None:
    """First center in ``grid`` not within ``threshold`` of any visited center.

    Returns None when every planned tile has already been imaged.
    """
    for cx, cy in grid:
        if not any(math.hypot(cx - vx, cy - vy) < threshold for vx, vy in visited):
            return (cx, cy)
    return None


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
        cx, cy = cam.globalCenterPosition()[:2]
        w, h = fov_w * 3, fov_h * 3
        pos = (cx - w / 2, cy - h / 2)
        roi = pg.RectROI(pos, (w, h), pen=pg.mkPen("y", width=2), removable=False)
        self._cameraWindow().addItem(roi, pos=pos)
        self._roi = roi

    def clearRegion(self):
        """Remove the survey rectangle and forget imaged-tile progress."""
        if self._roi is not None:
            self._cameraWindow().removeItem(self._roi)
            self._roi = None
        self._visited = []

    def reset(self):
        """Forget imaged-tile progress while keeping the region, so a re-run
        surveys the same rectangle from scratch."""
        self._visited = []

    def _bounds(self) -> tuple[float, float, float, float]:
        pos = self._roi.pos()
        size = self._roi.size()
        x0, y0 = float(pos.x()), float(pos.y())
        return x0, y0, x0 + float(size.x()), y0 + float(size.y())

    def nextTile(self) -> tuple[float, float] | None:
        """Global (x, y) center of the next un-imaged tile, or None when the region
        is fully imaged. Marks the returned tile as imaged. GUI-thread only."""
        if self._roi is None:
            return None
        fov_w, fov_h = self._fov()
        overlap = self._window.ui.surveyOverlapSpin.value()
        x0, y0, x1, y1 = self._bounds()
        grid = plan_grid(x0, y0, x1, y1, fov_w, fov_h, overlap)
        step = min(fov_w - overlap, fov_h - overlap)
        if step <= 0:
            step = min(fov_w, fov_h)
        center = select_next(grid, self._visited, threshold=step / 2)
        if center is not None:
            self._visited.append(center)
        return center
