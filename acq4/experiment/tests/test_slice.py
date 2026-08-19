"""Tests for SearchConstraints validation and the Slice object's regions,
coverage, survey statistics, and the record it writes into its data directory."""

import gc
import weakref

import coorx
import pytest

import acq4.util.DataManager as dm

from acq4.experiment.search_grid import count_grid, plan_grid
from acq4.experiment.search_region import (
    EllipseRegion,
    PolygonRegion,
    RectRegion,
    SearchRegion,
    region_from_dict,
)
from acq4.experiment.slice import (
    MAX_PLANNED_TILES,
    RegionTooLarge,
    SearchConstraints,
    Slice,
)


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


def test_detection_defaults_match_what_the_survey_used_before_these_were_settable():
    c = SearchConstraints()
    assert c.min_volume_m3 == 0.0
    assert c.step_z == 1e-6


def test_step_z_must_be_positive():
    # A zero or negative z increment is nonsense for a detection z-stack.
    with pytest.raises(ValueError, match="positive"):
        SearchConstraints(step_z=0.0)
    with pytest.raises(ValueError, match="positive"):
        SearchConstraints(step_z=-1e-6)


def test_min_volume_must_be_non_negative():
    with pytest.raises(ValueError, match="non-negative"):
        SearchConstraints(min_volume_m3=-1e-18)


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


def test_the_tile_grid_starts_in_the_middle_and_spirals_out():
    # A survey ordered by rows starts at a corner, which is the worst ground on
    # a slice: the edges are where the tissue is damaged. Starting at the most
    # interior tile puts the best tissue first, and an operator who stops the
    # run early has surveyed a compact area around the middle rather than a band
    # along one side. Any order at all would still cover the region, so nothing
    # else in the suite would notice the difference -- hence pinning it here.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    grid = s.tileGrid()
    assert len(grid) == 9

    assert grid[0] == pytest.approx((15e-6, 15e-6))
    # And then the eight tiles around it, each next to the last.
    steps = [
        max(abs(bx - ax), abs(by - ay))
        for (ax, ay), (bx, by) in zip(grid, grid[1:])
    ]
    assert steps == [pytest.approx(10e-6)] * 8


def test_each_region_spirals_out_from_its_own_middle():
    # Ordering is per region, not across the slice: two regions are two pieces
    # of tissue with a stage move between them, so the second one starts over at
    # its own middle rather than continuing rings drawn around the first.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.addRegion(RectRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    grid = s.tileGrid()
    assert len(grid) == 18
    assert grid[0] == pytest.approx((15e-6, 15e-6))
    assert grid[9] == pytest.approx((1e-3 + 15e-6, 1e-3 + 15e-6))


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
    # The grid is ordered outward from the middle of each region, so nextTile
    # must hand out tileGrid()'s tiles in that same order, not merely some order
    # that avoids repeats.
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
    # The regression guard for the whole migration: a rectangle must be tiled
    # exactly as it was when regions were 4-tuples. It provably is -- plan_grid
    # centers its grid over the box, so every tile it plans overlaps the box --
    # and this pins that so a future filter change cannot quietly cost tiles.
    # Compared as sets, because only the *order* the tiles are handed out in has
    # moved on from plan_grid's rows.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    assert sorted(s.tileGrid()) == sorted(
        plan_grid(0, 0, 30e-6, 30e-6, FOV[0], FOV[1], 0.0)
    )


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
    # Named by position rather than by index into `planned`, since the two are
    # ordered outward from their own middles and share no index.
    corners = [
        c
        for c in planned
        if c[0] in (pytest.approx(5e-6), pytest.approx(145e-6))
        and c[1] in (pytest.approx(5e-6), pytest.approx(145e-6))
    ]
    assert len(corners) == 4
    assert not any(c in kept for c in corners)
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


