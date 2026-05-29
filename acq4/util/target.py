# Graphics items for marking targets and bounding boxes in camera views.
# TargetBox supports z-depth-based fade and optional text labels.
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


# Distance from box center z within which opacity is 1.0
_FULL_ALPHA_DIST = 10e-6
# Distance from box center z beyond which opacity is 0.0
_ZERO_ALPHA_DIST = 17e-6


class TargetBox(Qt.QGraphicsRectItem):
    def __init__(self, start, end, label=None):
        super().__init__(Qt.QRectF(Qt.QPointF(start[0], start[1]), Qt.QPointF(end[0], end[1])))
        self.setBrush(Qt.QBrush(Qt.QColor(0, 0, 0, 0)))
        self._zRange = sorted((start[2], end[2]))
        self._focus = 0
        if label is not None:
            label_item = pg.TextItem(label, color=(255, 255, 0))
            label_item.setParentItem(self)
            rect = self.rect()
            label_item.setPos(rect.topRight())
        self._focusChanged()

    def noticeFocusChange(self, focus_device, causal_device):
        self._focus = focus_device.getFocusDepth()
        self._focusChanged()

    def _focusChanged(self):
        center_z = sum(self._zRange) / 2
        dist = abs(self._focus - center_z)
        if dist <= _FULL_ALPHA_DIST:
            alpha = 1.0
        elif dist >= _ZERO_ALPHA_DIST:
            alpha = 0.0
        else:
            alpha = 1.0 - (dist - _FULL_ALPHA_DIST) / (_ZERO_ALPHA_DIST - _FULL_ALPHA_DIST)
        self.setOpacity(alpha)

        if self._zRange[0] <= self._focus <= self._zRange[1]:
            color = (255, 255, 0)
        else:
            diff = (self._focus - center_z)
            color = color_for_diff(diff)
        self.setPen(pg.mkPen(color))
        self.update()
