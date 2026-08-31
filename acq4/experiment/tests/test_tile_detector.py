"""Tests for the tile detector's orchestration: the depth arithmetic it derives
from each tile's surface, focus restoration, stop handling, cell construction,
and the tile imagery it persists under the slice's directory."""

import os

import pytest

import acq4.util.DataManager as dm
from acq4.experiment import tile_detector
from acq4.experiment.slice import SearchConstraints
from acq4.util.task import Stopped


class FakeScope:
    """`camera` is wired in so `findSurfaceDepth` can move the camera's focus to
    the surface it reports, the way `Microscope.findSurfaceDepth` ends with
    `setFocusDepth(depth, ...).wait()` on the real device. Without that, a
    focus-depth capture taken after the surface search would look identical to
    one taken before it, and the two are not interchangeable."""

    def __init__(self, camera, surface=0.0):
        self.camera = camera
        self.surface = surface
        self.moves = []
        # Ordered log of "move"/"move_waited"/"surface_search" events, so tests
        # can pin the sequence the survey performs them in, not just that each
        # one happened.
        self.events = []

    def setGlobalPosition(self, pos, speed="fast", name=None):
        self.moves.append(tuple(pos))
        self.events.append("move")
        return FakeFuture(self.events, "move_waited")

    def findSurfaceDepth(self, imager):
        self.events.append("surface_search")
        self.camera.setFocusDepth(self.surface, name="fake surface focus")
        return self.surface


class FakeFuture:
    def __init__(self, log=None, label=None):
        self.waited = False
        self._log = log
        self._label = label

    def wait(self, **kwargs):
        self.waited = True
        if self._log is not None:
            self._log.append(self._label)
        return None


class FakePipette:
    """Stands in for the manipulator the detector sends home before each tile.

    `goHome` returns a future the caller is expected to wait on, the way
    `Pipette.goHome` returns the motion planner's. Both the call and the wait are
    logged into the scope's own event list, so a test can pin that the tip is
    home *before* the objective moves rather than merely that both happened.
    """

    def __init__(self, events):
        self.homeCalls = []
        self.events = events

    def goHome(self, speed="fast", **kwds):
        self.homeCalls.append(speed)
        self.events.append("home")
        return FakeFuture(self.events, "home_waited")


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
        self._focus = z
        return FakeFuture()

    def getPixelSize(self):
        # Asymmetric so a test reading the wrong axis (index 1 instead of 0)
        # cannot pass by accident.
        return (0.32e-6, 0.5e-6)


class FakeCell:
    """Stand-in for acq4_automation's Cell; `trackerFails` makes tracker init raise."""

    trackerFails = False

    def __init__(self, position):
        self.position = position
        self.score = None
        self.trackerInits = 0
        self.trackerStack = None
        self.trackerUseCellpose = None
        self.trackerKwargs = {}

    def initializeTrackerFromStack(self, camera, stack, use_cellpose=False, **tracker_kwargs):
        # Mirror Cell.initializeTrackerFromStack's **tracker_kwargs passthrough so
        # callers can forward tracker settings without this double knowing each one.
        self.trackerInits += 1
        self.trackerStack = stack
        self.trackerUseCellpose = use_cellpose
        self.trackerKwargs = tracker_kwargs
        if self.trackerFails:
            raise ValueError("cell too close to the stack edge")


@pytest.fixture
def rig(monkeypatch):
    """A detector wired to fake devices, with the device-touching helpers replaced.

    No pipette, which is the case every test that is not about the home move
    wants: a survey on a rig with no pipette selected has to image exactly as
    well as one with a pipette to park out of the way.

    Returns a namespace carrying the camera, the scope, the recorded _acquire
    arguments, and the detector callable itself.
    """
    return _makeRig(monkeypatch)


@pytest.fixture
def homingRig(monkeypatch):
    """The same rig with a pipette for the detector to send home per tile."""
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    return _makeRig(monkeypatch, camera=camera, scope=scope, pipette=FakePipette(scope.events))