def test_the_shape_filter_runs_before_the_order_is_chosen():
    # Not merely an implementation detail: which tile is most interior is a
    # property of the tiles that survive the shape. A filter applied afterwards
    # would spiral out from the middle of the bounding box -- for an L or a
    # crescent, ground the operator explicitly excluded -- and would leave holes
    # in the middle of the order where it had removed tiles.
    side = 150e-6
    ellipse = make_slice()
    ellipse.addRegion(EllipseRegion(0, 0, side, side))
    grid = ellipse.tileGrid()

    assert grid[0] == pytest.approx((75e-6, 75e-6))
    # Every ring around that seed is complete before the next one starts, which
    # is only true if the corners the ellipse dropped were never in the lattice
    # the rings were counted over.
    # Rounded, because a ring is a count of tiles and these centers are floats
    # a few ulps either side of an exact multiple of the field.
    rings = [
        round(max(abs(cx - 75e-6), abs(cy - 75e-6)) / 10e-6) for cx, cy in grid
    ]
    assert rings == sorted(rings)
    assert rings.count(1) == 8


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


def test_slice_holds_its_data_directory():
    handle = object()
    assert Slice(fov=(20e-6, 10e-6), dirHandle=handle).dirHandle is handle


def test_slice_without_a_data_directory_is_valid():
    # A slice created implicitly by "Add region here" was never formally started
    # and honestly has no directory.
    assert Slice(fov=(20e-6, 10e-6)).dirHandle is None


def test_force_rescan_uncovers_every_overlapping_region():
    # Overlapping regions both hold the position, so both must be re-imaged.
    s = Slice(fov=(20e-6, 10e-6))
    s.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    s.addRegion(RectRegion(1e-3 + 20e-6, 2e-3, 1e-3 + 80e-6, 2e-3 + 30e-6))
    for tile in s.tileGrid():
        s.markCovered(tile)

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert s.coveredTiles == []


class _EditsTheSliceMidScan(SearchRegion):
    """A region that replaces its slice's region list from inside the tiler's
    own iteration -- what a GUI-thread setRegions() landing in the middle of a
    worker-thread tileGrid() does.

    Deterministic on purpose: driving this with real threads would reproduce the
    hazard only sometimes, and a test that fails one run in fifty is not a test.
    """

    def __init__(self, slice_, replacement):
        self._slice = slice_
        self._replacement = replacement
        self.calls = 0

    def bounds(self):
        return (0.0, 0.0, 400e-6, 200e-6)

    def overlapsTile(self, center, fov):
        self.calls += 1
        if self.calls == 1:
            self._slice.setRegions(self._replacement)
        return True


def test_an_edit_during_tilegrid_does_not_drop_the_regions_behind_it():
    # The whole point of the swap. With the list mutated in place instead, the
    # for-loop's index walks off the end of a shortened list and every region
    # after the one being scanned is silently dropped from the survey.
    sl = Slice(fov=(100e-6, 50e-6))
    later = RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)
    mutator = _EditsTheSliceMidScan(sl, [])
    sl.setRegions([mutator, later])

    grid = sl.tileGrid()

    laterTiles = [c for c in grid if c[0] > 0.5e-3]
    assert laterTiles, "the region after the edited one was dropped mid-scan"


def test_the_edit_itself_takes_effect_on_the_next_call():
    # The swap must not be a no-op in the other direction: the point of editing
    # regions is that the next tile the producer asks for reflects the edit.
    sl = Slice(fov=(100e-6, 50e-6))
    mutator = _EditsTheSliceMidScan(sl, [])
    sl.setRegions([mutator, RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)])
    sl.tileGrid()

    assert sl.regions == []
    assert sl.tileGrid() == []


def test_setregions_copies_so_the_callers_list_is_not_live():
    # The panel hands over a list it goes on mutating as the operator draws.
    sl = Slice(fov=(100e-6, 50e-6))
    handed = [RectRegion(0.0, 0.0, 400e-6, 200e-6)]
    sl.setRegions(handed)
    handed.append(RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3))

    assert len(sl.regions) == 1


