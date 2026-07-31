"""Tests for the tile detector's orchestration: the depth arithmetic it derives
from each tile's surface, focus restoration, stop handling, and cell construction."""

import pytest

from acq4.experiment import tile_detector
from acq4.experiment.slice import SearchConstraints
from acq4.util.task import Stopped


class FakeScope:
    def __init__(self, surface=0.0):
        self.surface = surface
        self.moves = []

    def setGlobalPosition(self, pos, speed="fast", name=None):
        self.moves.append(tuple(pos))
        return FakeFuture()

    def findSurfaceDepth(self, imager):
        return self.surface


class FakeFuture:
    def wait(self, **kwargs):
        return None


class FakeCamera:
    def __init__(self, focus=-1e-3):
        self._focus = focus
        self.focusSets = []

    def name(self):
        return "FakeCamera"

    def getFocusDepth(self):
        return self._focus

    def setFocusDepth(self, z, speed="fast", name=None):
        self.focusSets.append(z)
        return FakeFuture()

    def getPixelSize(self):
        return (0.32e-6, 0.32e-6)


class FakeCell:
    """Stand-in for acq4_automation's Cell; `trackerFails` makes tracker init raise."""

    trackerFails = False

    def __init__(self, position):
        self.position = position
        self.score = None
        self.trackerInits = 0

    def initializeTrackerFromStack(self, camera, stack, use_cellpose=False):
        self.trackerInits += 1
        if self.trackerFails:
            raise ValueError("cell too close to the stack edge")


@pytest.fixture
def rig(monkeypatch):
    """A detector wired to fake devices, with the device-touching helpers replaced.

    Returns a namespace carrying the camera, the scope, the recorded _acquire
    arguments, and the detector callable itself.
    """
    camera = FakeCamera()
    scope = FakeScope(surface=-500e-6)
    acquireCalls = []
    detectCalls = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        acquireCalls.append((start_z, stop_z, step_z))
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, max_candidates):
        detectCalls.append(
            (stack, xy_scale, z_scale, models, min_volume_m3, max_candidates)
        )
        return [((1e-6, 2e-6, -530e-6), 0.8)]

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    detect = tile_detector.make_tile_detector(camera=camera, scope=scope, manager=None)

    class Rig:
        pass

    rig = Rig()
    rig.camera = camera
    rig.scope = scope
    rig.acquireCalls = acquireCalls
    rig.detectCalls = detectCalls
    rig.detect = detect
    return rig


def test_the_stack_spans_the_constrained_range_below_this_tiles_surface(rig):
    # The whole reason depth is expressed as offsets from the surface: the slab
    # follows the tissue, so a tile whose surface is at -500 um must be searched
    # 20-60 um below THAT, not below zero.
    rig.detect((0.0, 0.0), SearchConstraints(depth_range=(-20e-6, -60e-6)))

    start_z, stop_z, step_z = rig.acquireCalls[0]
    assert start_z == pytest.approx(-520e-6)
    assert stop_z == pytest.approx(-560e-6)
    assert step_z == pytest.approx(1e-6)


def test_the_depth_range_is_read_from_the_constraints_it_is_given(rig):
    # Not from a value captured when the detector was built: the operator may
    # edit the range between runs, and the slice hands its current constraints
    # to every call.
    rig.detect((0.0, 0.0), SearchConstraints(depth_range=(-5e-6, -15e-6)))

    start_z, stop_z, _ = rig.acquireCalls[0]
    assert start_z == pytest.approx(-505e-6)
    assert stop_z == pytest.approx(-515e-6)


def test_the_stage_moves_to_the_tile_before_the_surface_is_found(rig):
    # Surface is per tile, so searching for it before arriving would measure the
    # previous tile's tissue.
    rig.detect((3e-6, 4e-6), SearchConstraints())
    assert rig.scope.moves == [(3e-6, 4e-6)]


def test_focus_is_restored_after_a_successful_survey(rig):
    before = rig.camera.getFocusDepth()
    rig.detect((0.0, 0.0), SearchConstraints())
    assert rig.camera.focusSets[-1] == pytest.approx(before)