def _makeRig(monkeypatch, camera=None, scope=None, pipette=None, slice_dir=None):
    camera = FakeCamera() if camera is None else camera
    scope = FakeScope(camera, surface=-500e-6) if scope is None else scope
    acquireCalls = []
    detectCalls = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        acquireCalls.append((start_z, stop_z, step_z))
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix):
        detectCalls.append(
            (stack, xy_scale, z_scale, models, min_volume_m3, save_prefix)
        )
        return [((1e-6, 2e-6, -530e-6), 0.8, 1.5e-16)]

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    detect = tile_detector.make_tile_detector(
        camera=camera, scope=scope, manager=None, pipette=pipette, slice_dir=slice_dir
    )

    class Rig:
        pass

    rig = Rig()
    rig.camera = camera
    rig.scope = scope
    rig.pipette = pipette
    rig.acquireCalls = acquireCalls
    rig.detectCalls = detectCalls
    rig.sliceDir = slice_dir
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
    # to every call. Two calls on the SAME detector, so a detector that cached
    # the first call's constraints would give the second call the first call's
    # range instead of its own.
    rig.detect((0.0, 0.0), SearchConstraints(depth_range=(-20e-6, -60e-6)))
    rig.detect((0.0, 0.0), SearchConstraints(depth_range=(-5e-6, -15e-6)))

    start_z, stop_z, _ = rig.acquireCalls[1]
    assert start_z == pytest.approx(-505e-6)
    assert stop_z == pytest.approx(-515e-6)


def test_the_stage_moves_to_the_tile_before_the_surface_is_found(rig):
    # Surface is per tile, so searching for it before arriving would measure the
    # previous tile's tissue.
    rig.detect((3e-6, 4e-6), SearchConstraints())
    assert rig.scope.moves == [(3e-6, 4e-6)]
    assert rig.scope.events.index("move") < rig.scope.events.index("surface_search")


def test_the_stage_move_is_waited_on_before_the_surface_is_found(rig):
    # A future returned but never waited on means detection could run before
    # the stage has physically arrived at the tile.
    rig.detect((3e-6, 4e-6), SearchConstraints())
    assert rig.scope.events.index("move_waited") < rig.scope.events.index(
        "surface_search"
    )


def test_the_pipette_goes_home_before_the_objective_moves(homingRig):
    # The tip is parked wherever the last cell it worked was; the objective is
    # about to travel to another tile and image a stack through where it sits.
    homingRig.detect((3e-6, 4e-6), SearchConstraints())
    events = homingRig.scope.events
    assert events.index("home") < events.index("move")


def test_the_home_move_is_waited_on_before_the_objective_moves(homingRig):
    # A future returned but never waited on means the tile move starts while the
    # tip is still on its way out -- which is the whole hazard, not a smaller one.
    homingRig.detect((3e-6, 4e-6), SearchConstraints())
    events = homingRig.scope.events
    assert events.index("home_waited") < events.index("move")


def test_the_pipette_goes_home_for_every_tile(homingRig):
    # Not once per survey: a refill only happens once the queue has drained, so
    # the usual thing to have happened between two tiles is a cell being patched
    # and the tip left at that cell's target.
    homingRig.detect((0.0, 0.0), SearchConstraints())
    homingRig.detect((100e-6, 0.0), SearchConstraints())
    assert len(homingRig.pipette.homeCalls) == 2


def test_a_tile_is_surveyed_with_no_pipette_at_all(rig):
    # A run with no pipette selected is still allowed to survey; it simply has
    # nothing to move out of the way.
    cells = rig.detect((3e-6, 4e-6), SearchConstraints())
    assert rig.scope.moves == [(3e-6, 4e-6)]
    assert len(cells) == 1


@pytest.mark.parametrize("stop_at", [1, 2])
def test_a_stop_lands_before_and_after_the_home_move(homingRig, monkeypatch, stop_at):
    # The home move gets a guard on each side: the first check_stop() is the one
    # that keeps the tip where it is, and the second is what a Stop pressed
    # during the (slow) home move lands on, before the objective goes anywhere.
    calls = []

    def stopAtNth():
        calls.append(1)
        if len(calls) == stop_at:
            raise Stopped("stopped by operator")

    monkeypatch.setattr(tile_detector, "check_stop", stopAtNth)

    with pytest.raises(Stopped):
        homingRig.detect((0.0, 0.0), SearchConstraints())

    assert bool(homingRig.pipette.homeCalls) == (stop_at > 1)
    assert homingRig.scope.moves == []


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


