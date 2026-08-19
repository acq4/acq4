"""Tests for search-region shapes: the bounding box a survey plans its tiles over,
the exact rect-vs-shape overlap test that decides which of those tiles to image, and
the point test that decides which of the cells found in them may be patched."""

import math

import pytest

from acq4.experiment.search_region import (
    EllipseRegion,
    PolygonRegion,
    RectRegion,
    SearchRegion,
    region_from_dict,
    tile_rect,
)

# A 10 um tile, the size used throughout these tests.
TILE = (10e-6, 10e-6)


def test_tile_rect_is_centered_on_the_tile_center():
    # A tile is named by its center (that is what the stage is driven to), but
    # overlap tests need its extent, and getting this wrong by half a field
    # would shift every survey by half a tile.
    assert tile_rect((10.0, 20.0), (4.0, 6.0)) == (8.0, 17.0, 12.0, 23.0)


def test_the_base_class_refuses_to_answer_for_itself():
    # SearchRegion is the contract, not a usable shape: a subclass that forgets
    # to implement one of the three methods must fail loudly rather than
    # silently surveying nothing -- or, for contains(), silently admitting every
    # cell the segmenter found outside the tissue the operator outlined.
    region = SearchRegion()
    with pytest.raises(NotImplementedError):
        region.bounds()
    with pytest.raises(NotImplementedError):
        region.overlapsTile((0.0, 0.0), TILE)
    with pytest.raises(NotImplementedError):
        region.contains((0.0, 0.0))


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


# ---- rotation ----
# 30 degrees, and boxes that are not square: a square fixture cannot tell an x
# axis from a y one, and a right angle is as symmetric as a square, so either
# would let a swapped sin/cos or a swapped rx/ry pass.
ANGLE = 30.0
BOX = (1.0e-3, 2.0e-3, 1.6e-3, 2.4e-3)


def _turned(px, py, x, y, deg):
    """`(x, y)` turned `deg` degrees counter-clockwise about `(px, py)`.

    Written out here rather than imported, so the tests state the convention
    they are pinning instead of agreeing with the implementation by sharing it.
    """
    th = math.radians(deg)
    c, s = math.cos(th), math.sin(th)
    dx, dy = x - px, y - py
    return (px + dx * c - dy * s, py + dx * s + dy * c)


def _turned_oracle(region, center, fov, samples=60):
    """Independent oracle for a rotated region: densely sample the tile, turn
    each sample point *back* about the pivot, and ask the unrotated shape.

    A different method from either implementation -- point sampling against the
    axis-aligned membership test, rather than separating axes or a distance to a
    mapped parallelogram -- so agreement is evidence rather than a tautology.
    """
    x0, y0, x1, y1 = region.box()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    isEllipse = isinstance(region, EllipseRegion)
    tx0, ty0, tx1, ty1 = tile_rect(center, fov)
    for i in range(samples + 1):
        px = tx0 + (tx1 - tx0) * i / samples
        for j in range(samples + 1):
            py = ty0 + (ty1 - ty0) * j / samples
            ux, uy = _turned(x0, y0, px, py, -region.angle)
            if isEllipse:
                if ((ux - cx) / rx) ** 2 + ((uy - cy) / ry) ** 2 <= 1.0:
                    return True
            elif x0 <= ux <= x1 and y0 <= uy <= y1:
                return True
    return False


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
def test_a_region_is_unrotated_unless_told_otherwise(regionClass):
    # Four-argument construction is every existing caller, and it must keep
    # meaning the axis-aligned shape it has always meant.
    assert regionClass(*BOX).angle == 0.0
    assert regionClass(*BOX) == regionClass(*BOX, 0.0)


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
def test_the_angle_is_part_of_the_shape(regionClass):
    # Two regions over the same box at different angles cover different tissue,
    # so a region list must never treat one as the other.
    assert regionClass(*BOX, ANGLE) != regionClass(*BOX)


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
def test_the_pivot_is_the_first_corner(regionClass):
    # The convention `pg.ROI.setAngle` uses by default -- rotation about the
    # ROI's local origin, which is `pos()` -- and matching it is what lets a
    # rotated ROI round-trip exactly.
    #
    # Read off the centre of `bounds()`, which is the shape's own centre for
    # both of these: a turned ellipse's extent is symmetric about it by the
    # closed form, and a turned rectangle's four corners hull to a box centred
    # on it. Turning about the corner carries that centre somewhere new, which
    # is precisely what a centre pivot would not do.
    x0, y0, x1, y1 = BOX
    bx0, by0, bx1, by1 = regionClass(*BOX, ANGLE).bounds()
    boxCenter = ((x0 + x1) / 2, (y0 + y1) / 2)
    assert ((bx0 + bx1) / 2, (by0 + by1) / 2) == pytest.approx(
        _turned(x0, y0, *boxCenter, ANGLE)
    )
    assert ((bx0 + bx1) / 2, (by0 + by1) / 2) != pytest.approx(boxCenter)


