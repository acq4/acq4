"""Tests for Survey: the slice's facts and the selector that picks the next cell
from them under the current constraints."""

import threading
import uuid

import pytest

import acq4.util.DataManager as dm
from acq4.experiment import survey as survey_mod
from acq4.experiment.orchestrator import _cellDirInfo, _cellMetadata, _saveCellMetadata
from acq4.experiment.slice import SearchConstraints
from acq4.experiment.survey import MANUAL_FILE, NEED_TILE, Survey, TileRecord
from acq4.experiment.survey_record import CELL_METADATA_FILE, writeRecord

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
    better_first = survey_of(tile(0.0, det("dupB", 50e-6, 0.95)), tile(1.0, det("dupA", 51e-6, 0.7)))
    assert picks(better_first) == ["dupB"]


def test_an_equal_score_cross_tile_duplicate_goes_to_the_earlier_tile():
    assert picks(survey_of(tile(0.0, det("dupB", 50e-6, 0.9)), tile(1.0, det("dupA", 51e-6, 0.9)))) == ["dupB"]
    assert picks(survey_of(tile(0.0, det("dupA", 50e-6, 0.9)), tile(1.0, det("dupB", 51e-6, 0.9)))) == ["dupA"]


def test_equal_scores_within_a_tile_keep_the_detectors_order():
    s = survey_of(tile(0.0, det("z", 0.0, 0.9), det("a", 30e-6, 0.9), det("m", 60e-6, 0.9)))
    assert picks(s) == ["z", "a", "m"]


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


def test_requeued_ids_are_the_handed_out_cells_waiting_for_another_pass():
    s = survey_of(tile(0.0, det("a", 0.0), det("b", 50e-6), det("c", 100e-6)))
    first = s.handOut(s.next(C, EVERYWHERE).entry)
    s.handOut(s.next(C, EVERYWHERE).entry)
    manual = s.addManual((1e-3, 0.0, 0.0))
    assert s.requeuedIds() == frozenset()

    s.requeue(first)
    assert s.requeuedIds() == frozenset({first.candidate_id})
    assert manual["candidate_id"] not in s.requeuedIds()

    assert first.candidate_id in picks(s)
    assert s.requeuedIds() == frozenset()


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