@pytest.mark.parametrize("stop_at", [1, 2, 3, 4])
def test_a_stop_prevents_the_survey_from_imaging(rig, monkeypatch, stop_at):
    # Each of this rig's four check_stop() calls guards one slow step -- the
    # move, the surface search, the stack acquisition, and detection -- in that
    # order. Raising on only the Nth call proves that specific guard is doing
    # its job: every step from there on must not have run, regardless of
    # whether the guards before it fired. A rig with a pipette to send home has
    # a fifth, guarding that move; it is covered on its own fixture above, so
    # the numbering here stays the numbering of the imaging steps.
    calls = []

    def stopAtNth():
        calls.append(1)
        if len(calls) == stop_at:
            raise Stopped("stopped by operator")

    monkeypatch.setattr(tile_detector, "check_stop", stopAtNth)

    with pytest.raises(Stopped):
        rig.detect((0.0, 0.0), SearchConstraints())

    assert bool(rig.scope.moves) == (stop_at > 1)
    assert ("surface_search" in rig.scope.events) == (stop_at > 2)
    assert bool(rig.acquireCalls) == (stop_at > 3)
    assert rig.detectCalls == []


def test_detected_cells_carry_their_health_score(rig):
    cells = rig.detect((0.0, 0.0), SearchConstraints())
    assert len(cells) == 1
    assert cells[0].score == pytest.approx(0.8)
    assert cells[0].position == (1e-6, 2e-6, -530e-6)


def test_tracking_is_seeded_from_the_stack_the_cell_was_found_in(rig):
    cells = rig.detect((0.0, 0.0), SearchConstraints())
    assert cells[0].trackerInits == 1
    assert cells[0].trackerStack == ["frame"]
    assert cells[0].trackerUseCellpose is True


def test_a_cell_whose_tracker_cannot_be_seeded_is_still_returned(rig, monkeypatch):
    # A cell too close to the stack edge cannot be extracted, but it is a real
    # detection: discarding it would silently drop cells at every tile boundary.
    monkeypatch.setattr(FakeCell, "trackerFails", True)

    cells = rig.detect((0.0, 0.0), SearchConstraints())

    assert len(cells) == 1
    assert cells[0].score == pytest.approx(0.8)


def test_the_pixel_size_and_step_reach_detection(rig):
    rig.detect((0.0, 0.0), SearchConstraints())
    stack, xy_scale, z_scale, models, _min_volume, _prefix = rig.detectCalls[0]
    assert stack == ["frame"]
    assert xy_scale == pytest.approx(0.32e-6)
    assert z_scale == pytest.approx(1e-6)
    assert models == {
        "segmenter": None,
        "autoencoder": None,
        "classifier": None,
        "resnet_classifier": None,
    }


def test_min_volume_reaches_detection(monkeypatch):
    # make_tile_detector's own min_volume_m3 parameter must reach _detect
    # unchanged rather than being dropped. A non-default value, so a hard-coded
    # default is caught.
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    detectCalls = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix):
        detectCalls.append(min_volume_m3)
        return []

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    detect = tile_detector.make_tile_detector(
        camera=camera,
        scope=scope,
        manager=None,
        min_volume_m3=123e-18,
    )
    detect((0.0, 0.0), SearchConstraints())

    assert detectCalls[0] == pytest.approx(123e-18)


def test_detection_is_asked_for_every_cell_it_found(monkeypatch):
    # `n=None` is the whole of the truncate-before-filtering fix. detect_neurons
    # returns its cells best-first and `n` slices that list, so asking it for
    # the top few would spend the quota before CellProducer has dropped the
    # cells outside the region or below the health cutoff -- and a tile at a
    # region's edge, where the field of view straddles the outline on purpose,
    # is exactly where those discards cluster.
    pytest.importorskip(
        "acq4_automation",
        reason="needs acq4_automation's real object_detection module to monkeypatch",
    )
    from acq4_automation import object_detection

    calls = []

    def fakeDetectNeurons(stack, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(object_detection, "detect_neurons", fakeDetectNeurons)
    tile_detector._detect(
        ["frame"],
        xy_scale=0.5e-6,
        z_scale=1e-6,
        models={"segmenter": None},
        min_volume_m3=0.0,
        save_prefix=None,
    )

    assert calls[0]["n"] is None


def test_step_z_reaches_acquisition_and_detection(monkeypatch):
    # step_z must reach both _acquire and _detect unchanged. The default is
    # 1e-6, so a non-default value is required to catch a hard-coded 1e-6 in
    # either call site.
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    acquireCalls = []
    detectCalls = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        acquireCalls.append(step_z)
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix):
        detectCalls.append(z_scale)
        return []

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    detect = tile_detector.make_tile_detector(
        camera=camera, scope=scope, manager=None, step_z=3e-6
    )
    detect((0.0, 0.0), SearchConstraints())

    assert acquireCalls[0] == pytest.approx(3e-6)
    assert detectCalls[0] == pytest.approx(3e-6)


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


