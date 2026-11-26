"""Tests for SearchConstraints validation and the Slice object's regions,
coverage, survey statistics, and the record it writes into its data directory."""

import gc
import weakref
from uuid import uuid4

import coorx
import numpy as np
import pytest

import acq4.util.DataManager as dm

import acq4.experiment.survey as survey_module
from acq4.experiment.survey import TileRecord
from acq4.experiment.survey_planner import MAX_MASK_PIXELS, mask_pixel_count
from acq4.experiment.survey_record import writeRecord
from acq4.experiment.search_region import (
    EllipseRegion,
    PolygonRegion,
    RectRegion,
    SearchRegion,
    region_from_dict,
)
from acq4.experiment.slice import (
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


def test_min_cell_spacing_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        SearchConstraints(min_cell_spacing=0.0)


def test_the_density_cap_is_derived_from_the_spacing():
    assert SearchConstraints(min_cell_spacing=30e-6).max_cell_density == pytest.approx(8.842e12, rel=1e-3)


def test_max_cell_density_is_not_a_setting():
    with pytest.raises(TypeError):
        SearchConstraints(max_cell_density=5e12)


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


class _PlainCell:
    def __init__(self, position):
        self.position = position


@pytest.fixture(autouse=True)
def _plain_cells(monkeypatch):
    monkeypatch.setattr(survey_module, "_newCell", _PlainCell)


def _record(center, fov=None, **header):
    head = {"tile_center": list(center), **header}
    if fov is not None:
        head["fov"] = list(fov)
    return TileRecord(header=head, detections=())


def _cover(s, tile):
    s.survey.addTile(_record(tile))


def _coveredTiles(s):
    return [tuple(r.header["tile_center"]) for r in s.survey.tiles() if not r.superseded]


def _hand_out(s, cells):
    return [
        s.survey.handOut({"candidate_id": uuid4().hex, "position": list(c.position)})
        for c in cells
    ]


class FakeCell:
    """Stand-in for acq4_automation's Cell: a global position and a health score."""

    def __init__(self, position, score=1.0):
        self.position = position
        self.score = score


def test_a_new_slice_has_no_regions_and_nothing_to_survey():
    s = make_slice()
    assert s.regions == []
    assert s.nextTile() is None
    assert s.surveyStats() == (0, 0.0)


def test_adding_a_region_gives_the_survey_something_to_image():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    assert s.nextTile() is not None
    assert s.surveyStats() == (0, 0.0)


def test_regions_is_a_copy_so_callers_cannot_mutate_slice_state():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.regions.append(RectRegion(1e-3, 1e-3, 2e-3, 2e-3))
    assert len(s.regions) == 1


def test_a_second_region_is_surveyed_too():
    s = _sampler_slice()
    # 1e-3 keeps the region well clear of the first and sits at a realistic
    # stage coordinate.
    s.addRegion(RectRegion(1e-3, 1e-3, 1e-3 + 400e-6, 1e-3 + 200e-6))
    tiles = _survey_to_exhaustion(s)
    assert any(x < 0.5e-3 for x, _ in tiles)
    assert any(x > 0.5e-3 for x, _ in tiles)


def test_marking_a_tile_covered_advances_next_tile():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    first = s.nextTile()
    assert s.nextTile() == first, "nextTile must not mark; it only reports"
    _cover(s, first)
    assert s.nextTile() != first
    assert s.surveyStats()[0] == 1


def test_coverage_survives_a_new_region_being_added():
    # Shared coverage is the whole point: a second region's survey must not
    # re-image the first region's tiles.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    covered = s.nextTile()
    _cover(s, covered)
    s.addRegion(RectRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    assert s.surveyStats()[0] == 1
    assert s.nextTile() != covered


def test_reset_coverage_forgets_imaged_tiles_but_keeps_regions():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    _cover(s, s.nextTile())
    s.resetCoverage()
    assert s.nextTile() is not None
    assert len(s.regions) == 1
    assert s.surveyStats() == (0, 0.0)


def test_tile_volume_is_fov_area_times_the_depth_span():
    s = make_slice(constraints=SearchConstraints(depth_range=(-20e-6, -60e-6)))
    assert s.tileVolume() == pytest.approx(10e-6 * 10e-6 * 40e-6)


def test_registered_cells_are_found_near_their_own_tile_only():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    tile = s.nextTile()
    here = FakeCell((tile[0], tile[1], 0.0))
    far = FakeCell((tile[0] + 1e-3, tile[1], 0.0))
    _hand_out(s, [here, far])
    near = s.cellsNearTile(tile)
    assert [tuple(c.position) for c in near] == [tuple(here.position)]


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


def test_regions_of_different_shapes_share_one_slice_and_one_coverage_record():
    # Shapes are per region, not per slice: an operator can outline one area as a
    # rectangle and another as an ellipse, and coverage still spans both.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.addRegion(EllipseRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    assert [type(r) for r in s.regions] == [RectRegion, EllipseRegion]
    assert len(_survey_to_exhaustion(s)) > 2
    assert s.surveyStats()[1] > 50.0


def test_a_polygon_narrower_than_one_field_is_still_surveyed():
    # The end-to-end version of the band case: a diagonal band about 7 um wide
    # against a 10 um field is never most of any field, so a fixed eligibility
    # cutoff would report a region with nothing to survey.
    s = make_slice()
    s.addRegion(
        PolygonRegion([(0.0, 0.0), (60e-6, 60e-6), (60e-6, 70e-6), (0.0, 10e-6)])
    )
    tiles = _survey_to_exhaustion(s)
    assert len(tiles) > 2
    assert s.surveyStats()[1] > 50.0


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
    _survey_to_exhaustion(s)
    covered_before = len(_coveredTiles(s))

    uncovered = s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert uncovered > 0
    remaining = _coveredTiles(s)
    assert len(remaining) == covered_before - uncovered
    # Every surviving covered tile belongs to the far region.
    far = s.regions[1]
    assert all(far.overlapsTile(t, (20e-6, 10e-6)) for t in remaining)


def test_force_rescan_outside_every_region_is_a_no_op():
    # A hand-seeded cell outside every drawn region has no coverage to
    # invalidate; hand-added cells are outside the scanner's responsibility.
    s = _two_region_slice()
    _survey_to_exhaustion(s)
    before = list(_coveredTiles(s))

    assert s.forceRescan((9e-3, 9e-3), lambda cell: False) == 0
    assert _coveredTiles(s) == before


def test_force_rescan_deregisters_only_never_attempted_cells():
    s = _two_region_slice()
    _survey_to_exhaustion(s)
    tile = _coveredTiles(s)[0]
    attempted = _PositionedCell((tile[0], tile[1], -30e-6))
    fresh = _PositionedCell((tile[0], tile[1], -35e-6))
    attempted, fresh = _hand_out(s, [attempted, fresh])

    s.forceRescan(tile, lambda cell: cell is attempted)

    near = [tuple(c.position) for c in s.cellsNearTile(tile)]
    assert tuple(attempted.position) in near
    assert tuple(fresh.position) not in near


def test_force_rescan_leaves_cells_in_untouched_regions_registered():
    s = _two_region_slice()
    _survey_to_exhaustion(s)
    far_tile = [t for t in _coveredTiles(s) if t[0] > 4e-3][0]
    far_cell = _PositionedCell((far_tile[0], far_tile[1], -30e-6))
    _hand_out(s, [far_cell])

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert [tuple(c.position) for c in s.cellsNearTile(far_tile)] == [tuple(far_cell.position)]


def test_force_rescan_does_not_touch_regions_or_constraints():
    s = _two_region_slice()
    _survey_to_exhaustion(s)
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
    _survey_to_exhaustion(s)
    covered_before = len(_coveredTiles(s))

    uncovered = s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6, -30e-6), lambda cell: False)

    assert uncovered > 0
    remaining = _coveredTiles(s)
    assert len(remaining) == covered_before - uncovered
    far = s.regions[1]
    assert all(far.overlapsTile(t, (20e-6, 10e-6)) for t in remaining)


