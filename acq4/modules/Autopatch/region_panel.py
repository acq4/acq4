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
    """A pg.EllipseROI with its rotate handle replaced by a second scale handle.

    `rotatable=False` is what actually stops a rotation (see roiForRegion), and
    it already makes pg.EllipseROI's stock rotate handle inert. Replacing the
    handle as well is about the affordance rather than the geometry: a handle
    the operator can grab and drag, that then does nothing at all, is a control
    that lies. The replacement scales along the other axis, so the ellipse gains
    the width and height handles the rectangle already has.
    """

    def _addHandles(self):
        self.addScaleHandle([1.0, 0.5], [0.5, 0.5])
        self.addScaleHandle([0.5, 1.0], [0.5, 0.5])


def roiForRegion(region: SearchRegion) -> pg.ROI:
    """The editable ROI that draws `region`.

    `rotatable=False` on every shape. No region can express a rotation --
    RectRegion and EllipseRegion are axis-aligned boxes, and PolygonRegion's
    vertices are read back through the ROI's own transform -- so a rotated ROI
    either round-trips as an unrotated box displaced by the rotation, or as a
    polygon somewhere else entirely. Either way the operator outlines one patch
    of tissue and the survey tiles another. Dropping the rotate *handle* does
    not reach this: pg.MouseDragHandler enters rotate mode on an Alt-modified
    drag of the ROI body, with no handle involved, and consults this flag alone.
    """
    if isinstance(region, PolygonRegion):
        return pg.PolyLineROI(
            [list(v) for v in region.vertices],
            closed=True,
            pen=REGION_PEN,
            removable=True,
            rotatable=False,
        )
    x0, y0, x1, y1 = region.bounds()
    roiClass = _AxisAlignedEllipseROI if isinstance(region, EllipseRegion) else pg.RectROI
    return roiClass(
        (x0, y0), (x1 - x0, y1 - y0), pen=REGION_PEN, removable=True, rotatable=False
    )