def test_the_tracker_segments_with_the_configured_model(monkeypatch):
    """Tracking has to use the same checkpoint detection does; on stock cpsam it
    finds no cells in a tracking crop at all."""
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    monkeypatch.setattr(tile_detector, "_acquire", lambda *a, **k: ["frame"])
    monkeypatch.setattr(
        tile_detector,
        "_detect",
        lambda *a, **k: [((1e-6, 2e-6, -530e-6), 0.8, 1.5e-16)],
    )
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)
    detect = tile_detector.make_tile_detector(
        camera=camera,
        scope=scope,
        manager=FakeManager({"segmenterPath": "/models/tuned"}),
    )

    cells = detect((0.0, 0.0), SearchConstraints())

    assert cells[0].trackerKwargs["segmenter"] == "/models/tuned"


def test_health_models_without_a_manager_are_all_unset():
    # A headless or partially-configured rig must not raise here; detect_neurons
    # accepts None for every model.
    assert set(tile_detector._health_models(None).values()) == {None}


# -- the tile's own imagery ----------------------------------------------


@pytest.fixture
def sliceDir(tmp_path):
    """A real managed directory standing in for the one `newSlice` creates.

    Real rather than a double because what these tests are about is what the
    Data Manager can see afterwards, and "is this file indexed" is a question
    only a genuine DirHandle answers.
    """
    return dm.getDirHandle(str(tmp_path / "slice"), create=True)


def _savingRig(monkeypatch, sliceDir, writes=("stack", "mask")):
    """A rig whose detection stand-in writes the files the real detector writes.

    `detect_neurons` hands `save_prefix` across an RPC to a subprocess that
    writes `{prefix}.ma` and `{prefix}_cellpose_masks.npy` by raw path, so a
    double that only records the prefix would never exercise the indexing that
    has to follow those writes. `writes` names which of the two to produce, so
    a test can stand for a detector whose save failed and was swallowed.
    """
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    prefixes = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix):
        prefixes.append(save_prefix)
        if save_prefix is not None:
            if "stack" in writes:
                with open(f"{save_prefix}.ma", "wb") as fh:
                    fh.write(b"detection stack")
            if "mask" in writes:
                with open(f"{save_prefix}_cellpose_masks.npy", "wb") as fh:
                    fh.write(b"cellpose masks")
        return [((1e-6, 2e-6, -530e-6), 0.8, 1.5e-16)]

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    detect = tile_detector.make_tile_detector(
        camera=camera, scope=scope, manager=None, slice_dir=sliceDir
    )

    class Rig:
        pass

    rig = Rig()
    rig.detect = detect
    rig.prefixes = prefixes
    rig.sliceDir = sliceDir
    return rig


def _tilesDir(sliceDir):
    return sliceDir.getDir("tiles")


def test_the_tile_stack_and_masks_are_saved_under_the_slice_directory(
    monkeypatch, sliceDir
):
    # The whole point of the prefix: at the default depth range and step a tile
    # stack is ~41 full camera frames, and without somewhere to put it every one
    # of them is discarded the moment the tile's cells have been built.
    rig = _savingRig(monkeypatch, sliceDir)

    rig.detect((0.0, 0.0), SearchConstraints())

    tiles = _tilesDir(sliceDir)
    written = sorted(os.listdir(tiles.name()))
    assert [f for f in written if f.endswith(".ma")]
    assert [f for f in written if f.endswith("_cellpose_masks.npy")]