def test_force_rescan_accepts_a_3d_coorx_point_position():
    # The tile detector hands cells a global coorx.Point, not a tuple, so that
    # shape needs the same xy narrowing a plain 3-tuple gets.
    s = _two_region_slice()
    _survey_to_exhaustion(s)
    covered_before = len(_coveredTiles(s))

    position = coorx.Point([1e-3 + 30e-6, 2e-3 + 15e-6, -30e-6])
    uncovered = s.forceRescan(position, lambda cell: False)

    assert uncovered > 0
    remaining = _coveredTiles(s)
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
    _survey_to_exhaustion(s)

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert _coveredTiles(s) == []


class _EditsTheSliceMidScan(SearchRegion):
    """A region that replaces its slice's region list from inside the sampler's
    own rasterization -- what a GUI-thread setRegions() landing in the middle of
    a worker-thread nextTile() does.

    Deterministic on purpose: driving this with real threads would reproduce the
    hazard only sometimes, and a test that fails one run in fifty is not a test.
    """

    def __init__(self, slice_, replacement):
        self._slice = slice_
        self._replacement = replacement
        self.calls = 0

    def bounds(self):
        return (0.0, 0.0, 400e-6, 200e-6)

    def contains(self, point):
        return True

    def containsArray(self, xs, ys):
        self.calls += 1
        if self.calls == 1:
            self._slice.setRegions(self._replacement)
        return np.ones(np.shape(xs), dtype=bool)


