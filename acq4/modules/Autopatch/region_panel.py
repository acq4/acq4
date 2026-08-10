"""RegionPanel: Area 1's global-coordinate view of the slice -- the pinned
imagery to draw over, and the search regions drawn on it as editable ROIs."""

from __future__ import annotations

import pyqtgraph as pg

from acq4.experiment.search_region import (
    EllipseRegion,
    PolygonRegion,
    RectRegion,
    SearchRegion,
)
from acq4.util import Qt

# Yellow at 2px, matching the survey ROI the AutomationDebug bench already
# draws, so the same shape reads the same way in either module.
REGION_PEN = pg.mkPen("y", width=2)


class _AxisAlignedEllipseROI(pg.EllipseROI):
    """A pg.EllipseROI with no rotate handle.

    EllipseRegion is the ellipse inscribed in an axis-aligned bounding box, so
    there is no region for a rotated ROI to map back to: regionForRoi reads the
    ROI's position and size, and a rotation would be dropped without trace --
    the operator would draw one shape and the survey would tile another.
    """

    def _addHandles(self):
        self.addScaleHandle([1.0, 0.5], [0.5, 0.5])
        self.addScaleHandle([0.5, 1.0], [0.5, 0.5])


def roiForRegion(region: SearchRegion) -> pg.ROI:
    """The editable ROI that draws `region`."""
    if isinstance(region, PolygonRegion):
        return pg.PolyLineROI(
            [list(v) for v in region.vertices],
            closed=True,
            pen=REGION_PEN,
            removable=True,
        )
    x0, y0, x1, y1 = region.bounds()
    roiClass = _AxisAlignedEllipseROI if isinstance(region, EllipseRegion) else pg.RectROI
    return roiClass(
        (x0, y0), (x1 - x0, y1 - y0), pen=REGION_PEN, removable=True
    )


def regionForRoi(roi: pg.ROI) -> SearchRegion | None:
    """The region `roi` currently describes, or None if it does not describe one.

    An ROI can be dragged flat, and its handles can be dragged collinear;
    SearchRegion rejects both, since a region with no extent has no tiles. This
    is reached from a Qt signal while the operator is mid-drag, so it reports
    the failure by returning None rather than by raising a traceback out of a
    slot -- the same choice `SearchPanel.constraints()` makes, and for the same
    reason.

    Corner normalization is left to `_BoxRegion.__post_init__`, which already
    orders its corners -- an ROI resized past its own origin reports a negative
    size, and both paths through that hazard should agree by construction rather
    than by two implementations happening to match.
    """
    try:
        if isinstance(roi, pg.PolyLineROI):
            vertices = []
            for _, localPos in roi.getLocalHandlePositions():
                globalPos = roi.mapToParent(localPos)
                vertices.append((globalPos.x(), globalPos.y()))
            return PolygonRegion(tuple(vertices))
        pos = roi.pos()
        size = roi.size()
        x0, y0 = pos.x(), pos.y()
        regionClass = EllipseRegion if isinstance(roi, pg.EllipseROI) else RectRegion
        return regionClass(x0, y0, x0 + size.x(), y0 + size.y())
    except ValueError:
        return None


