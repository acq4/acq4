"""Tests for search-region shapes: the bounding box a survey plans its tiles over,
and the exact rect-vs-shape overlap test that decides which of those tiles to image."""

import pytest

from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion, SearchRegion, tile_rect

# A 10 um tile, the size used throughout these tests.
TILE = (10e-6, 10e-6)


def test_tile_rect_is_centered_on_the_tile_center():
    # A tile is named by its center (that is what the stage is driven to), but
    # overlap tests need its extent, and getting this wrong by half a field
    # would shift every survey by half a tile.
    assert tile_rect((10.0, 20.0), (4.0, 6.0)) == (8.0, 17.0, 12.0, 23.0)


def test_the_base_class_refuses_to_answer_for_itself():
    # SearchRegion is the contract, not a usable shape: a subclass that forgets
    # to implement one of the two methods must fail loudly rather than silently
    # surveying nothing.
    region = SearchRegion()
    with pytest.raises(NotImplementedError):
        region.bounds()
    with pytest.raises(NotImplementedError):
        region.overlapsTile((0.0, 0.0), TILE)


def test_rect_bounds_are_normalized_whichever_corners_are_given():
    # An ROI dragged up-and-left produces x1 < x0; the tiler would plan an empty
    # grid from that, so the region normalizes instead of trusting the caller.
    assert RectRegion(30e-6, 30e-6, 0.0, 0.0).bounds() == (0.0, 0.0, 30e-6, 30e-6)
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6).bounds() == (0.0, 0.0, 30e-6, 30e-6)


def test_rect_rejects_zero_extent_in_either_axis():
    # A degenerate region is a mis-drag, not a search: it would plan a grid of
    # tiles over a line and report progress against it.
    with pytest.raises(ValueError, match="nonzero extent"):
        RectRegion(0.0, 0.0, 0.0, 30e-6)
    with pytest.raises(ValueError, match="nonzero extent"):
        RectRegion(0.0, 0.0, 30e-6, 0.0)


def test_rect_overlaps_a_tile_inside_it():
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((15e-6, 15e-6), TILE) is True


def test_rect_does_not_overlap_a_tile_clear_of_it():
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((100e-6, 15e-6), TILE) is False


def test_rect_overlaps_a_tile_that_only_touches_its_edge():
    # Closed-rect semantics, and not a curiosity: plan_grid centers its grid over
    # the region so the outermost tiles deliberately overhang the edges. A
    # half-open test would drop a tile at every region border.
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    # This tile spans -10 um .. 0 um, touching the region's near edge exactly.
    assert region.overlapsTile((-5e-6, 15e-6), TILE) is True


def test_rect_regions_with_the_same_corners_are_equal():
    # Tests and UI code compare regions; a slice's region list is only
    # meaningfully assertable if equality is by value.
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) == RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) != RectRegion(0.0, 0.0, 20e-6, 30e-6)


def _selected_pattern(regionClass, fov_len, off):
    """Which of a 15x15 grid of tiles `regionClass` selects, as a tuple of bools.

    The region is a square of exactly 15 tiles per side at `off`, so the same
    *relative* geometry can be built at any magnitude. Identical patterns across
    magnitudes is the property that catches an implementation whose accuracy
    depends on absolute coordinate size -- which is exactly how a Qt-based
    implementation fails here.
    """
    side = 15 * fov_len
    region = regionClass(off, off, off + side, off + side)
    fov = (fov_len, fov_len)
    return tuple(
        region.overlapsTile(
            (off + (gx + 0.5) * fov_len, off + (gy + 0.5) * fov_len), fov
        )
        for gy in range(15)
        for gx in range(15)
    )


def _sampled_overlap(region, center, fov, samples=40):
    """Independent oracle: does any densely sampled point of the tile lie inside
    the ellipse?

    Deliberately a different method from the implementation's closest-point
    formula -- point sampling of the tile -- so agreement means something. If a
    single near-tangent tile ever disagrees, raise `samples`; do not "fix" the
    implementation to match a coarse sampler.
    """
    x0, y0, x1, y1 = region.bounds()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    tx0, ty0, tx1, ty1 = tile_rect(center, fov)
    for i in range(samples + 1):
        px = tx0 + (tx1 - tx0) * i / samples
        for j in range(samples + 1):
            py = ty0 + (ty1 - ty0) * j / samples
            if ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 <= 1.0:
                return True
    return False


def test_ellipse_is_inscribed_in_the_bounding_box_it_is_given():
    region = EllipseRegion(0.0, 0.0, 30e-6, 20e-6)
    assert region.bounds() == (0.0, 0.0, 30e-6, 20e-6)
    # Center of the box is inside; the box's corner is not.
    assert region.overlapsTile((15e-6, 10e-6), (1e-6, 1e-6)) is True
    assert region.overlapsTile((0.0, 0.0), (1e-9, 1e-9)) is False


