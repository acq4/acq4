"""Tests for the mapping between a Slice's SearchRegion shapes and the
pyqtgraph ROIs Area 1 draws them with."""

import math

import pytest

from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


# Deliberately asymmetric, at real SI magnitudes: a square fixture cannot test
# an axis mapping, which is exactly how a swapped rx/ry survived every ellipse
# test in P2c-1.
RECT = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
ELLIPSE = EllipseRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
TRIANGLE = PolygonRegion(((1.0e-3, 2.0e-3), (1.4e-3, 2.02e-3), (1.1e-3, 2.1e-3)))


class _AltDragEvent:
    """One event of the Alt-modified body drag pyqtgraph turns into a rotation.

    No handle is involved: pg.MouseDragHandler.mouseDragEvent reads the modifier
    off the event and enters rotate mode if `roi.rotatable`, so dropping the
    rotate handle does not reach this gesture -- only the flag does.

    Rotation is driven by the horizontal scene-position delta and centred on
    `buttonDownPos`, so those are the only coordinates that have to be real; the
    rest is the QGraphicsSceneMouseEvent surface the handler touches.
    """

    def __init__(self, roi, dx, finish=False):
        self._finish = finish
        self._dx = dx
        # Grabbed at the shape's own centre, the way a body drag is. In local
        # coordinates, which is what centerLocal wants.
        self._downPos = roi.boundingRect().center()

    def isStart(self):
        return not self._finish

    def isFinish(self):
        return self._finish

    def button(self):
        return Qt.Qt.LeftButton

    def modifiers(self):
        return Qt.Qt.AltModifier

    def buttonDownPos(self, *args):
        return self._downPos

    def pos(self):
        return self._downPos

    def buttonDownScenePos(self, *args):
        return Qt.QPointF(0.0, 0.0)

    def scenePos(self):
        return Qt.QPointF(self._dx, 0.0)

    def accept(self):
        pass

    def ignore(self):
        pass


def altDragRoi(roi, dx=60.0):
    """Alt-drag `roi`'s body -- pyqtgraph's rotate gesture -- and release."""
    roi.mouseDragEvent(_AltDragEvent(roi, dx))
    roi.mouseDragEvent(_AltDragEvent(roi, dx, finish=True))


@pytest.mark.parametrize("region", [RECT, ELLIPSE, TRIANGLE])
def test_a_region_round_trips_through_its_roi(qapp, region):
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    assert regionForRoi(roiForRegion(region)) == region


@pytest.mark.parametrize("region", [RECT, ELLIPSE, TRIANGLE])
def test_the_roi_lands_on_the_regions_own_bounds(qapp, region):
    # Round-tripping equal objects would still pass if both directions shared
    # the same wrong convention (origin vs centre, say). Checking the ROI's own
    # geometry against the region's bounds is what pins the convention.
    from acq4.modules.Autopatch.region_panel import roiForRegion

    roi = roiForRegion(region)
    x0, y0, x1, y1 = region.bounds()
    rect = roi.boundingRect()
    pos = roi.pos()
    assert pos.x() + rect.x() == pytest.approx(x0)
    assert pos.y() + rect.y() == pytest.approx(y0)
    assert rect.width() == pytest.approx(x1 - x0)
    assert rect.height() == pytest.approx(y1 - y0)


def test_a_rect_and_an_ellipse_map_to_different_roi_types(qapp):
    import pyqtgraph as pg

    from acq4.modules.Autopatch.region_panel import roiForRegion

    assert isinstance(roiForRegion(ELLIPSE), pg.EllipseROI)
    assert not isinstance(roiForRegion(RECT), pg.EllipseROI)


def test_an_ellipse_roi_has_a_rotate_handle(qapp):
    # pg.EllipseROI ships one, and now that a region can record an angle it
    # tells the truth: grabbing it turns the ellipse and the turn reaches the
    # slice. The rectangle offers the same gesture through an Alt-drag of its
    # body, which needs no handle.
    from acq4.modules.Autopatch.region_panel import roiForRegion

    handles = roiForRegion(ELLIPSE).handles
    assert any(h["type"] == "r" for h in handles)


