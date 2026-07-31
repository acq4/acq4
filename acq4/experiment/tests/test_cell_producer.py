"""Tests for CellProducer: walking a slice's tiles, the []-versus-None
exhaustion contract, and the search constraints (health cutoff, density cap,
and rescan policy) it filters candidates and tiles against."""

import pytest

from acq4.experiment.cell_producer import CellProducer
from acq4.experiment.slice import SearchConstraints, Slice

FOV = (10e-6, 10e-6)


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


def make_slice(constraints=None, regions=((0, 0, 30e-6, 30e-6),)):
    s = Slice(fov=FOV, constraints=constraints)
    for r in regions:
        s.addRegion(*r)
    return s


def test_a_call_images_one_tile_and_returns_its_cells():
    s = make_slice()
    tile = s.nextTile()
    cell = FakeCandidate((tile[0], tile[1], -30e-6))
    detector = RecordingDetector([[cell]])
    producer = CellProducer(s, detector)

    assert producer() == [cell]
    assert detector.calls[0][0] == tile


def test_the_imaged_tile_is_marked_covered_so_the_next_call_advances():
    s = make_slice()
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    producer()
    producer()

    assert detector.calls[0][0] != detector.calls[1][0]
    assert len(s.coveredTiles) == 2


def test_a_barren_tile_returns_empty_not_none():
    # [] is "made progress, found nothing here, ask again"; None would end the
    # whole run on the first empty field of view.
    s = make_slice()
    producer = CellProducer(s, RecordingDetector([[]]))
    result = producer()
    assert result == []
    assert result is not None


def test_none_only_once_every_tile_is_imaged():
    s = make_slice(regions=((0, 0, 10e-6, 10e-6),))  # exactly one tile
    producer = CellProducer(s, RecordingDetector())

    assert producer() == []
    assert producer() is None


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
    first = SearchConstraints(min_health=0.0, depth_range=(-5e-6, -25e-6))
    s = make_slice(constraints=first)
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    producer()
    assert detector.calls[0][1] is first

    other = SearchConstraints(min_health=0.9, depth_range=(-5e-6, -25e-6))
    s.setConstraints(other)
    producer()
    assert detector.calls[1][1] is other


def test_found_cells_are_registered_with_the_slice():
    s = make_slice()
    tile = s.nextTile()
    cell = FakeCandidate((tile[0], tile[1], -30e-6))
    CellProducer(s, RecordingDetector([[cell]]))()
    assert s.cellsNearTile(tile) == [cell]


def test_a_detector_failure_marks_the_tile_covered_rather_than_retrying_it_forever():
    # A tile that raises must not be handed out again on the next call: the
    # orchestrator wraps a producer exception into AbortExperiment, but a
    # producer used across runs would otherwise wedge on the same bad tile.
    s = make_slice()
    tile = s.nextTile()

    def exploding(center, constraints):
        raise RuntimeError("imaging failed")

    producer = CellProducer(s, exploding)
    with pytest.raises(RuntimeError, match="imaging failed"):
        producer()
    assert tile in s.coveredTiles


def test_a_populated_tile_returns_a_concrete_list_not_a_lazy_iterator():
    # The orchestrator's error handling wraps only the producer call, not the
    # iteration of whatever it returns: a generator that raised partway through
    # iteration would escape unwrapped and crash the run in a way nothing
    # handles. __call__ must hand back an already-realized list. The detector
    # here actually returns a generator, so registering the cells with the
    # slice and then returning them both have to work from the same run of
    # the underlying iterator -- proof that nothing was consumed out from
    # under the caller.
    s = make_slice()
    tile = s.nextTile()
    cell = FakeCandidate((tile[0], tile[1], -30e-6))

    def detector(center, constraints):
        return (c for c in [cell])

    producer = CellProducer(s, detector)
    result = producer()
    assert type(result) is list
    assert result == [cell]
    assert s.cellsNearTile(tile) == [cell]


def test_a_barren_tile_also_returns_a_concrete_list():
    s = make_slice()
    producer = CellProducer(s, RecordingDetector([[]]))
    result = producer()
    assert type(result) is list


def test_candidates_below_the_health_cutoff_are_not_queued():
    s = make_slice(constraints=SearchConstraints(min_health=0.6))
    tile = s.nextTile()
    good = FakeCandidate((tile[0], tile[1], -30e-6), score=0.9)
    bad = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6), score=0.3)
    producer = CellProducer(s, RecordingDetector([[good, bad]]))

    assert producer() == [good]


def test_a_candidate_exactly_at_the_cutoff_is_kept():
    s = make_slice(constraints=SearchConstraints(min_health=0.6))
    tile = s.nextTile()
    borderline = FakeCandidate((tile[0], tile[1], -30e-6), score=0.6)
    assert CellProducer(s, RecordingDetector([[borderline]]))() == [borderline]


def test_a_tile_whose_every_candidate_is_rejected_returns_empty_not_none():
    # Filtering everything out is still "made progress on a tile"; reporting it
    # as exhaustion would end the run.
    s = make_slice(constraints=SearchConstraints(min_health=0.9))
    tile = s.nextTile()
    weak = FakeCandidate((tile[0], tile[1], -30e-6), score=0.1)
    producer = CellProducer(s, RecordingDetector([[weak]]))
    result = producer()
    assert result == []
    assert result is not None


