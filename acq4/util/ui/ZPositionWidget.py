from __future__ import annotations

from typing import Optional

import pyqtgraph as pg
from acq4.util import Qt


class ZPositionWidget(Qt.QWidget):
    """Reusable Z-position display widget for showing depth information.

    Can be used in both interactive modes (with focus control) and display-only modes.
    Originally refactored from ScopeCameraModInterface for use in MultiPatchLogWidget.
    """

    sigFocusChanged = Qt.Signal(float)  # emitted when user changes focus position

    def __init__(self, parent=None, plot=None, interactive=True):
        super().__init__(parent)

        self._interactive = interactive
        self._focusDepth = 0.0
        self._surfaceDepth = 0.0
        self._targetDepth = 0.0

        # Setup layout
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        # Use provided plot or create our own
        if plot is not None:
            self.plot = plot
            self._ownPlot = False
        else:
            self.plot = pg.PlotWidget()
            self.plot.setLabel('left', 'Depth', 'm')
            self.plot.setLabel('bottom', 'Position')
            self.layout.addWidget(self.plot, 0, 0, 1, 2)
            self._ownPlot = True

        # Create plot items
        self.focusLine = self.plot.addLine(y=0, pen='y')
        self.surfaceLine = self.plot.addLine(y=0, pen='g')

        if self._interactive:
            self.movableFocusLine = self.plot.addLine(
                y=0, pen='y', markers=[('<|>', 0.5, 10)], movable=True)
            self.movableFocusLine.sigPositionChangeFinished.connect(self._focusDragged)
        else:
            self.movableFocusLine = None

        # Create controls if interactive
        if self._interactive:
            self._createInteractiveControls()
        else:
            self._createDisplayControls()

    def _createInteractiveControls(self):
        """Create controls for interactive mode (with buttons)."""
        self.setSurfaceBtn = Qt.QPushButton('Set Surface')
        self.layout.addWidget(self.setSurfaceBtn, 1, 0)
        self.setSurfaceBtn.clicked.connect(self._setSurfaceClicked)

        # Note: Find Surface button would need device reference, so we'll skip it for now
        # in the reusable version

        self.depthLabel = pg.ValueLabel(suffix='m', siPrefix=True)
        self.layout.addWidget(self.depthLabel, 2, 0)

    def _createDisplayControls(self):
        """Create controls for display-only mode."""
        self.depthLabel = pg.ValueLabel(suffix='m', siPrefix=True)
        if self._ownPlot:
            self.layout.addWidget(self.depthLabel, 1, 0)
        # If using external plot, don't add the label to layout
        # Parent can handle positioning

    def setFocusDepth(self, depth: float):
        """Set the current focus depth."""
        self._focusDepth = depth
        self.focusLine.setValue(depth)
        self._updateDepthLabel()

        if self._interactive and self.movableFocusLine is not None:
            with pg.SignalBlock(self.movableFocusLine.sigPositionChangeFinished, self._focusDragged):
                self.movableFocusLine.setValue(depth)

    def setSurfaceDepth(self, depth: float):
        """Set the surface depth reference."""
        self._surfaceDepth = depth
        self.surfaceLine.setValue(depth)
        self._updateDepthLabel()

    def setTargetDepth(self, depth: float):
        """Set target focus depth (for interactive mode)."""
        self._targetDepth = depth
        if self._interactive and self.movableFocusLine is not None:
            with pg.SignalBlock(self.movableFocusLine.sigPositionChangeFinished, self._focusDragged):
                self.movableFocusLine.setValue(depth)

    def getFocusDepth(self) -> float:
        """Get current focus depth."""
        return self._focusDepth

    def getSurfaceDepth(self) -> float:
        """Get current surface depth."""
        return self._surfaceDepth

    def _updateDepthLabel(self):
        """Update the depth label showing distance from surface."""
        if hasattr(self, 'depthLabel'):
            depth = self._focusDepth - self._surfaceDepth
            self.depthLabel.setValue(depth)

    def _setSurfaceClicked(self):
        """Handle set surface button click."""
        self.setSurfaceDepth(self._focusDepth)

    def _focusDragged(self):
        """Handle focus line being dragged."""
        if self.movableFocusLine is not None:
            newDepth = self.movableFocusLine.value()
            self.setFocusDepth(newDepth)
            self.sigFocusChanged.emit(newDepth)

    def getDepthLabel(self) -> Optional[pg.ValueLabel]:
        """Get the depth label widget for external positioning."""
        return getattr(self, 'depthLabel', None)

    def getPlotItems(self) -> dict:
        """Get the plot items for external management."""
        return {
            'focusLine': self.focusLine,
            'surfaceLine': self.surfaceLine,
            'movableFocusLine': self.movableFocusLine,
        }
