"""Tests for CellProducer: handing out one survey cell per call, imaging a tile
only when none is left, the []-versus-None exhaustion contract, and the search
constraints (health cutoff, density cap, and rescan policy) it filters against."""

import logging
import math
from datetime import datetime
from uuid import uuid4

import pytest

import acq4.experiment.survey as survey_module
import acq4.experiment.survey_record as survey_record
import acq4.util.DataManager as dm
from acq4.experiment.cell_producer import MAX_TILE_CANDIDATES, CellProducer
from acq4.experiment.search_region import RectRegion
from acq4.experiment.slice import SearchConstraints, Slice
from acq4.experiment.survey_record import TileDetections
from acq4.util.task import Stopped


class _PlainCell:
    def __init__(self, position):
        self.position = position


@pytest.fixture(autouse=True)
def plain_cells(monkeypatch):
    monkeypatch.setattr(survey_module, "_newCell", _PlainCell)


FOV = (10e-6, 10e-6)

# Most tests here pack candidates nanometres apart to exercise the other
# filters; a spacing this small keeps the spacing rule out of their way.
UNSPACED = 1e-12


class FakeCandidate:
    """Stand-in for a detected cell: a global position and a health score."""

    def __init__(self, position, score=1.0):
        self.position = position
        self.score = score

    def __repr__(self):
        return f"FakeCandidate({self.position}, score={self.score})"


class RecordingDetector:
    """A detector seam that returns scripted results and records its calls.

    `results` maps nothing -- it is consumed in order, one entry per call, each
    entry being the list of candidates that call returns. Running past the end
    returns an empty list (a barren tile), which is the common real case.
    """

    def __init__(self, results=()):
        self._results = list(results)
        self.calls = []

    def __call__(self, center, constraints):
        self.calls.append((tuple(center), constraints))
        return self._results.pop(0) if self._results else []


def make_slice(
    constraints=SearchConstraints(min_cell_spacing=UNSPACED),
    regions=(RectRegion(0, 0, 30e-6, 30e-6),),
):
    s = Slice(fov=FOV, constraints=constraints)
    for r in regions:
        s.addRegion(r)
    return s


def drain(producer, limit=50):
    """Every cell the producer hands out until it reports exhaustion."""
    cells = []
    for _ in range(limit):
        batch = producer()
        if batch is None:
            return cells
        assert len(batch) <= 1
        cells.extend(batch)
    raise AssertionError("producer never reported exhaustion")


def positions(cells):
    return [tuple(c.position) for c in cells]


def hand_out(s, position):
    """A cell already handed out of the slice's survey at `position`."""
    return s.survey.handOut({"candidate_id": uuid4().hex, "position": position, "source": "survey"})


def test_a_call_images_one_tile_and_hands_out_its_best_cell():
    det = RecordingDetector([[FakeCandidate((1e-6, 1e-6, 0), 0.5), FakeCandidate((2e-6, 1e-6, 0), 0.9)]])
    s = make_slice()
    p = CellProducer(s, det)
    first = p()
    assert len(det.calls) == 1
    assert [c.position[0] for c in first] == [2e-6]
    second = p()
    assert len(det.calls) == 1, "the imaged tile's next cell needs no new imaging"
    assert [c.position[0] for c in second] == [1e-6]


def test_the_detector_is_asked_for_the_slices_next_tile():
    s = make_slice()
    tile = s.nextTile()
    detector = RecordingDetector()
    CellProducer(s, detector)()
    assert detector.calls[0][0] == tile


def test_the_imaged_tile_is_covered_so_the_next_call_advances():
    s = make_slice()
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    producer()
    producer()

    assert detector.calls[0][0] != detector.calls[1][0]
    assert len(s.survey.tiles()) == 2


def test_a_barren_tile_returns_empty_not_none():
    p = CellProducer(make_slice(), RecordingDetector([[]]))
    assert p() == []


def test_none_only_once_every_tile_is_imaged_and_nothing_is_left():
    s = make_slice()
    p = CellProducer(s, RecordingDetector())
    results = [p() for _ in range(len(s.tileGrid()) + 1)]
    assert results[:-1] == [[]] * len(s.tileGrid())
    assert results[-1] is None