def test_deleting_a_region_leaves_coverage_alone():
    # Coverage records ground already imaged, not ground still wanted. Pruning
    # it when a region goes away would make a region redrawn over surveyed
    # tissue re-image it, and coverage is shared by every producer this slice
    # makes -- it is not a per-region tally.
    sl = Slice(fov=(100e-6, 50e-6))
    sl.setRegions([RectRegion(0.0, 0.0, 400e-6, 200e-6)])
    covered = sl.tileGrid()[0]
    sl.markCovered(covered)

    sl.setRegions([])

    assert sl.tileGrid() == []
    sl.setRegions([RectRegion(0.0, 0.0, 400e-6, 200e-6)])
    assert sl.nextTile() != covered



# A polygon the size of the one a mis-drag actually produced on the rig, at the
# field of view it was drawn at: a 0.687 m x 0.873 m bounding box against a
# 130.6 um field plans about 35 million tiles, which measured out at minutes of
# GUI-thread compute per ROI edit. The vertices are this test's own -- only the
# bounding box was recorded from the rig.
_MISDRAG_FOV = (130.6e-6, 130.6e-6)
_MISDRAG_REGION = PolygonRegion(
    ((0.0, 0.0), (0.687, 0.021), (0.687, 0.873), (0.013, 0.851))
)


def test_a_mis_dragged_region_is_refused_rather_than_planned():
    sl = Slice(fov=_MISDRAG_FOV)
    with pytest.raises(RegionTooLarge):
        sl.setRegions([_MISDRAG_REGION])


def test_the_refusal_names_the_size_and_the_tile_count():
    # The operator has to be told what they drew and why it was rejected; a bare
    # "too large" leaves them re-dragging blind.
    sl = Slice(fov=_MISDRAG_FOV)
    with pytest.raises(RegionTooLarge) as excinfo:
        sl.setRegions([_MISDRAG_REGION])
    message = str(excinfo.value)
    assert "0.687" in message
    assert "0.873" in message
    assert str(MAX_PLANNED_TILES) in message.replace(",", "")
    # The count reported is the grid that would actually have been planned, not
    # the cap it exceeded, and it is the tens-of-millions figure that makes the
    # refusal worth reading.
    planned = count_grid(*_MISDRAG_REGION.bounds(), *_MISDRAG_FOV, 0.0)
    assert planned > 35_000_000
    assert str(planned) in message.replace(",", "")


def test_a_refused_region_does_not_reach_the_slice():
    # Refusing is not the same as accepting-and-not-surveying: a slice left
    # holding the region would plan it on the very next tileGrid() call.
    sl = Slice(fov=_MISDRAG_FOV)
    kept = RectRegion(1e-3, 2e-3, 1.4e-3, 2.1e-3)
    sl.setRegions([kept])

    with pytest.raises(RegionTooLarge):
        sl.setRegions([kept, _MISDRAG_REGION])

    assert sl.regions == [kept]


def test_add_region_is_guarded_too():
    # addRegion() is the other way in, and "Add region here" reaches the slice
    # through it.
    sl = Slice(fov=_MISDRAG_FOV)
    with pytest.raises(RegionTooLarge):
        sl.addRegion(_MISDRAG_REGION)
    assert sl.regions == []


def test_the_guard_counts_the_tiles_without_planning_them():
    # The count is the whole hazard: the planner materialises every center
    # before any of them is filtered, so a guard that planned first would still
    # spend the minutes and the memory it exists to avoid. Proven by making the
    # planner unusable rather than by timing anything.
    import acq4.experiment.slice as slice_module

    def boom(*args, **kwargs):
        raise AssertionError("the guard planned the grid it was refusing")

    original, slice_module.plan_center_out = slice_module.plan_center_out, boom
    try:
        sl = Slice(fov=_MISDRAG_FOV)
        with pytest.raises(RegionTooLarge):
            sl.setRegions([_MISDRAG_REGION])
    finally:
        slice_module.plan_center_out = original