def test_a_rotated_rect_bounds_the_box_of_its_turned_corners(): 
    region = RectRegion(*BOX, ANGLE)
    x0, y0, x1, y1 = BOX
    turned = [
        _turned(x0, y0, cx, cy, ANGLE)
        for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    ]
    assert region.bounds() == pytest.approx(
        (
            min(p[0] for p in turned),
            min(p[1] for p in turned),
            max(p[0] for p in turned),
            max(p[1] for p in turned),
        )
    )
    # And it is genuinely wider than the box it came from, or the test above
    # would pass on an implementation that ignored the angle.
    assert region.bounds() != pytest.approx(BOX)


def test_a_rotated_ellipse_bounds_by_the_closed_form_half_extents():
    region = EllipseRegion(*BOX, ANGLE)
    x0, y0, x1, y1 = BOX
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    th = math.radians(ANGLE)
    hw = math.hypot(rx * math.cos(th), ry * math.sin(th))
    hh = math.hypot(rx * math.sin(th), ry * math.cos(th))
    cx, cy = _turned(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2, ANGLE)
    assert region.bounds() == pytest.approx((cx - hw, cy - hh, cx + hw, cy + hh))
    # A rotated ellipse is strictly narrower than its rotated bounding *box*,
    # which is what makes the closed form worth having rather than reusing the
    # rectangle's four-corner hull.
    assert hw < max(
        abs(_turned(x0, y0, c, d, ANGLE)[0] - cx)
        for c, d in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    )


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
def test_a_rotated_region_agrees_with_a_sampled_oracle_over_a_grid(regionClass):
    # A whole grid rather than a handful of tiles: rotation moves the boundary
    # past a different set of tiles on every side, and only the tiles near that
    # boundary can tell a correct implementation from an almost-correct one.
    fov_len = 100e-6
    region = regionClass(*BOX, ANGLE)
    fov = (fov_len, fov_len)
    bx0, by0, bx1, by1 = region.bounds()
    for gy in range(12):
        for gx in range(12):
            center = (bx0 + (gx + 0.5) * fov_len, by0 + (gy + 0.5) * fov_len)
            assert region.overlapsTile(center, fov) == _turned_oracle(
                region, center, fov
            ), (regionClass.__name__, gx, gy)


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
def test_rotating_a_region_changes_which_tiles_it_selects(regionClass):
    # The property that makes this feature worth anything: an implementation
    # that quietly dropped the angle would tile the operator's tissue at the
    # wrong orientation, and would pass any test that only counted tiles.
    fov_len = 100e-6
    fov = (fov_len, fov_len)
    turned = regionClass(*BOX, ANGLE)
    straight = regionClass(*BOX)
    bx0, by0, bx1, by1 = turned.bounds()
    centers = [
        (bx0 + (gx + 0.5) * fov_len, by0 + (gy + 0.5) * fov_len)
        for gy in range(12)
        for gx in range(12)
    ]
    turnedPattern = tuple(turned.overlapsTile(c, fov) for c in centers)
    straightPattern = tuple(straight.overlapsTile(c, fov) for c in centers)
    assert turnedPattern != straightPattern
    # Named tiles, so this cannot be satisfied by an off-by-one in tile count:
    # each is selected by exactly one of the two orientations.
    both = list(zip(centers, turnedPattern, straightPattern))
    onlyTurned = [c for c, turnedHit, straightHit in both if turnedHit and not straightHit]
    onlyStraight = [c for c, turnedHit, straightHit in both if straightHit and not turnedHit]
    assert onlyTurned and onlyStraight


