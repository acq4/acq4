from __future__ import annotations

import pyqtgraph as pg
from acq4.util import Qt


class ZPositionWidget(Qt.QWidget):
    """Z-position display: focus depth, commanded target and surface depth.

    Three independent horizontal lines on *plot*, each set by its own method; no
    controls and no device connections.

    *movable* makes the target line draggable; releasing it emits
    :attr:`sigTargetChangeRequested` with the depth it was dropped at, and the handler
    is then responsible for moving the line back if the request fails.

    *showTarget* False hides the target line. :meth:`setTargetDepth` still moves it.
    """

    sigTargetChangeRequested = Qt.Signal(float)  # emitted when user requests a change to the target depth

    def __init__(self, plot, movable=False, showTarget=True):
        super().__init__(None)
        self.plot = plot

        # Create plot items
        self.targetLine = self.plot.addLine(y=0, pen='y', markers=[('<|>', 0.5, 10)], movable=movable)
        self.targetLine.setVisible(showTarget)
        self.targetLine.sigPositionChangeFinished.connect(self._onTargetLineMoved)
        self.focusLine = self.plot.addLine(y=0, pen='y')
        self.surfaceLine = self.plot.addLine(y=0, pen='g')
        self.depthLabel = pg.ValueLabel(suffix='m', siPrefix=True)

    def _onTargetLineMoved(self, line):
        self.sigTargetChangeRequested.emit(line.value())

    def setFocusDepth(self, depth: float):
        """Set the focus depth marker."""
        self.focusLine.setValue(depth)
        self._updateDepthLabel()

    def setSurfaceDepth(self, depth: float):
        """Set the surface depth marker."""
        self.surfaceLine.setValue(depth)
        self._updateDepthLabel()

    def setTargetDepth(self, depth: float):
        """Set the target depth marker, without emitting a change request for it."""
        with pg.SignalBlock(self.targetLine.sigPositionChangeFinished, self._onTargetLineMoved):
            self.targetLine.setValue(depth)

    def getTargetDepth(self):
        return self.targetLine.value()

    def _updateDepthLabel(self):
        """Update the depth label showing distance from surface."""
        depth = self.focusLine.value() - self.surfaceLine.value()
        self.depthLabel.setValue(depth)