def test_a_large_but_plausible_region_is_still_accepted():
    # 20 mm x 4.95 mm at a 100 x 50 um field is 19,800 tiles -- larger than any
    # real slice and still under the cap, so the cap cannot be what stops an
    # operator outlining a whole piece of tissue. Asymmetric on both axes so a
    # guard that counted one axis twice would be caught.
    sl = Slice(fov=(100e-6, 50e-6))
    sl.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 20e-3, 2e-3 + 4.95e-3))

    planned = len(sl.tileGrid())
    assert planned == 19800
    assert planned <= MAX_PLANNED_TILES


def test_the_cap_is_measured_against_the_grid_that_would_actually_be_planned():
    # One more tile row past the case above crosses the cap, and the guard's
    # arithmetic must agree with plan_grid's about exactly where that is.
    sl = Slice(fov=(100e-6, 50e-6))
    with pytest.raises(RegionTooLarge) as excinfo:
        sl.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 20e-3, 2e-3 + 5.05e-3))
    assert "20200" in str(excinfo.value).replace(",", "")


# ---- containment ----


def test_a_slice_with_no_regions_contains_everything():
    # "No region drawn" means there is nothing to be outside of, not that the
    # slice is empty. A hand-seeded run has no regions at all, and a producer
    # that filtered cells against an empty region list would drop every one of
    # them and patch nothing.
    s = make_slice()
    assert s.containsPoint((0.0, 0.0)) is True
    assert s.containsPoint((1e3, -4e2)) is True


def test_a_slice_contains_a_point_inside_any_one_of_its_regions():
    # Regions are alternatives, not an intersection: an operator outlining two
    # separate pieces of tissue means either is worth patching in.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.addRegion(EllipseRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    assert s.containsPoint((15e-6, 15e-6)) is True
    assert s.containsPoint((1e-3 + 15e-6, 1e-3 + 15e-6)) is True


