from __future__ import annotations

import pyqtgraph as pg
from acq4.util import Qt


class ZPositionWidget(Qt.QWidget):
    """Z-position display widget for showing depth information. This has no controls or device
    connections."""
    sigTargetChangeRequested = Qt.Signal(float)  # emitted when user requests a change to the target depth

    def __init__(self, plot, movable=False):
        super().__init__(None)
        self.plot = plot
        self._movingToTarget = False

        # Create plot items
        self.targetLine = self.plot.addLine(y=0, pen='y', markers=[('<|>', 0.5, 10)], movable=movable)
        self.targetLine.sigPositionChangeFinished.connect(self._onTargetLineMoved)
        self.focusLine = self.plot.addLine(y=0, pen='y')
        self.surfaceLine = self.plot.addLine(y=0, pen='g')
        self.depthLabel = pg.ValueLabel(suffix='m', siPrefix=True)

    def _onTargetLineMoved(self, line):
        self.setMovingToTarget(True)
        self.sigTargetChangeRequested.emit(line.value())

    def setFocusDepth(self, depth: float):
        """Set the focus depth marker."""
        self.focusLine.setValue(depth)
        if not self._movingToTarget:
            with pg.SignalBlock(self.targetLine.sigPositionChangeFinished, self._onTargetLineMoved):
                self.targetLine.setValue(depth)
        self._updateDepthLabel()

    def setSurfaceDepth(self, depth: float):
        """Set the surface depth marker."""
        self.surfaceLine.setValue(depth)
        self._updateDepthLabel()

    def setTargetDepth(self, depth: float):
        """Set the target depth marker."""
        with pg.SignalBlock(self.targetLine.sigPositionChangeFinished, self._onTargetLineMoved):
            self.targetLine.setValue(depth)

    def getTargetDepth(self):
        return self.targetLine.value()

    def setMovingToTarget(self, is_moving: bool):
        """Indicate whether the device is currently moving toward its target depth.
        When not moving, the target line is snapped to the current focus position."""
        self._movingToTarget = is_moving

    def _updateDepthLabel(self):
        """Update the depth label showing distance from surface."""
        depth = self.focusLine.value() - self.surfaceLine.value()
        self.depthLabel.setValue(depth)