def test_two_concurrent_hand_outs_of_one_entry_build_unlocked_and_share_one_cell(monkeypatch):
    bothBuilding = threading.Barrier(2, timeout=2)

    def slowCell(position):
        bothBuilding.wait()
        return Cell(position)

    monkeypatch.setattr(survey_mod, "_newCell", slowCell)
    s = survey_of(tile(0.0, det("a", 0.0)))
    entry = s.next(C, EVERYWHERE).entry
    cells = []
    workers = [threading.Thread(target=lambda: cells.append(s.handOut(entry))) for _ in range(2)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert len(cells) == 2
    assert cells[0] is cells[1]
    assert s.handedOut() == [cells[0]]


def test_releasing_a_manual_hand_out_offers_it_again():
    s = Survey(FOV)
    m = s.addManual((1e-3, 0.0, 0.0))
    s.handOut(s.next(C, EVERYWHERE).entry)
    assert s.next(C, EVERYWHERE) == NEED_TILE
    s.release(m["candidate_id"])
    assert s.next(C, EVERYWHERE).entry["candidate_id"] == m["candidate_id"]


def test_releasing_an_excluded_manual_hand_out_leaves_it_excluded():
    s = Survey(FOV)
    m = s.addManual((1e-3, 0.0, 0.0))
    s.handOut(s.next(C, EVERYWHERE).entry)
    s.exclude(m["candidate_id"])
    s.release(m["candidate_id"])
    assert s.next(C, EVERYWHERE) == NEED_TILE


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


# ---- loading back ----


def slice_dir(tmp_path):
    return dm.getDirHandle(str(tmp_path), create=True).mkdir("slice")


def write_tile(sliceDir, name, record, **written):
    tiles = sliceDir.getDir("tiles", create=True)
    writeRecord(tiles, name, {**record.header, **written, "detections": list(record.detections)})
    return TileRecord(record.header, record.detections, tiles, name, bool(written.get("superseded")))


def cell_dir(sliceDir, name, position=None, metadata=True, location=None, disposition=None, **fields):
    """A Cell dir written the way the orchestrator writes one, with `fields` as
    the cell's provenance attributes."""
    handle = sliceDir.mkdir(name, info={"dirType": "Cell"})
    cell = Cell(position)
    cell.initialPosition = position
    for key, value in fields.items():
        setattr(cell, key, value)
    if metadata:
        _saveCellMetadata(cell, handle)
    else:
        handle.setInfo(_cellDirInfo(_cellMetadata(cell)))
    overrides = {"location": location, "disposition": disposition}
    handle.setInfo({k: v for k, v in overrides.items() if v is not None})
    return handle


def loaded(sliceDir):
    s = Survey(FOV, dirHandle=sliceDir)
    s.load(sliceDir)
    return s


def test_load_reads_tile_records_in_name_order_and_keeps_superseded(tmp_path):
    sliceDir = slice_dir(tmp_path)
    write_tile(sliceDir, "tile_b_detections.yaml", tile(1.0, det("b", 1.0)))
    write_tile(sliceDir, "tile_a_detections.yaml", tile(0.0, det("a", 0.0)), superseded=True)
    s = loaded(sliceDir)
    assert [r.recordName for r in s.tiles()] == ["tile_a_detections.yaml", "tile_b_detections.yaml"]
    assert [r.superseded for r in s.tiles()] == [True, False]
    assert s.tiles()[0].header == tile(0.0).header
    assert s.tiles()[0].detections == (det("a", 0.0),)
    assert s.tiles()[0].recordDir.name() == sliceDir["tiles"].name()
    assert picks(s) == ["b"]


def test_load_puts_unattempted_manual_entries_back_on_intent_and_keeps_exclusions(tmp_path):
    sliceDir = slice_dir(tmp_path)
    original = Survey(FOV, dirHandle=sliceDir)
    write_tile(sliceDir, "tile_a_detections.yaml", tile(0.0, det("a", 0.0), det("b", 50e-6)))
    tried = original.addManual((1e-3, 0.0, 0.0))
    waiting = original.addManual((2e-3, 0.0, 0.0))
    original.exclude("a")
    cell_dir(sliceDir, "cell_000", tried["position"], candidate_id=tried["candidate_id"], source="manual")

    s = loaded(sliceDir)
    assert s.excluded() == frozenset({"a"})
    assert s.handedOutIds() == frozenset({tried["candidate_id"]})
    assert picks(s) == [waiting["candidate_id"], "b"]


def test_load_rebuilds_a_cell_dir_as_a_hand_out_that_blocks_its_neighbours(tmp_path):
    sliceDir = slice_dir(tmp_path)
    record = tile(0.0, det("a", 0.0), det("near", 5e-6, 0.8), det("far", 50e-6, 0.7))
    write_tile(sliceDir, "tile_a_detections.yaml", record)
    handle = cell_dir(sliceDir, "cell_000", (0.0, 0.0, 0.0), candidate_id="a", source="survey",
                      disposition="patched")
    s = loaded(sliceDir)
    [cell] = s.handedOut()
    assert cell.candidate_id == "a"
    assert cell.tile_id == "t0.0"
    assert cell.cell_dir.name() == handle.name()
    assert cell.disposition == "patched"
    assert picks(s) == ["far"]


def test_loaded_hand_outs_count_toward_the_tile_cap(tmp_path):
    sliceDir = slice_dir(tmp_path)
    first = tile(0.0, *[det(f"a{i}", i * 20e-6, 0.9 - i * 0.01) for i in range(7)])
    write_tile(sliceDir, "tile_a_detections.yaml", first)
    write_tile(sliceDir, "tile_b_detections.yaml", tile(1.0, det("b0", 1.0)))
    for i in range(5):
        cell_dir(sliceDir, f"cell_{i:03d}", (i * 20e-6, 0.0, 0.0), candidate_id=f"a{i}")
    assert picks(loaded(sliceDir)) == ["b0"]


def test_a_cell_dir_without_a_candidate_id_gets_a_manual_entry_at_its_initial_position(tmp_path):
    sliceDir = slice_dir(tmp_path)
    write_tile(sliceDir, "tile_a_detections.yaml", tile(0.0, det("near", 5e-6), det("far", 50e-6)))
    cell_dir(sliceDir, "cell_000", (1e-6, 0.0, 0.0), location="(900.0, 0.0, 0.0) um")
    s = loaded(sliceDir)
    [entry] = s.manualEntries()
    assert entry["position"] == [1e-6, 0.0, 0.0]
    assert entry["source"] == "manual"
    [cell] = s.handedOut()
    assert cell.candidate_id == entry["candidate_id"]
    assert cell.cell_dir.name() == sliceDir["cell_000"].name()
    assert picks(s) == ["far"]
    assert not sliceDir.exists(MANUAL_FILE)


def test_a_cell_dir_without_metadata_is_placed_from_its_location(tmp_path):
    sliceDir = slice_dir(tmp_path)
    cell_dir(sliceDir, "cell_000", (12e-6, -3.5e-6, 40e-6), metadata=False, candidate_id="lost", source="survey")
    s = loaded(sliceDir)
    [entry] = s.manualEntries()
    assert entry["candidate_id"] == "lost"
    assert entry["source"] == "survey"
    assert entry["position"] == pytest.approx([12e-6, -3.5e-6, 40e-6])
    assert s.handedOutIds() == frozenset({"lost"})
    assert s.next(C, EVERYWHERE) == NEED_TILE


def test_a_cell_dir_with_no_position_is_skipped_and_logged(tmp_path, caplog):
    sliceDir = slice_dir(tmp_path)
    cell_dir(sliceDir, "cell_000", candidate_id="nowhere")
    s = loaded(sliceDir)
    assert s.handedOut() == []
    assert s.manualEntries() == ()
    assert "cell_000" in caplog.text


def test_a_malformed_tile_record_is_skipped_and_logged(tmp_path, caplog):
    sliceDir = slice_dir(tmp_path)
    tiles = sliceDir.getDir("tiles", create=True)
    with open(f"{tiles.name()}/tile_a_detections.yaml", "w") as fh:
        fh.write("tile_center: [0.0, 0.0\n")
    tiles.writeFile(["not", "a", "mapping"], "tile_b_detections.yaml", fileType="YamlFile")
    write_tile(sliceDir, "tile_c_detections.yaml", tile(2.0, det("c", 2.0)))
    s = loaded(sliceDir)
    assert [r.recordName for r in s.tiles()] == ["tile_c_detections.yaml"]
    assert "tile_a_detections.yaml" in caplog.text
    assert "tile_b_detections.yaml" in caplog.text


def test_load_gives_back_the_preview_the_saved_survey_gave(tmp_path):
    sliceDir = slice_dir(tmp_path)
    original = Survey(FOV, dirHandle=sliceDir)
    first = tile(0.0, *[det(f"a{i}", i * 20e-6, 0.9 - i * 0.01) for i in range(7)])
    second = tile(1.0, det("b0", 1.0), det("b1", 1.0 + 3e-6, 0.95), det("b2", 1.0 + 40e-6, 0.4))
    original.addTile(write_tile(sliceDir, "tile_20250101_000000_000000_aaaaaaaa_detections.yaml", first))
    original.addTile(write_tile(sliceDir, "tile_20250101_000001_000000_bbbbbbbb_detections.yaml", second))
    original.addManual((2.0, 0.0, 0.0))
    original.addManual((3.0, 0.0, 0.0))
    original.exclude("a3")
    for i in range(3):
        cell = original.handOut(original.next(C, EVERYWHERE).entry)
        cell_dir(sliceDir, f"cell_{i:03d}", cell.position, candidate_id=cell.candidate_id, source=cell.source)
    expected = original.preview(C, EVERYWHERE, n=20)

    s = loaded(sliceDir)
    assert s.handedOutIds() == original.handedOutIds()
    assert s.preview(C, EVERYWHERE, n=20) == expected


def test_a_cell_dir_without_a_candidate_id_keeps_its_id_across_resumes(tmp_path):
    sliceDir = slice_dir(tmp_path)
    worked = sliceDir.mkdir("cell_000", info={"dirType": "Cell", "location": "(1.0, 0.0, 0.0) um"})
    first = loaded(sliceDir)
    assert first.handedOutIds() == frozenset({worked.info()["__uuid__"]})
    first.exclude("unrelated")

    again = loaded(sliceDir)
    assert again.handedOutIds() == first.handedOutIds()
    assert again.next(C, EVERYWHERE) == NEED_TILE


def test_a_cell_dir_without_any_uuid_is_named_by_its_path_in_the_slice(tmp_path):
    sliceDir = slice_dir(tmp_path)
    sliceDir.mkdir("cell_000", info={"dirType": "Cell", "__uuid__": None, "location": "(1.0, 0.0, 0.0) um"})
    expected = uuid.uuid5(uuid.NAMESPACE_URL, "cell_000").hex
    assert loaded(sliceDir).handedOutIds() == frozenset({expected})
    assert loaded(sliceDir).handedOutIds() == frozenset({expected})


def test_a_second_cell_dir_for_one_candidate_takes_over_and_is_logged(tmp_path, caplog):
    sliceDir = slice_dir(tmp_path)
    write_tile(sliceDir, "tile_a_detections.yaml", tile(0.0, det("a", 0.0)))
    cell_dir(sliceDir, "cell_000", (0.0, 0.0, 0.0), candidate_id="a")
    cell_dir(sliceDir, "cell_001", (0.0, 0.0, 0.0), candidate_id="a")
    with caplog.at_level("INFO", logger=survey_mod.logger.name):
        [cell] = loaded(sliceDir).handedOut()
    assert cell.cell_dir.name() == sliceDir["cell_001"].name()
    [message] = [r.getMessage() for r in caplog.records if "cell_000" in r.getMessage()]
    assert "cell_001" in message


def test_a_malformed_cell_metadata_file_falls_back_to_the_location_and_is_logged(tmp_path, caplog):
    sliceDir = slice_dir(tmp_path)
    for name, location in (("cell_000", "(7.0, 0.0, 0.0) um"), ("cell_001", None)):
        handle = cell_dir(sliceDir, name, metadata=False, candidate_id=name, location=location)
        with open(f"{handle.name()}/{CELL_METADATA_FILE}", "w") as fh:
            fh.write("initial_position: [1.0, 2.0\n")
    s = loaded(sliceDir)
    assert s.handedOutIds() == frozenset({"cell_000"})
    [entry] = s.manualEntries()
    assert entry["position"] == pytest.approx([7e-6, 0.0, 0.0])
    assert f"cell_000/{CELL_METADATA_FILE}" in caplog.text
    assert f"cell_001/{CELL_METADATA_FILE}" in caplog.text
    assert "Skipping the Cell dir" in caplog.text


@pytest.mark.parametrize("fill", [
    lambda s: s.addTile(tile(0.0)),
    lambda s: s.addManual((0.0, 0.0, 0.0)),
    lambda s: s.handOut(det("a", 0.0)),
])
def test_load_refuses_a_survey_that_already_holds_anything(tmp_path, fill):
    sliceDir = slice_dir(tmp_path)
    s = Survey(FOV)
    fill(s)
    with pytest.raises(RuntimeError, match="Survey.load needs an empty survey"):
        s.load(sliceDir)