def test_without_a_detector_manual_entries_are_handed_out_then_none():
    s = make_slice()
    m = s.survey.addManual((1.0, 1.0, 0.0))
    p = CellProducer(s, None)
    [cell] = p()
    assert cell.candidate_id == m["candidate_id"]
    assert cell.source == "manual"
    assert p() is None


def test_manual_entries_are_handed_out_before_any_tile_is_imaged():
    det = RecordingDetector([[FakeCandidate((1e-6, 1e-6, 0))]])
    s = make_slice()
    s.survey.addManual((5.0, 5.0, 0.0))
    p = CellProducer(s, det)
    assert p()[0].source == "manual"
    assert det.calls == []


def test_each_imaged_tile_is_recorded_on_the_survey_with_the_slice_fov():
    s = make_slice()
    p = CellProducer(s, RecordingDetector([[FakeCandidate((1e-6, 1e-6, 0))]]))
    p()
    [record] = s.survey.tiles()
    assert record.header["fov"] == list(FOV)
    assert record.detections[0]["disposition"] == "queued"
    assert record.detections[0]["candidate_id"]


def test_a_slice_with_no_regions_is_exhausted_immediately():
    s = Slice(fov=FOV)
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    assert producer() is None
    assert detector.calls == [], "nothing to image, so the detector must not run"


def test_the_detector_receives_the_slices_current_constraints():
    # Constraints must be read from the slice at call time, not captured once
    # when the producer is built: an operator editing a search constraint
    # mid-experiment has to take effect on the very next tile, or the edit is
    # silently ignored.
    first = SearchConstraints(min_health=0.0, depth_range=(-5e-6, -25e-6), min_cell_spacing=UNSPACED)
    s = make_slice(constraints=first)
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    producer()
    assert detector.calls[0][1] is first

    other = SearchConstraints(min_health=0.9, depth_range=(-5e-6, -25e-6), min_cell_spacing=UNSPACED)
    s.setConstraints(other)
    producer()
    assert detector.calls[1][1] is other


def test_a_detector_failure_records_the_tile_as_failed_and_raises():
    class Boom(RecordingDetector):
        def __call__(self, center, constraints):
            raise RuntimeError("camera fell off")

    s = make_slice()
    p = CellProducer(s, Boom())
    with pytest.raises(RuntimeError):
        p()
    [record] = s.survey.tiles()
    assert record.header["failed"] == "camera fell off"
    assert s.isCovered(tuple(record.header["tile_center"]))


def test_a_stop_mid_tile_records_nothing_and_leaves_the_tile_uncovered():
    class Stopping(RecordingDetector):
        def __call__(self, center, constraints):
            raise Stopped()

    s = make_slice()
    tile = s.nextTile()
    with pytest.raises(Stopped):
        CellProducer(s, Stopping())()
    assert s.survey.tiles() == ()
    assert s.nextTile() == tile


def test_a_tile_abandoned_by_a_stop_is_re_imaged_by_a_later_producer():
    # The slice and its coverage outlive individual runs, so the proof that
    # matters is the next run's producer -- a fresh CellProducer over the same
    # persistent slice -- actually returning to the abandoned tile, not merely
    # that coverage looked right in the moment.
    s = make_slice()
    tile = s.nextTile()

    def stopping(center, constraints):
        raise Stopped("operator pressed stop mid-tile")

    with pytest.raises(Stopped):
        s.makeCellProducer(stopping)()

    detector = RecordingDetector()
    s.makeCellProducer(detector)()

    assert detector.calls[0][0] == tile
    assert s.isCovered(tile)


def test_a_stopped_tile_is_not_counted_as_surveyed():
    # A region whose every tile but one was imaged, with that one abandoned by a
    # stop, must not read as 100% surveyed: the readout is what tells the
    # operator whether the tissue has actually been looked at.
    s = make_slice(regions=(RectRegion(0, 0, 20e-6, 10e-6),))  # exactly two tiles

    def stopAtTheSecondTile(center, constraints):
        if len(s.survey.tiles()) == 1:
            raise Stopped("operator pressed stop mid-tile")
        return []

    producer = CellProducer(s, stopAtTheSecondTile)
    assert producer() == []
    with pytest.raises(Stopped):
        producer()

    total, covered, percent = s.surveyStats()
    assert (total, covered) == (2, 1)
    assert percent == pytest.approx(50.0)


