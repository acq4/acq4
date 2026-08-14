"""Area 1's progress overlay: cell markers and survey coverage drawn into the
region view. Renders lists it is handed and holds no slice, panel, or cells."""

from typing import NamedTuple

import pyqtgraph as pg

from acq4.util import Qt

# Under the region ROIs and over the mirrored pinned frames, so a marker never
# hides the handle the operator needs to grab. PinnedFrameMirror preserves the
# Camera module's own z-order, which is negative, so both layers sit above it.
_COVERAGE_Z = -50
_MARKER_Z = -40

# Markers keep a constant screen size, against the precedent of acq4's other
# two scatters (Photostim, ScanCanvasItem), which both use pxMode=False.
# Data-unit markers vanish when the view is zoomed out to a whole slice, and
# legibility at slice scale is this overlay's entire purpose.
_MARKER_SIZE_PX = 11

_COVERAGE_PEN = pg.mkPen(150, 150, 150, 90)
_COVERAGE_BRUSH = pg.mkBrush(150, 150, 150, 40)


class Marker(NamedTuple):
    """One cell's dot: where it is, how it is coloured, and which cell it is.

    `cellId` is `id(cell)`, never the cell: the scatter must not be a second
    store keeping a Cell alive past CellPanel._cells.
    """

    x: float
    y: float
    brush: object
    cellId: int


class ProgressOverlay(Qt.QObject):
    """Cell markers and to-do coverage in a ViewBox owned by someone else.

    A QObject, unlike the plain PinnedFrameMirror/CameraMirror classes beside
    it, because this layer reports clicks back out.
    """

    # Carries one id(cell). The window maps it back through CellPanel; this
    # object never resolves an id to a cell itself.
    sigMarkerClicked = Qt.Signal(object)

    def __init__(self, view):
        super().__init__()
        self._view = view
        self._coverageItems = []

        self.scatter = pg.ScatterPlotItem(
            pxMode=True, size=_MARKER_SIZE_PX, pen=pg.mkPen(0, 0, 0, 120)
        )
        # addItem() before setZValue(): ViewBox.addItem() raises an item's z to
        # view.zValue()+1 when it is lower, so setting z first collapses it.
        # The same ordering PinnedFrameMirror.refresh() documents.
        self._view.addItem(self.scatter)
        self.scatter.setZValue(_MARKER_Z)
        self.scatter.sigClicked.connect(self._onScatterClicked)

    def setMarkers(self, markers) -> None:
        """Draw exactly `markers`, replacing whatever was drawn before."""
        self.scatter.setData(
            x=[m.x for m in markers],
            y=[m.y for m in markers],
            brush=[m.brush for m in markers],
            data=[m.cellId for m in markers],
        )

    def setCoverage(self, tiles, fov) -> None:
        """Shade one field-sized rect at each of `tiles`, replacing the last set.

        The caller passes the *to-do* tiles, not the covered ones, so an empty
        overlay reads as "fully surveyed" and what is drawn is the actionable
        set.
        """
        self._clearCoverage()
        fovW, fovH = fov
        for cx, cy in tiles:
            item = Qt.QGraphicsRectItem(
                cx - fovW / 2.0, cy - fovH / 2.0, fovW, fovH
            )
            item.setPen(_COVERAGE_PEN)
            item.setBrush(_COVERAGE_BRUSH)
            # Shading is a backdrop, not a target: a click must reach the
            # region ROI or the marker above it, never this.
            item.setAcceptedMouseButtons(Qt.Qt.NoButton)
            self._view.addItem(item)
            item.setZValue(_COVERAGE_Z)
            self._coverageItems.append(item)

    def coverageItems(self) -> list:
        return list(self._coverageItems)

    def clear(self) -> None:
        """Draw nothing, while staying attached to the view."""
        self.setMarkers([])
        self._clearCoverage()

    def release(self) -> None:
        """Take every item back out of a view that outlives this overlay."""
        Qt.disconnect(self.scatter.sigClicked, self._onScatterClicked)
        self._clearCoverage()
        self._view.removeItem(self.scatter)

    def _clearCoverage(self) -> None:
        for item in self._coverageItems:
            self._view.removeItem(item)
        self._coverageItems = []

    def _onScatterClicked(self, _plot, points, _event) -> None:
        if not len(points):
            return
        # The topmost point only. A click landing on overlapping markers is one
        # selection, and Area 5 has one current row.
        self.sigMarkerClicked.emit(points[0].data())
