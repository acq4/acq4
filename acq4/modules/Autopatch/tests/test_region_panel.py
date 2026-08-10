"""Tests for Area 1's region view: what it draws, what it reports back when the
operator edits a region, and what it lets them touch."""

import pytest

from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


RECT = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
OTHER = RectRegion(3.0e-3, 1.0e-3, 3.6e-3, 1.2e-3)
ELLIPSE = EllipseRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
TRIANGLE = PolygonRegion(((1.0e-3, 2.0e-3), (1.4e-3, 2.02e-3), (1.1e-3, 2.1e-3)))

# The gate has to hold for every shape, and the three ROI classes behind them
# have three different editing surfaces: a rect's handles, an ellipse's handles,
# and a polygon's clickable edges on top of its handles.
SHAPES = [RECT, ELLIPSE, TRIANGLE]


def makePanel():
    from acq4.modules.Autopatch.region_panel import RegionPanel

    return RegionPanel()


def clickSegment(roi, segment, pos):
    """Left-click one of a polygon's edges the way the scene would deliver it.

    QGraphicsScene routes a press only to an item whose acceptedMouseButtons
    include that button, so a segment set to NoButton never sees the event at
    all. That dispatch is the whole mechanism behind locking a polygon, and
    calling roi.segmentClicked() directly steps straight over it.
    """
    if not (segment.acceptedMouseButtons() & Qt.Qt.LeftButton):
        return
    roi.segmentClicked(segment, pos=pos)


def test_a_fresh_panel_holds_no_regions(qapp):
    assert makePanel().regions() == []


def test_setregions_draws_one_roi_per_region(qapp):
    panel = makePanel()
    panel.setRegions([RECT, OTHER])

    assert len(panel._rois) == 2
    assert panel.regions() == [RECT, OTHER]


def test_setregions_replaces_rather_than_appends(qapp):
    # The window pushes the slice's whole region list on every refresh, so a
    # panel that appended would redraw the same region once per refresh.
    panel = makePanel()
    panel.setRegions([RECT, OTHER])
    panel.setRegions([ELLIPSE])

    assert len(panel._rois) == 1
    assert panel.regions() == [ELLIPSE]


def test_setregions_does_not_echo_back(qapp):
    # setRegions is how the slice's state reaches the panel. Echoing it would
    # write straight back into the slice, and a New slice that cleared the panel
    # would be told by that panel that its regions are empty.
    panel = makePanel()
    seen = []
    panel.sigRegionsChanged.connect(seen.append)
    panel.setRegions([RECT])

    assert seen == []


def test_dragging_a_region_reports_the_whole_list(qapp):
    # The window replaces the slice's regions wholesale, so an edit to one has
    # to arrive with its neighbours intact rather than on its own.
    panel = makePanel()
    panel.setRegions([RECT, OTHER])
    seen = []
    panel.sigRegionsChanged.connect(seen.append)

    roi = panel._rois[0]
    # finish=False: setPos's own default (finish=True) already emits
    # sigRegionChangeFinished, which is what a real drag never does mid-gesture
    # (pg.MouseDragHandler always moves with finish=False and fires the signal
    # exactly once, from _moveFinished, on release) -- so the explicit emit
    # below is what stands in for that release.
    roi.setPos((2.0e-3, 5.0e-3), finish=False)
    roi.sigRegionChangeFinished.emit(roi)

    assert len(seen) == 1
    moved, untouched = seen[0]
    # bounds(), compared with approx: pos + size round-trips through the same
    # subtraction and re-addition RectRegion's own fixture construction does,
    # and at these magnitudes that is not bit-exact (2.0e-3 + (1.4e-3 - 1.0e-3)
    # is 2.4000000000000002e-3 on this interpreter, not 2.4e-3).
    assert moved.bounds() == pytest.approx((2.0e-3, 5.0e-3, 2.4e-3, 5.1e-3))
    assert untouched == OTHER


def test_removing_a_region_reports_the_list_without_it(qapp):
    panel = makePanel()
    panel.setRegions([RECT, OTHER])
    seen = []
    panel.sigRegionsChanged.connect(seen.append)

    panel._rois[0].sigRemoveRequested.emit(panel._rois[0])

    assert seen == [[OTHER]]
    assert panel.regions() == [OTHER]


def test_a_removed_roi_leaves_the_view(qapp):
    # Dropping it from the list but leaving the item in the scene would keep a
    # deleted region on screen, and keep it alive.
    panel = makePanel()
    panel.setRegions([RECT])
    roi = panel._rois[0]

    roi.sigRemoveRequested.emit(roi)

    assert roi.scene() is None


