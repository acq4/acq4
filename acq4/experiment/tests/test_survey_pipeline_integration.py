"""Integration: an orchestrator run pulling cells one at a time from a slice's
survey across two overlapping tiles and a hand seed, onto a real Data Manager
directory, with synthetic imaging and detections."""

from acq4.experiment import survey as survey_mod
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.survey import MANUAL_FILE

from .test_survey_record_integration import buildSurveyedSlice
from .test_tile_detector import FakeCell


def test_a_run_works_the_hand_seed_first_then_each_tile_one_cell_at_a_time(tmp_path, monkeypatch, make_pf):
    monkeypatch.setattr(survey_mod, "_newCell", FakeCell)
    sliceDir, slice_, detector, scope = buildSurveyedSlice(tmp_path, monkeypatch)
    manual = slice_.survey.addManual((500e-6, 50e-6, -530e-6))
    pf = make_pf()
    ran, tilesImagedAtEachCell = [], []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        tilesImagedAtEachCell.append(len(scope.moves))

    pf.run = run
    Orchestrator(pf, cellProducer=slice_.makeCellProducer(detector)).run_sync()

    assert ran[0].candidate_id == manual["candidate_id"]
    assert tilesImagedAtEachCell[0] == 0
    sources = [c.source for c in ran]
    assert sources == ["manual", "survey", "survey", "survey"]
    xs = sorted(round(c.position[0] * 1e6) for c in ran[1:])
    assert len([x for x in xs if 94 <= x <= 97]) == 1, "the shared cell is worked once"
    assert tilesImagedAtEachCell == [0, 1, 1, 2], tilesImagedAtEachCell
    saved = sliceDir[MANUAL_FILE].read()
    assert [e["candidate_id"] for e in saved["manual"]] == [manual["candidate_id"]]
    records = [r for r in slice_.survey.tiles()]
    assert len(records) == 2 and all(r.header["fov"] == [100e-6, 100e-6] for r in records)
    assert slice_.nextTile() is None
