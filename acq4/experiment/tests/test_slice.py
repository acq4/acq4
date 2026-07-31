"""Tests for SearchConstraints validation and the Slice object's regions,
coverage, and survey statistics."""

import gc
import weakref

import pytest

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
    s.addRegion(0, 0, 30e-6, 30e-6)
    assert len(s.tileGrid()) == 9
    assert s.surveyStats() == (9, 0, 0.0)


def test_regions_is_a_copy_so_callers_cannot_mutate_slice_state():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    s.regions.append((1, 1, 2, 2))
    assert len(s.regions) == 1


def test_a_second_region_extends_the_grid_without_disturbing_the_first():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    first = s.tileGrid()
    # 1e-3 keeps the region well clear of the first and sits at a realistic
    # stage coordinate.
    s.addRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6)
    both = s.tileGrid()
    assert both[: len(first)] == first
    assert len(both) == 18


def test_marking_a_tile_covered_advances_next_tile():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    first = s.nextTile()
    assert s.nextTile() == first, "nextTile must not mark; it only reports"
    s.markCovered(first)
    assert s.nextTile() != first
    assert s.surveyStats() == (9, 1, pytest.approx(100 / 9))


def test_next_tile_is_none_once_every_tile_is_covered():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    for _ in range(9):
        s.markCovered(s.nextTile())
    assert s.nextTile() is None
    assert s.surveyStats() == (9, 9, 100.0)


def test_next_tile_follows_tile_grid_order():
    # The grid is serpentine-ordered to minimize stage travel between tiles,
    # so nextTile must hand out tileGrid()'s tiles in that same order, not
    # merely some order that avoids repeats.
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
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
    s.addRegion(0, 0, 30e-6, 30e-6)
    covered = s.nextTile()
    s.markCovered(covered)
    s.addRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6)
    assert covered in s.coveredTiles
    assert s.surveyStats()[1] == 1


def test_covered_tiles_is_a_copy_so_callers_cannot_mutate_slice_state():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    s.markCovered(s.nextTile())
    s.coveredTiles.append((1, 1))
    assert len(s.coveredTiles) == 1


def test_reset_coverage_forgets_imaged_tiles_but_keeps_regions():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
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
    s.addRegion(0, 0, 30e-6, 30e-6)
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


def test_directory_defaults_to_none_and_round_trips_through_the_constructor():
    # `directory` is the acq4 slice directory handle this search state
    # belongs to, kept so a caller can find where to write per-slice data
    # alongside it; it must come back unchanged.
    assert make_slice().directory is None
    sentinel = object()
    assert make_slice(directory=sentinel).directory is sentinel


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
    plain.addRegion(0, 0, 30e-6, 30e-6)
    overlapped = make_slice(overlap=5e-6)
    overlapped.addRegion(0, 0, 30e-6, 30e-6)
    assert len(overlapped.tileGrid()) > len(plain.tileGrid())


def test_make_cell_producer_returns_a_view_the_slice_does_not_retain():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
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
