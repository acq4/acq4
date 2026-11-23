"""Integration: a two-tile survey with overlap, run through the real tile
detector and CellProducer onto a real Data Manager directory, with synthetic
imaging and detections standing in for the camera and the cellpose subprocess."""

import os

import numpy as np
import pytest
from coorx import SRT3DTransform

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


@pytest.fixture
def survey(tmp_path, monkeypatch):
    sliceDir = dm.getDirHandle(str(tmp_path)).mkdir("slice")
    sliceDir.setInfo({"dirType": "Slice"})
    camera = FakeCamera()
    scope = FakeScope(camera, surface=-500e-6)
    # One cell sits in both tiles' overlap and is detected by each, 1 um apart:
    # the second sighting must be refused as the same cell.
    # Tiling: step = 100 - 10 = 90 um, so a 190 um wide region tiles as centres
    # x = 50 and 140 um (tileGrid), spanning 0-100 and 90-190: overlap is 90-100.
    shared = (95e-6, 50e-6, -530e-6)
    detections = {
        "first": [(shared, 0.9, 1.5e-16, 8e-11), ((20e-6, 50e-6, -530e-6), 0.8, 1.5e-16, 8e-11)],
        "second": [((96e-6, 50e-6, -530e-6), 0.9, 1.5e-16, 8e-11), ((150e-6, 50e-6, -540e-6), 0.85, 1.5e-16, 8e-11)],
    }
    order = iter(["first", "second"])

    def acquire(cam, start_z, stop_z, step_z):
        x, y, _ = scope.moves[-1]
        offset = (x - FOV[0] / 2, y - FOV[1] / 2, start_z)
        return [
            Frame(np.zeros((8, 8)), {"transform": SRT3DTransform(
                scale=(PIXEL, PIXEL, 1.0), offset=(offset[0], offset[1], offset[2] - i * step_z),
                from_cs="frame", to_cs="global")})
            for i in range(3)
        ]

    def detect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix):
        with open(f"{save_prefix}.ma", "wb") as fh:
            fh.write(b"stack")
        with open(f"{save_prefix}_cellpose_masks.npy", "wb") as fh:
            fh.write(b"masks")
        return detections[next(order)]

    monkeypatch.setattr(tile_detector, "_acquire", acquire)
    monkeypatch.setattr(tile_detector, "_detect", detect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)
    detector = tile_detector.make_tile_detector(camera=camera, scope=scope, manager=None, slice_dir=sliceDir)
    s = Slice(fov=FOV, overlap=10e-6, constraints=SearchConstraints(min_health=0.0), dirHandle=sliceDir)
    s.addRegion(RectRegion(0.0, 0.0, 190e-6, 100e-6))
    producer = CellProducer(s, detector)
    queued = producer() + producer()
    return sliceDir, queued


def _records(sliceDir):
    tiles = sliceDir.getDir("tiles")
    names = sorted(n for n in tiles.ls() if n.endswith("_detections.yaml"))
    return tiles, [tiles[n].read() for n in names]


def test_the_shared_cell_is_queued_once(survey):
    _sliceDir, queued = survey
    positions = sorted(tuple(c.position) for c in queued)
    assert len(positions) == 3
    assert (96e-6, 50e-6, -530e-6) not in positions


def test_each_tile_records_every_detection_with_its_verdict(survey):
    sliceDir, _queued = survey
    _tiles, records = _records(sliceDir)
    assert [[d["disposition"] for d in r["detections"]] for r in records] == [
        ["queued", "queued"],
        ["too_close", "queued"],
    ]


def test_queued_cells_join_back_to_their_records(survey):
    sliceDir, queued = survey
    tiles, records = _records(sliceDir)
    recorded = {d["candidate_id"]: r["tile_id"] for r in records for d in r["detections"]}
    for cell in queued:
        assert recorded[cell.candidate_id] == cell.tile_id
        assert tiles[f"{cell.detection_prefix.split(os.sep)[-1]}.ma"].info()["__uuid__"] == cell.tile_id


def test_every_tile_file_has_a_uuid_and_the_slices_id(survey):
    sliceDir, _queued = survey
    tiles = sliceDir.getDir("tiles")
    for name in tiles.ls():
        info = tiles[name].info()
        assert len(info["__uuid__"]) == 32
        assert info["slice_id"] == sliceDir.info()["__uuid__"]


def test_each_tile_stack_transform_places_its_origin_at_the_tiles_corner(survey):
    sliceDir, _queued = survey
    tiles, records = _records(sliceDir)
    for record in records:
        stack = next(n for n in tiles.ls() if n.endswith(".ma") and tiles[n].info()["__uuid__"] == record["tile_id"])
        origin = load_transform(tiles[stack].info()["transform"]).map((0, 0, 0))
        cx, cy = record["tile_center"]
        assert origin[:2] == pytest.approx([cx - FOV[0] / 2, cy - FOV[1] / 2])
