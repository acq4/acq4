"""Tests for the tuning units the orchestrator opens: a survey unit around each
producer refill and a cell unit per processed cell, summarised into cell metadata."""

import logging
import random
import threading
import warnings
from collections import Counter

import pytest

import acq4.util.DataManager as dm
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AbortExperiment, RetryCurrentCell
from acq4.experiment.orchestrator import Orchestrator
from acq4.util import tuning_points
from acq4.util.tests.memory_ledger import MemoryLedger
from acq4.util.tuning_points import Point, Runtime, TuningPointWarning

from .test_actions_device import FakePipette
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
    def _arm(mutators, cell_close_hook=None):
        ledger = MemoryLedger(random.Random(0))
        runtime = Runtime("run-1", mutators, ledger, cell_close_hook=cell_close_hook)
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


def test_summary_is_written_when_stopped_with_a_pause_pending(
    make_pf, slice_dir, arm, qtbot
):
    arm([ValueMutator("cell_mut", "cell", CELL_POINT, ("x", "y"))])
    sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
    cell = SurveyedCell("c0")
    pf = make_pf()
    cellDirs = {}
    asked = threading.Event()
    gate = threading.Event()

    def run(ctx, **kwargs):
        cellDirs[ctx.cell] = ctx.manager.getCurrentDir()
        tuning_points.value(CELL_POINT, None)
        asked.set()
        gate.wait(5)

    pf.run = run
    orch = _orch(pf, FakeManager(slice_dir), make_producer([[cell], None]))
    task = orch.start()
    try:
        qtbot.waitUntil(asked.is_set, timeout=5000)
        orch.pause()
        orch.stop("test stop")
    finally:
        gate.set()
        task.wait(timeout=5)
        tuning_points.close_unit(sliceUnit)

    assert "cell_mut" in cellDirs[cell].info()["performance_tuning"]["conditions"]


class PositionedCell(SurveyedCell):
    position = (0.0, 0.0, -50e-6)


def _failing_hook(cell_dir):
    raise RuntimeError("provenance hook broke")


def _pipetted_orch(pf, manager, pipette, producer):
    return Orchestrator(
        pf,
        manager=manager,
        contextFactory=lambda cell: ExecutionContext(
            cell=cell, manager=manager, pipette=pipette
        ),
        cellProducer=producer,
    )


def test_close_out_failure_on_a_normal_pass_halts_the_run(
    make_pf, slice_dir, arm, caplog
):
    arm(
        [ValueMutator("cell_mut", "cell", CELL_POINT, ("x", "y"))],
        cell_close_hook=_failing_hook,
    )
    sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
    pip = FakePipette()
    manager = FakeManager(slice_dir)
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: tuning_points.value(CELL_POINT, None)
    orch = _pipetted_orch(
        pf, manager, pip, make_producer([[PositionedCell("c0")], None])
    )
    errors = []
    orch.sigRunError.connect(errors.append)

    try:
        with caplog.at_level(logging.ERROR, logger="acq4.experiment.orchestrator"):
            with pytest.raises(AbortExperiment) as exc:
                orch.run_sync()
    finally:
        tuning_points.close_unit(sliceUnit)

    assert isinstance(exc.value.__cause__, RuntimeError)
    assert "provenance hook broke" in str(exc.value)
    assert [r.exc_type for r in errors] == ["RuntimeError"]
    assert len(pip.pipetteDevice.park_calls) == 1
    assert manager.current_dir is slice_dir
    assert [r.getMessage().splitlines()[0] for r in caplog.records] == [
        "Failed to record the tuning summary for cell <cell c0>:"
    ]


def test_close_out_failure_does_not_replace_the_protocols_failure(
    make_pf, slice_dir, arm, caplog
):
    arm(
        [ValueMutator("cell_mut", "cell", CELL_POINT, ("x", "y"))],
        cell_close_hook=_failing_hook,
    )
    sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
    pip = FakePipette()
    pf = make_pf()

    def run(ctx, **kwargs):
        tuning_points.value(CELL_POINT, None)
        raise ValueError("the real failure")

    pf.run = run
    orch = _pipetted_orch(
        pf, FakeManager(slice_dir), pip, make_producer([[PositionedCell("c0")], None])
    )
    errors = []
    orch.sigRunError.connect(errors.append)

    try:
        with caplog.at_level(logging.ERROR, logger="acq4.experiment.orchestrator"):
            with pytest.raises(AbortExperiment) as exc:
                orch.run_sync()
    finally:
        tuning_points.close_unit(sliceUnit)

    assert "the real failure" in str(exc.value)
    assert [r.exc_type for r in errors] == ["ValueError"]
    assert len(pip.pipetteDevice.park_calls) == 1
    messages = [r.getMessage() for r in caplog.records]
    assert messages[0].startswith("Unexpected exception while processing cell")
    assert messages[1].startswith(
        "Failed to record the tuning summary for cell <cell c0>:"
    )
    assert "provenance hook broke" in messages[1]
    assert len(messages) == 2
