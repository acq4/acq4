from __future__ import annotations

import pyqtgraph as pg
from acq4.util import Qt


class ZPositionWidget(Qt.QWidget):
    """Z-position display widget for showing depth information. This has no controls or device
    connections."""

    def __init__(self, plot):
        super().__init__(None)
        self.plot = plot

        # Create plot items
        self.targetLine = self.plot.addLine(y=0, pen='y')
        self.focusLine = self.plot.addLine(y=0, pen='y')
        self.surfaceLine = self.plot.addLine(y=0, pen='g')
        self.depthLabel = pg.ValueLabel(suffix='m', siPrefix=True)

    def setFocusDepth(self, depth: float):
        """Set the focus depth marker."""
        self.focusLine.setValue(depth)
        self._updateDepthLabel()

    def setSurfaceDepth(self, depth: float):
        """Set the surface depth marker."""
        self.surfaceLine.setValue(depth)
        self._updateDepthLabel()

    def setTargetDepth(self, depth: float):
        """Set the target depth marker."""
        self.targetLine.setValue(depth)

    def _updateDepthLabel(self):
        """Update the depth label showing distance from surface."""
        depth = self.focusLine.value() - self.surfaceLine.value()
        self.depthLabel.setValue(depth)
