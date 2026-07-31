"""Tests for CellProducer: walking a slice's tiles, the []-versus-None
exhaustion contract, and the search constraints it filters candidates against."""

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
