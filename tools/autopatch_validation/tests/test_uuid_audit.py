"""Tests for the uuid audit, on Data Manager trees built in the test."""

import os
import sys

from pyqtgraph.configfile import writeConfigFile

import acq4.util.DataManager as dm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid_audit  # noqa: E402


def _slice(tmp_path):
    sliceDir = dm.getDirHandle(str(tmp_path), create=True).mkdir("slice_000")
    sliceDir.setInfo({"dirType": "Slice"})
    return sliceDir


def test_a_clean_tree_has_no_findings(tmp_path):
    sliceDir = _slice(tmp_path)
    tiles = sliceDir.mkdir("tiles")
    stack = tiles.createFile("tile_1.ma")
    tiles.writeFile({"tile_id": stack.info()["__uuid__"], "detections": [{"candidate_id": "c1"}]},
                    "tile_1_detections.yaml", fileType="YamlFile")
    sliceDir.mkdir("cell_000", info={"dirType": "Cell", "candidate_id": "c1", "tile_id": stack.info()["__uuid__"]})

    # The slice, not the root: a root made by getDirHandle(create=True) never
    # went through mkdir and has no uuid of its own.
    report = uuid_audit.auditTree(sliceDir.name())

    assert report["missing"] == []
    assert report["duplicates"] == {}
    assert report["unresolved"] == []
    assert report["entries"] >= 5


def test_an_entry_without_a_uuid_is_reported(tmp_path):
    os.makedirs(tmp_path / "old")
    with open(tmp_path / "old" / "data.ma", "wb") as fh:
        fh.write(b"x")
    writeConfigFile({".": {}, "data.ma": {"__timestamp__": 1.0}}, str(tmp_path / "old" / ".index"))

    report = uuid_audit.auditTree(str(tmp_path))

    assert sorted(report["missing"]) == sorted([str(tmp_path / "old"), str(tmp_path / "old" / "data.ma")])


def test_a_uuid_used_twice_is_reported(tmp_path):
    os.makedirs(tmp_path / "d")
    for name in ("a", "b"):
        with open(tmp_path / "d" / name, "wb") as fh:
            fh.write(b"x")
    writeConfigFile({".": {"__uuid__": "u0"}, "a": {"__uuid__": "same"}, "b": {"__uuid__": "same"}}, str(tmp_path / "d" / ".index"))

    assert list(uuid_audit.auditTree(str(tmp_path))["duplicates"]) == ["same"]


def test_a_cell_pointing_at_no_detection_is_reported(tmp_path):
    sliceDir = _slice(tmp_path)
    cell = sliceDir.mkdir("cell_000", info={"dirType": "Cell", "candidate_id": "nowhere"})

    assert uuid_audit.auditTree(sliceDir.name())["unresolved"] == [cell.name()]


def test_a_hand_seeded_cell_with_no_ids_is_fine(tmp_path):
    sliceDir = _slice(tmp_path)
    sliceDir.mkdir("cell_000", info={"dirType": "Cell"})

    assert uuid_audit.auditTree(sliceDir.name())["unresolved"] == []


def test_a_cell_whose_tile_matches_no_record_is_reported(tmp_path):
    sliceDir = _slice(tmp_path)
    tiles = sliceDir.mkdir("tiles")
    tiles.writeFile({"tile_id": "t1", "detections": [{"candidate_id": "c1"}]},
                    "tile_1_detections.yaml", fileType="YamlFile")
    cell = sliceDir.mkdir("cell_000", info={"dirType": "Cell", "candidate_id": "c1", "tile_id": "other"})

    assert uuid_audit.auditTree(sliceDir.name())["unresolved"] == [cell.name()]


def test_odd_detection_records_are_skipped(tmp_path):
    sliceDir = _slice(tmp_path)
    tiles = sliceDir.mkdir("tiles")
    tiles.writeFile({"tile_id": "t1", "detections": None}, "a_detections.yaml", fileType="YamlFile")
    tiles.writeFile(["not", "a", "dict"], "b_detections.yaml", fileType="YamlFile")
    sliceDir.mkdir("cell_000", info={"dirType": "Cell", "candidate_id": "c1"})

    assert uuid_audit.auditTree(sliceDir.name())["unresolved"] == [os.path.join(sliceDir.name(), "cell_000")]


def test_a_subdirectory_without_its_own_index_is_audited_from_the_parent(tmp_path):
    os.makedirs(tmp_path / "d" / "sub")
    writeConfigFile({".": {"__uuid__": "u0"}, "sub": {"__timestamp__": 1.0}}, str(tmp_path / "d" / ".index"))

    assert uuid_audit.auditTree(str(tmp_path))["missing"] == [str(tmp_path / "d" / "sub")]


def test_main_exits_zero_on_a_clean_tree(tmp_path, capsys):
    sliceDir = _slice(tmp_path)

    assert uuid_audit.main([sliceDir.name()]) == 0
    assert "0 without a uuid" in capsys.readouterr().out


def test_main_exits_one_on_a_finding(tmp_path, capsys):
    os.makedirs(tmp_path / "old")
    writeConfigFile({".": {}}, str(tmp_path / "old" / ".index"))

    assert uuid_audit.main([str(tmp_path)]) == 1
    assert f"  missing  {tmp_path / 'old'}" in capsys.readouterr().out


def test_main_rejects_a_root_that_is_not_a_directory(tmp_path, capsys):
    assert uuid_audit.main([str(tmp_path / "typo")]) == 2
    assert "not a directory" in capsys.readouterr().err
