"""Tests for the spacing report, on detection records written in the test."""

import os
import sys

import numpy as np
import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spacing_report as sr  # noqa: E402


def _record(tilesDir, name, detected_at, detections):
    with open(os.path.join(tilesDir, name), "w") as fh:
        yaml.safe_dump({"tile_id": name, "detected_at": detected_at, "detections": detections}, fh)


def _d(cid, x, disposition="queued", z=0.0):
    return {"candidate_id": cid, "position": [x, 0.0, z], "score": 0.9, "disposition": disposition}


@pytest.fixture
def sliceDir(tmp_path):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "b_detections.yaml", 2.0, [_d("c", 10e-6), _d("d", 100e-6)])
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 50e-6), _d("x", 0.0, "unhealthy")])
    return str(tmp_path)


def test_detections_load_in_survey_order(sliceDir):
    assert [d["candidate_id"] for d in sr.loadDetections(sliceDir)] == ["a", "b", "x", "c", "d"]


def test_loading_skips_records_that_are_not_mappings_and_null_detections(sliceDir):
    tiles = os.path.join(sliceDir, "tiles")
    with open(os.path.join(tiles, "junk_detections.yaml"), "w") as fh:
        fh.write("- not\n- a mapping\n")
    _record(tiles, "empty_detections.yaml", 3.0, None)

    assert len(sr.loadDetections(sliceDir)) == 5


def test_nearest_neighbour_distances():
    np.testing.assert_allclose(sr.nearestNeighbourDistances([[0, 0, 0], [3, 4, 0], [10, 0, 0]]), [5, 5, np.hypot(7, 4)])


def test_close_pairs_are_strictly_inside_the_radius():
    assert sr.closePairs([[0, 0, 0], [3, 4, 0], [20, 0, 0]], 5.0) == []
    assert sr.closePairs([[0, 0, 0], [3, 4, 0], [20, 0, 0]], 5.1) == [(0, 1, pytest.approx(5.0))]


def test_resimulating_a_wider_spacing_drops_the_near_repeat(sliceDir):
    detections = sr.loadDetections(sliceDir)
    assert [d["candidate_id"] for d in sr.resimulate(detections, 5e-6)] == ["a", "b", "c", "d"]
    assert [d["candidate_id"] for d in sr.resimulate(detections, 30e-6)] == ["a", "b", "d"]


def test_resimulating_ignores_candidates_the_spacing_never_judged(sliceDir):
    assert "x" not in [d["candidate_id"] for d in sr.resimulate(sr.loadDetections(sliceDir), 1e-9)]


def test_the_plot_is_written(sliceDir, tmp_path):
    out = tmp_path / "spacing.png"
    sr.plot(sr.loadDetections(sliceDir), 30e-6, str(out))
    assert out.stat().st_size > 0


def test_main_exits_zero_when_no_queued_pair_is_close(tmp_path, capsys):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 50e-6)])
    out = tmp_path / "spacing.png"

    assert sr.main([str(tmp_path), "--out", str(out)]) == 0
    assert "0 queued pairs closer than 30 µm" in capsys.readouterr().out
    assert out.stat().st_size > 0


def test_main_exits_one_and_names_a_close_pair(tmp_path, capsys):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 10e-6)])

    assert sr.main([str(tmp_path), "--out", str(tmp_path / "spacing.png")]) == 1
    assert "a / b: 10.0 µm" in capsys.readouterr().out


def test_main_rejects_a_slice_dir_that_is_not_a_directory(tmp_path, capsys):
    assert sr.main([str(tmp_path / "typo")]) == 2
    assert "not a directory" in capsys.readouterr().err