def test_an_edit_during_next_tile_does_not_drop_the_regions_behind_it():
    # The whole point of the swap. With the list mutated in place instead, the
    # for-loop's index walks off the end of a shortened list and every region
    # after the one being rasterized is silently dropped from the survey.
    later = RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)
    picks = []
    for seed in range(16):
        sl = Slice(fov=(100e-6, 50e-6), sampler_seed=seed)
        sl.setRegions([_EditsTheSliceMidScan(sl, []), later])
        picks.append(sl.nextTile())

    assert any(x > 0.5e-3 for x, _ in picks), (
        "the region after the edited one was dropped mid-scan"
    )


def test_the_edit_itself_takes_effect_on_the_next_call():
    # The swap must not be a no-op in the other direction: the point of editing
    # regions is that the next tile the producer asks for reflects the edit.
    sl = Slice(fov=(100e-6, 50e-6))
    mutator = _EditsTheSliceMidScan(sl, [])
    sl.setRegions([mutator, RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)])
    sl.nextTile()

    assert sl.regions == []
    assert sl.nextTile() is None


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
    covered = sl.nextTile()
    _cover(sl, covered)

    sl.setRegions([])

    assert sl.nextTile() is None
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


def test_the_refusal_names_the_size_and_the_pixel_count():
    # The operator has to be told what they drew and why it was rejected; a bare
    # "too large" leaves them re-dragging blind.
    sl = Slice(fov=_MISDRAG_FOV)
    with pytest.raises(RegionTooLarge) as excinfo:
        sl.setRegions([_MISDRAG_REGION])
    message = str(excinfo.value)
    assert "0.687" in message
    assert "0.873" in message
    assert str(MAX_MASK_PIXELS) in message.replace(",", "")
    # The count reported is the map that would actually have been built, not
    # the cap it exceeded, and it is the billions figure that makes the refusal
    # worth reading.
    pixels = mask_pixel_count(_MISDRAG_REGION.bounds(), _MISDRAG_FOV)
    assert pixels > 1_000_000_000
    assert str(pixels) in message.replace(",", "")


def test_a_refused_region_does_not_reach_the_slice():
    # Refusing is not the same as accepting-and-not-surveying: a slice left
    # holding the region would rasterize it on the very next nextTile() call.
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


def test_the_guard_measures_the_map_without_building_it():
    # The size is the whole hazard: rasterizing first would spend the time and
    # memory the guard exists to avoid. Proven by making the rasterizer
    # unusable rather than by timing anything.
    import acq4.experiment.slice as slice_module

    def boom(*args, **kwargs):
        raise AssertionError("the guard rasterized the regions it was refusing")

    original, slice_module.rasterize_regions = slice_module.rasterize_regions, boom
    try:
        sl = Slice(fov=_MISDRAG_FOV)
        with pytest.raises(RegionTooLarge):
            sl.setRegions([_MISDRAG_REGION])
    finally:
        slice_module.rasterize_regions = original


def test_a_large_but_plausible_region_is_still_accepted():
    # 10 mm x 9.8 mm at a 100 x 50 um field is just under the cap -- larger
    # than any real slice, so the cap cannot be what stops an operator
    # outlining a whole piece of tissue. Asymmetric on both axes so a guard
    # that counted one axis twice would be caught.
    sl = Slice(fov=(100e-6, 50e-6))
    region = RectRegion(1e-3, 2e-3, 1e-3 + 10e-3, 2e-3 + 9.8e-3)
    sl.addRegion(region)

    assert mask_pixel_count(region.bounds(), sl.fov) <= MAX_MASK_PIXELS


def test_the_cap_is_measured_against_the_map_that_would_actually_be_built():
    # A little more height crosses the cap, and the guard's arithmetic must
    # agree with the rasterizer's about the pixel count.
    sl = Slice(fov=(100e-6, 50e-6))
    region = RectRegion(1e-3, 2e-3, 1e-3 + 10e-3, 2e-3 + 9.9e-3)
    with pytest.raises(RegionTooLarge) as excinfo:
        sl.addRegion(region)
    assert str(mask_pixel_count(region.bounds(), sl.fov)) in str(excinfo.value)