def test_a_populated_tile_returns_a_concrete_list_not_a_lazy_iterator():
    # The orchestrator's error handling wraps only the producer call, not the
    # iteration of whatever it returns: a generator that raised partway through
    # iteration would escape unwrapped and crash the run in a way nothing
    # handles. __call__ must hand back an already-realized list. The detector
    # here actually returns a generator, so recording the tile and then
    # returning from it both have to work from the same run of the underlying
    # iterator -- proof that nothing was consumed out from under the caller.
    s = make_slice()
    tile = s.nextTile()
    cell = FakeCandidate((tile[0], tile[1], -30e-6))

    def detector(center, constraints):
        return (c for c in [cell])

    producer = CellProducer(s, detector)
    result = producer()
    assert type(result) is list
    assert positions(result) == [cell.position]


def test_a_barren_tile_also_returns_a_concrete_list():
    s = make_slice()
    producer = CellProducer(s, RecordingDetector([[]]))
    result = producer()
    assert type(result) is list


def test_candidates_below_the_health_cutoff_are_not_handed_out():
    s = make_slice(constraints=SearchConstraints(min_health=0.6, min_cell_spacing=UNSPACED))
    tile = s.nextTile()
    good = FakeCandidate((tile[0], tile[1], -30e-6), score=0.9)
    bad = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6), score=0.3)
    producer = CellProducer(s, RecordingDetector([[good, bad]]))

    assert positions(drain(producer)) == [good.position]


def test_a_candidate_exactly_at_the_cutoff_is_kept():
    s = make_slice(constraints=SearchConstraints(min_health=0.6, min_cell_spacing=UNSPACED))
    tile = s.nextTile()
    borderline = FakeCandidate((tile[0], tile[1], -30e-6), score=0.6)
    assert positions(drain(CellProducer(s, RecordingDetector([[borderline]])))) == [borderline.position]


def test_a_tile_whose_every_candidate_is_rejected_returns_empty_not_none():
    # Filtering everything out is still "made progress on a tile"; reporting it
    # as exhaustion would end the run.
    s = make_slice(constraints=SearchConstraints(min_health=0.9, min_cell_spacing=UNSPACED))
    tile = s.nextTile()
    weak = FakeCandidate((tile[0], tile[1], -30e-6), score=0.1)
    producer = CellProducer(s, RecordingDetector([[weak]]))
    result = producer()
    assert result == []
    assert result is not None


def test_rejected_candidates_are_not_handed_out():
    s = make_slice(constraints=SearchConstraints(min_health=0.9, min_cell_spacing=UNSPACED))
    tile = s.nextTile()
    weak = FakeCandidate((tile[0], tile[1], -30e-6), score=0.1)
    drain(CellProducer(s, RecordingDetector([[weak]])))
    assert s.survey.handedOut() == []
    assert s.cellsNearTile(tile) == []


def test_a_candidate_without_a_score_passes_the_cutoff():
    # "Add from target" cells and any detector that does not score its output
    # must not be silently discarded by a nonzero cutoff.
    s = make_slice(constraints=SearchConstraints(min_health=0.9, min_cell_spacing=UNSPACED))
    tile = s.nextTile()
    unscored = FakeCandidate((tile[0], tile[1], -30e-6))
    unscored.score = None
    assert positions(drain(CellProducer(s, RecordingDetector([[unscored]])))) == [unscored.position]


def test_a_candidate_with_no_score_attribute_at_all_passes_the_cutoff():
    # The real detector's candidates never carry a `score` attribute until
    # someone assigns one after the fact, so an unscored candidate is missing
    # the attribute entirely, not merely holding it as None. Either shape must
    # be treated as unscored rather than raising or being rejected.
    s = make_slice(constraints=SearchConstraints(min_health=0.9, min_cell_spacing=UNSPACED))
    tile = s.nextTile()
    unscored = FakeCandidate((tile[0], tile[1], -30e-6))
    del unscored.score
    assert positions(drain(CellProducer(s, RecordingDetector([[unscored]])))) == [unscored.position]