@pytest.mark.parametrize("fov_len,off", [(1.0, 0.0), (1e-6, 3.0), (1e3, -2e4)])
def test_rotated_tile_selection_is_identical_at_every_magnitude(fov_len, off):
    # The same scale-invariance property the axis-aligned shapes are held to.
    # The separating-axis and mapped-parallelogram tests were chosen over a
    # Qt-based one precisely so this holds; asserting it is what keeps an
    # absolute tolerance from creeping back in.
    def pattern(regionClass, fov_len, off):
        side = 9 * fov_len
        region = regionClass(off, off, off + side, off + side * 0.6, ANGLE)
        fov = (fov_len, fov_len)
        bx0, by0, _, _ = region.bounds()
        return tuple(
            region.overlapsTile(
                (bx0 + (gx + 0.5) * fov_len, by0 + (gy + 0.5) * fov_len), fov
            )
            for gy in range(12)
            for gx in range(12)
        )

    for regionClass in (RectRegion, EllipseRegion):
        assert pattern(regionClass, fov_len, off) == pattern(regionClass, 1.0, 0.0)


def test_the_rotated_ellipse_still_maps_each_axis_to_its_own_radius():
    # A 4:1 ellipse turned a quarter of the way to upright. A swapped rx/ry
    # survived every symmetric ellipse test on this branch once already; at this
    # angle the two radii do not exchange roles, so the swap has nowhere to hide.
    region = EllipseRegion(0.0, 0.0, 40e-6, 10e-6, ANGLE)
    speck = (1e-12, 1e-12)
    cx, cy = _turned(0.0, 0.0, 20e-6, 5e-6, ANGLE)
    # 18 um along the turned semi-major axis: inside. 7 um along the turned
    # semi-minor axis: outside.
    th = math.radians(ANGLE)
    major = (cx + 18e-6 * math.cos(th), cy + 18e-6 * math.sin(th))
    minor = (cx - 7e-6 * math.sin(th), cy + 7e-6 * math.cos(th))
    assert region.overlapsTile(major, speck) is True
    assert region.overlapsTile(minor, speck) is False


# ---- containment ----
# A separate question from overlap, and deliberately the opposite trade. A tile
# is an area and is imaged if it touches the region at all; a detected cell is a
# location and is patched only if it is genuinely inside. The camera images past
# the outline on purpose -- a field straddling the edge is what gives the
# segmenter the context to find cells sitting right at it -- so every survey run
# turns up detections outside the tissue the operator drew.


def _contains_oracle(region, x, y):
    """Independent membership oracle for the box-derived shapes: turn the point
    back about the pivot and ask the axis-aligned shape it came from.

    Written from `box()` and `angle` rather than sharing the implementation's
    arithmetic, so agreement is evidence rather than a restatement.
    """
    x0, y0, x1, y1 = region.box()
    ux, uy = _turned(x0, y0, x, y, -region.angle)
    if isinstance(region, EllipseRegion):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
        return ((ux - cx) / rx) ** 2 + ((uy - cy) / ry) ** 2 <= 1.0
    return x0 <= ux <= x1 and y0 <= uy <= y1


