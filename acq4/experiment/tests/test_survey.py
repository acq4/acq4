"""Tests for Survey: the slice's facts and the selector that picks the next cell
from them under the current constraints."""

import pytest

import acq4.util.DataManager as dm
from acq4.experiment import survey as survey_mod
from acq4.experiment.slice import SearchConstraints
from acq4.experiment.survey import MANUAL_FILE, NEED_TILE, Survey, TileRecord

FOV = (100e-6, 100e-6)
C = SearchConstraints(min_health=0.5, min_cell_spacing=10e-6)
EVERYWHERE = lambda position: True  # noqa: E731


class Cell:
    """Stands in for acq4_automation's Cell: a position and settable attributes."""

    def __init__(self, position):
        self.position = position


@pytest.fixture(autouse=True)
def plain_cells(monkeypatch):
    monkeypatch.setattr(survey_mod, "_newCell", Cell)


def det(cid, x, score=0.9, y=0.0, z=0.0):
    return {"candidate_id": cid, "position": [x, y, z], "score": score, "volume": 1e-16}


def tile(cx, *detections, **header):
    head = {"tile_id": f"t{cx}", "tile_center": [cx, 0.0], "fov": list(FOV),
            "detection_prefix": f"tiles/tile_{cx}", "detection_models": {}}
    head.update(header)
    return TileRecord(header=head, detections=tuple(detections))


def survey_of(*records):
    s = Survey(FOV)
    for r in records:
        s.addTile(r)
    return s


def picks(s, n=20):
    out = []
    for _ in range(n):
        choice = s.next(C, EVERYWHERE)
        if choice == NEED_TILE:
            break
        out.append(choice.entry["candidate_id"])
        s.handOut(choice.entry)
    return out


def test_an_empty_survey_needs_a_tile():
    assert Survey(FOV).next(C, EVERYWHERE) == NEED_TILE


def test_within_a_tile_the_best_score_goes_first():
    s = survey_of(tile(0.0, det("a", 0.0, 0.6), det("b", 30e-6, 0.9)))
    assert picks(s) == ["b", "a"]


def test_unhealthy_and_out_of_region_detections_are_never_picked():
    s = survey_of(tile(0.0, det("sick", 0.0, 0.1), det("out", 60e-6), det("ok", 30e-6)))
    inside = lambda p: p[0] < 45e-6  # noqa: E731
    first = s.next(C, inside)
    assert first.entry["candidate_id"] == "ok"
    s.handOut(first.entry)
    assert s.next(C, inside) == NEED_TILE


def test_an_unscored_detection_passes_the_cutoff_and_ranks_after_scored_ones():
    s = survey_of(tile(0.0, det("unscored", 0.0, None), det("scored", 30e-6, 0.6)))
    assert picks(s) == ["scored", "unscored"]


def test_the_cap_limits_hand_outs_per_tile_then_the_next_tile_is_used():
    first = tile(0.0, *[det(f"a{i}", i * 20e-6, 0.9 - i * 0.01) for i in range(7)])
    second = tile(1.0, det("b0", 1.0))
    s = survey_of(first, second)
    assert picks(s) == ["a0", "a1", "a2", "a3", "a4", "b0"]


def test_tiles_are_used_in_imaging_order_not_score_order():
    s = survey_of(tile(0.0, det("early", 0.0, 0.6)), tile(1.0, det("late", 1.0, 0.99)))
    assert picks(s)[0] == "early"


def test_a_cross_tile_duplicate_goes_to_the_better_score_whichever_tile_is_first():
    worse_first = survey_of(tile(0.0, det("dupA", 50e-6, 0.7)), tile(1.0, det("dupB", 51e-6, 0.95)))
    assert picks(worse_first) == ["dupB"]


def test_spacing_applies_against_handed_out_cells():
    s = survey_of(tile(0.0, det("a", 0.0)))
    s.handOut(s.next(C, EVERYWHERE).entry)
    s.addTile(tile(1.0, det("near", 5e-6), det("far", 50e-6)))
    assert picks(s) == ["far"]


def test_spacing_applies_against_manual_entries():
    s = survey_of(tile(0.0, det("near", 5e-6), det("far", 50e-6)))
    s.addManual((0.0, 0.0, 0.0))
    s.handOut(s.next(C, EVERYWHERE).entry)
    assert picks(s) == ["far"]


def test_manual_entries_come_first_in_the_order_added_and_skip_the_filters():
    s = survey_of(tile(0.0, det("t", 0.0)))
    m1 = s.addManual((500e-6, 0.0, 0.0))
    m2 = s.addManual((500e-6 + 1e-6, 0.0, 0.0))
    first = s.next(C, lambda p: False)
    assert first.entry["candidate_id"] == m1["candidate_id"]
    assert first.entry["source"] == "manual"
    s.handOut(first.entry)
    assert s.next(C, lambda p: False).entry["candidate_id"] == m2["candidate_id"]