def _crowding_constraints(cells_per_tile):
    """Constraints whose derived density cap is `cells_per_tile` in one tile.

    The volume goes through the same `z_span()` `Slice.tileVolume()` uses. The cap
    itself goes through a cube root to become a spacing and back, which is not
    exact, so tests pick cell counts clear of the cap rather than on it.
    """
    depth_range = (-20e-6, -60e-6)
    volume = 10e-6 * 10e-6 * SearchConstraints(depth_range=depth_range).z_span()
    density = cells_per_tile / volume
    return SearchConstraints(
        depth_range=depth_range,
        min_health=0.0,
        min_cell_spacing=(3.0 / (4.0 * math.pi * density)) ** (1.0 / 3.0),
    )


def test_a_crowded_tile_is_recorded_as_skipped_without_imaging():
    s = make_slice(constraints=_crowding_constraints(1))
    tile = s.nextTile()
    s.survey.addManual((tile[0], tile[1], 0.0))
    p = CellProducer(s, RecordingDetector())
    p()                     # hands out the manual entry, which now crowds the tile
    p()
    skipped = [r for r in s.survey.tiles() if r.header.get("skipped") == "crowded"]
    assert skipped and tuple(skipped[0].header["tile_center"]) == tuple(tile)


def test_a_tile_already_at_the_density_cap_is_skipped_without_imaging():
    s = make_slice(constraints=_crowding_constraints(1.5), regions=(RectRegion(0, 0, 10e-6, 10e-6),))
    tile = s.nextTile()
    hand_out(s, (tile[0], tile[1], -30e-6))
    hand_out(s, (tile[0] + 1e-6, tile[1], -30e-6))
    detector = RecordingDetector([[FakeCandidate((tile[0], tile[1], -30e-6))]])
    producer = CellProducer(s, detector)

    assert producer() is None, "the only tile is crowded, so nothing is left"
    assert detector.calls == [], "a crowded tile must not be imaged at all"
    assert s.uncoveredTiles() == [], "and it must not be handed out again"


def test_a_tile_below_the_density_cap_is_imaged_normally():
    # Two tiles so a crowd elsewhere in the slice can be told apart from a
    # crowd in the tile under test: the cap is a per-tile locality check, not
    # a slice-wide cell budget, and cells piling up in one tile must not make
    # every other tile in the slice look crowded too.
    s = make_slice(
        constraints=_crowding_constraints(2), regions=(RectRegion(0, 0, 20e-6, 10e-6),)
    )
    tile = s.nextTile()
    other_tile = (tile[0] + 10e-6, tile[1])
    hand_out(s, (tile[0], tile[1], -30e-6))
    hand_out(s, (other_tile[0], other_tile[1], -30e-6))
    hand_out(s, (other_tile[0] + 1e-6, other_tile[1], -30e-6))
    found = FakeCandidate((tile[0] + 4e-6, tile[1] + 4e-6, -40e-6))
    detector = RecordingDetector([[found]])

    assert positions(CellProducer(s, detector)()) == [found.position]
    assert len(detector.calls) == 1