def test_a_point_outside_every_region_is_not_contained():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.addRegion(EllipseRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    assert s.containsPoint((500e-6, 500e-6)) is False
    # In the second region's bounding box but outside the inscribed ellipse:
    # the shape has to be consulted, not just the box.
    assert s.containsPoint((1e-3, 1e-3)) is False


def test_containment_is_stricter_than_the_ground_the_survey_images():
    # The asymmetry the whole filter exists for: the tile at the region's edge
    # is imaged (its overhang is deliberate), so the segmenter sees this point
    # and may well find a cell there -- and it still is not in the region.
    # A region whose extent is not a whole number of fields, which is what makes
    # the grid overhang it: plan_grid centres 3 tiles over 25 um of region, so
    # the outermost tiles reach 2.5 um past each edge.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 25e-6, 25e-6))
    justOutside = (-2e-6, 12.5e-6)
    assert any(
        abs(justOutside[0] - tx) <= FOV[0] / 2 and abs(justOutside[1] - ty) <= FOV[1] / 2
        for tx, ty in s.tileGrid()
    ), "premise: this point falls inside a tile the survey images"
    assert s.containsPoint(justOutside) is False


def test_contains_point_reads_only_x_and_y():
    # Detected cells carry a 3-D global coorx.Point; depth is no part of a
    # region's question.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    assert s.containsPoint(coorx.Point([15e-6, 15e-6, -30e-6])) is True
    assert s.containsPoint([15e-6, 15e-6, -30e-6]) is True
    assert s.containsPoint(coorx.Point([150e-6, 15e-6, -30e-6])) is False


# ---- persistence ----


@pytest.fixture
def slice_dir(tmp_path):
    """A real managed directory, because what is being tested is the record on
    disk: a fake DirHandle would prove only that saveState() called the methods
    the test author expected it to, not that a `.index` and a YAML file come
    back out saying what went in."""
    return dm.getDirHandle(str(tmp_path), create=True)


def _saved_slice(dirHandle, **kwargs):
    kwargs.setdefault("fov", (100e-6, 50e-6))
    kwargs.setdefault("overlap", 7e-6)
    kwargs.setdefault(
        "constraints",
        SearchConstraints(
            depth_range=(-15e-6, -75e-6),
            min_health=0.62,
            max_cell_density=3e12,
            rescans_allowed=True,
            min_volume_m3=5e-17,
            step_z=2e-6,
        ),
    )
    s = Slice(dirHandle=dirHandle, **kwargs)
    s.setRegions(
        [
            RectRegion(1e-3, 2e-3, 1.4e-3, 2.2e-3, 31.5),
            EllipseRegion(3e-3, 2e-3, 3.4e-3, 2.2e-3),
            PolygonRegion(((5e-3, 2e-3), (5.4e-3, 2e-3), (5.2e-3, 2.3e-3))),
        ]
    )
    for tile in s.tileGrid()[:5]:
        s.markCovered(tile)
    return s


def test_a_slice_with_no_directory_saves_nothing(tmp_path):
    # The "Add region here" slice: it came into existence to hold a region and
    # honestly has nowhere to write. Saving must be a no-op rather than a
    # raise, because every caller of saveState() is a GUI slot that has
    # already committed the operator's edit by the time it asks.
    s = make_slice()
    s.addRegion(RectRegion(0.0, 0.0, 30e-6, 30e-6))

    s.saveState()

    assert list(tmp_path.iterdir()) == []


def test_save_state_writes_the_regions_the_operator_drew(slice_dir):
    s = _saved_slice(slice_dir)

    s.saveState()

    written = slice_dir["regions.yaml"].read()
    assert [region_from_dict(d) for d in written] == s.regions


def test_saved_regions_keep_their_angle_and_their_order(slice_dir):
    # Order matters as much as geometry: tileGrid() concatenates region by
    # region and a survey works them in that order, so a record that reordered
    # them would restore a slice that images the same tissue in a different
    # sequence -- and the angle is the part a naive format loses.
    s = _saved_slice(slice_dir)

    s.saveState()

    written = slice_dir["regions.yaml"].read()
    assert [d["shape"] for d in written] == ["rect", "ellipse", "polygon"]
    assert written[0]["angle"] == 31.5


def test_save_state_writes_the_search_parameters(slice_dir):
    s = _saved_slice(slice_dir)

    s.saveState()

    state = slice_dir["search_state.yaml"].read()
    assert state["fov"] == [100e-6, 50e-6]
    assert state["overlap"] == 7e-6
    assert state["constraints"] == {
        "depth_range": [-15e-6, -75e-6],
        "min_health": 0.62,
        "max_cell_density": 3e12,
        "rescans_allowed": True,
        "min_volume_m3": 5e-17,
        "step_z": 2e-6,
    }


def test_save_state_writes_the_coverage_and_the_survey_it_implies(slice_dir):
    s = _saved_slice(slice_dir)
    total, covered, percent = s.surveyStats()

    s.saveState()

    state = slice_dir["search_state.yaml"].read()
    assert [tuple(t) for t in state["covered"]] == s.coveredTiles
    assert state["survey"] == {
        "total_tiles": total,
        "covered_tiles": covered,
        "percent_covered": percent,
    }


def test_save_state_mirrors_a_summary_onto_the_directory_index(slice_dir):
    # The scalars a Data Manager browser can sort a night's slices by without
    # opening any of them.
    s = _saved_slice(slice_dir)

    s.saveState()

    info = slice_dir.info()
    assert info["n_regions"] == 3
    assert info["percent_covered"] == s.surveyStats()[2]
    assert info["min_health"] == 0.62
    assert info["depth_range"] == [-15e-6, -75e-6]


def test_the_index_summary_survives_being_read_back_off_disk(slice_dir):
    # The `.index` is written with repr() and read back with eval() in a
    # namespace that knows nothing about this module, so a frozen dataclass or
    # a big array put there would be written and never read. Only plain scalars
    # may go in, and this is what proves it.
    s = _saved_slice(slice_dir)
    s.saveState()

    reopened = dm.getDirHandle(slice_dir.name())
    reopened._index = None  # force a genuine re-read rather than the cache
    info = reopened.info()

    assert info["n_regions"] == 3
    assert info["depth_range"] == [-15e-6, -75e-6]


def test_save_state_overwrites_the_previous_save(slice_dir):
    # Called on every region edit, so the record is the slice as it stands and
    # not an accumulating pile of near-identical files.
    s = _saved_slice(slice_dir)
    s.saveState()

    s.setRegions([RectRegion(1e-3, 2e-3, 1.4e-3, 2.2e-3)])
    s.saveState()

    written = slice_dir["regions.yaml"].read()
    assert len(written) == 1
    assert slice_dir.info()["n_regions"] == 1


def test_snapshot_state_then_write_snapshot_writes_the_same_record_as_save_state(
    slice_dir,
):
    # saveState() is snapshotState() immediately followed by writeSnapshot():
    # a caller that must not read this Slice off the GUI thread (see
    # AutopatchWindow._flushSliceState) captures the snapshot where saveState()
    # would, and hands it to writeSnapshot() to do the actual writing --
    # possibly later, possibly on another thread. Splitting them must not
    # change what ends up on disk.
    s = _saved_slice(slice_dir)

    snapshot = s.snapshotState()
    Slice.writeSnapshot(snapshot)

    assert slice_dir["regions.yaml"].read() == [r.to_dict() for r in s.regions]
    state = slice_dir["search_state.yaml"].read()
    assert [tuple(t) for t in state["covered"]] == s.coveredTiles
    assert slice_dir.info()["n_regions"] == 3


def test_snapshot_state_is_plain_data_not_a_reference_into_the_slice(slice_dir):
    # The whole point of splitting the snapshot out of saveState() is that a
    # worker thread writing it later must never touch this Slice's own
    # mutable state -- only regions.to_dict()'d already, coordinates already
    # float()'d, nothing that setRegions()/markCovered() could still mutate
    # out from under a write in progress.
    s = _saved_slice(slice_dir)

    snapshot = s.snapshotState()

    assert all(isinstance(d, dict) for d in snapshot["regions"])
    s.setRegions([RectRegion(0.0, 0.0, 1e-3, 1e-3)])
    s.markCovered((999.0, 999.0))
    s.setConstraints(SearchConstraints(min_volume_m3=9e-17, step_z=9e-6))
    # The snapshot already taken must be untouched by the mutations above.
    assert len(snapshot["regions"]) == 3
    assert (999.0, 999.0) not in [tuple(c) for c in snapshot["state"]["covered"]]
    assert snapshot["state"]["constraints"]["min_volume_m3"] == 5e-17
    assert snapshot["state"]["constraints"]["step_z"] == 2e-6


def test_snapshot_state_returns_none_without_a_directory():
    s = make_slice()
    s.addRegion(RectRegion(0.0, 0.0, 30e-6, 30e-6))

    assert s.snapshotState() is None


class _RefusesToWrite:
    """A DirHandle whose every write fails -- a full disk, a storage directory
    that went away with a network mount, a permission that changed under a
    running session."""

    def __init__(self):
        self.attempts = 0

    def writeFile(self, *args, **kwargs):
        self.attempts += 1
        raise OSError("no space left on device")

    def setInfo(self, *args, **kwargs):
        raise OSError("no space left on device")


def test_save_state_never_raises(slice_dir):
    # Losing the record must not take down whatever asked for the save. Every
    # caller is either a GUI slot that has already committed the operator's
    # edit or newSlice() partway through discarding a slice, and a raise in
    # either place costs far more than the file it failed to write.
    s = _saved_slice(_RefusesToWrite())

    s.saveState()


def test_a_failed_write_still_tries_the_rest(slice_dir):
    # The regions are the irreplaceable half -- an operator traced them by hand
    # -- so they are written first; but one file failing must not silently drop
    # the others, since the reason it failed may well be specific to it.
    handle = _RefusesToWrite()
    s = _saved_slice(handle)

    s.saveState()

    assert handle.attempts == 2


class _SwapsRegionsWhileBeingSaved(SearchRegion):
    """A region that replaces its slice's region list the moment it is asked to
    serialize itself -- a GUI-thread setRegions() landing in the middle of a
    save.

    Deterministic on purpose, for the reason _EditsTheSliceMidScan gives:
    driving this with real threads would reproduce the hazard only sometimes.
    """

    def __init__(self, slice_, replacement):
        self._slice = slice_
        self._replacement = replacement

    def bounds(self):
        return (0.0, 0.0, 400e-6, 200e-6)

    def overlapsTile(self, center, fov):
        return True

    def to_dict(self):
        self._slice.setRegions(self._replacement)
        return {"shape": "rect", "box": [0.0, 0.0, 400e-6, 200e-6], "angle": 0.0}


def test_a_save_records_one_whole_set_of_regions(slice_dir):
    # The same discipline setRegions() and tileGrid() keep: bind the list once,
    # so a reader sees either the whole old set or the whole new one. A save
    # that re-read the attribute for its statistics would write a file whose
    # regions and whose tile counts describe two different slices.
    s = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    later = RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)
    s.setRegions([_SwapsRegionsWhileBeingSaved(s, []), later])

    s.saveState()

    written = slice_dir["regions.yaml"].read()
    state = slice_dir["search_state.yaml"].read()
    assert len(written) == 2, "the region after the edited one was dropped mid-save"
    assert state["survey"]["total_tiles"] > 0, (
        "the statistics were computed from a different region list than the one saved"
    )


