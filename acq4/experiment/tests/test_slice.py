"""Tests for SearchConstraints validation and the Slice object's regions,
coverage, and survey statistics."""

import gc
import weakref

import coorx
import pytest

from acq4.experiment.search_grid import plan_grid
from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion
from acq4.experiment.slice import SearchConstraints, Slice


def test_defaults_are_a_usable_search():
    c = SearchConstraints()
    assert c.depth_range == (-20e-6, -60e-6)
    assert 0.0 <= c.min_health <= 1.0
    assert c.max_cell_density > 0
    assert c.rescans_allowed is False


def test_depth_range_offsets_must_be_at_or_below_the_surface():
    # Offsets are relative to the tissue surface and negative is deeper, so a
    # positive offset would search in the bath above the tissue.
    with pytest.raises(ValueError, match="at or below the surface"):
        SearchConstraints(depth_range=(20e-6, -60e-6))
    # The positive offset can land in either position of the pair, so both
    # must be checked.
    with pytest.raises(ValueError, match="at or below the surface"):
        SearchConstraints(depth_range=(-60e-6, 20e-6))


def test_depth_range_must_span_a_nonzero_thickness():
    with pytest.raises(ValueError, match="nonzero thickness"):
        SearchConstraints(depth_range=(-40e-6, -40e-6))


def test_depth_range_accepts_either_ordering():
    # An operator may type the deeper bound first; both describe the same slab.
    shallow_first = SearchConstraints(depth_range=(-20e-6, -60e-6))
    deep_first = SearchConstraints(depth_range=(-60e-6, -20e-6))
    assert shallow_first.z_span() == deep_first.z_span()
    assert shallow_first.z_span() == pytest.approx(40e-6)


def test_z_bounds_adds_offsets_to_the_surface_and_orders_shallow_before_deep():
    # z_bounds must return (shallower, deeper), which for negative offsets
    # means (max, min); a swapped min/max or subtracted offset would only
    # show up when the surface is nonzero, since surface=0 makes signed
    # offsets look the same as their negation.
    c = SearchConstraints(depth_range=(-20e-6, -60e-6))
    assert c.z_bounds(-500e-6) == pytest.approx((-520e-6, -560e-6))


def test_z_bounds_is_unaffected_by_depth_range_ordering():
    c = SearchConstraints(depth_range=(-60e-6, -20e-6))
    assert c.z_bounds(-500e-6) == pytest.approx((-520e-6, -560e-6))


def test_z_bounds_at_a_zero_surface():
    # surface=0.0 is the degenerate case where offsets equal their own
    # negation's magnitude, so it alone can't catch a sign error; kept as a
    # sanity check alongside the nonzero-surface cases above.
    c = SearchConstraints(depth_range=(-20e-6, -60e-6))
    assert c.z_bounds(0.0) == pytest.approx((-20e-6, -60e-6))


def test_min_health_must_be_a_probability():
    with pytest.raises(ValueError, match="between 0 and 1"):
        SearchConstraints(min_health=1.5)
    with pytest.raises(ValueError, match="between 0 and 1"):
        SearchConstraints(min_health=-0.1)


def test_max_cell_density_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        SearchConstraints(max_cell_density=0.0)


def test_constraints_are_frozen():
    c = SearchConstraints()
    with pytest.raises(Exception):
        c.min_health = 0.9


# A 10x10 um FOV with no overlap, so a 30x30 um region is exactly a 3x3 grid of
# tiles and tile centers land on predictable coordinates.
FOV = (10e-6, 10e-6)


def make_slice(**kwargs):
    kwargs.setdefault("fov", FOV)
    return Slice(**kwargs)


class FakeCell:
    """Stand-in for acq4_automation's Cell: a global position and a health score."""

    def __init__(self, position, score=1.0):
        self.position = position
        self.score = score


def test_a_new_slice_has_no_regions_and_nothing_to_survey():
    s = make_slice()
    assert s.regions == []
    assert s.tileGrid() == []
    assert s.nextTile() is None
    assert s.surveyStats() == (0, 0, 0.0)


def test_adding_a_region_produces_a_tile_grid():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    assert len(s.tileGrid()) == 9
    assert s.surveyStats() == (9, 0, 0.0)


