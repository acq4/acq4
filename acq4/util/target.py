import numpy as np

import pyqtgraph as pg
from acq4.util import Qt
from pyqtgraph.graphicsItems.TargetItem import TargetItem


def color_for_diff(diff):
    dist = diff * 255 / 50e-6
    return np.clip(dist + 256, 0, 255), np.clip(256 - dist, 0, 255), 0


class Target(TargetItem):
    """graphics item for displaying a 3D point using color to represent Z"""
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._zPos = 0
        self._focusDepth = 0
        self._depthChanged()

    def setDepth(self, z):
        self._zPos = z
        self._depthChanged()

    def setFocusDepth(self, z):
        self._focusDepth = z
        self._depthChanged()

    def _depthChanged(self):
        # adjust the apparent depth of the target
        color = color_for_diff(self._focusDepth - self._zPos)
        self.setPen(pg.mkPen(color))
        self.update()


class TargetBox(Qt.QGraphicsRectItem):
    def __init__(self, start, end):
        super().__init__(Qt.QRectF(Qt.QPointF(start[0], start[1]), Qt.QPointF(end[0], end[1])))
        self.setBrush(Qt.QBrush(Qt.QColor(0, 0, 0, 0)))
        self._zRange = sorted((start[2], end[2]))
        self._focus = 0
        self._focusChanged()

    def noticeFocusChange(self, focus_device, causal_device):
        self._focus = focus_device.getFocusDepth()
        self._focusChanged()

    def _focusChanged(self):
        if self._zRange[0] <= self._focus <= self._zRange[1]:
            color = (255, 255, 0)
        else:
            diff = (self._focus - sum(self._zRange) / 2)
            color = color_for_diff(diff)
        self.setPen(pg.mkPen(color))
        self.update()
