"""Tests for the spacing report, on detection records written in the test."""

import os
import re
import sys

import numpy as np
import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spacing_report as sr  # noqa: E402
from acq4.experiment.slice import SearchConstraints  # noqa: E402


def _record(tilesDir, name, detected_at, detections, **header):
    with open(os.path.join(tilesDir, name), "w") as fh:
        yaml.safe_dump(
            {"tile_id": name, "detected_at": detected_at, "detections": detections, **header}, fh
        )


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


def test_resimulating_caps_each_tile_and_a_spacing_drop_does_not_use_a_slot(tmp_path):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0)])
    _record(str(tiles), "b_detections.yaml", 2.0,
            [_d("near", 5e-6), _d("b1", 100e-6), _d("b2", 200e-6), _d("b3", 300e-6)])

    queued = sr.resimulate(sr.loadDetections(str(tmp_path)), 30e-6, cap=2)

    assert [d["candidate_id"] for d in queued] == ["a", "b1", "b2"]


@pytest.mark.parametrize("points", [[], [[0, 0, 0]]])
def test_too_few_points_have_no_neighbours_or_pairs(points):
    assert len(sr.nearestNeighbourDistances(points)) == 0
    assert sr.closePairs(points, 1.0) == []


def test_main_on_a_slice_with_no_records_exits_zero_and_writes_the_plot(tmp_path, capsys):
    (tmp_path / "tiles").mkdir()
    out = tmp_path / "spacing.png"

    assert sr.main([str(tmp_path), "--out", str(out)]) == 0
    assert "0 detections, 0 queued" in capsys.readouterr().out
    assert out.stat().st_size > 0


def test_main_counts_nearest_neighbours_beyond_the_last_bin(tmp_path, capsys):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 250e-6)])

    assert sr.main([str(tmp_path), "--out", str(tmp_path / "spacing.png")]) == 0
    assert re.search(r"100\+ +## 2", capsys.readouterr().out)


def test_main_counts_a_distance_of_exactly_the_last_edge_once(tmp_path, capsys):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 100e-6)])

    assert sr.main([str(tmp_path), "--out", str(tmp_path / "spacing.png")]) == 0
    assert re.search(r"100\+ +0\n", capsys.readouterr().out)


def test_spacing_defaults_to_the_one_the_records_were_surveyed_with(tmp_path, capsys):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 40e-6)],
            constraints={"min_cell_spacing": 50e-6})

    assert sr.main([str(tmp_path), "--out", str(tmp_path / "spacing.png")]) == 1
    out = capsys.readouterr().out
    assert "spacing 50 µm (from the records)" in out
    assert "closer than 50 µm" in out


def test_spacing_falls_back_to_thirty_microns_without_a_recorded_one(tmp_path, capsys):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 50e-6)])

    assert sr.main([str(tmp_path), "--out", str(tmp_path / "spacing.png")]) == 0
    out = capsys.readouterr().out
    assert "spacing 30 µm (default)" in out
    assert "closer than 30 µm" in out


def test_an_explicit_spacing_wins_over_the_records(tmp_path, capsys):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 40e-6)],
            constraints={"min_cell_spacing": 50e-6})

    assert sr.main([str(tmp_path), "--spacing", "30e-6", "--out", str(tmp_path / "spacing.png")]) == 0
    assert "spacing 30 µm (from --spacing)" in capsys.readouterr().out


def test_the_plot_uses_the_chosen_spacing_not_the_last_trial(tmp_path, monkeypatch):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    _record(str(tiles), "a_detections.yaml", 1.0, [_d("a", 0.0), _d("b", 50e-6)])
    seen = []
    monkeypatch.setattr(sr, "plot", lambda detections, spacing, path: seen.append(spacing))

    sr.main([str(tmp_path), "--spacing", "30e-6", "--try", "10e-6", "20e-6", "--out", str(tmp_path / "s.png")])

    assert seen == [30e-6]


def _sliceWithRecords(tmp_path, superseded=False, excluded=()):
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    header = lambda cx: {"tile_center": [cx, 0.0], "fov": [100e-6, 100e-6]}
    _record(str(tiles), "tile_1_aaaaaaaa_detections.yaml", 1.0,
            [_d("a", 0.0), _d("b", 50e-6)], **header(0.0))
    _record(str(tiles), "tile_2_bbbbbbbb_detections.yaml", 2.0,
            [_d("c", 500e-6), _d("d", 600e-6)], superseded=superseded, **header(550e-6))
    manual = {
        "manual": [{"candidate_id": "m1", "position": [900e-6, 0.0, 0.0], "source": "manual", "added_at": 3.0}],
        "excluded": list(excluded),
    }
    with open(tmp_path / "survey_manual.yaml", "w") as fh:
        yaml.safe_dump(manual, fh)
    return tmp_path


def test_live_picks_put_manual_first_then_tiles_in_order(tmp_path):
    sliceDir = _sliceWithRecords(tmp_path)
    survey, regions = sr.loadSurvey(str(sliceDir))

    picks = sr.livePicks(survey, regions, SearchConstraints(min_health=0.0, min_cell_spacing=10e-6))

    assert picks[0]["source"] == "manual"
    assert [p["source"] for p in picks[1:]] == ["survey"] * (len(picks) - 1)
    assert [p["candidate_id"] for p in picks] == ["m1", "a", "b", "c", "d"]


def test_live_picks_skip_excluded_and_superseded(tmp_path):
    sliceDir = _sliceWithRecords(tmp_path, superseded=True, excluded=["b"])
    survey, regions = sr.loadSurvey(str(sliceDir))

    picks = sr.livePicks(survey, regions, SearchConstraints(min_health=0.0, min_cell_spacing=10e-6))

    ids = [p["candidate_id"] for p in picks]
    assert ids == ["m1", "a"]


def test_main_live_prints_one_line_per_pick(tmp_path, capsys):
    sliceDir = _sliceWithRecords(tmp_path)

    assert sr.main([str(sliceDir), "--live", "--spacing", "10e-6"]) == 0

    lines = capsys.readouterr().out.strip().splitlines()[1:]
    assert len(lines) == 5
    assert "m1" in lines[0] and "manual" in lines[0]
