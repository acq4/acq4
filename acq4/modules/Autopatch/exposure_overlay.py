"""Area 1's exposure heat map: where recent pipette insertions have disturbed the
tissue, drawn under the region view's other layers. Holds no slice."""

import math
import time

import numpy as np
import pyqtgraph as pg

from acq4.experiment.survey_planner import exposure_at
from acq4.util import Qt

# Over the mirrored pinned frames (negative, from -10000 up) and under the
# survey coverage shading (-50), the region ROI bodies and the markers.
_EXPOSURE_Z = -55

_PIXEL = 10e-6
_MAX_PIXELS = 1_500_000
_REFRESH_MS = 10_000
_MAX_ALPHA = 190


def _lookupTable() -> np.ndarray:
    """A heat colormap whose alpha rises with exposure, so ground nothing has
    touched stays see-through."""
    lut = pg.colormap.get("inferno").getLookupTable(0.0, 1.0, 256, alpha=True)
    lut = np.array(lut, dtype=np.uint8)
    lut[:, 3] = np.linspace(0, _MAX_ALPHA, 256).astype(np.uint8)
    return lut


class ExposureOverlay(Qt.QObject):
    """An exposure heat map in a ViewBox owned by someone else.

    `source()` returns (regions, fov, insertions, sigma, tau), or None when there
    is nothing to draw; it is called on every refresh, so the overlay never holds
    a slice. Hidden by default; the refresh timer runs only while shown.
    """

    def __init__(self, view, source, clock=time.time):
        super().__init__()
        self._view = view
        self._source = source
        self._clock = clock
        self._shown = False

        self.item = pg.ImageItem()
        self.item.setLookupTable(_lookupTable())
        self.item.setLevels((0.0, 1.0))
        self.item.setVisible(False)
        # addItem() before setZValue(): ViewBox.addItem() raises an item's z to
        # view.zValue()+1 when it is lower. See ProgressOverlay.__init__.
        self._view.addItem(self.item)
        self.item.setZValue(_EXPOSURE_Z)

        self._timer = Qt.QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

    def isShown(self) -> bool:
        return self._shown

    def timerActive(self) -> bool:
        return self._timer.isActive()

    def timerIntervalMs(self) -> int:
        return self._timer.interval()

    def setShown(self, shown: bool) -> None:
        self._shown = shown
        self.item.setVisible(shown)
        if shown:
            self.refresh()
            self._timer.start()
        else:
            self._timer.stop()

    def refresh(self) -> None:
        """Redraw from the source's current state; does nothing while hidden."""
        if not self._shown:
            return
        data = self._source()
        if data is None or not data[0]:
            self.item.clear()
            return
        regions, fov, insertions, sigma, tau = data
        x0, y0, x1, y1 = _paddedBounds(regions, fov)
        pixel = max(_PIXEL, math.sqrt((x1 - x0) * (y1 - y0) / _MAX_PIXELS))
        nx = max(1, round((x1 - x0) / pixel))
        ny = max(1, round((y1 - y0) / pixel))
        xs = x0 + (np.arange(nx) + 0.5) * pixel
        ys = y0 + (np.arange(ny) + 0.5) * pixel
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        points = np.column_stack([gx.ravel(), gy.ravel()])
        exposure = exposure_at(points, insertions, self._clock(), sigma, tau)
        self.item.setImage(exposure.reshape(nx, ny), autoLevels=False)
        self.item.setRect(Qt.QRectF(x0, y0, nx * pixel, ny * pixel))

    def release(self) -> None:
        """Take the item back out of a view that outlives this overlay.

        Also drops the source, which is typically a bound method of the window
        that owns this overlay: keeping it would make a reference cycle.
        """
        self._timer.stop()
        self._source = lambda: None
        self._view.removeItem(self.item)


def _paddedBounds(regions, fov):
    boxes = [r.bounds() for r in regions]
    return (
        min(b[0] for b in boxes) - fov[0] / 2,
        min(b[1] for b in boxes) - fov[1] / 2,
        max(b[2] for b in boxes) + fov[0] / 2,
        max(b[3] for b in boxes) + fov[1] / 2,
    )