def test_adding_a_polygon_vertex_reaches_the_reported_region(qapp):
    # Reshaping a polygon is pyqtgraph's own segmentClicked inserting a handle
    # where an edge was clicked -- the mechanism that makes outlining a cortical
    # layer possible without any drawing code of ours. Pinned here because the
    # panel depends on it: a handle added this way has to arrive in the region
    # the panel reports, in global coordinates.
    #
    # segments[0] is the *closing* edge (last vertex back to first), not the
    # first one, so the new vertex lands between the triangle's third and first
    # points. Membership rather than a position is asserted for that reason --
    # pyqtgraph's ordering is its own business as long as handle order,
    # getState()['points'], and shape() agree, which they do.
    triangle = PolygonRegion(
        ((1.0e-3, 2.0e-3), (1.4e-3, 2.02e-3), (1.1e-3, 2.1e-3))
    )
    panel = makePanel()
    panel.setRegions([triangle])
    roi = panel._rois[0]

    roi.segmentClicked(roi.segments[0], pos=Qt.QPointF(1.2e-3, 2.01e-3))

    reported = panel.regions()[0]
    assert len(reported.vertices) == 4
    assert (1.2e-3, 2.01e-3) in [
        (pytest.approx(x), pytest.approx(y)) for x, y in reported.vertices
    ]


def test_an_roi_squashed_flat_stays_on_screen_but_is_not_reported(qapp):
    # Removing it would delete the operator's work mid-drag; reporting it would
    # hand the slice a region with no tiles. It stays visible and uncounted.
    panel = makePanel()
    panel.setRegions([RECT, OTHER])

    panel._rois[0].setSize((0.0, 0.1e-3))

    assert len(panel._rois) == 2
    assert panel.regions() == [OTHER]


def test_fit_to_regions_ignores_a_squashed_roi(qapp):
    # regions() drops it, so fitToRegions must read through regions() rather
    # than the ROI list, or it frames a bounding box it cannot compute -- and
    # framing a zero-extent ROI is itself the unrecoverable scale the empty-set
    # case below is careful to avoid.
    panel = makePanel()
    panel.setRegions([RECT])
    panel._rois[0].setSize((0.0, 0.0))
    before = panel.view.viewRange()

    panel.fitToRegions()

    assert panel.view.viewRange() == before


def test_the_shape_selector_offers_all_three_shapes(qapp):
    # PolygonRegion has been implemented and tested since P2c-1 with no control
    # able to produce one; a cortical layer is the reason regions became shapes.
    panel = makePanel()
    shapes = [panel.shapeCombo.itemData(i) for i in range(panel.shapeCombo.count())]

    assert shapes == ["rect", "ellipse", "polygon"]


def test_the_shape_selector_reports_item_data_not_its_label(qapp):
    panel = makePanel()
    panel.shapeCombo.setCurrentIndex(panel.shapeCombo.findData("polygon"))

    assert panel.regionShape() == "polygon"


def test_the_add_region_button_asks_its_owner(qapp):
    # The panel does not know where the camera is pointing; the window does.
    panel = makePanel()
    panel.setSliceReady(True)
    requests = []
    panel.sigAddRegionRequested.connect(lambda: requests.append(True))

    panel.addRegionBtn.click()

    assert requests == [True]


def test_fit_to_regions_frames_every_region(qapp):
    panel = makePanel()
    panel.setRegions([RECT, OTHER])

    panel.fitToRegions()

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()
    assert vx0 <= 1.0e-3 and vx1 >= 3.6e-3
    assert vy0 <= 1.0e-3 and vy1 >= 2.1e-3


def test_fit_to_regions_with_nothing_drawn_is_a_no_op(qapp):
    # The button is live before the operator has drawn anything, and autoranging
    # over an empty set is how a view ends up at an unrecoverable scale.
    panel = makePanel()
    before = panel.view.viewRange()

    panel.fitToRegions()

    assert panel.view.viewRange() == before


def makePinnedFrameItem(x, y, w, h):
    """An image item standing in for one mirrored pinned frame, placed and
    scaled to cover (x, y) to (x + w, y + h) in global metres."""
    import numpy as np
    import pyqtgraph as pg

    # Asymmetric on purpose: a square array cannot catch a swapped axis.
    item = pg.ImageItem(np.zeros((4, 7), dtype=float))
    # Scaled off the item's own bounding rect rather than off the array shape,
    # which is not the same thing: pg.ImageItem's default column-major axis
    # order makes shape (4, 7) an item 4 wide and 7 tall.
    pixels = item.boundingRect()
    transform = Qt.QTransform()
    transform.translate(x, y)
    transform.scale(w / pixels.width(), h / pixels.height())
    item.setTransform(transform)
    return item