def _containment_pattern(regionClass, scale, off):
    """Which of a 15x15 grid of points `regionClass` contains, as a tuple of bools.

    The same relative geometry at any magnitude, for the same reason
    `_selected_pattern` is built that way: a pattern that changes with absolute
    coordinate size is an implementation whose accuracy depends on where the
    stage happens to be.
    """
    side = 12 * scale
    region = regionClass(off + scale, off + scale, off + scale + side, off + scale + side)
    return tuple(
        region.contains((off + (gx + 0.5) * scale, off + (gy + 0.5) * scale))
        for gy in range(15)
        for gx in range(15)
    )


def test_a_rect_contains_the_points_inside_its_box_and_no_others():
    region = RectRegion(0.0, 0.0, 30e-6, 20e-6)
    assert region.contains((15e-6, 10e-6)) is True
    assert region.contains((0.0, 0.0)) is True
    assert region.contains((31e-6, 10e-6)) is False
    assert region.contains((15e-6, -1e-9)) is False


def test_containment_is_a_stricter_question_than_tile_overlap():
    # The reason this method exists. A tile centred just outside the region
    # still overlaps it -- that overhang is deliberate, and is what the survey
    # images -- but a cell detected out there is outside the tissue the operator
    # asked for and must not be queued.
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    justOutside = (-3e-6, 15e-6)
    assert region.overlapsTile(justOutside, TILE) is True
    assert region.contains(justOutside) is False


def test_contains_reads_only_the_first_two_coordinates():
    # A detected cell's position is a 3-vector and arrives as a coorx Point; a
    # region is a shape in the xy plane, so depth is not part of the question.
    # Anything indexable works, the same latitude Slice.forceRescan allows.
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.contains([15e-6, 15e-6, -40e-6]) is True
    assert region.contains((15e-6, 15e-6, 1.0)) is True
    assert region.contains([100e-6, 15e-6, -40e-6]) is False


def test_an_ellipse_contains_its_centre_but_not_its_box_corners():
    region = EllipseRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.contains((15e-6, 15e-6)) is True
    # Inside the bounding box, outside the inscribed circle: 21 um from the
    # centre, which has a radius of 15 um.
    assert region.contains((0.0, 0.0)) is False


def test_ellipse_containment_maps_each_axis_to_its_own_radius():
    # A 4:1 ellipse: the only configuration in which a swapped rx/ry is visible.
    region = EllipseRegion(0.0, 0.0, 40e-6, 10e-6)
    assert region.contains((34e-6, 5e-6)) is True    # 14 um along the 20 um axis
    assert region.contains((20e-6, 12e-6)) is False  # 7 um along the 5 um axis


def test_a_polygon_contains_points_in_its_arms_but_not_in_its_notch():
    # The same L the tile-overlap tests use: the bounding box would admit cells
    # from a quadrant of tissue the operator explicitly cut out.
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
    assert region.contains((6e-6, 25e-6)) is True
    assert region.contains((25e-6, 6e-6)) is True
    assert region.contains((25e-6, 25e-6)) is False
    assert region.contains((40e-6, 6e-6)) is False


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
def test_rotated_containment_agrees_with_a_turned_oracle_over_a_grid(regionClass):
    # A whole grid rather than a handful of points: an angle dropped, negated,
    # or applied about the wrong pivot moves the boundary past a different set
    # of points on every side, and only points near that boundary can tell the
    # difference.
    region = regionClass(*BOX, ANGLE)
    bx0, by0, bx1, by1 = region.bounds()
    step = 60e-6
    for gy in range(14):
        for gx in range(14):
            p = (bx0 + gx * step, by0 + gy * step)
            assert region.contains(p) == _contains_oracle(region, *p), (
                regionClass.__name__,
                gx,
                gy,
            )


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
def test_rotating_a_region_changes_which_points_it_contains(regionClass):
    # An implementation that quietly ignored the angle would admit cells from
    # one corner of the operator's tissue and refuse them from another, and
    # would pass any test that only counted contained points.
    turned = regionClass(*BOX, ANGLE)
    straight = regionClass(*BOX)
    bx0, by0, _, _ = turned.bounds()
    step = 60e-6
    points = [
        (bx0 + gx * step, by0 + gy * step) for gy in range(14) for gx in range(14)
    ]
    onlyTurned = [p for p in points if turned.contains(p) and not straight.contains(p)]
    onlyStraight = [p for p in points if straight.contains(p) and not turned.contains(p)]
    assert onlyTurned and onlyStraight


