"""Tests for everything besides the tracking history that a run records about a
cell: the metadata file written the moment its directory exists, the scalars
mirrored onto that directory's index, and the reference stack and position
series written as the pass closes out."""
import os

import numpy as np
import pytest
import yaml
from coorx import Point

import acq4.util.DataManager as dm
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AbortExperiment
from acq4.experiment.orchestrator import Orchestrator

from .test_actions_prompt_storage import FakeManager


class FakeObjectStack:
    """The reference cube a tracker cuts out of the stack its cell was found in."""

    def __init__(self, data, transform=None):
        self.data = data
        self.transform = transform


class FakeMotionEstimator:
    def __init__(self, stacks=()):
        self.object_stacks = list(stacks)

    @property
    def original_object_stack(self):
        # Raises IndexError on an estimator that holds nothing, exactly as the
        # real property does -- which is the case a reader here has to survive.
        return self.object_stacks[0]


class CellposeCellTracker:
    """Named for the real class, because `use_cellpose` is derived from the
    tracker's class name rather than from anything recorded at detection."""

    def __init__(self, results=(), stacks=(), segmenter=None):
        self.tracking_results = list(results)
        self.motion_estimator = FakeMotionEstimator(stacks)
        self._segmenter = segmenter
        self.saved_to = []

    def save_history(self, path):
        self.saved_to.append(path)
        with open(path, "w") as fh:
            fh.write("tracking history")


class FakeDetectedCell:
    """A cell as tile_detector builds one: scored, sized, seeded from the tile
    stack, and carrying the provenance of the tile it came out of."""

    def __init__(self, name="c1", tracker=None, positions=None):
        self._name = name
        self.initialPosition = Point([1e-6, 2e-6, -530e-6], "global")
        self._positions = positions or {1000.0: self.initialPosition}
        self.score = 0.75
        self.volume = 1.5e-16
        self.tile_center = (7e-6, 9e-6)
        self.detection_prefix = "/data/slice_000/tiles/tile_20260818_101112_131415"
        self.detection_models = {
            "segmenter": "/models/seg.pt",
            "autoencoder": None,
            "classifier": None,
            "resnet_classifier": "/models/resnet.pt",
        }
        self.allow_refresh_reference = True
        self._tracker = tracker

    def __repr__(self):
        return f"<cell {self._name}>"


def _tracker(results=(), stacks=None, segmenter="/models/seg.pt"):
    if stacks is None:
        stacks = [FakeObjectStack(np.arange(24, dtype="uint16").reshape(2, 3, 4))]
    return CellposeCellTracker(results=results, stacks=stacks, segmenter=segmenter)


@pytest.fixture
def root_dir(tmp_path):
    return dm.getDirHandle(str(tmp_path), create=True)


def _orch(pf, manager):
    return Orchestrator(
        pf,
        manager=manager,
        contextFactory=lambda cell: ExecutionContext(cell=cell, manager=manager),
    )


def _metadata(cell_dir):
    with open(os.path.join(cell_dir.name(), "cell_metadata.yaml")) as fh:
        return yaml.safe_load(fh)


# -- written the moment the directory exists -----------------------------


def test_the_metadata_file_is_written_before_the_protocol_runs(make_pf, root_dir):
    # The one save that has to survive a pass that dies: everything in it is
    # already fixed by the time the directory is made, and a cell whose protocol
    # crashed on its first move is the cell an operator most wants to read.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []

    def spy_run(ctx, **kwargs):
        cellDir = ctx.manager.getCurrentDir()
        seen.append(sorted(os.listdir(cellDir.name())))

    pf.run = spy_run
    _orch(pf, man).run_sync_cell(FakeDetectedCell(tracker=_tracker()))

    assert "cell_metadata.yaml" in seen[0]


