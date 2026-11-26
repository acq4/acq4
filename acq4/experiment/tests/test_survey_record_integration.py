"""Integration: a two-tile survey with overlap, run through the real tile
detector and CellProducer onto a real Data Manager directory, with synthetic
imaging and detections standing in for the camera and the cellpose subprocess."""

import os

import numpy as np
import pytest
from coorx import SRT3DTransform

import acq4.experiment.survey as survey_module
import acq4.util.DataManager as dm
from acq4.experiment import tile_detector
from acq4.experiment.cell_producer import CellProducer
from acq4.experiment.search_region import RectRegion
from acq4.experiment.slice import SearchConstraints, Slice
from acq4.util.geometry import load_transform
from acq4.util.imaging.frame import Frame

from .test_tile_detector import FakeCamera, FakeCell, FakeScope

FOV = (100e-6, 100e-6)
PIXEL = 1e-6
STEP_Z = 1e-6


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


def buildSurveyedSlice(tmp_path, monkeypatch):
    """A slice with one rectangular region, synthetic imaging and detections, and
    its tile detector; nothing has been surveyed yet."""
    sliceDir = dm.getDirHandle(str(tmp_path)).mkdir("slice")
    sliceDir.setInfo({"dirType": "Slice"})
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    # One cell sits in both tiles' overlap and is detected by each, 1 um apart:
    # the second sighting must be refused as the same cell.
    # Under sampler seed 3 a 190 um wide region surveys as fields centred at
    # x = 132.5 and 57.5 um, spanning 82.5-182.5 and 7.5-107.5: overlap is
    # 82.5-107.5.
    shared = (95e-6, 50e-6, -530e-6)
    detections = {
        "first": [(shared, 0.9, 1.5e-16, 8e-11), ((20e-6, 50e-6, -530e-6), 0.8, 1.5e-16, 8e-11)],
        "second": [((96e-6, 50e-6, -530e-6), 0.9, 1.5e-16, 8e-11), ((150e-6, 50e-6, -540e-6), 0.85, 1.5e-16, 8e-11)],
    }

    def acquire(cam, start_z, stop_z, step_z):
        x, y, _ = scope.moves[-1]
        offset = (x - FOV[0] / 2, y - FOV[1] / 2, start_z)
        frames = []
        for i in range(3):
            transform = SRT3DTransform(
                scale=(PIXEL, PIXEL, 1.0), offset=(offset[0], offset[1], offset[2] + i * step_z),
                from_cs="frame", to_cs="global").as_affine()
            m = transform.matrix
            m[:, 2] = m[:, 2] / np.linalg.norm(m[:, 2]) * step_z
            transform.matrix = m
            frames.append(Frame(np.zeros((8, 8)), {"transform": transform}))
        return frames

    def detect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix):
        with open(f"{save_prefix}.ma", "wb") as fh:
            fh.write(b"stack")
        with open(f"{save_prefix}_cellpose_masks.npy", "wb") as fh:
            fh.write(b"masks")
        return detections["first" if scope.moves[-1][0] < 100e-6 else "second"]

    monkeypatch.setattr(tile_detector, "_acquire", acquire)
    monkeypatch.setattr(tile_detector, "_detect", detect)
    monkeypatch.setattr(survey_module, "_newCell", FakeCell)
    detector = tile_detector.make_tile_detector(camera=camera, scope=scope, manager=None, slice_dir=sliceDir)
    s = Slice(fov=FOV, overlap=10e-6, constraints=SearchConstraints(min_health=0.0), dirHandle=sliceDir,
              sampler_seed=3)
    s.addRegion(RectRegion(0.0, 0.0, 190e-6, 100e-6))
    return sliceDir, s, detector, scope


@pytest.fixture
def survey(tmp_path, monkeypatch):
    sliceDir, s, detector, scope = buildSurveyedSlice(tmp_path, monkeypatch)
    producer = CellProducer(s, detector)
    queued = drain(producer)
    return sliceDir, queued, [m[0] for m in scope.moves]