def test_ellipse_rejects_zero_extent_like_a_rectangle_does():
    with pytest.raises(ValueError, match="nonzero extent"):
        EllipseRegion(0.0, 0.0, 30e-6, 0.0)


def test_a_small_tile_in_a_bounding_box_corner_is_excluded():
    # The ellipse inscribed in (0,0)-(30,30) um is a circle at (15,15) um of
    # radius 15 um. This tile spans 0..2 um in both axes, so its nearest point to
    # that center is its far corner (2,2) um -- sqrt(2)*13 um = 18.4 um away, well
    # outside the circle. Qt's QPainterPath.intersects() answers True here (a
    # measured false positive); this test is the guard against anyone replacing
    # the closed-form geometry with it.
    region = EllipseRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((1e-6, 1e-6), (2e-6, 2e-6)) is False


def test_the_ellipse_tile_pattern_excludes_the_corners_it_should():
    # Pins the reference pattern the invariance test compares against, so that
    # test cannot pass vacuously against an all-True or all-False pattern.
    pattern = _selected_pattern(EllipseRegion, 1.0, 0.0)
    assert len(pattern) == 225
    assert sum(pattern) == 201
    # The four corner tiles of the grid are the unambiguous exclusions.
    assert pattern[0] is False
    assert pattern[14] is False
    assert pattern[210] is False
    assert pattern[224] is False


@pytest.mark.parametrize(
    "fov_len,off",
    [
        (200e-6, 0.0),        # a 3 mm region with a 200 um field: the realistic survey
        (200e-6, 5e-2),       # ...the same, out at a 5 cm stage coordinate
        (2e-6, 1e-3),         # a 30 um region with a 2 um field, off at 1 mm
        (1e-3, 4e7),          # absurd magnitude: pure arithmetic must not care
        (50e-6, -3.2e-3),     # negative stage coordinates are ordinary
    ],
)
def test_ellipse_tile_selection_is_identical_at_every_magnitude(fov_len, off):
    # Qt's path intersection fails every one of these while passing the unit-scale
    # reference, which is why this property is tested rather than assumed.
    assert _selected_pattern(EllipseRegion, fov_len, off) == _selected_pattern(
        EllipseRegion, 1.0, 0.0
    )


def test_ellipse_agrees_with_a_sampled_oracle_over_a_whole_grid_of_tiles():
    # 15x15 tiles of 200 um over a 3 mm circular region -- the shape of a real
    # survey, and the configuration in which a Qt-based implementation gets 24 of
    # these 225 answers wrong.
    fov_len = 200e-6
    region = EllipseRegion(0.0, 0.0, 15 * fov_len, 15 * fov_len)
    fov = (fov_len, fov_len)
    for gy in range(15):
        for gx in range(15):
            center = ((gx + 0.5) * fov_len, (gy + 0.5) * fov_len)
            assert region.overlapsTile(center, fov) == _sampled_overlap(
                region, center, fov
            ), (gx, gy)


def test_the_ellipse_maps_each_axis_to_its_own_radius():
    # A 4:1 ellipse: the only configuration in which x and y are distinguishable,
    # and the one an operator actually gets, since "Add region here" seeds
    # 3*fov_w x 3*fov_h and a cropped camera ROI is not square.
    region = EllipseRegion(0.0, 0.0, 40e-6, 10e-6)
    tiny = (1e-9, 1e-9)
    # 7 um off-centre along the 5 um semi-minor axis: outside.
    assert region.overlapsTile((20e-6, 12e-6), tiny) is False
    # 14 um off-centre along the 20 um semi-major axis: inside.
    assert region.overlapsTile((34e-6, 5e-6), tiny) is True


def test_a_rectangle_and_an_ellipse_with_the_same_box_are_not_equal():
    # Same corners, different tissue: the shapes must never compare equal, or a
    # region list would silently treat one as the other.
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) != EllipseRegion(0.0, 0.0, 30e-6, 30e-6)


# A triangle with no edge slope that lands on tile corners: an edge passing
# exactly through a tile corner is a genuine boundary tie (the tile touches the
# shape at a single point), and which way it resolves is float-noise sensitive.
# Those ties are real ambiguity, not precision loss, so the invariance property
# below is stated for a shape that has none.
TRIANGLE = ((0.7, 0.3), (14.1, 2.9), (2.6, 13.1))


