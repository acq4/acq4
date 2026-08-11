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


def roiForRegion(region: SearchRegion) -> pg.ROI:
    """The editable ROI that draws `region`.

    Rotatable, on every shape, because every shape can now record the result: a
    box region carries an angle, and a polygon's vertices are read back through
    the ROI's own transform, which a rotation is part of. The stock
    `pg.EllipseROI` is used as it ships, rotate handle and all, since that handle
    now does what it looks like it does.

    Sized from `box()` rather than `bounds()`: those differ once there is an
    angle, and it is the box the operator sized -- not the larger axis-aligned
    extent the tiler plans over -- that the ROI is drawn from and turned.

    `setAngle` with no explicit centre turns the ROI about its local origin and
    leaves `pos()` where it is, which is the pivot `_BoxRegion` documents. That
    correspondence is what makes `regionForRoi` below its exact inverse.
    """
    if isinstance(region, PolygonRegion):
        return pg.PolyLineROI(
            [list(v) for v in region.vertices],
            closed=True,
            pen=REGION_PEN,
            removable=True,
            rotatable=True,
        )
    x0, y0, x1, y1 = region.box()
    roiClass = pg.EllipseROI if isinstance(region, EllipseRegion) else pg.RectROI
    roi = roiClass(
        (x0, y0), (x1 - x0, y1 - y0), pen=REGION_PEN, removable=True, rotatable=True
    )
    if region.angle:
        roi.setAngle(region.angle)
    return roi


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

    An ROI resized past its own origin reports a negative size, so the corner
    `pos()` sits on is no longer the region's `(x0, y0)`. That matters more than
    it used to: `(x0, y0)` is the pivot, so handing the region the wrong corner
    would turn the shape about the wrong point and draw it somewhere else. The
    box's lowest corner is found in ROI-local coordinates and mapped out through
    the ROI's transform, which is the corner that is its own image under the turn
    and therefore the one the region's convention wants.

    A polygon needs none of this: its vertices go through `mapToParent`
    individually, so a rotation arrives baked into the coordinates.
    """
    try:
        if isinstance(roi, pg.PolyLineROI):
            vertices = []
            for _, localPos in roi.getLocalHandlePositions():
                globalPos = roi.mapToParent(localPos)
                vertices.append((globalPos.x(), globalPos.y()))
            return PolygonRegion(tuple(vertices))
        size = roi.size()
        w, h = size.x(), size.y()
        localX = 0.0 if w >= 0 else w
        localY = 0.0 if h >= 0 else h
        if localX == 0.0 and localY == 0.0:
            # The ordinary case, read straight off `pos()` so that an unrotated
            # region round-trips through exactly the floats it was built from.
            corner = roi.pos()
        else:
            corner = roi.mapToParent(Qt.QPointF(localX, localY))
        x0, y0 = corner.x(), corner.y()
        regionClass = EllipseRegion if isinstance(roi, pg.EllipseROI) else RectRegion
        return regionClass(x0, y0, x0 + abs(w), y0 + abs(h), roi.angle())
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

        `rotatable` belongs in that list now that a region can record an angle:
        it is a fourth way to change the tissue a survey is about to image, and
        pg.MouseDragHandler enters rotate mode on an Alt-modified drag of the ROI
        *body* -- no handle involved -- so hiding the handles does not reach it.
        """
        editable = self.isEditable()
        roi.translatable = editable
        roi.resizable = editable
        roi.rotatable = editable
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
        which drops an ROI squashed to no extent. Framing one would re-centre
        the view on a shape that is not a region: ViewBox.setRange keeps the
        current span when a range has none of its own, so the scale survives,
        but the operator is moved somewhere they did not ask to go.
        """
        rect = None
        for item in self.view.addedItems:
            if item in self._rois:
                continue
            itemRect = item.mapRectToView(item.boundingRect()).normalized()
            rect = itemRect if rect is None else rect.united(itemRect)
        return rect

    def setViewport(self, center, span) -> None:
        """Frame the view on `center` across `span`, both in global metres.

        A fresh pg.ViewBox reports a range of about [[-0.167, 1.167], [0, 1]],
        and this view's units are global metres, so an operator clicking in an
        empty Area 1 lands a polygon vertex half a metre out and a small drag is
        hundreds of millimetres. The window calls this when a slice starts, so
        the first click lands on tissue-sized coordinates.

        Takes a coordinate and a span rather than a camera: this panel renders a
        region list and holds no devices. The view is aspect-locked, so the
        axis that does not match the widget's shape is widened past `span`.

        `fitToRegions` is the later re-framing, once there is something drawn to
        frame; this is the one that has to work with nothing drawn at all.
        """
        cx, cy = center
        w, h = span
        self.view.setRange(
            xRange=(cx - w / 2, cx + w / 2),
            yRange=(cy - h / 2, cy + h / 2),
            padding=0,
        )

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