def _records(sliceDir):
    tiles = sliceDir.getDir("tiles")
    names = sorted(n for n in tiles.ls() if n.endswith("_detections.yaml"))
    return tiles, [tiles[n].read() for n in names]


def _by_tile(records):
    return {round(r["tile_center"][0], 9): r for r in records}


def _verdicts(imaged):
    """Whichever tile is imaged first queues both its detections; the other
    tile's sighting of the shared cell is refused."""
    first, second = ([57.5e-6, 132.5e-6] if imaged[0] < 100e-6 else [132.5e-6, 57.5e-6])
    return {round(first, 9): ["queued", "queued"], round(second, 9): ["too_close", "queued"]}


def test_the_shared_cell_is_queued_once(survey):
    sliceDir, queued, _imaged = survey
    positions = sorted(tuple(c.position) for c in queued)
    assert len(positions) == 3
    sightings = [(95e-6, 50e-6, -530e-6), (96e-6, 50e-6, -530e-6)]
    assert sum(p in positions for p in sightings) == 1
    _tiles, records = _records(sliceDir)
    by_tile = _by_tile(records)
    assert set(by_tile) == {57.5e-6, 132.5e-6}
    refused = {
        d["position"][0]: x for x, r in by_tile.items() for d in r["detections"] if d["disposition"] == "too_close"
    }
    queued_in = {
        d["position"][0]: x for x, r in by_tile.items() for d in r["detections"] if d["disposition"] == "queued"
    }
    [refusedAt] = [x for x in (95e-6, 96e-6) if x in refused]
    [queuedAt] = [x for x in (95e-6, 96e-6) if x in queued_in]
    assert queued_in[queuedAt] != refused[refusedAt]


def test_each_tile_records_every_detection_with_its_verdict(survey):
    sliceDir, _queued, imaged = survey
    _tiles, records = _records(sliceDir)
    by_tile = _by_tile(records)
    assert {x: [d["disposition"] for d in r["detections"]] for x, r in by_tile.items()} == _verdicts(imaged)


def test_queued_cells_join_back_to_their_records(survey):
    sliceDir, queued, _imaged = survey
    tiles, records = _records(sliceDir)
    recorded = {d["candidate_id"]: r["tile_id"] for r in records for d in r["detections"]}
    assert queued
    for cell in queued:
        assert recorded[cell.candidate_id] == cell.tile_id
        assert tiles[f"{cell.detection_prefix.split(os.sep)[-1]}.ma"].info()["__uuid__"] == cell.tile_id


def test_every_record_header_carries_the_slice_fov(survey):
    sliceDir, _queued, _imaged = survey
    _tiles, records = _records(sliceDir)
    assert records
    assert all(r["fov"] == [100e-6, 100e-6] for r in records)


def test_every_tile_file_has_a_uuid_and_the_slices_id(survey):
    sliceDir, _queued, _imaged = survey
    tiles = sliceDir.getDir("tiles")
    for name in tiles.ls():
        info = tiles[name].info()
        assert len(info["__uuid__"]) == 32
        assert info["slice_id"] == sliceDir.info()["__uuid__"]


def test_each_tile_stack_transform_places_its_voxels_in_the_tiles_frame(survey):
    sliceDir, _queued, _imaged = survey
    tiles, records = _records(sliceDir)
    for record in records:
        stacks = [n for n in tiles.ls() if n.endswith(".ma") and tiles[n].info()["__uuid__"] == record["tile_id"]]
        assert len(stacks) == 1, f"expected one stack for tile {record['tile_id']}, found {stacks}"
        transform = load_transform(tiles[stacks[0]].info()["transform"])
        cx, cy = record["tile_center"]
        x0, y0 = cx - FOV[0] / 2, cy - FOV[1] / 2
        z0 = transform.map((0, 0, 0))[2]
        assert transform.map((0, 0, 0))[:2] == pytest.approx([x0, y0])
        assert transform.map((2, 3, 1)) == pytest.approx([x0 + 2 * PIXEL, y0 + 3 * PIXEL, z0 + STEP_Z])