@pytest.mark.parametrize("region", [RECT, ELLIPSE, TRIANGLE])
def test_a_rotation_gesture_reaches_the_region(qapp, region):
    # The gesture the operator actually makes: pg.MouseDragHandler enters rotate
    # mode on an Alt-modified drag of the ROI body, with no handle involved. The
    # turn has to arrive in the region, because a region that quietly stayed
    # axis-aligned would have the survey tile tissue the operator did not
    # outline -- displaced by up to half a field of view.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(region)
    before = regionForRoi(roi)

    altDragRoi(roi)

    assert roi.angle() != 0
    assert regionForRoi(roi) != before


def test_a_roi_dragged_past_its_own_origin_still_makes_a_region(qapp):
    # An ROI resized past its origin reports a negative size; the region built
    # from it must still describe the box the operator sees on screen.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(RECT)
    roi.setPos((1.4e-3, 2.1e-3))
    roi.setSize((-0.4e-3, -0.1e-3))

    assert regionForRoi(roi) == RECT


@pytest.mark.parametrize("size", [(0.0, 0.1e-3), (0.4e-3, 0.0), (0.0, 0.0)])
def test_an_roi_squashed_flat_reports_no_region(qapp, size):
    # A pg.RectROI can be dragged to zero extent, and SearchRegion raises on
    # that. Raising here would surface as a traceback on the GUI thread from
    # inside a signal handler, mid-drag. One case per axis: a check that only
    # looks at width passes a test that only squashes height.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(RECT)
    roi.setSize(size)

    assert regionForRoi(roi) is None


@pytest.mark.parametrize(
    "points",
    [
        # Three vertices on a line: a bounding box with no extent in one axis.
        [[1.0e-3, 2.0e-3], [1.2e-3, 2.0e-3], [1.4e-3, 2.0e-3]],
        # Two vertices left after the operator removes handles from a triangle.
        [[1.0e-3, 2.0e-3], [1.4e-3, 2.02e-3]],
    ],
)
def test_a_polygon_with_no_area_reports_no_region(qapp, points):
    # The polygon equivalents of a squashed box. Built by construction rather
    # than by calling roi.setPoints() on a triangle: setPoints() reaches
    # clearPoints() -> removeHandle() -> removeSegment(), which calls
    # self.scene().removeItem() and raises AttributeError on an ROI that is not
    # in a scene. Constructing is the path with no such requirement.
    import pyqtgraph as pg

    from acq4.modules.Autopatch.region_panel import regionForRoi

    roi = pg.PolyLineROI(points, closed=True)

    assert regionForRoi(roi) is None


def test_a_moved_polygon_reports_its_vertices_in_global_coordinates(qapp):
    # A PolyLineROI holds its vertices in ROI-local coordinates, so dragging the
    # body moves the shape without touching them. Reading them raw would put the
    # region back where it started and survey the wrong tissue.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(TRIANGLE)
    roi.setPos((0.5e-3, 0.25e-3))

    moved = regionForRoi(roi)
    assert moved.vertices == tuple(
        (x + 0.5e-3, y + 0.25e-3) for x, y in TRIANGLE.vertices
    )


# ---- rotation ----
# Non-trivial angles over a box that is neither square nor axis-symmetric: a
# right angle would let a swapped sin/cos through, and a square fixture cannot
# tell an x axis from a y one.
ROTATED = [
    RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3, 30.0),
    EllipseRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3, 30.0),
    RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3, 37.0),
    EllipseRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3, -37.0),
]


def turned(px, py, x, y, deg):
    """`(x, y)` turned `deg` degrees counter-clockwise about `(px, py)`.

    Spelled out here rather than imported from the region, so these tests state
    the convention they pin instead of agreeing with it by sharing its code.
    """
    th = math.radians(deg)
    c, s = math.cos(th), math.sin(th)
    dx, dy = x - px, y - py
    return (px + dx * c - dy * s, py + dx * s + dy * c)


