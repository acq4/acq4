"""Tests for the mapping between a Slice's SearchRegion shapes and the
pyqtgraph ROIs Area 1 draws them with."""

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


def test_an_ellipse_roi_cannot_be_rotated(qapp):
    # EllipseRegion is inscribed in an axis-aligned box, so a rotate handle
    # would let the operator draw a shape that has no region to map back to:
    # regionForRoi reads pos and size and would drop the rotation silently.
    from acq4.modules.Autopatch.region_panel import roiForRegion

    handles = roiForRegion(ELLIPSE).handles
    assert not any(h["type"] == "r" for h in handles)


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