def test_without_rescans_exhaustion_is_final():
    s = make_slice(
        regions=(RectRegion(0, 0, 10e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=False, min_cell_spacing=UNSPACED),
    )
    producer = CellProducer(s, RecordingDetector())
    producer()
    assert s.uncoveredTiles() == []
    assert producer() is None
    assert producer() is None


def test_rescans_allowed_grants_exactly_one_more_pass():
    # Unlimited rescanning could never return None, which would wedge the run
    # loop; one extra pass makes the switch mean something and keeps the
    # contract. See CellProducer's docstring.
    s = make_slice(
        regions=(RectRegion(0, 0, 10e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=True, min_cell_spacing=UNSPACED),
    )
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    assert producer() == []  # first pass images the only tile
    assert producer() == []  # rescan re-images it
    assert producer() is None  # and then it really is exhausted
    assert len(detector.calls) == 2


def test_a_second_producer_from_the_same_slice_gets_its_own_rescan_allowance():
    # The allowance is per-producer, matching _producerExhausted's per-run
    # lifetime, so a later run over the same slice may rescan again.
    s = make_slice(
        regions=(RectRegion(0, 0, 10e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=True, min_cell_spacing=UNSPACED),
    )
    first = s.makeCellProducer(RecordingDetector())
    first()
    first()
    assert first() is None

    second = s.makeCellProducer(RecordingDetector())
    assert second() == []
    assert second() is None


def test_rescan_pass_re_walks_every_tile_not_just_one():
    # The single-tile rescan tests above can't tell a re-walk of the whole
    # slice apart from a single lucky tile being handed out twice. A
    # multi-tile region closes that gap: the rescan pass must hand out the
    # same number of tiles as the first pass before it, too, is exhausted.
    s = make_slice(
        regions=(RectRegion(0, 0, 20e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=True, min_cell_spacing=UNSPACED),
    )
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    assert producer() == []
    assert producer() == []
    assert len(detector.calls) == 2, "first pass should walk both tiles"
    assert s.uncoveredTiles() == []

    assert producer() == []
    assert producer() == []
    assert len(detector.calls) == 4, "rescan pass should walk both tiles again"

    assert producer() is None
    assert len(detector.calls) == 4


# ---- the region filter and the candidate cap ----


def test_candidates_outside_the_slices_regions_are_not_handed_out():
    # The camera images past the outline deliberately -- a field straddling the
    # edge is what gives the segmenter the context to find cells sitting right
    # at it -- so a border tile routinely detects cells in tissue the operator
    # did not outline. Patching those is patching outside the drawn region.
    s = make_slice(regions=(RectRegion(0, 0, 25e-6, 25e-6),))
    tile = s.nextTile()
    inside = FakeCandidate((tile[0], tile[1], -30e-6))
    outside = FakeCandidate((-2e-6, 12.5e-6, -30e-6))
    assert s.containsPoint(outside.position) is False, "premise: this one is outside"

    producer = CellProducer(s, RecordingDetector([[inside, outside]]))
    assert positions(drain(producer)) == [inside.position]


def test_an_out_of_region_candidate_does_not_count_toward_the_density_cap():
    # A cell that is never handed out was never a target, so counting it toward
    # the crowding of the tile it was found near would spend the density budget
    # on tissue the survey will not patch.
    s = make_slice(regions=(RectRegion(0, 0, 25e-6, 25e-6),))
    tile = s.nextTile()
    outside = FakeCandidate((-2e-6, 12.5e-6, -30e-6))
    drain(CellProducer(s, RecordingDetector([[outside]])))
    assert s.cellsNearTile(tile) == []


def test_the_region_filter_follows_the_slices_current_regions():
    # Regions are read per tile rather than captured when the producer is built,
    # for the same reason the constraints are: an operator who redraws the
    # outline mid-experiment has to have that take effect on the very next tile.
    # (A slice with no regions at all cannot reach this filter -- it has no
    # tiles, so the producer reports exhaustion first. That case is the
    # hand-seeded run, and it is pinned on Slice.containsPoint itself.)
    s = make_slice(regions=(RectRegion(0, 0, 25e-6, 25e-6),))
    cell = FakeCandidate((12.5e-6, 12.5e-6, -30e-6))
    producer = CellProducer(s, RecordingDetector([[cell], [cell]]))

    assert positions(producer()) == [cell.position]

    s.setRegions([RectRegion(1e-3, 1e-3, 1e-3 + 25e-6, 1e-3 + 25e-6)])
    assert producer() == []


def test_out_of_region_candidates_do_not_eat_the_candidate_quota():
    # The reason the cap is applied here rather than inside the detector.
    # Detections arrive best-first and untruncated; truncating first would let a
    # border tile fill the whole quota with cells outside the region while
    # usable ones sat just below the cut, and the tile would come back empty.
    s = make_slice(regions=(RectRegion(0, 0, 25e-6, 25e-6),))
    tile = s.nextTile()
    outside = [
        FakeCandidate((-2e-6, 12.5e-6 + i * 1e-9, -30e-6))
        for i in range(MAX_TILE_CANDIDATES)
    ]
    inside = [
        FakeCandidate((tile[0] + i * 1e-9, tile[1], -30e-6)) for i in range(3)
    ]
    producer = CellProducer(s, RecordingDetector([outside + inside]))
    assert positions(drain(producer)) == [c.position for c in inside]


def test_unhealthy_candidates_do_not_eat_the_candidate_quota_either():
    # The health cutoff is the same shape of filter as the region test and has
    # to happen on the same side of the cap.
    s = make_slice(constraints=SearchConstraints(min_health=0.6, min_cell_spacing=UNSPACED))
    tile = s.nextTile()
    sick = [
        FakeCandidate((tile[0], tile[1] + i * 1e-9, -30e-6), score=0.1)
        for i in range(MAX_TILE_CANDIDATES)
    ]
    healthy = [
        FakeCandidate((tile[0] + i * 1e-9, tile[1], -30e-6), score=0.9)
        for i in range(2)
    ]
    producer = CellProducer(s, RecordingDetector([sick + healthy]))
    assert positions(drain(producer)) == [c.position for c in healthy]


def test_only_the_best_few_surviving_candidates_are_handed_out_from_one_tile():
    # The cap is still a cap: a tile densely packed with good cells contributes
    # a handful of targets, not all of them, so the survey keeps moving.
    # Detections arrive best-first, so the survivors kept are the leading ones.
    s = make_slice()
    tile = s.nextTile()
    many = [
        FakeCandidate((tile[0] + i * 1e-9, tile[1], -30e-6))
        for i in range(MAX_TILE_CANDIDATES + 4)
    ]
    producer = CellProducer(s, RecordingDetector([many]))
    assert positions(drain(producer)) == [c.position for c in many[:MAX_TILE_CANDIDATES]]


def test_the_candidate_cap_is_adjustable_per_producer():
    s = make_slice()
    tile = s.nextTile()
    many = [
        FakeCandidate((tile[0] + i * 1e-9, tile[1], -30e-6)) for i in range(6)
    ]
    producer = CellProducer(s, RecordingDetector([many]), max_candidates=2)
    assert positions(drain(producer)) == [c.position for c in many[:2]]


def test_only_the_handed_out_cells_count_toward_the_density_cap():
    # Cells cut by the cap are not targets, and counting them would let one
    # crowded tile's discards close its neighbours off.
    s = make_slice()
    tile = s.nextTile()
    many = [
        FakeCandidate((tile[0] + i * 1e-9, tile[1], -30e-6))
        for i in range(MAX_TILE_CANDIDATES + 4)
    ]
    drain(CellProducer(s, RecordingDetector([many])))
    assert positions(s.cellsNearTile(tile)) == [c.position for c in many[:MAX_TILE_CANDIDATES]]


def test_the_cap_still_spreads_hand_outs_across_tiles():
    many = [FakeCandidate((i * 1e-6, 1e-6, 0), 0.9 - i * 0.01) for i in range(MAX_TILE_CANDIDATES + 2)]
    det = RecordingDetector([many, [FakeCandidate((15e-6, 1e-6, 0))]])
    s = make_slice()
    cells = drain(CellProducer(s, det))
    assert len(det.calls) >= 2
    assert sum(1 for c in cells if c.position[1] == 1e-6 and c.position[0] < 10e-6) == MAX_TILE_CANDIDATES


def _spaced(spacing=3e-6):
    return SearchConstraints(min_health=0.0, min_cell_spacing=spacing)


def test_a_candidate_near_an_already_handed_out_cell_is_not_handed_out():
    s = make_slice(constraints=_spaced())
    tile = s.nextTile()
    hand_out(s, (tile[0], tile[1], -30e-6))
    near = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6))
    assert drain(CellProducer(s, RecordingDetector([[near]]))) == []


def test_spacing_is_measured_in_3d():
    s = make_slice(constraints=_spaced())
    tile = s.nextTile()
    hand_out(s, (tile[0], tile[1], -30e-6))
    below = FakeCandidate((tile[0], tile[1], -40e-6))
    assert positions(drain(CellProducer(s, RecordingDetector([[below]])))) == [below.position]


def test_a_candidate_just_outside_the_spacing_is_handed_out():
    s = make_slice(constraints=_spaced())
    tile = s.nextTile()
    hand_out(s, (tile[0], tile[1], -30e-6))
    clear = FakeCandidate((tile[0] + 3.03e-6, tile[1], -30e-6))
    assert positions(drain(CellProducer(s, RecordingDetector([[clear]])))) == [clear.position]


def test_of_two_close_candidates_in_one_tile_the_better_is_kept():
    s = make_slice(constraints=_spaced())
    tile = s.nextTile()
    best = FakeCandidate((tile[0], tile[1], -30e-6), score=0.9)
    worse = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6), score=0.8)
    assert positions(drain(CellProducer(s, RecordingDetector([[best, worse]])))) == [best.position]