def test_a_requeued_cell_is_picked_again_as_the_same_object():
    s = survey_of(tile(0.0, det("a", 0.0)))
    cell = s.handOut(s.next(C, EVERYWHERE).entry)
    assert s.next(C, EVERYWHERE) == NEED_TILE
    s.requeue(cell)
    again = s.next(C, EVERYWHERE)
    assert s.handOut(again.entry) is cell


def test_excluded_entries_are_never_picked():
    s = survey_of(tile(0.0, det("a", 0.0), det("b", 50e-6, 0.5)))
    s.exclude("a")
    assert picks(s) == ["b"]
    m = s.addManual((1.0, 0.0, 0.0))
    s.exclude(m["candidate_id"])
    assert s.next(C, EVERYWHERE) == NEED_TILE


def test_lowering_the_cutoff_revives_an_old_tile_without_imaging():
    s = survey_of(tile(0.0, det("a", 0.0, 0.3)))
    assert s.next(C, EVERYWHERE) == NEED_TILE
    lower = SearchConstraints(min_health=0.2, min_cell_spacing=10e-6)
    assert s.next(lower, EVERYWHERE).entry["candidate_id"] == "a"


def test_superseded_tiles_offer_nothing_and_leave_the_footprints():
    s = survey_of(tile(0.0, det("a", 0.0)), tile(1.0, det("b", 1.0)))
    assert s.supersede(lambda r: r.header["tile_center"][0] == 0.0) == 1
    assert picks(s) == ["b"]
    assert len(s.footprints()) == 1


def test_footprints_use_each_records_own_fov_or_the_surveys():
    s = survey_of(tile(0.0, fov=[2.0, 2.0]))
    s.addTile(TileRecord(header={"tile_center": [5.0, 0.0]}, detections=()))
    assert s.footprints() == [(-1.0, -1.0, 1.0, 1.0), (5.0 - 50e-6, -50e-6, 5.0 + 50e-6, 50e-6)]


def test_preview_matches_successive_picks_without_handing_anything_out():
    records = (tile(0.0, det("a", 0.0), det("b", 50e-6, 0.8)), tile(1.0, det("c", 1.0)))
    s = survey_of(*records)
    s.addManual((2.0, 0.0, 0.0))
    preview = [e["candidate_id"] for e in s.preview(C, EVERYWHERE, n=10)]
    assert s.handedOutIds() == frozenset()
    assert preview == picks(s)


def test_preview_stops_at_n():
    s = survey_of(tile(0.0, *[det(f"a{i}", i * 20e-6) for i in range(4)]))
    assert len(s.preview(C, EVERYWHERE, n=2)) == 2


def test_a_hand_out_carries_the_survey_provenance():
    s = survey_of(tile(0.0, {**det("a", 0.0), "area": 8e-11}))
    cell = s.handOut(s.next(C, EVERYWHERE).entry)
    assert cell.candidate_id == "a"
    assert cell.source == "survey"
    assert cell.tile_id == "t0.0"
    assert cell.tile_center == (0.0, 0.0)
    assert cell.detection_prefix == "tiles/tile_0.0"
    assert (cell.score, cell.volume, cell.area) == (0.9, 1e-16, 8e-11)


def test_release_frees_a_hand_out_for_picking_again():
    s = survey_of(tile(0.0, det("a", 0.0)))
    s.handOut(s.next(C, EVERYWHERE).entry)
    s.release("a")
    assert s.next(C, EVERYWHERE).entry["candidate_id"] == "a"


def test_manual_entries_and_exclusions_are_written_to_the_slice_dir(tmp_path):
    sliceDir = dm.getDirHandle(str(tmp_path)).mkdir("slice")
    s = Survey(FOV, dirHandle=sliceDir)
    m = s.addManual((1e-6, 2e-6, 3e-6))
    s.exclude("gone")
    saved = sliceDir[MANUAL_FILE].read()
    assert saved["manual"][0]["candidate_id"] == m["candidate_id"]
    assert saved["manual"][0]["position"] == [1e-6, 2e-6, 3e-6]
    assert saved["manual"][0]["source"] == "manual"
    assert saved["excluded"] == ["gone"]
    assert "__uuid__" in sliceDir[MANUAL_FILE].info()


def test_superseding_rewrites_the_record_file(tmp_path):
    tiles = dm.getDirHandle(str(tmp_path)).mkdir("tiles")
    record = TileRecord(header={"tile_center": [0.0, 0.0]}, detections=(det("a", 0.0),),
                        recordDir=tiles, recordName="tile_x_detections.yaml")
    s = survey_of(record)
    s.supersede(lambda r: True)
    saved = tiles["tile_x_detections.yaml"].read()
    assert saved["superseded"] is True
    assert saved["detections"][0]["candidate_id"] == "a"