def _polygon_pattern(scale, off):
    """TRIANGLE scaled by `scale` and offset to `off`, over a 15x15 tile grid."""
    region = PolygonRegion([(off + vx * scale, off + vy * scale) for vx, vy in TRIANGLE])
    fov = (scale, scale)
    return tuple(
        region.overlapsTile((off + (gx + 0.5) * scale, off + (gy + 0.5) * scale), fov)
        for gy in range(15)
        for gx in range(15)
    )


def test_polygon_needs_at_least_three_vertices():
    with pytest.raises(ValueError, match="at least 3 vertices"):
        PolygonRegion([(0.0, 0.0), (30e-6, 30e-6)])


def test_polygon_rejects_a_zero_area_polygon():
    with pytest.raises(ValueError, match="nonzero extent"):
        PolygonRegion([(0.0, 0.0), (1e-6, 0.0), (2e-6, 0.0)])


def test_polygon_bounds_are_the_extremes_of_its_vertices():
    region = PolygonRegion([(10e-6, 5e-6), (30e-6, 8e-6), (12e-6, 25e-6)])
    assert region.bounds() == (10e-6, 5e-6, 30e-6, 25e-6)


def test_a_polygon_excludes_tiles_only_its_bounding_box_would_plan():
    # An L: the 30x30 um box minus the quadrant beyond (12, 12) um. This is the
    # whole point of filtering -- the bounding box plans a 3x3 grid, and one of
    # those tiles sits entirely in tissue the operator excluded.
    region = PolygonRegion(
        [
            (0.0, 0.0),
            (30e-6, 0.0),
            (30e-6, 12e-6),
            (12e-6, 12e-6),
            (12e-6, 30e-6),
            (0.0, 30e-6),
        ]
    )
    assert region.bounds() == (0.0, 0.0, 30e-6, 30e-6)
    # Spans 20..30 um in both axes: entirely inside the notch.
    assert region.overlapsTile((25e-6, 25e-6), TILE) is False
    # Its two neighbours each still clip the 10..12 um arm of the L.
    assert region.overlapsTile((15e-6, 25e-6), TILE) is True
    assert region.overlapsTile((25e-6, 15e-6), TILE) is True


def test_a_band_narrower_than_one_tile_still_selects_tiles():
    # A 2 um-wide diagonal band. This is the case a center-containment test gets
    # catastrophically wrong: no tile center lies inside the band, so it would
    # plan zero tiles and survey nothing at all.
    region = PolygonRegion(
        [(0.0, 6e-6), (22e-6, 28e-6), (22e-6, 30e-6), (0.0, 8e-6)]
    )
    centers = [(x, y) for x in (5e-6, 15e-6, 25e-6) for y in (5e-6, 15e-6, 25e-6)]
    # A zero-size tile is exactly a point test, so this asserts the premise
    # rather than assuming it: not one tile center is inside the band.
    assert not any(region.overlapsTile(c, (0.0, 0.0)) for c in centers)
    # And yet the band crosses five of those tiles, which must be surveyed.
    assert sum(region.overlapsTile(c, TILE) for c in centers) == 5
    # A tile the band misses entirely is still excluded.
    assert region.overlapsTile((15e-6, 5e-6), TILE) is False


def test_a_polygon_wholly_inside_one_tile_overlaps_it():
    # A shape smaller than a field of view is one tile's worth of work, not zero.
    region = PolygonRegion([(4e-6, 4e-6), (6e-6, 4e-6), (5e-6, 6e-6)])
    assert region.overlapsTile((5e-6, 5e-6), TILE) is True


def test_a_tile_wholly_inside_a_polygon_overlaps_it():
    # No edge crosses this tile, so the edge tests all fail and the containment
    # fallback is the only thing that can answer. Without it the interior of every
    # large region reads as "not to be imaged".
    region = PolygonRegion(
        [(0.0, 0.0), (100e-6, 0.0), (100e-6, 100e-6), (0.0, 100e-6)]
    )
    assert region.overlapsTile((50e-6, 50e-6), TILE) is True
    # The same absence of edge crossings must answer False from outside.
    assert region.overlapsTile((500e-6, 500e-6), TILE) is False


def test_the_polygon_tile_pattern_is_neither_everything_nor_nothing():
    # Pins the reference the invariance test compares against.
    pattern = _polygon_pattern(1.0, 0.0)
    assert len(pattern) == 225
    assert sum(pattern) == 111


@pytest.mark.parametrize(
    "scale,off",
    [
        (200e-6, 0.0),
        (200e-6, 5e-2),
        (2e-6, 1e-3),
        (1e-3, 4e7),
        (50e-6, -3.2e-3),   # negative stage coordinates are ordinary
    ],
)
def test_polygon_tile_selection_is_identical_at_every_magnitude(scale, off):
    assert _polygon_pattern(scale, off) == _polygon_pattern(1.0, 0.0)