def test_two_small_regions_far_apart_are_refused_together():
    # One raster spans every region, so the guard is on their union's box: two
    # modest regions metres apart would otherwise slip through one at a time.
    sl = Slice(fov=(100e-6, 50e-6))
    sl.addRegion(RectRegion(0.0, 0.0, 400e-6, 200e-6))
    with pytest.raises(RegionTooLarge):
        sl.addRegion(RectRegion(5.0, 5.0, 5.0004, 5.0002))
    assert len(sl.regions) == 1


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
    # A looser region-fraction cutoff lets fields straddle the outline, which is
    # what makes the survey overhang it. Seed 6 offers a field centred on the
    # region's left edge.
    s = make_slice(
        constraints=SearchConstraints(min_region_fraction=0.5), sampler_seed=6
    )
    s.addRegion(RectRegion(0, 0, 25e-6, 25e-6))
    justOutside = (-2e-6, 12.5e-6)
    assert any(
        abs(justOutside[0] - tx) <= FOV[0] / 2 and abs(justOutside[1] - ty) <= FOV[1] / 2
        for tx, ty in _survey_to_exhaustion(s)
    ), "premise: this point falls inside a field the survey images"
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
    kwargs.setdefault("sampler_seed", 5)
    kwargs.setdefault(
        "constraints",
        SearchConstraints(
            depth_range=(-15e-6, -75e-6),
            min_health=0.62,
            min_cell_spacing=25e-6,
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
    for _ in range(5):
        _cover(s, s.nextTile())
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
    # Order matters as much as geometry: a record that reordered them would
    # restore a slice whose region list differs from the one the operator
    # drew -- and the angle is the part a naive format loses.
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
        "min_cell_spacing": 25e-6,
        "rescans_allowed": True,
        "min_volume_m3": 5e-17,
        "step_z": 2e-6,
        "exposure_sigma": 50e-6,
        "exposure_tau": 300.0,
        "exposure_threshold": 0.1,
        "min_region_fraction": 0.8,
        "max_resurvey": 0.25,
    }


def test_save_state_writes_the_survey_counts_and_no_covered_list(slice_dir):
    s = _saved_slice(slice_dir)
    fields, percent = s.surveyStats()

    s.saveState()

    state = slice_dir["search_state.yaml"].read()
    assert "covered" not in state
    assert state["survey"] == {
        "fields_imaged": fields,
        "percent_covered": percent,
    }


def test_save_state_mirrors_a_summary_onto_the_directory_index(slice_dir):
    # The scalars a Data Manager browser can sort a night's slices by without
    # opening any of them.
    s = _saved_slice(slice_dir)

    s.saveState()

    info = slice_dir.info()
    assert info["n_regions"] == 3
    assert info["percent_covered"] == s.surveyStats()[1]
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
    assert "covered" not in state
    assert slice_dir.info()["n_regions"] == 3


def test_snapshot_state_is_plain_data_not_a_reference_into_the_slice(slice_dir):
    # The whole point of splitting the snapshot out of saveState() is that a
    # worker thread writing it later must never touch this Slice's own
    # mutable state -- only regions.to_dict()'d already, coordinates already
    # float()'d, nothing that setRegions() or a new tile record could still mutate
    # out from under a write in progress.
    s = _saved_slice(slice_dir)

    snapshot = s.snapshotState()

    assert all(isinstance(d, dict) for d in snapshot["regions"])
    s.setRegions([RectRegion(0.0, 0.0, 1e-3, 1e-3)])
    _cover(s, (999.0, 999.0))
    s.setConstraints(SearchConstraints(min_volume_m3=9e-17, step_z=9e-6))
    # The snapshot already taken must be untouched by the mutations above.
    assert len(snapshot["regions"]) == 3
    assert "covered" not in snapshot["state"]
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

    def contains(self, point):
        return True

    def containsArray(self, xs, ys):
        return np.ones(np.shape(xs), dtype=bool)

    def to_dict(self):
        self._slice.setRegions(self._replacement)
        return {"shape": "rect", "box": [0.0, 0.0, 400e-6, 200e-6], "angle": 0.0}


def test_a_save_records_one_whole_set_of_regions(slice_dir):
    # The same discipline setRegions() and nextTile() keep: bind the list once,
    # so a reader sees either the whole old set or the whole new one. A save
    # that re-read the attribute for its statistics would write a file whose
    # regions and whose coverage figure describe two different slices.
    s = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    later = RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)
    s.setRegions([_SwapsRegionsWhileBeingSaved(s, []), later])
    _cover(s, (1.2e-3, 1.1e-3))

    s.saveState()

    written = slice_dir["regions.yaml"].read()
    state = slice_dir["search_state.yaml"].read()
    assert len(written) == 2, "the region after the edited one was dropped mid-save"
    assert state["survey"]["percent_covered"] > 0, (
        "the statistics were computed from a different region list than the one saved"
    )