def test_rejected_candidates_are_not_registered_with_the_slice():
    s = make_slice(constraints=SearchConstraints(min_health=0.9))
    tile = s.nextTile()
    weak = FakeCandidate((tile[0], tile[1], -30e-6), score=0.1)
    CellProducer(s, RecordingDetector([[weak]]))()
    assert s.cellsNearTile(tile) == []


def test_a_candidate_without_a_score_passes_the_cutoff():
    # "Add from target" cells and any detector that does not score its output
    # must not be silently discarded by a nonzero cutoff.
    s = make_slice(constraints=SearchConstraints(min_health=0.9))
    tile = s.nextTile()
    unscored = FakeCandidate((tile[0], tile[1], -30e-6))
    unscored.score = None
    assert CellProducer(s, RecordingDetector([[unscored]]))() == [unscored]


def test_a_candidate_with_no_score_attribute_at_all_passes_the_cutoff():
    # The real detector's candidates never carry a `score` attribute until
    # someone assigns one after the fact, so an unscored candidate is missing
    # the attribute entirely, not merely holding it as None. Either shape must
    # be treated as unscored rather than raising or being rejected.
    s = make_slice(constraints=SearchConstraints(min_health=0.9))
    tile = s.nextTile()
    unscored = FakeCandidate((tile[0], tile[1], -30e-6))
    del unscored.score
    assert CellProducer(s, RecordingDetector([[unscored]]))() == [unscored]


def _crowding_constraints(cells_per_tile):
    """Constraints whose density cap is reached by `cells_per_tile` in one tile.

    The volume is computed through the same `z_span()` used by
    `Slice.tileVolume()`, rather than a literal depth span, so the cap this
    produces lands on the same floating-point value the producer compares
    against: a literal `40e-6` is not bit-identical to `abs(-20e-6 - -60e-6)`,
    which would make an "exactly at the cap" test actually sit a hair above it.
    """
    depth_range = (-20e-6, -60e-6)
    volume = 10e-6 * 10e-6 * SearchConstraints(depth_range=depth_range).z_span()
    return SearchConstraints(
        depth_range=depth_range,
        min_health=0.0,
        max_cell_density=cells_per_tile / volume,
    )


def test_a_tile_already_at_the_density_cap_is_skipped_without_imaging():
    s = make_slice(constraints=_crowding_constraints(2))
    tile = s.nextTile()
    s.registerCells(
        [
            FakeCandidate((tile[0], tile[1], -30e-6)),
            FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6)),
        ]
    )
    detector = RecordingDetector([[FakeCandidate((tile[0], tile[1], -30e-6))]])
    producer = CellProducer(s, detector)

    assert producer() == []
    assert detector.calls == [], "a crowded tile must not be imaged at all"
    assert tile in s.coveredTiles, "and it must not be handed out again"


def test_a_tile_below_the_density_cap_is_imaged_normally():
    # Two tiles so a crowd elsewhere in the slice can be told apart from a
    # crowd in the tile under test: the cap is a per-tile locality check, not
    # a slice-wide cell budget, and cells piling up in one tile must not make
    # every other tile in the slice look crowded too.
    s = make_slice(
        constraints=_crowding_constraints(2), regions=((0, 0, 20e-6, 10e-6),)
    )
    tile = s.nextTile()
    other_tile = (tile[0] + 10e-6, tile[1])
    s.registerCells([FakeCandidate((tile[0], tile[1], -30e-6))])
    s.registerCells(
        [
            FakeCandidate((other_tile[0], other_tile[1], -30e-6)),
            FakeCandidate((other_tile[0] + 1e-6, other_tile[1], -30e-6)),
        ]
    )
    found = FakeCandidate((tile[0], tile[1], -35e-6))
    detector = RecordingDetector([[found]])

    assert CellProducer(s, detector)() == [found]
    assert len(detector.calls) == 1


def test_without_rescans_exhaustion_is_final():
    s = make_slice(
        regions=((0, 0, 10e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=False),
    )
    producer = CellProducer(s, RecordingDetector())
    producer()
    assert producer() is None
    assert producer() is None


def test_rescans_allowed_grants_exactly_one_more_pass():
    # Unlimited rescanning could never return None, which would wedge the run
    # loop; one extra pass makes the switch mean something and keeps the
    # contract. See CellProducer's docstring.
    s = make_slice(
        regions=((0, 0, 10e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=True),
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
        regions=((0, 0, 10e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=True),
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
        regions=((0, 0, 20e-6, 10e-6),),
        constraints=SearchConstraints(rescans_allowed=True),
    )
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    assert producer() == []
    assert producer() == []
    assert len(detector.calls) == 2, "first pass should walk both tiles"

    assert producer() == []
    assert producer() == []
    assert len(detector.calls) == 4, "rescan pass should walk both tiles again"

    assert producer() is None
    assert len(detector.calls) == 4