def test_the_metadata_survives_a_protocol_that_dies(make_pf, root_dir):
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []

    def failing_run(ctx, **kwargs):
        seen.append(ctx.manager.getCurrentDir())
        raise RuntimeError("something in the protocol broke")

    pf.run = failing_run
    with pytest.raises(AbortExperiment):
        _orch(pf, man).run_sync_cell(FakeDetectedCell(tracker=_tracker()))

    assert _metadata(seen[0])["score"] == pytest.approx(0.75)


def test_the_metadata_records_what_found_the_cell_and_with_what(make_pf, root_dir):
    # score is a raw model output whose meaning depends entirely on the
    # checkpoint that produced it, so the two have to be readable together.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    _orch(pf, man).run_sync_cell(FakeDetectedCell(tracker=_tracker()))

    meta = _metadata(seen[0])
    assert meta["score"] == pytest.approx(0.75)
    assert meta["volume"] == pytest.approx(1.5e-16)
    assert meta["initial_position"] == pytest.approx([1e-6, 2e-6, -530e-6])
    assert meta["tile_center"] == pytest.approx([7e-6, 9e-6])
    assert meta["detected_at"] == pytest.approx(1000.0)
    assert meta["detection_prefix"].endswith("tile_20260818_101112_131415")
    assert meta["detection_models"]["resnet_classifier"] == "/models/resnet.pt"
    assert meta["tracker_class"] == "CellposeCellTracker"
    assert meta["segmenter"] == "/models/seg.pt"
    assert meta["use_cellpose"] is True
    assert meta["allow_refresh_reference"] is True


def test_the_metadata_is_plain_data_a_yaml_reader_can_load(make_pf, root_dir):
    # coorx Points and numpy scalars have no YAML representation, so anything
    # that reached the file un-converted would either fail the write outright or
    # produce a file only a Python unpickler could read back.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    cell = FakeDetectedCell(tracker=_tracker())
    cell.score = np.float32(0.5)
    _orch(pf, man).run_sync_cell(cell)

    meta = _metadata(seen[0])
    assert isinstance(meta["score"], float)
    assert all(isinstance(v, float) for v in meta["initial_position"])


def test_a_hand_seeded_cell_gets_metadata_without_raising(make_pf, root_dir):
    # `volume` and the three provenance attributes are attached by the detectors
    # and are not declared on Cell at all, so reading them off a cell the
    # operator seeded by hand raises AttributeError rather than answering None.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    cell = FakeDetectedCell(tracker=_tracker())
    del cell.volume
    del cell.tile_center
    del cell.detection_prefix
    del cell.detection_models

    _orch(pf, man).run_sync_cell(cell)

    meta = _metadata(seen[0])
    assert meta["volume"] is None
    assert meta["tile_center"] is None
    assert meta["detection_prefix"] is None
    assert meta["detection_models"] == {}


def test_a_metadata_failure_does_not_halt_the_run(make_pf, root_dir):
    # Bookkeeping on the way into a cell's protocol. A cell whose metadata file
    # cannot be written is still a cell worth patching.
    man = FakeManager(root_dir)
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    cell = FakeDetectedCell(tracker=_tracker())
    # A property that raises on read, which is what a half-built cell looks like
    # from here; nothing else about the pass should notice.
    type(cell).score = property(lambda self: 1 / 0)
    try:
        finished = []
        orch = _orch(pf, man)
        orch.sigCellFinished.connect(lambda c, s: finished.append(s))
        orch.run_sync_cell(cell)
    finally:
        del type(cell).score

    assert ran == [cell]
    assert finished == ["done"]


def test_the_cell_directory_index_carries_the_headline_numbers(make_pf, root_dir):
    # folderTypes.cfg already gives a Cell a `location` field, and the Data
    # Manager shows the index beside the operator's own notes; a run that knows
    # where the cell is should not leave that blank.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    _orch(pf, man).run_sync_cell(FakeDetectedCell(tracker=_tracker()))

    info = seen[0].info()
    assert info["score"] == pytest.approx(0.75)
    assert info["volume"] == pytest.approx(1.5e-16)
    assert "-530" in info["location"]