def test_focus_is_restored_when_acquisition_raises(rig, monkeypatch):
    # A survey that dies mid-stack must not leave the objective parked deep in
    # the tissue for whatever runs next.
    before = rig.camera.getFocusDepth()

    def boom(cam, start_z, stop_z, step_z):
        raise RuntimeError("camera died")

    monkeypatch.setattr(tile_detector, "_acquire", boom)

    with pytest.raises(RuntimeError, match="camera died"):
        rig.detect((0.0, 0.0), SearchConstraints())

    assert rig.camera.focusSets[-1] == pytest.approx(before)


def test_a_stop_prevents_the_survey_from_imaging(rig, monkeypatch):
    # Imaging a tile is slow, so a stop must be honoured before the stack starts,
    # not only after it finishes.
    def stopNow():
        raise Stopped("stopped by operator")

    monkeypatch.setattr(tile_detector, "check_stop", stopNow)

    with pytest.raises(Stopped):
        rig.detect((0.0, 0.0), SearchConstraints())

    assert rig.acquireCalls == []
    assert rig.scope.moves == []


def test_detected_cells_carry_their_health_score(rig):
    cells = rig.detect((0.0, 0.0), SearchConstraints())
    assert len(cells) == 1
    assert cells[0].score == pytest.approx(0.8)
    assert cells[0].position == (1e-6, 2e-6, -530e-6)


def test_tracking_is_seeded_from_the_stack_the_cell_was_found_in(rig):
    cells = rig.detect((0.0, 0.0), SearchConstraints())
    assert cells[0].trackerInits == 1


def test_a_cell_whose_tracker_cannot_be_seeded_is_still_returned(rig, monkeypatch):
    # A cell too close to the stack edge cannot be extracted, but it is a real
    # detection: discarding it would silently drop cells at every tile boundary.
    monkeypatch.setattr(FakeCell, "trackerFails", True)

    cells = rig.detect((0.0, 0.0), SearchConstraints())

    assert len(cells) == 1
    assert cells[0].score == pytest.approx(0.8)


def test_the_pixel_size_and_step_reach_detection(rig):
    rig.detect((0.0, 0.0), SearchConstraints())
    stack, xy_scale, z_scale, _models, _min_volume, _n = rig.detectCalls[0]
    assert stack == ["frame"]
    assert xy_scale == pytest.approx(0.32e-6)
    assert z_scale == pytest.approx(1e-6)


def test_min_volume_and_max_candidates_reach_detection(monkeypatch):
    # make_tile_detector's own min_volume_m3/max_candidates parameters must
    # reach _detect unchanged, not get dropped or swapped with each other.
    # Non-default values on both sides so a hard-coded default is caught.
    camera = FakeCamera()
    scope = FakeScope(surface=-500e-6)
    detectCalls = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, max_candidates):
        detectCalls.append((min_volume_m3, max_candidates))
        return []

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    detect = tile_detector.make_tile_detector(
        camera=camera,
        scope=scope,
        manager=None,
        min_volume_m3=123e-18,
        max_candidates=7,
    )
    detect((0.0, 0.0), SearchConstraints())

    min_volume_m3, max_candidates = detectCalls[0]
    assert min_volume_m3 == pytest.approx(123e-18)
    assert max_candidates == 7


class FakeManager:
    def __init__(self, misc):
        self.config = {"misc": misc}


def test_health_models_come_from_the_misc_config():
    models = tile_detector._health_models(
        FakeManager({"segmenterPath": "/seg.pt", "classifierPath": "/cls.pt"})
    )
    assert models["segmenter"] == "/seg.pt"
    assert models["classifier"] == "/cls.pt"
    assert models["autoencoder"] is None
    assert models["resnet_classifier"] is None


def test_health_models_without_a_manager_are_all_unset():
    # A headless or partially-configured rig must not raise here; detect_neurons
    # accepts None for every model.
    assert set(tile_detector._health_models(None).values()) == {None}