def test_the_tile_grid_is_serpentine_within_a_region():
    # Alternating the direction of each row is what keeps a survey's stage
    # travel down: at the end of a row the next tile is the one directly
    # above, not all the way back at the far edge. Sorted (or any other
    # row-major) order costs a full row's traverse per row and would still
    # cover the region, so nothing else in the suite would notice the
    # difference -- hence pinning the order itself here.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    grid = s.tileGrid()
    assert len(grid) == 9

    rows = [grid[0:3], grid[3:6], grid[6:9]]
    # Each row is one y, and the rows step through y in order.
    ys = [row[0][1] for row in rows]
    for row, y in zip(rows, ys):
        assert [center[1] for center in row] == [pytest.approx(y)] * 3
    assert ys == sorted(ys)

    # And the x direction reverses row to row.
    xs = [[center[0] for center in row] for row in rows]
    assert xs[0] == sorted(xs[0])
    assert xs[1] == sorted(xs[1], reverse=True)
    assert xs[2] == sorted(xs[2])
    # The step from the end of one row to the start of the next is one tile,
    # which is the whole point; row-major order would make it two.
    assert xs[0][-1] == pytest.approx(xs[1][0])
    assert xs[1][-1] == pytest.approx(xs[2][0])


def test_regions_is_a_copy_so_callers_cannot_mutate_slice_state():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.regions.append(RectRegion(1e-3, 1e-3, 2e-3, 2e-3))
    assert len(s.regions) == 1