@pytest.mark.parametrize(
    "regionClass", [RectRegion, EllipseRegion]
)
@pytest.mark.parametrize(
    "scale,off",
    [
        (200e-6, 0.0),
        (200e-6, 5e-2),
        (2e-6, 1e-3),
        (1e-3, 4e7),
        (50e-6, -3.2e-3),
    ],
)
def test_containment_is_identical_at_every_magnitude(regionClass, scale, off):
    # The scale-freedom the whole module is written for: pure arithmetic on
    # quantities of the same magnitude, with no absolute tolerance to be wrong
    # about at either 1e-6 or 1e7.
    assert _containment_pattern(regionClass, scale, off) == _containment_pattern(
        regionClass, 1.0, 0.0
    )


def test_the_containment_pattern_is_neither_everything_nor_nothing():
    # Pins the references the invariance test compares against, so it cannot
    # pass vacuously against an all-True or all-False implementation.
    assert sum(_containment_pattern(RectRegion, 1.0, 0.0)) == 144
    assert sum(_containment_pattern(EllipseRegion, 1.0, 0.0)) == 112


@pytest.mark.parametrize(
    "region",
    [
        RectRegion(*BOX, ANGLE),
        EllipseRegion(*BOX, ANGLE),
        PolygonRegion([(1.0e-3, 2.0e-3), (1.6e-3, 2.1e-3), (1.2e-3, 2.4e-3)]),
    ],
)
def test_a_contained_point_always_sits_in_a_tile_the_survey_images(region):
    # The two questions must not contradict each other: a cell inside the region
    # has to have been findable, which means the tile around it was one the
    # survey imaged. Containment stricter than overlap is the point; containment
    # admitting a point from a tile the survey skips would be a bug.
    bx0, by0, bx1, by1 = region.bounds()
    fov = ((bx1 - bx0) / 8, (by1 - by0) / 8)
    step = (bx1 - bx0) / 13
    for gy in range(14):
        for gx in range(14):
            p = (bx0 + gx * step, by0 + gy * step)
            if region.contains(p):
                assert region.overlapsTile(p, fov) is True, (gx, gy)


# ---- persistence: to_dict / from_dict / region_from_dict ----

# The angles a round-trip test has to survive. Zero is in the list on purpose:
# it is a shape's ordinary state and the one an implementation that stored a
# centre and a half-extent would be likeliest to move (see _BoxRegion's own
# docstring on why the pivot is a corner). The rest sample every quadrant,
# including the axis-aligned quarter turns where a cos or sin lands exactly on
# 0 or 1, and one angle past a full turn.
ROUND_TRIP_ANGLES = [
    0.0, 0.5, 7.3, 30.0, 45.0, 90.0, 123.456, 180.0, 217.9, 270.0, 359.5, 412.75, -37.25,
]


@pytest.mark.parametrize("regionClass", [RectRegion, EllipseRegion])
@pytest.mark.parametrize("angle", ROUND_TRIP_ANGLES)
def test_a_box_region_round_trips_exactly_at_every_angle(regionClass, angle):
    # Exactly, not approximately: a region is what the operator drew by hand,
    # and a saved slice reopened with its outlines a float off the tissue they
    # were traced onto is a record that quietly lies about where it looked.
    # This is the same exactness `_BoxRegion` chose a corner pivot to get, so
    # the persistence format stores what that pivot is measured from -- the
    # `box()` the operator sized and the angle -- rather than anything derived.
    region = regionClass(*BOX, angle)
    restored = regionClass.from_dict(region.to_dict())
    assert restored == region
    assert restored.box() == region.box()
    assert restored.angle == region.angle


