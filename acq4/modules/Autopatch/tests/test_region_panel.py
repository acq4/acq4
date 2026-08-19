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
    # than the ROI list. Framing a zero-extent ROI would not wreck the scale --
    # ViewBox.setRange keeps the current span for a range with none -- but it
    # would re-centre the view on a shape the survey is ignoring.
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


# A region smaller than one field of view, and the single tile that surveys it.
# Chosen that way so the shading reaches a long way past the region it came
# from: fitToRegions() pads by a tenth of what it frames, and an overhang
# smaller than that padding would land inside the padding either way and so
# would not say which of the two was framed.
SMALL = RectRegion(1.0e-3, 2.0e-3, 1.06e-3, 2.03e-3)
COVERAGE_FOV = (200e-6, 100e-6)
COVERAGE_TILE = (1.03e-3, 2.015e-3)


def makeOverlay(panel):
    """Attach a real ProgressOverlay to `panel` the way AutopatchWindow does.

    The window's own two steps in its own order: construct against the view,
    then hand the marker scatter to excludeFromFraming(). A test that left the
    second step out would be asserting about a panel no operator ever has.
    """
    from acq4.modules.Autopatch.progress_overlay import ProgressOverlay

    overlay = ProgressOverlay(panel.view)
    panel.excludeFromFraming(overlay.scatter)
    return overlay


def test_fit_to_regions_frames_the_survey_coverage_shading(qapp):
    """Measured on a rig: pressing Fit on a slice with a region and tiles still
    to survey raised AttributeError out of the button's slot, because the
    shading ProgressOverlay.setCoverage() draws is plain Qt.QGraphicsRectItems
    -- the only things put in this view that are not pyqtgraph items, and so
    the only ones with no mapRectToView() to map their bounds through.

    The shading is framed rather than skipped, which is what the overhang
    asserted below pins down: a tile is a whole field of view, so a region
    smaller than one is surveyed well past its own edges, and what the survey
    will image is worth seeing.

    x is the axis to assert an overhang on. The view is aspect-locked, so
    whichever axis does not match the widget's shape is widened past what was
    asked for -- the union here is twice as wide as it is tall, so y is the
    widened one and only x reports the range this actually chose.
    """
    panel = makePanel()
    overlay = makeOverlay(panel)
    panel.setRegions([SMALL])

    overlay.setCoverage([COVERAGE_TILE], COVERAGE_FOV)
    panel.fitToRegions()

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()
    fovW, fovH = COVERAGE_FOV
    cx, cy = COVERAGE_TILE
    assert vx0 <= cx - fovW / 2 and vx1 >= cx + fovW / 2
    assert vy0 <= cy - fovH / 2 and vy1 >= cy + fovH / 2


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
def test_a_paused_run_hands_rotation_back(qapp, region):
    # A region can record an angle now, so rotation is an ordinary edit and the
    # gate owes it the same treatment as dragging and resizing: off while a run
    # is in flight (asserted above), on again once the run parks at a pause.
    # Its own test because the locked side is the one that protects a survey,
    # and a one-sided test on a two-sided invariant passes happily while the
    # other side is broken.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([region])
    panel.setInteractionLocked(True)
    panel.setRunStatus("paused")

    assert panel._rois[0].rotatable


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


def test_a_fresh_viewport_spans_about_a_metre(qapp):
    # The reason setViewport() exists, pinned so it cannot quietly stop being
    # true: pg.ViewBox's default range is in this view's own units, which are
    # global metres. A click in an empty Area 1 therefore lands a polygon vertex
    # half a metre out, and a "small" drag is hundreds of millimetres.
    panel = makePanel()

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()

    assert (vx1 - vx0) > 0.1
    assert (vy1 - vy0) > 0.1


def test_set_viewport_centres_the_view_where_it_is_told(qapp):
    panel = makePanel()

    panel.setViewport((1.5e-3, -2.5e-3), (200e-6, 120e-6))

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()
    assert (vx0 + vx1) / 2 == pytest.approx(1.5e-3)
    assert (vy0 + vy1) / 2 == pytest.approx(-2.5e-3)


