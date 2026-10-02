from __future__ import annotations

import pyqtgraph as pg
from acq4.util import Qt


class ZPositionWidget(Qt.QWidget):
    """Z-position display: focus depth, commanded target and surface depth.

    Three independent horizontal lines on *plot*, each set by its own method. The
    focus line is where the device is, so it lags during a move; the target line is
    where the device has been commanded to go, and is only ever moved by
    :meth:`setTargetDepth` or by the user dragging it. This has no controls and no
    device connections.

    With *movable* True the target line can be dragged, and releasing it emits
    :attr:`sigTargetChangeRequested` with the depth it was dropped at. Whoever handles
    that signal owns what happens next, including putting the line back where the
    device actually is if the request comes to nothing.

    With *showTarget* False the target line is hidden, for a plot with no target to
    show. :meth:`setTargetDepth` still moves it, so it comes back correct if shown.
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