# ---- loading back ----


def _recorded_slice(dirHandle):
    """A saved slice whose first five tiles have records on disk, the way
    CellProducer writes them."""
    s = _saved_slice(dirHandle)
    tiles = dirHandle.getDir("tiles", create=True)
    for i, record in enumerate(s.survey.tiles()):
        writeRecord(tiles, f"tile_{i:03d}_detections.yaml", {**record.header, "detections": []})
    s.saveState()
    return s


def test_load_state_restores_regions_constraints_and_coverage(slice_dir):
    saved = _recorded_slice(slice_dir)

    restored = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    assert restored.loadState() is True

    assert restored.regions == saved.regions
    assert restored.constraints == saved.constraints
    assert saved.surveyStats()[0] == 5
    assert restored.surveyStats() == saved.surveyStats()
    assert restored.nextTile() == saved.nextTile()
    assert restored.nextTile() not in _coveredTiles(saved)


def test_load_state_restores_the_cells_already_attempted(slice_dir):
    _recorded_slice(slice_dir)
    tiles = slice_dir["tiles"]
    center = tiles["tile_000_detections.yaml"].read()["tile_center"]
    worked = {"candidate_id": "worked", "position": [center[0], center[1], 0.0], "score": 0.9}
    writeRecord(tiles, "tile_000_detections.yaml", {"tile_center": center, "detections": [worked]})
    slice_dir.mkdir("cell_000", info={"dirType": "Cell", "candidate_id": "worked", "disposition": "patched"})

    restored = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    restored.loadState()

    [cell] = restored.survey.handedOut()
    assert cell.candidate_id == "worked"
    assert cell.disposition == "patched"
    assert cell.cell_dir.name() == slice_dir["cell_000"].name()


def test_load_state_reports_a_directory_holding_only_survey_records(slice_dir):
    writeRecord(slice_dir.getDir("tiles", create=True), "tile_000_detections.yaml",
                {"tile_center": [0.0, 0.0], "detections": []})
    assert Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir).loadState() is True


def test_load_state_restores_the_overlap_the_tiles_were_planned_at(slice_dir):
    # The overlap is part of how the tiles on disk were imaged, so it is read
    # back rather than reset to a fresh slice's.
    saved = _saved_slice(slice_dir)
    saved.saveState()

    restored = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
    restored.loadState()

    assert restored._overlap == saved._overlap == 7e-6


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


def test_a_record_from_before_spacing_loads_the_default_spacing(slice_dir, caplog):
    _saved_slice(slice_dir).saveState()
    state = slice_dir["search_state.yaml"].read()
    del state["constraints"]["min_cell_spacing"]
    state["constraints"]["max_cell_density"] = 3e12
    slice_dir.writeFile(state, "search_state.yaml", fileType="YamlFile")

    with caplog.at_level("INFO"):
        restored = Slice(fov=(100e-6, 50e-6), dirHandle=slice_dir)
        restored.loadState()

    assert restored.constraints.min_cell_spacing == SearchConstraints().min_cell_spacing
    assert "max_cell_density of 3000000000000.0; ignoring it" in caplog.text
    assert f"min_cell_spacing of {SearchConstraints().min_cell_spacing}" in caplog.text


class _At:
    def __init__(self, position):
        self.position = position


def test_cells_within_measures_3d_distance():
    s = make_slice()
    near = _At((0.0, 0.0, -30e-6))
    deeper = _At((0.0, 0.0, -60e-6))
    _hand_out(s, [near, deeper])
    found = s.cellsWithin((1e-6, 0.0, -30e-6), 10e-6)
    assert [tuple(c.position) for c in found] == [tuple(near.position)]


def test_cells_within_excludes_a_cell_exactly_at_the_radius():
    s = make_slice()
    _hand_out(s, [_At((10e-6, 0.0, 0.0))])
    assert s.cellsWithin((0.0, 0.0, 0.0), 10e-6) == []


def test_a_field_is_covered_once_a_record_images_its_footprint():
    s = Slice(fov=(10e-6, 10e-6))
    s.addRegion(RectRegion(0, 0, 10e-6, 10e-6))
    tile = s.nextTile()
    assert s.surveyStats() == (0, 0.0)
    s.survey.addTile(_record(tile))
    assert s.nextTile() is None
    assert s.surveyStats() == (1, 100.0)