# ---- loading back ----


def test_load_state_restores_what_save_state_wrote(slice_dir):
    saved = _saved_slice(slice_dir)
    saved.saveState()

    restored = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    assert restored.loadState() is True

    assert restored.regions == saved.regions
    assert restored.constraints == saved.constraints
    assert restored.coveredTiles == saved.coveredTiles
    assert restored.surveyStats() == saved.surveyStats()


def test_load_state_restores_the_overlap_the_tiles_were_planned_at(slice_dir):
    # Coverage is a list of tile centres, and which centres a grid has depends
    # on the overlap. Restoring the tiles without it would leave the record
    # claiming ground was imaged at coordinates this slice never plans.
    saved = _saved_slice(slice_dir)
    saved.saveState()

    restored = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    restored.loadState()

    assert restored.tileGrid() == saved.tileGrid()


def test_load_state_leaves_the_field_of_view_alone(slice_dir):
    # The field of view belongs to the camera that is mounted now, not to the
    # one that was mounted when the record was written. It is saved for the
    # record and deliberately not applied.
    saved = _saved_slice(slice_dir)
    saved.saveState()

    restored = Slice(fov=(200e-6, 200e-6), dirHandle=slice_dir)
    restored.loadState()

    assert restored.fov == (200e-6, 200e-6)


def test_load_state_defaults_detection_settings_missing_from_an_older_record(slice_dir):
    # A record written before min_volume_m3/step_z existed simply lacks those
    # keys; loading it falls back to the library defaults rather than raising.
    saved = _saved_slice(slice_dir)
    saved.saveState()
    state = slice_dir["search_state.yaml"].read()
    del state["constraints"]["min_volume_m3"]
    del state["constraints"]["step_z"]
    slice_dir.writeFile(state, "search_state.yaml", fileType="YamlFile")

    restored = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    assert restored.loadState() is True

    assert restored.constraints.min_volume_m3 == 0.0
    assert restored.constraints.step_z == 1e-6


def test_load_state_finds_nothing_in_a_directory_with_no_record(slice_dir):
    s = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    assert s.loadState() is False
    assert s.regions == []


def test_load_state_without_a_directory_finds_nothing():
    assert Slice(fov=(100e-6, 50e-6)).loadState() is False
