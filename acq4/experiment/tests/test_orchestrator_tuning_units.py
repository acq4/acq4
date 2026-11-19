"""Tests for the tuning units the orchestrator opens: a survey unit around each
producer refill and a cell unit per processed cell, summarised into cell metadata."""

import random
import warnings
from collections import Counter

import pytest

import acq4.util.DataManager as dm
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import RetryCurrentCell
from acq4.experiment.orchestrator import Orchestrator
from acq4.util import tuning_points
from acq4.util.tests.memory_ledger import MemoryLedger
from acq4.util.tuning_points import Point, Runtime, TuningPointWarning

from .test_actions_prompt_storage import FakeManager
from .test_orchestrator_producer import make_producer

CELL_POINT = "test_cell_value"
SURVEY_POINT = "test_survey_value"


class ValueMutator:
    def __init__(self, name, unit, point, conditions):
        self.name = name
        self.unit = unit
        self.answers = {point}
        self.conditions = list(conditions)

    def eligible(self, facts):
        return True

    def value(self, point, default, condition, facts):
        return condition


class SurveyedCell:
    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return f"<cell {self._name}>"


@pytest.fixture(autouse=True)
def stray_tuning_warnings_fail():
    with warnings.catch_warnings():
        warnings.simplefilter("error", TuningPointWarning)
        yield


@pytest.fixture(autouse=True)
def test_points(monkeypatch):
    monkeypatch.setitem(
        tuning_points.POINTS,
        CELL_POINT,
        Point("value", "cell", (), "Test-only cell point.", "test"),
    )
    monkeypatch.setitem(
        tuning_points.POINTS,
        SURVEY_POINT,
        Point("value", "survey", (), "Test-only survey point.", "test"),
    )


@pytest.fixture
def slice_dir(tmp_path):
    root = dm.getDirHandle(str(tmp_path), create=True)
    return root.mkdir("slice_000", info={"dirType": "Slice"})


@pytest.fixture
def arm():
    def _arm(mutators):
        ledger = MemoryLedger(random.Random(0))
        runtime = Runtime("run-1", mutators, ledger)
        tuning_points.install(runtime)
        return ledger

    yield _arm
    tuning_points.uninstall()


def surveying_producer(batches):
    """A producer that asks the survey point on every refill, as a real survey would."""
    inner = make_producer(batches)

    def producer():
        tuning_points.value(SURVEY_POINT, None)
        return inner()

    return producer


def _orch(pf, manager, producer):
    return Orchestrator(
        pf,
        manager=manager,
        contextFactory=lambda cell: ExecutionContext(cell=cell, manager=manager),
        cellProducer=producer,
    )


def _recording_protocol(pf, cellDirs, asks=None):
    def run(ctx, **kwargs):
        cellDirs[ctx.cell] = ctx.manager.getCurrentDir()
        answer = tuning_points.value(CELL_POINT, None)
        if asks is not None:
            asks.append(answer)

    pf.run = run


def test_cell_metadata_carries_cell_and_survey_conditions(make_pf, slice_dir, arm):
    arm(
        [
            ValueMutator("cell_mut", "cell", CELL_POINT, ("x", "y")),
            ValueMutator("survey_mut", "survey", SURVEY_POINT, (1, 2)),
        ]
    )
    sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
    cells = [SurveyedCell(f"c{i}") for i in range(4)]
    surveys = [cells[:2], cells[2:]]
    pf = make_pf()
    cellDirs = {}
    _recording_protocol(pf, cellDirs)

    _orch(pf, FakeManager(slice_dir), surveying_producer([*surveys, None])).run_sync()
    tuning_points.close_unit(sliceUnit)

    blocks = {cell: cellDirs[cell].info()["performance_tuning"] for cell in cells}
    for cell, block in blocks.items():
        assert set(block["conditions"]) == {"cell_mut", "survey_mut"}
        assert block["assigned_by"] == {"cell_mut": "cell", "survey_mut": "survey"}
        assert block["survey_id"] == cell.tuningSurveyId
    for survey in surveys:
        first, second = (blocks[cell] for cell in survey)
        assert first["survey_id"] == second["survey_id"]
        assert first["conditions"]["survey_mut"] == second["conditions"]["survey_mut"]
    assert blocks[cells[0]]["survey_id"] != blocks[cells[2]]["survey_id"]


def test_balance_holds_through_the_slice(make_pf, slice_dir, arm):
    ledger = arm([ValueMutator("cell_mut", "cell", CELL_POINT, ("x", "y"))])
    sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
    cells = [SurveyedCell(f"c{i}") for i in range(4)]
    pf = make_pf()
    cellDirs = {}
    _recording_protocol(pf, cellDirs)

    _orch(
        pf, FakeManager(slice_dir), make_producer([cells[:1], cells[1:], None])
    ).run_sync()
    tuning_points.close_unit(sliceUnit)

    assigned = Counter(
        cellDirs[cell].info()["performance_tuning"]["conditions"]["cell_mut"]
        for cell in cells
    )
    assert assigned == {"x": 2, "y": 2}
    opened = [line for line in ledger.lines if line["event"] == "unit_open"]
    closed = [line for line in ledger.lines if line["event"] == "unit_close"]
    assert Counter(line["unit"] for line in opened) == {
        "slice": 1,
        "survey": 3,
        "cell": 4,
    }
    assert sorted(line["unit_id"] for line in opened) == sorted(
        line["unit_id"] for line in closed
    )
    for line in opened:
        if line["unit"] != "slice":
            assert line["parent_id"] == sliceUnit.id


def test_retry_stays_in_one_cell_unit(make_pf, slice_dir, arm):
    ledger = arm([ValueMutator("cell_mut", "cell", CELL_POINT, ("x", "y"))])
    sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
    cell = SurveyedCell("c0")
    pf = make_pf()
    cellDirs = {}
    asks = []

    def run(ctx, **kwargs):
        cellDirs[ctx.cell] = ctx.manager.getCurrentDir()
        asks.append(tuning_points.value(CELL_POINT, None))
        if len(asks) == 1:
            raise RetryCurrentCell("again")

    pf.run = run
    _orch(pf, FakeManager(slice_dir), make_producer([[cell], None])).run_sync()
    tuning_points.close_unit(sliceUnit)

    assert asks[0] == asks[1]
    cellUnits = [
        line
        for line in ledger.lines
        if line["event"] == "unit_open" and line["unit"] == "cell"
    ]
    assert len(cellUnits) == 1
    assert len(ledger.decision_lines("cell_mut")) == 1
    block = cellDirs[cell].info()["performance_tuning"]
    assert block["fired"] == {"cell_mut": {CELL_POINT: 2}}


def test_no_metadata_when_nothing_installed(make_pf, slice_dir):
    cells = [SurveyedCell(f"c{i}") for i in range(2)]
    pf = make_pf()
    cellDirs = {}
    _recording_protocol(pf, cellDirs)

    _orch(pf, FakeManager(slice_dir), surveying_producer([cells, None])).run_sync()

    for cell in cells:
        assert "performance_tuning" not in cellDirs[cell].info()