def test_fit_to_regions_frames_pinned_frames_when_nothing_is_drawn(qapp):
    # The ordinary first state: imagery mirrored in, no region seeded yet. A
    # fresh viewport spans about a metre, so 200um of tissue is rendered
    # sub-pixel and there is no other one-click way to reach it.
    panel = makePanel()
    panel.view.addItem(makePinnedFrameItem(1.0e-3, 2.0e-3, 0.2e-3, 0.1e-3))

    panel.fitToRegions()

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()
    assert vx0 <= 1.0e-3 and vx1 >= 1.2e-3
    assert vy0 <= 2.0e-3 and vy1 >= 2.1e-3
    # And framed, not merely containing it: a viewport still a metre wide
    # contains those bounds too.
    assert (vx1 - vx0) < 1.0e-3


def test_fit_to_regions_frames_the_regions_and_the_pinned_frames_together(qapp):
    # Both, not whichever it finds first: a region drawn beside the imagery it
    # was drawn from must not push that imagery off screen.
    panel = makePanel()
    panel.view.addItem(makePinnedFrameItem(3.0e-3, 1.0e-3, 0.2e-3, 0.1e-3))
    panel.setRegions([RECT])

    panel.fitToRegions()

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()
    assert vx0 <= 1.0e-3 and vx1 >= 3.2e-3
    assert vy0 <= 1.0e-3 and vy1 >= 2.1e-3


def test_a_panel_with_no_slice_cannot_be_drawn_on(qapp):
    # New slice is what makes Area 1 usable, and greyed-out controls are how the
    # operator is told so -- the same treatment Area 2 already gets.
    panel = makePanel()

    assert not panel.addRegionBtn.isEnabled()
    assert not panel.shapeCombo.isEnabled()


def test_a_slice_makes_the_controls_live(qapp):
    panel = makePanel()
    panel.setSliceReady(True)

    assert panel.addRegionBtn.isEnabled()
    assert panel.shapeCombo.isEnabled()


@pytest.mark.parametrize("region", SHAPES)
def test_a_running_run_locks_editing(qapp, region):
    # The regions parameterise a search already underway on the worker thread.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([region])
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")

    roi = panel._rois[0]
    assert not panel.addRegionBtn.isEnabled()
    assert not roi.translatable
    assert not roi.resizable
    assert not roi.removable
    assert not roi.rotatable
    assert not any(handle.isVisible() for handle in roi.getHandles())
    assert all(
        segment.acceptedMouseButtons() == Qt.Qt.NoButton
        for segment in getattr(roi, "segments", [])
    )


@pytest.mark.parametrize("region", SHAPES)
def test_a_paused_run_unlocks_editing(qapp, region):
    # The other side of the same invariant. A one-sided test on a two-sided
    # invariant passes happily while the other side is broken -- which is how
    # CellPanel's flush regressed in both directions across P2b's reviews.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([region])
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    panel.setRunStatus("paused")

    roi = panel._rois[0]
    assert panel.addRegionBtn.isEnabled()
    assert roi.translatable
    assert roi.resizable
    assert roi.removable
    assert all(
        segment.acceptedMouseButtons() == Qt.Qt.LeftButton
        for segment in getattr(roi, "segments", [])
    )


@pytest.mark.parametrize("region", SHAPES)
def test_a_paused_run_does_not_hand_back_a_rotation(qapp, region):
    # Unlocking restores every affordance the ROI shipped with -- except this
    # one, which it never had. `rotatable` is off by construction and is not the
    # gate's to give back: no region can express a rotation whatever the run is
    # doing. Its own test because unlocking sets three sibling flags to True and
    # a fourth set alongside them would look like it belonged.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([region])
    panel.setInteractionLocked(True)
    panel.setRunStatus("paused")

    assert not panel._rois[0].rotatable