def test_a_wider_fov_record_covers_every_field_under_it():
    s = Slice(fov=(10e-6, 10e-6))
    s.addRegion(RectRegion(0, 0, 25e-6, 25e-6))
    s.survey.addTile(_record((12.5e-6, 12.5e-6), fov=(40e-6, 40e-6)))
    assert s.nextTile() is None
    assert s.surveyStats()[1] == 100.0


def test_reset_coverage_supersedes_every_record():
    s = Slice(fov=(10e-6, 10e-6))
    s.addRegion(RectRegion(0, 0, 10e-6, 10e-6))
    s.survey.addTile(_record(s.nextTile()))
    s.resetCoverage()
    assert s.nextTile() is not None
    assert all(r.superseded for r in s.survey.tiles())


def test_force_rescan_supersedes_only_records_in_the_regions_at_the_position():
    s = Slice(fov=(10e-6, 10e-6))
    s.addRegion(RectRegion(0, 0, 10e-6, 10e-6))
    s.addRegion(RectRegion(100e-6, 0, 110e-6, 10e-6))
    s.survey.addTile(_record((5e-6, 5e-6)))
    s.survey.addTile(_record((105e-6, 5e-6)))
    assert s.forceRescan((5e-6, 5e-6, 0.0), isAttempted=lambda c: True) == 1
    assert [r.superseded for r in s.survey.tiles()] == [True, False]


def test_old_search_state_coverage_is_ignored_with_a_log_line(tmp_path, caplog):
    sliceDir = dm.getDirHandle(str(tmp_path)).mkdir("slice")
    s = Slice(fov=(10e-6, 10e-6), dirHandle=sliceDir)
    s.saveState()
    state = sliceDir["search_state.yaml"].read()
    assert "covered" not in state
    state["covered"] = [[5e-6, 5e-6]]
    sliceDir.writeFile(state, "search_state.yaml", fileType="YamlFile")
    fresh = Slice(fov=(10e-6, 10e-6), dirHandle=sliceDir)
    with caplog.at_level("INFO"):
        fresh.loadState()
    assert fresh.survey.tiles() == ()
    assert "covered" in caplog.text


def test_setting_dir_handle_after_construction_moves_where_manual_cells_are_written(
    tmp_path,
):
    s = Slice(fov=(10e-6, 10e-6))
    sliceDir = dm.getDirHandle(str(tmp_path)).mkdir("slice")
    s.dirHandle = sliceDir
    s.survey.addManual((1e-6, 2e-6, 3e-6))
    assert sliceDir.exists("survey_manual.yaml")


# ---- pinned frames in a snapshot ----


def _frameArray(value=0):
    import numpy as np
    from MetaArray import MetaArray

    image = np.full((3, 4), value, dtype=np.uint16)
    return MetaArray(image, info=[{"name": "X"}, {"name": "Y"}, {"zValue": value}])


def _frameFiles(dirHandle):
    from acq4.experiment.slice import PINNED_FRAMES_DIR

    return sorted(dirHandle.getDir(PINNED_FRAMES_DIR).ls())


def test_a_snapshot_writes_one_file_per_pinned_frame(slice_dir):
    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": [_frameArray(1), _frameArray(2)]})

    assert _frameFiles(slice_dir) == ["frame_000.ma", "frame_001.ma"]


def test_a_shorter_pinned_set_deletes_the_frames_beyond_it(slice_dir):
    from MetaArray import MetaArray

    from acq4.experiment.slice import PINNED_FRAMES_DIR

    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": [_frameArray(1), _frameArray(2)]})
    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": [_frameArray(7)]})

    assert _frameFiles(slice_dir) == ["frame_000.ma"]
    back = MetaArray(file=slice_dir.getDir(PINNED_FRAMES_DIR)["frame_000.ma"].name())
    assert back.infoCopy()[-1]["zValue"] == 7


def test_an_empty_pinned_set_deletes_every_frame_but_keeps_the_directory(slice_dir):
    from acq4.experiment.slice import PINNED_FRAMES_DIR

    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": [_frameArray(1)]})
    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": []})

    assert slice_dir.exists(PINNED_FRAMES_DIR)
    assert _frameFiles(slice_dir) == []


def test_an_empty_pinned_set_creates_no_directory(slice_dir):
    from acq4.experiment.slice import PINNED_FRAMES_DIR

    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": []})

    assert not slice_dir.exists(PINNED_FRAMES_DIR)


def test_a_snapshot_without_pinned_frames_leaves_the_archive_alone(slice_dir):
    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": [_frameArray(1)]})
    s = _saved_slice(slice_dir)

    Slice.writeSnapshot(s.snapshotState())

    assert _frameFiles(slice_dir) == ["frame_000.ma"]