def test_duplicates_do_not_eat_the_candidate_quota():
    s = make_slice(constraints=_spaced())
    tile = s.nextTile()
    hand_out(s, (tile[0], tile[1], -30e-6))
    dupes = [FakeCandidate((tile[0] + i * 1e-8, tile[1], -30e-6)) for i in range(MAX_TILE_CANDIDATES)]
    fresh = [FakeCandidate((tile[0], tile[1], -40e-6 - i * 4e-6)) for i in range(MAX_TILE_CANDIDATES)]
    producer = CellProducer(s, RecordingDetector([dupes + fresh]))
    assert positions(drain(producer)) == [c.position for c in fresh]


def test_every_candidate_gets_a_disposition_in_detection_order():
    s = make_slice(constraints=SearchConstraints(min_health=0.5, min_cell_spacing=3e-6))
    tile = s.nextTile()
    queued = FakeCandidate((tile[0], tile[1], -30e-6), score=0.9)
    close = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6), score=0.8)
    sick = FakeCandidate((tile[0], tile[1], -45e-6), score=0.1)
    outside = FakeCandidate((-50e-6, -50e-6, -30e-6), score=0.9)
    spare = FakeCandidate((tile[0], tile[1], -55e-6), score=0.7)
    producer = CellProducer(s, RecordingDetector(), max_candidates=1)

    candidates = [queued, close, sick, outside, spare]
    entries = producer._triage(candidates, s.constraints)

    assert [(e["position"], e["disposition"]) for e in entries] == [
        (list(queued.position), "queued"),
        (list(close.position), "too_close"),
        (list(sick.position), "unhealthy"),
        (list(outside.position), "out_of_region"),
        (list(spare.position), "over_cap"),
    ]


