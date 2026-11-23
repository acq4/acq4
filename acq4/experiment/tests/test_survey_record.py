"""Tests for the per-tile detection record: what it holds, and that a failed
write is logged rather than raised."""

import logging

import acq4.util.DataManager as dm
from acq4.experiment.survey_record import TileDetections, detectionEntry, writeTileRecord


class Detected:
    def __init__(self, position, score=0.8, volume=1.5e-16, candidate_id="c1", area=None):
        self.position = position
        self.score = score
        self.volume = volume
        self.candidate_id = candidate_id
        if area is not None:
            self.area = area


def test_the_record_holds_the_header_and_every_entry(tmp_path):
    out = dm.getDirHandle(str(tmp_path), create=True)
    a = Detected((1e-6, 2e-6, -3e-5), candidate_id="a", area=8e-11)
    b = Detected((4e-6, 5e-6, -3e-5), candidate_id="b", score=0.1)
    detections = TileDetections([a, b], {"tile_id": "t1", "tile_center": [0.0, 0.0]}, out, "tile_x_detections.yaml")

    writeTileRecord(detections, [(a, "queued"), (b, "unhealthy")])

    record = out["tile_x_detections.yaml"].read()
    assert record["tile_id"] == "t1"
    assert record["detections"] == [
        {"candidate_id": "a", "position": [1e-6, 2e-6, -3e-5], "score": 0.8, "volume": 1.5e-16, "area": 8e-11, "disposition": "queued"},
        {"candidate_id": "b", "position": [4e-6, 5e-6, -3e-5], "score": 0.1, "volume": 1.5e-16, "disposition": "unhealthy"},
    ]


def test_the_record_file_gets_a_uuid_like_any_other(tmp_path):
    out = dm.getDirHandle(str(tmp_path), create=True)
    writeTileRecord(TileDetections([], {}, out, "r_detections.yaml"), [])
    assert len(out["r_detections.yaml"].info()["__uuid__"]) == 32


def test_nothing_is_written_with_nowhere_to_write(tmp_path):
    writeTileRecord(TileDetections([], {}), [])
    assert list(tmp_path.iterdir()) == []


def test_an_unscored_hand_cell_still_makes_an_entry():
    class Bare:
        position = (0.0, 0.0, 0.0)

    assert detectionEntry(Bare(), "queued") == {
        "candidate_id": None, "position": [0.0, 0.0, 0.0], "score": None, "volume": None, "disposition": "queued",
    }


def test_a_failed_write_is_logged_not_raised(tmp_path, caplog):
    out = dm.getDirHandle(str(tmp_path), create=True)
    with caplog.at_level(logging.ERROR):
        writeTileRecord(TileDetections([], {}, out, "no/such/dir_detections.yaml"), [])
    assert "Could not write the detection record" in caplog.text