def test_the_saved_tile_files_are_indexed_so_the_data_manager_sees_them(
    monkeypatch, sliceDir
):
    # The detector writes them by raw path from a teleprox subprocess that has
    # no DirHandle to write through, so nothing has told the Data Manager they
    # exist. An unindexed file does not appear in the file tree at all.
    rig = _savingRig(monkeypatch, sliceDir)

    rig.detect((7e-6, 9e-6), SearchConstraints())

    tiles = _tilesDir(sliceDir)
    base = os.path.basename(rig.prefixes[0])
    assert tiles.isManaged(f"{base}.ma")
    assert tiles.isManaged(f"{base}_cellpose_masks.npy")
    # The file names carry only a timestamp, so the coordinate they were taken
    # at is what makes a stack findable from a place on the slice.
    info = tiles[f"{base}.ma"].info()
    assert list(info["tile_center"]) == pytest.approx([7e-6, 9e-6])


def test_every_tile_gets_its_own_base_name(monkeypatch, sliceDir):
    # Two tiles of one survey write into the same directory; a shared base name
    # would have the second tile overwrite the first's stack and mask.
    rig = _savingRig(monkeypatch, sliceDir)

    rig.detect((0.0, 0.0), SearchConstraints())
    rig.detect((100e-6, 0.0), SearchConstraints())

    assert rig.prefixes[0] != rig.prefixes[1]
    assert len(os.listdir(_tilesDir(sliceDir).name())) >= 4


def test_a_detected_cell_records_the_tile_it_was_found_in(monkeypatch, sliceDir):
    # A cell in a Cell directory has to be relatable back to the stack and mask
    # it was found in; the base name is the only thing that relates them.
    rig = _savingRig(monkeypatch, sliceDir)

    cells = rig.detect((7e-6, 9e-6), SearchConstraints())

    assert cells[0].detection_prefix == rig.prefixes[0]
    assert cells[0].tile_center == pytest.approx((7e-6, 9e-6))


def test_a_cell_records_the_models_that_scored_it(monkeypatch, sliceDir):
    # score is a raw model output; without the checkpoint that produced it the
    # number cannot be compared with a score from any other run.
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    monkeypatch.setattr(tile_detector, "_acquire", lambda *a, **k: ["frame"])
    monkeypatch.setattr(
        tile_detector, "_detect", lambda *a, **k: [((1e-6, 2e-6, -530e-6), 0.8, 1.5e-16)]
    )
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)
    detect = tile_detector.make_tile_detector(
        camera=camera,
        scope=scope,
        manager=FakeManager({"segmenterPath": "/models/tuned", "classifierPath": "/c.pt"}),
    )

    cells = detect((0.0, 0.0), SearchConstraints())

    assert cells[0].detection_models["segmenter"] == "/models/tuned"
    assert cells[0].detection_models["classifier"] == "/c.pt"


def test_a_slice_with_no_directory_still_surveys(monkeypatch):
    # A run started without ever pressing "New slice" leaves Slice.dirHandle at
    # None. It must survey exactly as well, and simply save no imagery.
    rig = _makeRig(monkeypatch)

    cells = rig.detect((0.0, 0.0), SearchConstraints())

    assert rig.detectCalls[0][-1] is None
    assert len(cells) == 1
    assert cells[0].detection_prefix is None


def test_a_storage_failure_does_not_abort_the_survey(monkeypatch, sliceDir):
    # The experiment is the experiment: a disk that cannot take the tile stack
    # must not cost the operator the cells in it.
    def boom(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(type(sliceDir), "getDir", boom)
    rig = _savingRig(monkeypatch, sliceDir)

    cells = rig.detect((0.0, 0.0), SearchConstraints())

    assert rig.prefixes[0] is None
    assert len(cells) == 1


def test_a_cell_records_no_prefix_when_the_stack_never_landed(monkeypatch, sliceDir):
    # detect_neurons logs and swallows its own save failure, so the survey can
    # be handed cells with the prefix's files missing. A cell must not carry a
    # pointer to a stack that was never written.
    rig = _savingRig(monkeypatch, sliceDir, writes=())

    cells = rig.detect((0.0, 0.0), SearchConstraints())

    assert rig.prefixes[0] is not None
    assert cells[0].detection_prefix is None