def regionForRoi(roi: pg.ROI) -> SearchRegion | None:
    """The region `roi` currently describes, or None if it does not describe one.

    An ROI can be dragged flat, and a polygon's handles can be dragged onto a
    horizontal or vertical line; SearchRegion rejects both, since what it checks
    is the axis-aligned bounding box and a box with no extent has no tiles. A
    polygon flattened onto a *diagonal* is not rejected -- its bounding box
    still has extent -- and tiles along that line. This is reached from a Qt
    signal while the operator is mid-drag, so it reports the failure by
    returning None rather than by raising a traceback out of a slot -- the same
    choice `SearchPanel.constraints()` makes, and for the same reason.

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

        # The three independent reasons editing can be off, kept apart because
        # no writer can see another's condition: collapsing them into one
        # boolean would let a run ending unlock a panel that still has no slice
        # behind it. Same split SearchPanel already makes.
        self._runLocked = False
        self._sliceReady = False
        self._runStatus = None

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

        self._applyLock()

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
        self._applyRoiLock(roi)

    def _detachRoi(self, roi: pg.ROI) -> None:
        Qt.disconnect(roi.sigRegionChangeFinished, self._onRoiEdited)
        Qt.disconnect(roi.sigRemoveRequested, self._onRoiRemoved)
        self._rois.remove(roi)
        self.view.removeItem(roi)

    def _onRoiEdited(self, roi) -> None:
        # Re-applied first, because an edit can grow the ROI's own handle list:
        # PolyLineROI.segmentClicked adds one, and a handle is born visible and
        # draggable whatever the gate currently says. Keeping "an ROI that has
        # just reported an edit matches the gate" true here makes it a local
        # property of this panel rather than a survey of every pyqtgraph path
        # that can add a handle.
        self._applyRoiLock(roi)
        # On sigRegionChangeFinished, not sigRegionChanged: a drag in progress
        # is not a decision, and every emission costs the slice a full retile.
        self.sigRegionsChanged.emit(self.regions())

    def _onRoiRemoved(self, roi) -> None:
        self._detachRoi(roi)
        self.sigRegionsChanged.emit(self.regions())

    # ---- editing gate ----
    def setInteractionLocked(self, locked: bool) -> None:
        """Disable editing while a run is in flight; the regions stay visible.

        The operator watching a run must still see what is being surveyed, so
        this is about editing, not about hiding.
        """
        self._runLocked = locked
        self._applyLock()

    def setSliceReady(self, ready: bool) -> None:
        """Whether a slice exists for these regions to belong to.

        New slice is what makes Area 1 usable, and the greyed-out controls are
        how the operator is told that it is the first step.
        """
        self._sliceReady = ready
        self._applyLock()

    def setRunStatus(self, status: str) -> None:
        """The bound run's last reported status.

        Only "paused" matters here, and only the *emitted* status will do.
        Orchestrator._checkPause() runs at the top of the run loop, before the
        refill check, so a Pause clicked during a survey does not stop that
        survey -- the producer goes on imaging tiles and reading regions for as
        long as it takes, and the loop parks at the next iteration. But
        sigStatus("paused") is emitted from inside _checkPause, immediately
        before it blocks, so while that status is current the worker is parked
        there and cannot be inside a refill. That is what makes editing safe.
        """
        self._runStatus = status
        self._applyLock()

    def isEditable(self) -> bool:
        """Whether regions may currently be edited.

        Public because the window reads it too: it drops region edits that
        arrive while this is False, since a signal is not a permission check.
        """
        if not self._sliceReady:
            return False
        return not self._runLocked or self._runStatus == "paused"

    def _applyLock(self) -> None:
        editable = self.isEditable()
        self.addRegionBtn.setEnabled(editable)
        self.shapeCombo.setEnabled(editable)
        for roi in self._rois:
            self._applyRoiLock(roi)

    def _applyRoiLock(self, roi: pg.ROI) -> None:
        """Make one ROI match the current gate.

        Every affordance, not just the drag: leaving the handles live would let
        a locked region be resized, and leaving `removable` on would let it be
        deleted from the context menu.

        A polygon carries one more surface than the flags reach. Its edges are
        separate child items, each created accepting left clicks and wired to
        segmentClicked, which inserts a vertex where the edge was clicked. So a
        locked polygon with live segments is one click away from a reshaped
        region reaching the slice mid-survey.

        `rotatable` is deliberately not touched: it is off from construction for
        every shape (see roiForRegion) and is not the gate's to hand back, since
        no region can express a rotation whether a run is in flight or not.
        """
        editable = self.isEditable()
        roi.translatable = editable
        roi.resizable = editable
        roi.removable = editable
        for handle in roi.getHandles():
            handle.setVisible(editable)
        for segment in getattr(roi, "segments", []):
            segment.setAcceptedMouseButtons(
                Qt.Qt.LeftButton if editable else Qt.Qt.NoButton
            )

    # ---- view ----
    def regionShape(self) -> str:
        """The shape key for the next region drawn: rect, ellipse, or polygon."""
        return self.shapeCombo.currentData()

    def _mirroredImageryBounds(self) -> Qt.QRectF | None:
        """The extent of everything in the view that is not a region ROI, or
        None if there is nothing else there.

        In practice the mirrored pinned frames. Read off the view rather than
        from PinnedFrameMirror: the panel renders regions and knows nothing
        about what else is put in its view, and a back-reference to the mirror
        would make the two mutually dependent for a bounding box.

        Region ROIs are skipped because their bounds come from `regions()`,
        which drops an ROI squashed to no extent -- and a zero-extent rectangle
        is exactly what would frame the view at a scale nobody can recover from.
        """
        rect = None
        for item in self.view.addedItems:
            if item in self._rois:
                continue
            itemRect = item.mapRectToView(item.boundingRect()).normalized()
            rect = itemRect if rect is None else rect.united(itemRect)
        return rect

    def fitToRegions(self) -> None:
        """Frame every drawn region and the imagery drawn under them.

        Both, because a panel with pinned frames mirrored in and no region
        seeded yet is the ordinary first state: a fresh viewport spans about a
        metre, which renders a field of view sub-pixel, and this button is the
        only one-click way back.

        With neither this does nothing: autoranging over an empty set is how a
        view ends up at a scale the operator cannot recover from, and the button
        is live before anything has been drawn.
        """
        rect = self._mirroredImageryBounds()
        for region in self.regions():
            x0, y0, x1, y1 = region.bounds()
            regionRect = Qt.QRectF(x0, y0, x1 - x0, y1 - y0)
            rect = regionRect if rect is None else rect.united(regionRect)
        if rect is None:
            return
        self.view.setRange(
            xRange=(rect.left(), rect.right()),
            yRange=(rect.top(), rect.bottom()),
            padding=0.1,
        )