def test_a_tiles_survey_record_lists_every_candidate_with_its_disposition():
    s = make_slice(constraints=SearchConstraints(min_health=0.5, min_cell_spacing=3e-6))
    tile = s.nextTile()
    queued = FakeCandidate((tile[0], tile[1], -30e-6), score=0.9)
    close = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6), score=0.8)
    sick = FakeCandidate((tile[0], tile[1], -45e-6), score=0.1)

    CellProducer(s, RecordingDetector([[queued, close, sick]]))()

    detections = s.survey.tiles()[0].detections
    assert [d["disposition"] for d in detections] == ["queued", "too_close", "unhealthy"]


def test_a_tiles_record_file_lists_every_candidate_with_its_disposition(tmp_path):
    out = dm.getDirHandle(str(tmp_path), create=True)
    s = make_slice(constraints=SearchConstraints(min_health=0.5, min_cell_spacing=3e-6))
    tile = s.nextTile()
    queued = FakeCandidate((tile[0], tile[1], -30e-6), score=0.9)
    close = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6), score=0.8)
    sick = FakeCandidate((tile[0], tile[1], -45e-6), score=0.1)
    detections = TileDetections([queued, close, sick], {"tile_id": "t1"}, out, "tile_x_detections.yaml")

    assert positions(CellProducer(s, RecordingDetector([detections]))()) == [queued.position]

    record = out["tile_x_detections.yaml"].read()
    assert record["tile_id"] == "t1"
    assert [d["disposition"] for d in record["detections"]] == ["queued", "too_close", "unhealthy"]


def test_slice_and_producer_are_freed_by_refcounting_alone():
    """No cycle between a slice and the producers it makes.

    Both outlive individual runs and neither is a QObject, so they must be
    reclaimable without the cyclic collector. A graph only gc can break is
    collected non-deterministically and possibly off the GUI thread, which is
    how this module reaches a hard crash on application exit.
    """
    import gc
    import weakref

    s = Slice(fov=FOV)
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    producer = s.makeCellProducer(RecordingDetector())
    producer()

    slice_ref = weakref.ref(s)
    producer_ref = weakref.ref(producer)

    gc.disable()
    try:
        del producer
        assert producer_ref() is None, "producer survived; a cycle holds it"
        del s
        assert slice_ref() is None, "slice survived; a cycle holds it"
    finally:
        gc.enable()