class RegionPanel(Qt.QWidget):
    """Area 1's view of the slice: the imagery to draw over, and the search
    regions drawn on it as ROIs the operator can move, resize, and delete.

    Renders a list of regions and reports a list of regions. It holds no Slice
    and never touches one -- the window is what binds the two -- which is what
    lets it be built and tested with no slice, no camera, and no orchestrator,
    and what would let region drawing move into the Camera window later without
    any of this changing.
    """

    # The complete region list after an edit that originated here.
    sigRegionsChanged = Qt.Signal(object)
    sigAddRegionRequested = Qt.Signal()

    def __init__(self):
        super().__init__()
        self._rois: list[pg.ROI] = []

        self.graphicsView = pg.GraphicsView()
        self.graphicsView.setObjectName("Autopatch_regionView")
        self.view = pg.ViewBox()
        self.view.enableAutoRange(x=False, y=False)
        # Tissue is not distorted by the widget's aspect ratio, and a region
        # drawn over a squashed view would not be the region surveyed.
        self.view.setAspectLocked(True)
        self.graphicsView.setCentralItem(self.view)
        # The view is the panel's content, not a strip above its controls: a
        # region spans a slice, and the operator resizes the window to draw.
        self.graphicsView.setSizePolicy(
            Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding
        )
        self.graphicsView.setMinimumSize(300, 300)

        # Item data, not display text, is what regionShape() returns: the window
        # maps it to a region class, and a label is a label.
        self.shapeCombo = Qt.QComboBox()
        for label, key in (
            ("Rectangle", "rect"),
            ("Ellipse", "ellipse"),
            ("Polygon", "polygon"),
        ):
            self.shapeCombo.addItem(label, key)
        self.shapeCombo.setToolTip('The shape "Add region here" seeds.')

        self.addRegionBtn = Qt.QPushButton("Add region here")
        self.addRegionBtn.setToolTip(
            "Add a search region covering roughly 3x3 fields of view around the "
            "camera's current center."
        )
        self.fitBtn = Qt.QPushButton("Fit to regions")
        self.mirrorCheck = Qt.QCheckBox("Mirror to Camera")
        self.mirrorCheck.setToolTip(
            "Draw these regions in the Camera module's view as well. They stay "
            "editable only here."
        )

        controls = Qt.QHBoxLayout()
        controls.addWidget(self.shapeCombo)
        controls.addWidget(self.addRegionBtn)
        controls.addWidget(self.fitBtn)
        controls.addWidget(self.mirrorCheck)
        controls.addStretch()

        layout = Qt.QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.graphicsView)
        self.setLayout(layout)

        self.addRegionBtn.clicked.connect(self.sigAddRegionRequested)
        self.fitBtn.clicked.connect(self.fitToRegions)

    # ---- regions ----
    def regions(self) -> list[SearchRegion]:
        """The regions currently drawn, in the order they were added.

        An ROI the operator has squashed flat describes no region, and is left
        out rather than reported or raised over: it stays on screen to be pulled
        back into shape, and contributes no tiles until it is.
        """
        return [r for r in (regionForRoi(roi) for roi in self._rois) if r is not None]

    def setRegions(self, regions) -> None:
        """Draw `regions`, replacing whatever is drawn now.

        Deliberately silent: this is how the slice's state reaches the panel, so
        echoing it back would have the window write it straight into the slice
        again, and a New slice that cleared this panel would be told by the
        panel it just cleared that the regions are empty.
        """
        for roi in list(self._rois):
            self._detachRoi(roi)
        for region in regions:
            self._attachRoi(roiForRegion(region))

    def _attachRoi(self, roi: pg.ROI) -> None:
        self._rois.append(roi)
        self.view.addItem(roi)
        roi.sigRegionChangeFinished.connect(self._onRoiEdited)
        roi.sigRemoveRequested.connect(self._onRoiRemoved)

    def _detachRoi(self, roi: pg.ROI) -> None:
        Qt.disconnect(roi.sigRegionChangeFinished, self._onRoiEdited)
        Qt.disconnect(roi.sigRemoveRequested, self._onRoiRemoved)
        self._rois.remove(roi)
        self.view.removeItem(roi)

    def _onRoiEdited(self, _roi) -> None:
        # On sigRegionChangeFinished, not sigRegionChanged: a drag in progress
        # is not a decision, and every emission costs the slice a full retile.
        self.sigRegionsChanged.emit(self.regions())

    def _onRoiRemoved(self, roi) -> None:
        self._detachRoi(roi)
        self.sigRegionsChanged.emit(self.regions())

    # ---- view ----
    def regionShape(self) -> str:
        """The shape key for the next region drawn: rect, ellipse, or polygon."""
        return self.shapeCombo.currentData()

    def fitToRegions(self) -> None:
        """Frame every drawn region.

        With nothing drawn this does nothing: autoranging over an empty set is
        how a view ends up at a scale the operator cannot recover from, and the
        button is live before anything has been drawn.
        """
        bounds = [region.bounds() for region in self.regions()]
        if not bounds:
            return
        x0 = min(b[0] for b in bounds)
        y0 = min(b[1] for b in bounds)
        x1 = max(b[2] for b in bounds)
        y1 = max(b[3] for b in bounds)
        self.view.setRange(
            xRange=(x0, x1), yRange=(y0, y1), padding=0.1
        )