def test_set_viewport_frames_the_span_it_is_given(qapp):
    # The span is what makes a field of view visible rather than sub-pixel. The
    # view is aspect-locked, so one axis may be widened to fit the widget; both
    # must at least contain what was asked for, and neither may still be at the
    # metre scale a fresh viewport starts at.
    panel = makePanel()

    panel.setViewport((1.5e-3, -2.5e-3), (200e-6, 120e-6))

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()
    assert (vx1 - vx0) >= 200e-6
    assert (vy1 - vy0) >= 120e-6
    assert (vx1 - vx0) < 10e-3
    assert (vy1 - vy0) < 10e-3


def test_colour_source_combo_carries_keys_as_item_data(qapp):
    """Item data, not display text, for the same reason regionShape() does:
    the window maps a key to a colour function, and a label is a label."""
    from acq4.modules.Autopatch.progress_colors import COLOR_SOURCES

    panel = makePanel()

    keys = [
        panel.colorCombo.itemData(i) for i in range(panel.colorCombo.count())
    ]
    assert keys == [key for _label, key, _func in COLOR_SOURCES]


def test_colour_source_reports_the_selection(qapp):
    """Asserts the literal key rather than itemData(1), so a combo carrying no
    item data at all (itemData returning None on both sides) or a colorSource()
    that read display text instead of data can no longer pass unnoticed."""
    from acq4.modules.Autopatch.progress_colors import COLOR_SOURCES

    assert COLOR_SOURCES[1][1] == "health"
    panel = makePanel()

    panel.colorCombo.setCurrentIndex(1)

    assert panel.colorSource() == "health"


def test_changing_the_colour_source_announces_the_new_key(qapp):
    """Asserts the literal key rather than itemData(1), so a combo carrying no
    item data at all (itemData returning None on both sides) or a colorSource()
    that read display text instead of data can no longer pass unnoticed."""
    from acq4.modules.Autopatch.progress_colors import COLOR_SOURCES

    assert COLOR_SOURCES[1][1] == "health"
    panel = makePanel()
    seen = []
    panel.sigColorSourceChanged.connect(seen.append)

    panel.colorCombo.setCurrentIndex(1)

    assert seen == ["health"]


def test_legend_renders_one_entry_per_pair(qapp):
    import pyqtgraph as pg

    panel = makePanel()

    panel.setLegend([("Patched", pg.mkBrush(0, 170, 60)), ("Failed", pg.mkBrush(215, 45, 45))])

    assert panel.legendLabels() == ["Patched", "Failed"]


def test_setting_a_legend_replaces_the_last_one(qapp):
    import pyqtgraph as pg

    panel = makePanel()
    panel.setLegend([("Patched", pg.mkBrush(0, 170, 60))])

    panel.setLegend([("Sparse", pg.mkBrush(70, 110, 200))])

    assert panel.legendLabels() == ["Sparse"]


def test_legend_swatch_shows_the_brush_colour(qapp):
    # A legend with correct labels and wrong colours lies to the operator about
    # what they are looking at, which is worse than no legend at all. Painting
    # every swatch a fixed colour, ignoring the brush entirely, still passes
    # the two tests above, since neither reads a swatch's colour.
    import pyqtgraph as pg

    panel = makePanel()
    firstBrush = pg.mkBrush(70, 110, 200)
    secondBrush = pg.mkBrush(240, 140, 20)

    panel.setLegend([("Sparse", firstBrush), ("Crowded", secondBrush)])

    # legendLabels() picks out labels by their non-empty text; swatches are the
    # complementary QLabels in the row, the ones with no text at all.
    swatches = [
        panel.legendRow.itemAt(i).widget()
        for i in range(panel.legendRow.count())
        if isinstance(panel.legendRow.itemAt(i).widget(), Qt.QLabel)
        and not panel.legendRow.itemAt(i).widget().text()
    ]

    assert len(swatches) == 2
    assert swatches[0].palette().color(swatches[0].backgroundRole()) == firstBrush.color()
    assert swatches[1].palette().color(swatches[1].backgroundRole()) == secondBrush.color()


def test_the_slice_view_shrinks_with_the_panel_rather_than_holding_a_floor(qapp):
    """The window puts this panel in an area whose size the operator sets, and
    the view is what should give when they make it small: a slice view that
    refuses to go under a few hundred pixels square gets scrolled inside that
    area instead, which is a viewport dragged over a picture rather than a
    smaller picture. Small enough to still be a view, and no larger.
    """
    panel = makePanel()

    minimum = panel.graphicsView.minimumSize()
    assert minimum.width() <= 150, minimum.width()
    assert minimum.height() <= 150, minimum.height()