def roiCorners(roi):
    """The four corners of an ROI's box, in parent (global) coordinates.

    Flattened to a plain list of numbers, because `pytest.approx` compares
    sequences of scalars and refuses nested ones.
    """
    size = roi.size()
    flat = []
    for lx, ly in ((0.0, 0.0), (size.x(), 0.0), (size.x(), size.y()), (0.0, size.y())):
        p = roi.mapToParent(Qt.QPointF(lx, ly))
        flat += [p.x(), p.y()]
    return flat


def flat(points):
    """`[(x, y), ...]` as `[x, y, ...]`, for the same reason."""
    return [c for point in points for c in point]


@pytest.mark.parametrize("region", ROTATED)
def test_a_rotated_region_round_trips_through_its_roi(qapp, region):
    # Exactly, not approximately. This is the whole reason the region's pivot is
    # the (x0, y0) corner rather than the shape's centre: the corner is what
    # pg.ROI.setAngle leaves `pos()` sitting on, so the read back is the same
    # arithmetic the axis-aligned case has always used. A centre pivot has to
    # halve and un-halve, and measurably does not return the original float.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    assert regionForRoi(roiForRegion(region)) == region


@pytest.mark.parametrize("region", ROTATED)
def test_the_rotated_roi_is_drawn_where_the_region_says(qapp, region):
    # Round-tripping equal objects would still pass if both directions shared
    # the same wrong pivot. Checking the ROI's own painted corners against the
    # turn the region describes is what pins the convention to the screen -- and
    # a displaced outline is exactly the failure this feature exists to avoid.
    from acq4.modules.Autopatch.region_panel import roiForRegion

    x0, y0, x1, y1 = region.box()
    expected = flat(
        turned(x0, y0, cx, cy, region.angle)
        for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    )
    assert roiCorners(roiForRegion(region)) == pytest.approx(expected)


def test_a_rotated_roi_dragged_past_its_own_origin_still_describes_its_shape(qapp):
    # An ROI resized past its origin reports a negative size, and the region
    # normalizes its corners. With the pivot living on the (x0, y0) corner, a
    # naive read would hand the region the wrong pivot and displace the shape.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(RectRegion(1.4e-3, 2.1e-3, 1.8e-3, 2.2e-3, 37.0))
    before = roiCorners(roi)
    # The opposite corner *as drawn*, not as the box was typed: the ROI turns
    # about its local origin, so putting the origin on the corner's unrotated
    # position would pivot the shape somewhere else entirely.
    roi.setPos((before[4], before[5]))
    roi.setSize((-0.4e-3, -0.1e-3))

    # Same four corners, so the operator sees the same rectangle...
    assert sorted(roiCorners(roi)) == pytest.approx(sorted(before))
    # ...and rebuilding from the region it reports draws that same rectangle.
    assert sorted(roiCorners(roiForRegion(regionForRoi(roi)))) == pytest.approx(
        sorted(before)
    )


def test_a_rotated_polygon_reports_its_turned_vertices(qapp):
    # A polygon needs no angle field: regionForRoi maps every vertex through
    # roi.mapToParent, which already includes the ROI's own transform, so a
    # rotation arrives baked into the coordinates. Pinned here because that is
    # load-bearing rather than incidental -- reading the vertices raw would put
    # the region back where it started.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(TRIANGLE)
    altDragRoi(roi)
    pivot = roi.mapToParent(roi.boundingRect().center())

    reported = regionForRoi(roi)
    assert flat(reported.vertices) == pytest.approx(
        flat(
            turned(pivot.x(), pivot.y(), x, y, roi.angle())
            for x, y in TRIANGLE.vertices
        )
    )
    # And that turned polygon survives being drawn again.
    assert regionForRoi(roiForRegion(reported)) == reported