def test_a_polygon_round_trips_exactly():
    region = PolygonRegion(
        [(1.0e-3, 2.0e-3), (1.6e-3, 2.1e-3), (1.2e-3, 2.4e-3), (0.9e-3, 2.2e-3)]
    )
    restored = PolygonRegion.from_dict(region.to_dict())
    assert restored == region
    assert restored.vertices == region.vertices


@pytest.mark.parametrize(
    "region,shape",
    [
        (RectRegion(*BOX), "rect"),
        (EllipseRegion(*BOX), "ellipse"),
        (PolygonRegion([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]), "polygon"),
    ],
)
def test_a_serialized_region_names_its_shape(region, shape):
    # The shape tag is what lets a saved list rebuild without the caller
    # switching on type, and it is also the only part of the record a human
    # reading the file can use to tell a rect from the ellipse inscribed in
    # the identical box.
    assert region.to_dict()["shape"] == shape


@pytest.mark.parametrize(
    "region",
    [
        RectRegion(*BOX, ANGLE),
        EllipseRegion(*BOX, ANGLE),
        PolygonRegion([(1.0e-3, 2.0e-3), (1.6e-3, 2.1e-3), (1.2e-3, 2.4e-3)]),
    ],
)
def test_the_dispatcher_rebuilds_the_shape_that_was_saved(region):
    restored = region_from_dict(region.to_dict())
    assert type(restored) is type(region)
    assert restored == region


def test_the_dispatcher_refuses_a_shape_it_does_not_know():
    # A file written by a later version, or hand-edited: rebuilding the wrong
    # shape from it would put a survey over tissue nobody outlined, so it
    # fails loudly instead.
    with pytest.raises(ValueError, match="unknown region shape"):
        region_from_dict({"shape": "trapezoid", "box": [0.0, 0.0, 1.0, 1.0]})


@pytest.mark.parametrize(
    "region",
    [
        RectRegion(*BOX, ANGLE),
        EllipseRegion(*BOX, ANGLE),
        PolygonRegion([(1.0e-3, 2.0e-3), (1.6e-3, 2.1e-3), (1.2e-3, 2.4e-3)]),
    ],
)
def test_a_serialized_region_is_plain_data(region):
    # The whole reason these methods exist: the regions are frozen dataclasses,
    # and both places a slice's state lands -- a YAML file and the directory
    # index, which is written with repr() and read back with eval() in a
    # namespace that has never heard of RectRegion -- can carry only dicts,
    # lists, strings, and numbers.
    d = region.to_dict()

    def plain(value):
        if isinstance(value, dict):
            return all(isinstance(k, str) and plain(v) for k, v in value.items())
        if isinstance(value, list):
            return all(plain(v) for v in value)
        return isinstance(value, (str, float, int, bool)) or value is None

    assert plain(d), d
    assert eval(repr(d)) == d


def test_a_serialized_region_survives_yaml():
    # The format Slice.saveState() writes it in. yaml round-trips a float
    # through repr(), so this is exact rather than merely close, and a tuple
    # left in the payload would come back tagged rather than as a list.
    yaml = pytest.importorskip("yaml")
    region = EllipseRegion(*BOX, 123.456)
    restored = region_from_dict(yaml.safe_load(yaml.safe_dump(region.to_dict())))
    assert restored == region


def test_a_box_region_without_an_angle_reads_as_unturned():
    # A hand-written or older record that names only the box: a missing angle
    # is the ordinary unturned shape, not a reason to refuse the region.
    assert RectRegion.from_dict({"shape": "rect", "box": [0.0, 0.0, 1.0, 2.0]}) == (
        RectRegion(0.0, 0.0, 1.0, 2.0)
    )


def test_the_base_class_refuses_to_serialize_itself():
    # to_dict() is the fourth question a shape has to answer, and a subclass
    # that forgot it must fail loudly rather than have its geometry silently
    # dropped from the slice record.
    with pytest.raises(NotImplementedError):
        SearchRegion().to_dict()
