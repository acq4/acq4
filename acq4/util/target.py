import numpy as np
import pyqtgraph as pg
from pyqtgraph.graphicsItems.TargetItem import TargetItem


class Target(TargetItem):
    """graphics item for displaying a 3D point using color to represent Z
    """

    def __init__(self, *args, **kwds):
        TargetItem.__init__(self, *args, **kwds)
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
        depth = self._focusDepth - self._zPos
        dist = depth * 255 / 50e-6
        color = (np.clip(dist+256, 0, 255), np.clip(256-dist, 0, 255), 0)
        self.pen = pg.mkPen(color)
        self._picture = None
        self.update()