def test_a_pinned_frames_only_snapshot_writes_no_search_state(slice_dir):
    from acq4.experiment.slice import REGIONS_FILE, SEARCH_STATE_FILE

    Slice.writeSnapshot({"dirHandle": slice_dir, "pinnedFrames": [_frameArray(1)]})

    assert not slice_dir.exists(REGIONS_FILE)
    assert not slice_dir.exists(SEARCH_STATE_FILE)


def test_a_failed_pinned_frames_write_is_logged_and_the_state_still_lands(
    slice_dir, caplog
):
    from acq4.experiment.slice import PINNED_FRAMES_DIR, SEARCH_STATE_FILE

    # A plain file where the archive directory belongs, so creating it fails.
    with open(slice_dir.name() + "/" + PINNED_FRAMES_DIR, "w") as fh:
        fh.write("in the way")
    snapshot = _saved_slice(slice_dir).snapshotState()
    snapshot["pinnedFrames"] = [_frameArray(1)]

    with caplog.at_level("ERROR"):
        Slice.writeSnapshot(snapshot)

    assert "pinned frames" in caplog.text
    assert slice_dir.exists(SEARCH_STATE_FILE)


# ---- the exposure-aware field sampler ----

SAMPLER_FOV = (100e-6, 50e-6)
SAMPLER_REGION = RectRegion(0.0, 0.0, 400e-6, 200e-6)


def _sampler_slice(seed=7, **kwargs):
    s = Slice(fov=SAMPLER_FOV, sampler_seed=seed, **kwargs)
    s.addRegion(SAMPLER_REGION)
    return s


def _survey_to_exhaustion(s, limit=200):
    """Image whatever nextTile() offers until it offers nothing; returns the centres."""
    tiles = []
    while len(tiles) < limit:
        tile = s.nextTile()
        if tile is None:
            return tiles
        _cover(s, tile)
        tiles.append(tile)
    raise AssertionError(f"still being offered tiles after {limit}")


def test_exposure_constraints_default_to_the_issue_values():
    c = SearchConstraints()
    assert c.exposure_sigma == 50e-6
    assert c.exposure_tau == 300.0
    assert c.exposure_threshold == 0.1
    assert c.min_region_fraction == 0.8
    assert c.max_resurvey == 0.25


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exposure_sigma": 0.0},
        {"exposure_sigma": -1e-6},
        {"exposure_tau": 0.0},
        {"exposure_tau": -5.0},
        {"exposure_threshold": -0.1},
        {"min_region_fraction": -0.1},
        {"min_region_fraction": 1.1},
        {"max_resurvey": -0.1},
        {"max_resurvey": 1.1},
    ],
)
def test_exposure_constraints_reject_nonsense(kwargs):
    with pytest.raises(ValueError):
        SearchConstraints(**kwargs)


def test_next_tile_is_a_field_that_is_mostly_region():
    s = _sampler_slice()
    x, y = s.nextTile()
    fw, fh = SAMPLER_FOV
    inside = (
        max(0.0, min(x + fw / 2, 400e-6) - max(x - fw / 2, 0.0))
        * max(0.0, min(y + fh / 2, 200e-6) - max(y - fh / 2, 0.0))
    )
    assert inside / (fw * fh) >= 0.8 - 1e-9


def test_next_tile_reports_without_marking():
    s = _sampler_slice()
    assert s.nextTile() == s.nextTile()


def test_a_survey_ends_with_none_once_the_region_is_imaged():
    s = _sampler_slice()
    tiles = _survey_to_exhaustion(s)
    assert len(tiles) >= 8
    assert s.nextTile() is None
    assert s.surveyStats()[1] > 70.0


def test_the_same_seed_and_coverage_choose_the_same_field():
    assert _sampler_slice(seed=3).nextTile() == _sampler_slice(seed=3).nextTile()
    picks = {_sampler_slice(seed=n).nextTile() for n in range(8)}
    assert len(picks) > 1


def test_a_slice_without_a_seed_draws_a_fresh_one():
    seeds = {Slice(fov=SAMPLER_FOV).sampler_seed for _ in range(4)}
    assert len(seeds) > 1


def test_record_insertion_is_kept_as_an_immutable_tuple():
    s = _sampler_slice()
    assert s.insertions == ()
    before = s.insertions
    s.recordInsertion((1e-4, 2e-4), 1000.0)
    assert s.insertions == ((1e-4, 2e-4, 1000.0),)
    assert before == (), "the tuple a reader already holds must not change under it"
    assert isinstance(s.insertions, tuple)