def test_an_unconvertible_detection_is_logged_and_dropped_but_the_tile_is_recorded(caplog):
    s = make_slice()
    good = FakeCandidate((1e-6, 1e-6, 0), 0.9)
    bad = FakeCandidate((2e-6, 1e-6, 0), "not a number")
    short = FakeCandidate((3e-6, 1e-6), 0.8)
    p = CellProducer(s, RecordingDetector([[good, bad, short]]))
    with caplog.at_level(logging.ERROR):
        cells = p()
    assert caplog.text.count("Dropping a detection") == 2
    assert positions(cells) == [good.position]
    [record] = s.survey.tiles()
    assert [d["position"] for d in record.detections] == [[1e-6, 1e-6, 0.0]]
    assert s.isCovered(tuple(record.header["tile_center"]))

    spaced = make_slice(constraints=SearchConstraints(min_cell_spacing=5e-6))
    unrecordable = FakeCandidate((1e-6, 1e-6, 0), 0.95)
    unrecordable.volume = "not a number"
    nearby = FakeCandidate((2e-6, 1e-6, 0), 0.9)
    p = CellProducer(spaced, RecordingDetector([[unrecordable, nearby]]))
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        cells = p()
    assert caplog.text.count("Dropping a detection") == 1
    assert positions(cells) == [nearby.position]
    [record] = spaced.survey.tiles()
    assert [d["disposition"] for d in record.detections] == ["queued"]


def test_an_error_from_the_region_check_is_not_taken_for_a_bad_detection(monkeypatch):
    s = make_slice()

    def broken(position):
        raise RuntimeError("region check broke")

    monkeypatch.setattr(s, "containsPoint", broken)
    p = CellProducer(s, RecordingDetector([[FakeCandidate((1e-6, 1e-6, 0), 0.9)]]))
    with pytest.raises(RuntimeError, match="region check broke"):
        p()


def _sliceWithDir(tmp_path, **kwargs):
    d = dm.getDirHandle(str(tmp_path)).mkdir("slice")
    s = Slice(fov=FOV, constraints=SearchConstraints(min_cell_spacing=UNSPACED), dirHandle=d, **kwargs)
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    return s, d


def _records(d):
    tiles = d.getDir("tiles")
    return [tiles[n].read() for n in sorted(tiles.ls()) if n.endswith("_detections.yaml")]


def test_two_skips_in_one_call_write_two_distinct_record_files(tmp_path, monkeypatch):
    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 18, 10, 11, 12, 131415)

    monkeypatch.setattr(survey_record, "datetime", FrozenClock)
    s, d = _sliceWithDir(tmp_path)
    s.setConstraints(_crowding_constraints(1))
    for tile in s.tileGrid()[:2]:
        s.survey.handOut(
            {"candidate_id": uuid4().hex, "position": (tile[0], tile[1], -30e-6), "source": "survey"}
        )
    CellProducer(s, RecordingDetector())()
    names = [n for n in d.getDir("tiles").ls() if n.endswith("_detections.yaml")]
    assert len(names) >= 2 and len(set(names)) == len(names)


def test_a_skipped_tile_leaves_a_record_file_marked_crowded(tmp_path):
    s, d = _sliceWithDir(tmp_path)
    s.setConstraints(_crowding_constraints(1))
    tile = s.nextTile()
    s.survey.handOut({"candidate_id": uuid4().hex, "position": (tile[0], tile[1], -30e-6), "source": "survey"})
    CellProducer(s, RecordingDetector())()
    assert "crowded" in [r.get("skipped") for r in _records(d)]


def test_a_failed_tile_leaves_a_record_file_with_the_message(tmp_path):
    s, d = _sliceWithDir(tmp_path)

    def boom(center, constraints):
        raise RuntimeError("camera fell off")

    with pytest.raises(RuntimeError):
        CellProducer(s, boom)()
    [record] = _records(d)
    assert record["failed"] == "camera fell off"
