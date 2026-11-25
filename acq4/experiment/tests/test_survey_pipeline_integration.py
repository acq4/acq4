"""Integration: an orchestrator run pulling cells one at a time from a slice's
survey across two overlapping tiles and a hand seed, onto a real Data Manager
directory, with synthetic imaging and detections."""

from acq4.experiment.context import ExecutionContext
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.survey import MANUAL_FILE

from .test_actions_prompt_storage import FakeManager
from .test_survey_record_integration import buildSurveyedSlice


def test_a_run_works_the_hand_seed_first_then_each_tile_one_cell_at_a_time(tmp_path, monkeypatch, make_pf):
    sliceDir, slice_, detector, scope = buildSurveyedSlice(tmp_path, monkeypatch)
    manual = slice_.survey.addManual((500e-6, 50e-6, -530e-6))
    pf = make_pf()
    manager = FakeManager(sliceDir)
    ran, cellDirs, tilesImagedAtEachCell = [], [], []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        cellDirs.append(ctx.manager.getCurrentDir())
        tilesImagedAtEachCell.append(len(scope.moves))

    pf.run = run
    Orchestrator(
        pf,
        manager=manager,
        contextFactory=lambda cell: ExecutionContext(cell=cell, manager=manager),
        cellProducer=slice_.makeCellProducer(detector),
    ).run_sync()

    assert ran[0].candidate_id == manual["candidate_id"]
    assert tilesImagedAtEachCell[0] == 0
    sources = [c.source for c in ran]
    assert sources == ["manual", "survey", "survey", "survey"]
    xs = sorted(round(c.position[0] * 1e6) for c in ran[1:])
    assert len([x for x in xs if 94 <= x <= 97]) == 1, "the shared cell is worked once"
    assert tilesImagedAtEachCell == [0, 1, 1, 2], tilesImagedAtEachCell
    assert len({d.name() for d in cellDirs}) == len(ran)
    for cell, cellDir in zip(ran, cellDirs):
        info = cellDir.info()
        assert info["dirType"] == "Cell"
        assert cellDir.parent().name() == sliceDir.name()
        assert (info["candidate_id"], info["source"]) == (cell.candidate_id, cell.source)
    saved = sliceDir[MANUAL_FILE].read()
    assert [e["candidate_id"] for e in saved["manual"]] == [manual["candidate_id"]]
    records = list(slice_.survey.tiles())
    assert len(records) == 2 and all(r.header["fov"] == [100e-6, 100e-6] for r in records)
    assert slice_.nextTile() is None
