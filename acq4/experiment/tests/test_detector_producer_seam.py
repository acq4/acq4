"""Integration test for the detector <-> producer seam: a real Slice, a real
CellProducer, and a real make_tile_detector callable driven end to end against
fake devices, with only the three device-touching helpers replaced."""

import pytest

from acq4.experiment import tile_detector
from acq4.experiment.slice import SearchConstraints, Slice

from .test_tile_detector import FakeCamera, FakeCell, FakeScope

# 100x80 um tiles over a 300x80 um region: exactly three tiles in one row, and
# non-square so a swapped axis cannot pass by coincidence.
FOV = (100e-6, 80e-6)
REGION = (0.0, 0.0, 300e-6, 80e-6)
TILE_COUNT = 3
# Deliberately nowhere near zero: with the surface at 0 the signed depth offsets
# would look the same as their own negation, so a sign error in the arithmetic
# between the constraints and _acquire would not show up.
SURFACE = -500e-6
NEAR, FAR = -20e-6, -60e-6


@pytest.fixture
def seam(monkeypatch):
    """A real Slice/CellProducer/tile detector chain over fake devices.

    Only `_acquire`, `_detect`, and `_newCell` -- the three helpers that reach a
    real camera, the detection models, and acq4_automation's Cell -- are
    replaced. The stage moves, the surface search, the depth arithmetic, the tile
    walk, the coverage bookkeeping, and the constraint filtering are all the
    genuine articles, which is the point: each half of this chain has its own
    unit tests, and this is what proves they fit together.
    """
    camera = FakeCamera()
    scope = FakeScope(camera, surface=SURFACE)
    acquireCalls = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        acquireCalls.append((start_z, stop_z, step_z))
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, max_candidates):
        # One candidate per tile, positioned in the tile the stage is parked
        # over. A real detection is a position inside the field just imaged, and
        # the density cap is a per-tile locality check, so a candidate has to
        # land in its own tile for the chain to behave as it does on a rig.
        cx, cy = scope.moves[-1]
        return [((cx, cy, SURFACE + (NEAR + FAR) / 2), 0.8)]

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    def build(constraints=None):
        if constraints is None:
            constraints = SearchConstraints(depth_range=(NEAR, FAR))
        sliceState = Slice(fov=FOV, constraints=constraints)
        sliceState.addRegion(*REGION)
        return sliceState, sliceState.makeCellProducer(
            tile_detector.make_tile_detector(camera=camera, scope=scope, manager=None)
        )

    class Seam:
        pass

    seam = Seam()
    seam.camera = camera
    seam.scope = scope
    seam.acquireCalls = acquireCalls
    seam.build = build
    return seam


def test_the_chain_produces_cells_from_the_tile_it_imaged(seam):
    sliceState, producer = seam.build()

    tile = sliceState.nextTile()
    cells = producer()

    assert len(cells) == 1
    cell = cells[0]
    assert cell.score == pytest.approx(0.8)
    assert cell.position[:2] == pytest.approx(tile)
    # The stage actually went there, and the cells reached the slice's own
    # register (which is what the density cap reads).
    assert seam.scope.moves == [tile]
    assert sliceState.cellsNearTile(tile) == [cell]


def test_the_depth_range_reaching_acquisition_is_measured_from_this_tiles_surface(seam):
    _sliceState, producer = seam.build()

    producer()

    start_z, stop_z, _step_z = seam.acquireCalls[0]
    assert start_z == pytest.approx(SURFACE + NEAR)
    assert stop_z == pytest.approx(SURFACE + FAR)
    # Shallow first, then deeper: the stack is acquired travelling into the
    # tissue, and a swapped pair would drive the objective to the far bound
    # before imaging anything.
    assert start_z > stop_z


def test_coverage_advances_one_tile_per_call_until_the_producer_is_exhausted(seam):
    sliceState, producer = seam.build()

    imagedTiles = []
    for expected in range(1, TILE_COUNT + 1):
        imagedTiles.append(sliceState.nextTile())
        assert producer() is not None
        assert len(sliceState.coveredTiles) == expected
        assert sliceState.surveyStats() == (
            TILE_COUNT,
            expected,
            pytest.approx(100.0 * expected / TILE_COUNT),
        )

    # Every tile a distinct one, imaged exactly once.
    assert len(set(imagedTiles)) == TILE_COUNT
    assert seam.scope.moves == imagedTiles
    assert len(seam.acquireCalls) == TILE_COUNT

    assert producer() is None, "a fully covered slice must report exhaustion"
    assert len(seam.acquireCalls) == TILE_COUNT, "and image nothing more"


def test_the_health_cutoff_filters_what_the_real_detector_chain_returns(seam):
    # The scored candidates come out of _detect, are wrapped into cells by
    # tile_detector, and are filtered by CellProducer against the slice's
    # constraints -- three separate objects, so a cutoff that reached none of
    # them would still look fine in each one's own unit tests.
    sliceState, producer = seam.build(
        constraints=SearchConstraints(depth_range=(NEAR, FAR), min_health=0.9)
    )

    result = producer()

    assert result == [], "a 0.8-scoring candidate must not clear a 0.9 cutoff"
    # Still a covered tile, and still not exhaustion: the tile was imaged.
    assert len(sliceState.coveredTiles) == 1
    assert result is not None