def test_a_second_region_extends_the_grid_without_disturbing_the_first():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    first = s.tileGrid()
    # 1e-3 keeps the region well clear of the first and sits at a realistic
    # stage coordinate.
    s.addRegion(RectRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    both = s.tileGrid()
    assert both[: len(first)] == first
    assert len(both) == 18


def test_marking_a_tile_covered_advances_next_tile():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    first = s.nextTile()
    assert s.nextTile() == first, "nextTile must not mark; it only reports"
    s.markCovered(first)
    assert s.nextTile() != first
    assert s.surveyStats() == (9, 1, pytest.approx(100 / 9))


def test_next_tile_is_none_once_every_tile_is_covered():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    for _ in range(9):
        s.markCovered(s.nextTile())
    assert s.nextTile() is None
    assert s.surveyStats() == (9, 9, 100.0)


def test_next_tile_follows_tile_grid_order():
    # The grid is serpentine-ordered to minimize stage travel between tiles,
    # so nextTile must hand out tileGrid()'s tiles in that same order, not
    # merely some order that avoids repeats.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    grid = s.tileGrid()
    for expected in grid:
        tile = s.nextTile()
        assert tile == expected
        s.markCovered(tile)
    assert s.nextTile() is None


def test_coverage_survives_a_new_region_being_added():
    # Shared coverage is the whole point: a second region's survey must not
    # re-image the first region's tiles.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    covered = s.nextTile()
    s.markCovered(covered)
    s.addRegion(RectRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    assert covered in s.coveredTiles
    assert s.surveyStats()[1] == 1


def test_covered_tiles_is_a_copy_so_callers_cannot_mutate_slice_state():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.markCovered(s.nextTile())
    s.coveredTiles.append((1, 1))
    assert len(s.coveredTiles) == 1


def test_reset_coverage_forgets_imaged_tiles_but_keeps_regions():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.markCovered(s.nextTile())
    s.resetCoverage()
    assert s.coveredTiles == []
    assert len(s.regions) == 1
    assert s.surveyStats() == (9, 0, 0.0)


def test_tile_volume_is_fov_area_times_the_depth_span():
    s = make_slice(constraints=SearchConstraints(depth_range=(-20e-6, -60e-6)))
    assert s.tileVolume() == pytest.approx(10e-6 * 10e-6 * 40e-6)


def test_registered_cells_are_found_near_their_own_tile_only():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    tile = s.nextTile()
    here = FakeCell((tile[0], tile[1], 0.0))
    far = FakeCell((tile[0] + 1e-3, tile[1], 0.0))
    s.registerCells([here, far])
    near = s.cellsNearTile(tile)
    assert here in near
    assert far not in near


def test_setting_constraints_replaces_them_wholesale():
    s = make_slice()
    replacement = SearchConstraints(min_health=0.9)
    s.setConstraints(replacement)
    assert s.constraints is replacement


def test_fov_must_be_positive_in_both_axes():
    # A non-positive FOV would make tile stepping and coverage matching
    # meaningless, so both axes are checked independently.
    with pytest.raises(ValueError, match="fov must be positive"):
        Slice(fov=(0.0, 10e-6))
    with pytest.raises(ValueError, match="fov must be positive"):
        Slice(fov=(10e-6, -1e-6))


def test_threshold_is_half_the_step_between_tile_centers():
    # No overlap: the step is the smaller FOV axis, so threshold is half that.
    s = make_slice(fov=(10e-6, 20e-6))
    assert s.threshold == pytest.approx(5e-6)


def test_threshold_falls_back_to_half_the_smaller_fov_when_overlap_swallows_the_step():
    # An overlap >= the smaller FOV axis would make the step zero or negative,
    # so threshold falls back to half the smaller FOV instead.
    s = make_slice(fov=(10e-6, 20e-6), overlap=15e-6)
    assert s.threshold == pytest.approx(5e-6)


def test_overlap_produces_more_tiles_than_no_overlap_over_the_same_rectangle():
    # Overlapping tiles step less far apart, so more of them are needed to
    # cover the same extent.
    plain = make_slice(overlap=0.0)
    plain.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    overlapped = make_slice(overlap=5e-6)
    overlapped.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    assert len(overlapped.tileGrid()) > len(plain.tileGrid())


def test_make_cell_producer_returns_a_view_the_slice_does_not_retain():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    producer = s.makeCellProducer(lambda center, constraints: [])
    assert producer() == []

    # A reference cycle through the slice would keep the producer alive past
    # its last strong reference; disabling the cyclic collector first means
    # only reference counting is at work, so a dead weakref is proof the
    # slice holds no path back to what it handed out, however deeply nested.
    weak = weakref.ref(producer)
    gc.disable()
    try:
        del producer
        assert weak() is None
    finally:
        gc.enable()


def test_a_rectangular_region_plans_exactly_its_bounding_box_grid():
    # The regression guard for the whole migration: a rectangle must behave
    # exactly as it did when regions were 4-tuples. It provably does -- plan_grid
    # centers its grid over the box, so every tile it plans overlaps the box --
    # and this pins that so a future filter change cannot quietly cost tiles.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    assert s.tileGrid() == plan_grid(0, 0, 30e-6, 30e-6, FOV[0], FOV[1], 0.0)


def test_an_elliptical_region_drops_the_corner_tiles_its_bounding_box_plans():
    # 15x15 tiles, the resolution at which a bounding box's corners are genuinely
    # outside the ellipse. Those 24 tiles are the imaging time shapes exist to
    # save; at a coarser 3x3 every tile reaches the ellipse and there is nothing
    # to drop, which is why this test is not written at 3x3.
    side = 150e-6
    ellipse = make_slice()
    ellipse.addRegion(EllipseRegion(0, 0, side, side))
    box = make_slice()
    box.addRegion(RectRegion(0, 0, side, side))

    planned = box.tileGrid()
    kept = ellipse.tileGrid()
    assert len(planned) == 225
    assert len(kept) == 201
    # What it drops are the box's corners; what it keeps includes the middle.
    assert planned[0] not in kept
    assert planned[14] not in kept
    assert any(c == pytest.approx((75e-6, 75e-6)) for c in kept)


def test_an_elliptical_regions_tiles_still_cover_the_whole_ellipse():
    # Filtering must not leave holes *inside* the shape: every point of the
    # ellipse has to fall inside some tile that will actually be imaged.
    side = 150e-6
    s = make_slice()
    s.addRegion(EllipseRegion(0, 0, side, side))
    grid = s.tileGrid()
    center = side / 2
    radius = side / 2
    n = 40
    for i in range(n + 1):
        for j in range(n + 1):
            px, py = side * i / n, side * j / n
            if (px - center) ** 2 + (py - center) ** 2 > radius * radius:
                continue
            assert any(
                abs(px - tx) <= FOV[0] / 2 + 1e-12
                and abs(py - ty) <= FOV[1] / 2 + 1e-12
                for tx, ty in grid
            ), (px, py)


def test_filtering_preserves_the_serpentine_order_within_a_region():
    # nextTile hands out tileGrid()'s order, and that order is what keeps stage
    # travel down. Filtering must remove tiles without reordering the survivors.
    side = 150e-6
    ellipse = make_slice()
    ellipse.addRegion(EllipseRegion(0, 0, side, side))
    box = make_slice()
    box.addRegion(RectRegion(0, 0, side, side))

    planned = box.tileGrid()
    positions = [planned.index(c) for c in ellipse.tileGrid()]
    assert positions == sorted(positions)


def test_regions_of_different_shapes_share_one_slice_and_one_coverage_record():
    # Shapes are per region, not per slice: an operator can outline one area as a
    # rectangle and another as an ellipse, and coverage still spans both.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.addRegion(EllipseRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    assert [type(r) for r in s.regions] == [RectRegion, EllipseRegion]
    # Nine tiles each: at 3x3 every tile of the box reaches the inscribed ellipse.
    assert len(s.tileGrid()) == 18

    s.markCovered(s.nextTile())
    assert s.surveyStats() == (18, 1, pytest.approx(100 / 18))


def test_a_polygon_narrower_than_one_tile_still_gets_a_grid():
    # The end-to-end version of the band case: a 2 um-wide diagonal band contains
    # no tile center at all, so a Slice that filtered by containment would report
    # a region with nothing to survey.
    s = make_slice()
    s.addRegion(
        PolygonRegion([(0.0, 6e-6), (22e-6, 28e-6), (22e-6, 30e-6), (0.0, 8e-6)])
    )
    grid = s.tileGrid()
    assert len(grid) > 0
    assert len(grid) < len(plan_grid(0.0, 6e-6, 22e-6, 30e-6, FOV[0], FOV[1], 0.0))
    assert s.nextTile() == grid[0]


class _PositionedCell:
    """A stand-in for acq4_automation's Cell: a position is all Slice reads."""

    def __init__(self, position):
        self.position = position


def _two_region_slice():
    """A slice with two well-separated regions at realistic stage coordinates.

    Deliberately not at the origin, and deliberately not square: a symmetric
    fixture cannot test an asymmetric mapping, and origin-centred geometry
    cannot see coordinate-magnitude float error.
    """
    s = Slice(fov=(20e-6, 10e-6))
    s.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    s.addRegion(RectRegion(5e-3, 7e-3, 5e-3 + 60e-6, 7e-3 + 30e-6))
    return s


def test_force_rescan_uncovers_only_the_region_holding_the_position():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    covered_before = len(s.coveredTiles)

    uncovered = s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert uncovered > 0
    remaining = s.coveredTiles
    assert len(remaining) == covered_before - uncovered
    # Every surviving covered tile belongs to the far region.
    far = s.regions[1]
    assert all(far.overlapsTile(t, (20e-6, 10e-6)) for t in remaining)


def test_force_rescan_outside_every_region_is_a_no_op():
    # A hand-seeded cell outside every drawn region has no coverage to
    # invalidate; hand-added cells are outside the scanner's responsibility.
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    before = list(s.coveredTiles)

    assert s.forceRescan((9e-3, 9e-3), lambda cell: False) == 0
    assert s.coveredTiles == before


def test_force_rescan_deregisters_only_never_attempted_cells():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    tile = s.tileGrid()[0]
    attempted = _PositionedCell((tile[0], tile[1], -30e-6))
    fresh = _PositionedCell((tile[0], tile[1], -35e-6))
    s.registerCells([attempted, fresh])

    s.forceRescan(tile, lambda cell: cell is attempted)

    near = s.cellsNearTile(tile)
    assert attempted in near
    assert fresh not in near


def test_force_rescan_leaves_cells_in_untouched_regions_registered():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    far_tile = [t for t in s.tileGrid() if t[0] > 4e-3][0]
    far_cell = _PositionedCell((far_tile[0], far_tile[1], -30e-6))
    s.registerCells([far_cell])

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert far_cell in s.cellsNearTile(far_tile)


def test_force_rescan_does_not_touch_regions_or_constraints():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    regions_before = s.regions
    constraints_before = s.constraints

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert s.regions == regions_before
    assert s.constraints is constraints_before


def test_force_rescan_accepts_a_3d_tuple_position():
    # A detected cell's position carries depth as a third element (a real
    # example: acq4_automation.feature_tracking.cell.Cell.position, built from
    # a stack scanned in z). forceRescan must use only the xy of that position
    # rather than fail trying to unpack three values as two.
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    covered_before = len(s.coveredTiles)

    uncovered = s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6, -30e-6), lambda cell: False)

    assert uncovered > 0
    remaining = s.coveredTiles
    assert len(remaining) == covered_before - uncovered
    far = s.regions[1]
    assert all(far.overlapsTile(t, (20e-6, 10e-6)) for t in remaining)


def test_force_rescan_accepts_a_3d_coorx_point_position():
    # The tile detector hands cells a global coorx.Point, not a tuple, so that
    # shape needs the same xy narrowing a plain 3-tuple gets.
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    covered_before = len(s.coveredTiles)

    position = coorx.Point([1e-3 + 30e-6, 2e-3 + 15e-6, -30e-6])
    uncovered = s.forceRescan(position, lambda cell: False)

    assert uncovered > 0
    remaining = s.coveredTiles
    assert len(remaining) == covered_before - uncovered
    far = s.regions[1]
    assert all(far.overlapsTile(t, (20e-6, 10e-6)) for t in remaining)


def test_force_rescan_uncovers_every_overlapping_region():
    # Overlapping regions both hold the position, so both must be re-imaged.
    s = Slice(fov=(20e-6, 10e-6))
    s.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    s.addRegion(RectRegion(1e-3 + 20e-6, 2e-3, 1e-3 + 80e-6, 2e-3 + 30e-6))
    for tile in s.tileGrid():
        s.markCovered(tile)

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert s.coveredTiles == []

