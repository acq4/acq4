from __future__ import annotations

import pyqtgraph as pg
from acq4.util import Qt


class ZPositionWidget(Qt.QWidget):
    """Z-position display widget for showing depth information."""

    def __init__(self, plot):
        super().__init__(None)
        self.plot = plot

        # Create plot items
        self.targetLine = self.plot.addLine(y=0, pen='y')
        self.focusLine = self.plot.addLine(y=0, pen='y')
        self.surfaceLine = self.plot.addLine(y=0, pen='g')
        self.depthLabel = pg.ValueLabel(suffix='m', siPrefix=True)

    def setFocusDepth(self, depth: float):
        """Set the current focus depth."""
        self.focusLine.setValue(depth)
        self._updateDepthLabel()

    def setSurfaceDepth(self, depth: float):
        """Set the surface depth reference."""
        self.surfaceLine.setValue(depth)
        self._updateDepthLabel()

    def setTargetDepth(self, depth: float):
        """Set the target depth."""
        self.targetLine.setValue(depth)

    def getFocusDepth(self) -> float:
        """Get current focus depth."""
        return self.focusLine.value()

    def getSurfaceDepth(self) -> float:
        """Get current surface depth."""
        return self.surfaceLine.value()

    def _updateDepthLabel(self):
        """Update the depth label showing distance from surface."""
        depth = self.getFocusDepth() - self.getSurfaceDepth()
        self.depthLabel.setValue(depth)