def test_a_fresh_insertion_steers_the_next_field_away_from_it():
    import time

    from acq4.experiment.survey_planner import field_exposure

    s = _sampler_slice()
    first = s.nextTile()
    s.recordInsertion(first, time.time())
    second = s.nextTile()
    c = s.constraints
    assert field_exposure(
        [second], SAMPLER_FOV, s.insertions, time.time(), c.exposure_sigma, c.exposure_tau
    )[0] < c.exposure_threshold


def test_a_stale_insertion_no_longer_matters():
    s = _sampler_slice()
    expected = s.nextTile()
    s.recordInsertion(expected, 0.0)
    assert s.nextTile() == expected


def test_survey_stats_are_fields_imaged_and_percent_of_region_area():
    s = _sampler_slice()
    assert s.surveyStats() == (0, 0.0)
    s.survey.addTile(_record((50e-6, 100e-6)))
    fields, percent = s.surveyStats()
    assert fields == 1
    # one 100x50 field wholly inside a 400x200 region: 5000 of 80000 um^2
    assert percent == pytest.approx(100 * 5000 / 80000, abs=1.0)


def test_survey_stats_count_live_footprints_only():
    s = _sampler_slice()
    s.survey.addTile(_record((50e-6, 100e-6)))
    s.survey.addTile(_record((150e-6, 100e-6)))
    s.resetCoverage()
    assert s.surveyStats() == (0, 0.0)


def test_a_slice_with_no_regions_reports_no_area():
    s = make_slice()
    s.survey.addTile(_record((0.0, 0.0)))
    assert s.surveyStats() == (1, 0.0)


def test_a_region_past_the_pixel_cap_is_refused():
    from acq4.experiment.survey_planner import MAX_MASK_PIXELS

    s = Slice(fov=SAMPLER_FOV)
    with pytest.raises(RegionTooLarge, match="0.5"):
        s.setRegions([RectRegion(0.0, 0.0, 0.5, 0.5)])
    assert s.regions == []
    assert MAX_MASK_PIXELS == 4_000_000


def test_the_sampler_state_round_trips_through_the_record(slice_dir):
    saved = Slice(
        fov=SAMPLER_FOV,
        sampler_seed=1234,
        dirHandle=slice_dir,
        constraints=SearchConstraints(
            exposure_sigma=40e-6,
            exposure_tau=120.0,
            exposure_threshold=0.2,
            min_region_fraction=0.7,
            max_resurvey=0.1,
        ),
    )
    saved.addRegion(SAMPLER_REGION)
    saved.recordInsertion((1e-4, 2e-4), 1000.5)
    saved.recordInsertion((3e-4, 1e-4), 1002.5)
    saved.saveState()

    state = slice_dir["search_state.yaml"].read()
    assert state["sampler_seed"] == 1234
    assert state["insertions"] == [[1e-4, 2e-4, 1000.5], [3e-4, 1e-4, 1002.5]]
    assert state["survey"] == {"fields_imaged": 0, "percent_covered": 0.0}

    restored = Slice(fov=SAMPLER_FOV, dirHandle=slice_dir)
    assert restored.loadState() is True
    assert restored.sampler_seed == 1234
    assert restored.insertions == ((1e-4, 2e-4, 1000.5), (3e-4, 1e-4, 1002.5))
    assert restored.constraints == saved.constraints


def test_a_resumed_slice_continues_the_same_sequence(slice_dir):
    saved = Slice(fov=SAMPLER_FOV, sampler_seed=99, dirHandle=slice_dir)
    saved.addRegion(SAMPLER_REGION)
    saved.saveState()
    restored = Slice(fov=SAMPLER_FOV, dirHandle=slice_dir)
    restored.loadState()
    assert restored.nextTile() == saved.nextTile()


def test_a_record_written_before_the_sampler_still_loads(slice_dir):
    saved = Slice(fov=SAMPLER_FOV, dirHandle=slice_dir)
    saved.addRegion(SAMPLER_REGION)
    saved.saveState()
    state = slice_dir["search_state.yaml"].read()
    for key in ("sampler_seed", "insertions"):
        del state[key]
    for key in (
        "exposure_sigma",
        "exposure_tau",
        "exposure_threshold",
        "min_region_fraction",
        "max_resurvey",
    ):
        del state["constraints"][key]
    state["survey"] = {"total_tiles": 9, "covered_tiles": 3, "percent_covered": 33.0}
    slice_dir.writeFile(state, "search_state.yaml", fileType="YamlFile")

    restored = Slice(fov=SAMPLER_FOV, dirHandle=slice_dir)
    assert restored.loadState() is True

    assert restored.constraints == SearchConstraints()
    assert restored.insertions == ()
    assert isinstance(restored.sampler_seed, int)
    assert restored.nextTile() is not None