# -- written as the pass closes out --------------------------------------


def test_the_reference_stack_is_saved_even_when_the_cell_was_never_tracked(
    make_pf, root_dir
):
    # The cube the detector actually saw. A cell that was detected, seeded from
    # the tile stack, queued and then abandoned has no tracking results at all,
    # and this is the only per-cell imagery it will ever have.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    _orch(pf, man).run_sync_cell(FakeDetectedCell(tracker=_tracker(results=())))

    assert "reference_stack.ma" in os.listdir(seen[0].name())


def test_the_saved_reference_stack_holds_the_trackers_own_array(make_pf, root_dir):
    from MetaArray import MetaArray

    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    data = np.arange(24, dtype="uint16").reshape(2, 3, 4)
    cell = FakeDetectedCell(tracker=_tracker(stacks=[FakeObjectStack(data)]))
    _orch(pf, man).run_sync_cell(cell)

    written = MetaArray(file=os.path.join(seen[0].name(), "reference_stack.ma"))
    assert np.array_equal(np.asarray(written), data)


def test_the_reference_stack_records_where_in_the_world_it_is(make_pf, root_dir):
    # Without the transform the cube is a picture of nowhere in particular. It
    # goes onto the file's index rather than into the array, which works because
    # the index's serializer already special-cases a coorx Transform -- the one
    # non-plain type it knows how to write and read back.
    from coorx import SRT3DTransform

    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    transform = SRT3DTransform(
        scale=(1e-6, 1e-6, 1e-6),
        offset=(1e-3, 2e-3, -5e-4),
        from_cs="ijk",
        to_cs="global",
    )
    stacks = [FakeObjectStack(np.zeros((2, 3, 4), dtype="uint16"), transform)]
    _orch(pf, man).run_sync_cell(FakeDetectedCell(tracker=_tracker(stacks=stacks)))

    saved = seen[0]["reference_stack.ma"].info()["transform"]
    assert np.allclose(saved.offset, [1e-3, 2e-3, -5e-4])


def test_a_cell_whose_tracker_holds_no_reference_saves_no_stack(make_pf, root_dir):
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    _orch(pf, man).run_sync_cell(FakeDetectedCell(tracker=_tracker(stacks=[])))

    assert "reference_stack.ma" not in os.listdir(seen[0].name())


def test_the_position_history_is_saved(make_pf, root_dir):
    # The .acqtrack carries a position per tracking result, but only for the
    # frames that produced one, and never the detection position the cell was
    # created at. This is the whole series.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    positions = {
        1000.0: Point([1e-6, 2e-6, -530e-6], "global"),
        1001.5: Point([1.1e-6, 2e-6, -531e-6], "global"),
    }
    cell = FakeDetectedCell(tracker=_tracker(), positions=positions)
    _orch(pf, man).run_sync_cell(cell)

    with open(os.path.join(seen[0].name(), "position_history.yaml")) as fh:
        history = yaml.safe_load(fh)
    assert [t for t, _ in history] == pytest.approx([1000.0, 1001.5])
    assert history[1][1] == pytest.approx([1.1e-6, 2e-6, -531e-6])


def test_a_close_out_save_failure_does_not_replace_what_ended_the_pass(
    make_pf, root_dir
):
    # _closeCellDataDir runs from _processCell's finally, so an exception here
    # would replace the halt the operator actually needs to see.
    man = FakeManager(root_dir)
    pf = make_pf()

    def failing_run(ctx, **kwargs):
        raise RuntimeError("something in the protocol broke")

    pf.run = failing_run
    cell = FakeDetectedCell(tracker=_tracker())
    # An estimator that raises rather than answering, standing for any of the
    # ways reading a tracker can go wrong on a cell that has already failed.
    cell._tracker.motion_estimator = None

    with pytest.raises(AbortExperiment):
        _orch(pf, man).run_sync_cell(cell)