@pytest.mark.parametrize("region", SHAPES)
def test_a_locked_roi_cannot_be_rotated(qapp, region):
    # The lock's flags stop a drag and a resize; an Alt-drag is a third gesture
    # that needs no handle, and a rotation reported to the slice mid-run is an
    # edit the gate is supposed to make impossible.
    from .test_region_adapters import altDragRoi

    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([region])
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    seen = []
    panel.sigRegionsChanged.connect(seen.append)
    before = panel.regions()

    altDragRoi(panel._rois[0])

    assert panel._rois[0].angle() == 0
    assert panel.regions() == before
    assert seen == []


def test_a_locked_polygons_edge_cannot_be_clicked_into_a_new_vertex(qapp):
    # A polygon's editing surface is not only its handles: pyqtgraph gives every
    # edge its own item that takes left clicks and inserts a vertex there. Left
    # live, one click on a locked polygon reshapes the region and hands the whole
    # list to the window -- mid-survey, which is the one thing the gate exists to
    # prevent.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([TRIANGLE])
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    seen = []
    panel.sigRegionsChanged.connect(seen.append)
    roi = panel._rois[0]

    clickSegment(roi, roi.segments[0], Qt.QPointF(1.2e-3, 2.01e-3))

    assert len(panel.regions()[0].vertices) == 3
    assert seen == []


def test_an_unlocked_polygons_edge_still_inserts_a_vertex(qapp):
    # The other side: gating the segments must not leave a polygon permanently
    # unreshapeable, which is the only reason to choose polygon at all.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([TRIANGLE])
    roi = panel._rois[0]

    clickSegment(roi, roi.segments[0], Qt.QPointF(1.2e-3, 2.01e-3))

    assert len(panel.regions()[0].vertices) == 4


def test_a_handle_that_appears_while_locked_is_hidden_too(qapp):
    # An edit can grow an ROI's own handle list -- segmentClicked adds one --
    # and a handle is born visible and draggable whatever the gate says. So the
    # gate is re-applied whenever an ROI reports a change, keeping "an ROI that
    # has just reported an edit matches the gate" a local property of this panel
    # rather than a survey of every pyqtgraph path that can add a handle.
    #
    # Driven straight through segmentClicked, past the dispatch that stops a
    # locked polygon reaching here at all (see the test above), because that is
    # the only way to reach this repair from a locked panel. It reaches the
    # handle and not the segment: pyqtgraph adds the handle -- which is what
    # emits -- before it builds the segment.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([TRIANGLE])
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    roi = panel._rois[0]

    roi.segmentClicked(roi.segments[0], pos=Qt.QPointF(1.2e-3, 2.01e-3))

    assert not any(handle.isVisible() for handle in roi.getHandles())


def test_surveying_locks_editing_even_though_pause_was_pressed(qapp):
    # "surveying" is what a run reports while the producer images tiles, and a
    # Pause pressed during one does not park the loop until that refill is done.
    # Unlocking on anything short of the emitted "paused" would let an edit land
    # while the producer is reading regions.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    panel.setRunStatus("surveying")

    assert not panel.addRegionBtn.isEnabled()


@pytest.mark.parametrize("region", SHAPES)
def test_resuming_from_paused_locks_editing_again(qapp, region):
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([region])
    panel.setInteractionLocked(True)
    panel.setRunStatus("paused")
    panel.setRunStatus("running")

    roi = panel._rois[0]
    assert not panel.addRegionBtn.isEnabled()
    assert not roi.translatable
    assert all(
        segment.acceptedMouseButtons() == Qt.Qt.NoButton
        for segment in getattr(roi, "segments", [])
    )


def test_the_gate_is_readable_from_outside(qapp):
    # The window drops region edits that arrive while the panel is locked, and
    # asking the panel is how it knows. Public because a second reader of a
    # private predicate is a private predicate with two owners.
    panel = makePanel()
    assert not panel.isEditable()

    panel.setSliceReady(True)
    assert panel.isEditable()

    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    assert not panel.isEditable()


def test_regions_drawn_while_locked_are_still_shown(qapp):
    # Locking is about editing, not about hiding: the operator watching a run
    # must still see what is being surveyed.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    panel.setRegions([RECT, OTHER])

    assert len(panel._rois) == 2
    assert panel.regions() == [RECT, OTHER]


@pytest.mark.parametrize("region", SHAPES)
def test_a_region_added_while_locked_is_locked_too(qapp, region):
    # setRegions builds fresh ROIs, which default to editable; a gate applied
    # only on the transition would leave them draggable mid-run.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    panel.setRegions([region])

    roi = panel._rois[0]
    assert not roi.translatable
    assert all(
        segment.acceptedMouseButtons() == Qt.Qt.NoButton
        for segment in getattr(roi, "segments", [])
    )
