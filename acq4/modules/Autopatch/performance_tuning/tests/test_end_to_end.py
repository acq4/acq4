"""End-to-end tests: a catalogue becomes a run group, runs through the orchestrator, and is analysed and accepted."""

import json
import shutil
import warnings
from collections import Counter
from datetime import datetime

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.experiment.actions.fsm import patch
from acq4.experiment.context import ExecutionContext
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.protocol_file import ProtocolFile
from acq4.experiment.tests.conftest import FakePatchPipette
from acq4.experiment.tests.test_actions_device import FakePipetteDevice
from acq4.modules.Autopatch.performance_tuning import (
    arming,
    brief,
    catalogue,
    join,
    lifecycle,
    provenance,
    record,
    report,
    scaffold,
    tracking,
)
from acq4.modules.Autopatch.performance_tuning.ledger import JsonlLedger, ledger_path
from acq4.modules.Autopatch.performance_tuning.mutators import MUTATORS
from acq4.modules.Autopatch.performance_tuning.window import TuningWindow
from acq4.modules.Autopatch.tests.conftest import fakeManager  # noqa: F401
from acq4.modules.Autopatch.tests.test_window_integration import _makeWindow, qapp
from acq4.util import tuning_points
from acq4.util.tuning_points import TuningPointWarning

from .conftest import write_log
from .test_window import ANALYZE_SCRIPT

PROTOCOL = "acq4/modules/Autopatch/example_protocols/_example_patch.py"
NOTES = "Health cutoff acts on queueing, seal timeout inside patching. — test"
RUN_ID = "run-e2e"
EXPECTED_KEYS = (
    "n_units",
    "n_cells",
    "n_whole_cell",
    "minutes_per_whole_cell",
    "minutes_fallback_cells",
    "whole_cells_per_slice",
)
SURVEYS_WITH_CELLS = 2


class _Cell:
    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return f"<cell {self._name}>"


class _StateManager:
    def getProfile(self):
        return "default"


class _PatchingPipette(FakePatchPipette):
    """A FakePatchPipette that reaches whole cell on every patch, parks at home, and notes the seal timeout it ran under."""

    def __init__(self, profiles):
        super().__init__()
        self._profiles = profiles
        self.pipetteDevice = FakePipetteDevice([])
        self.pipetteDevice.global_position = self.pipetteDevice.home_position
        self.sealTimeouts = []

    def stateManager(self):
        return _StateManager()

    def setState(self, state, **config):
        if state == "approach":
            self.sealTimeouts.append(
                self._profiles["default"]["seal"]["autoSealTimeout"]
            )
            self._seq = ["seal", "cell attached", "whole cell"]
        return super().setState(state, **config)


@pytest.fixture(autouse=True)
def _clean():
    tuning_points.uninstall()
    with warnings.catch_warnings():
        warnings.simplefilter("error", TuningPointWarning)
        yield
    tuning_points.uninstall()


@pytest.fixture
def profiles(monkeypatch):
    store = {"default": {"seal": {"autoSealTimeout": 45.0}}}
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


@pytest.fixture
def config_dir(fakeManager, tmp_path):
    fakeManager.configDir = str(tmp_path / "config")
    return fakeManager.configDir


@pytest.fixture
def autopatch(qapp, tmp_path, config_dir, cat_path):
    w = _makeWindow(tmp_path)
    w.tuningTrialsDir = tmp_path / "trials"
    w.tuningCataloguePath = cat_path
    yield w
    w.teardown()


def _factors(cat_path, *names):
    entries = {f.name: f for f in catalogue.load(cat_path)}
    return [entries[n] for n in names]


def _spans(lines):
    opened, spans = {}, {}
    for line in lines:
        key = (line.get("unit"), line.get("unit_id"))
        if line.get("event") == "unit_open":
            opened[key] = datetime.fromisoformat(line["t"])
        elif line.get("event") == "unit_close":
            spans[key] = (
                datetime.fromisoformat(line["t"]) - opened[key]
            ).total_seconds()
    return spans


def _tracking_row(text, name):
    (line,) = [l for l in text.splitlines() if l.startswith(f"| {name} |")]
    return [cell.strip() for cell in line.strip("|").split("|")]


def _surveying_producer(batches):
    def producer():
        tuning_points.value("min_health", 0.5, facts={"score": 0.9})
        return batches.pop(0)

    return producer


def _patching_protocol(tmp_path, cellDirs):
    path = tmp_path / "patching_protocol.py"
    path.write_text("PARAMS = []\n\n\ndef run(ctx, **kwargs):\n    return None\n")
    pf = ProtocolFile(str(path))
    pf.load()

    def run(ctx, **kwargs):
        cellDirs.append(ctx.manager.getCurrentDir())
        patch(ctx, record_events=False)

    pf.run = run
    return pf


def test_catalogue_to_report_through_the_orchestrator(
    autopatch, fakeManager, config_dir, cat_path, tmp_path, profiles
):
    trials_dir = tmp_path / "trials"
    trials = scaffold.new_run_group(
        _factors(cat_path, "seal_timeout", "min_health"),
        PROTOCOL,
        interactions_expected=False,
        interaction_notes=NOTES,
        run_id=RUN_ID,
        trials_dir=trials_dir,
        catalogue_path=cat_path,
    )
    autopatch.newSlice()
    slice_dir = autopatch.slice.dirHandle
    ledger = JsonlLedger(ledger_path(fakeManager, RUN_ID))
    hook = provenance.make_cell_close_hook(
        str(record.acq4_root() / PROTOCOL), config_dir
    )
    arming.arm(
        autopatch, RUN_ID, record.instantiate(trials[0]), ledger, cell_close_hook=hook
    )

    cells = [_Cell(f"c{i}") for i in range(6)]
    # Unequal surveys, so a swapped survey condition changes per-condition cell counts.
    batches = [cells[:4], cells[4:], None]
    pip = _PatchingPipette(profiles)
    cellDirs = []
    Orchestrator(
        _patching_protocol(tmp_path, cellDirs),
        manager=fakeManager,
        contextFactory=lambda cell: ExecutionContext(
            cell=cell, manager=fakeManager, pipette=pip
        ),
        cellProducer=_surveying_producer(batches),
    ).run_sync()
    arming.disarm(autopatch)

    assert len(cellDirs) == len(cells)
    blocks = [d.info()["performance_tuning"] for d in cellDirs]
    for block in blocks:
        assert block["run_id"] == RUN_ID
        assert set(block["conditions"]) == {"seal_timeout", "min_health"}
        assert set(block["provenance"]) == {"acq4", "config", "protocol_sha256"}
        assert block["provenance"]["acq4"]["sha"]
    assert pip.sealTimeouts == [b["conditions"]["seal_timeout"] for b in blocks]
    assert Counter(b["conditions"]["seal_timeout"] for b in blocks) == {
        30.0: 3,
        60.0: 3,
    }
    assert profiles["default"]["seal"]["autoSealTimeout"] == 45.0

    lines = ledger.lines()
    for event in ("unit_open", "unit_close"):
        assert Counter(l["unit"] for l in lines if l.get("event") == event) == {
            "slice": 1,
            "survey": SURVEYS_WITH_CELLS + 1,
            "cell": len(cells),
        }

    # Whole cell depends on the condition, so swapped attribution changes the numbers.
    whole = [
        b["conditions"]["seal_timeout"] == 60.0 or i == 0 for i, b in enumerate(blocks)
    ]
    for d, is_whole in zip(cellDirs, whole):
        write_log(d, duration=60.0, whole_cell=is_whole)
    lifecycle.link_data(trials_dir, trials[0], [slice_dir.name()])

    spans = _spans(lines)
    survey_conditions = {
        l["unit_id"]: l["condition"]
        for l in lines
        if l.get("event") == "decision" and l["mutator"] == "min_health"
    }
    assert len(survey_conditions) == SURVEYS_WITH_CELLS + 1
    for block in blocks:
        assert (
            block["conditions"]["min_health"] == survey_conditions[block["survey_id"]]
        )
    cell_facts = [
        {
            "conditions": b["conditions"],
            "survey_id": b["survey_id"],
            "whole": is_whole,
            "seconds": spans[("cell", d.info()["__uuid__"])],
        }
        for b, d, is_whole in zip(blocks, cellDirs, whole)
    ]

    for trial in trials:
        trial = record.load(trial.dir)
        frame = join.attempts_with_conditions(trial.dir / "data", RUN_ID)
        out = trial.dir / "analyses" / "001-e2e" / "out"
        summary = report.write(frame, trial, out)
        assert (
            report.validate_summary(json.loads((out / "summary.json").read_text()))
            == []
        )
        factor = trial.primary_factor
        assert summary["primary_factor"] == factor
        assert summary["unit"] == MUTATORS[factor].unit
        assert not summary["no_units_assigned"]
        for condition in MUTATORS[factor].conditions:
            cells_here = [c for c in cell_facts if c["conditions"][factor] == condition]
            if factor == "min_health":
                units = {c["survey_id"] for c in cells_here}
                extra = sum(
                    spans[("survey", survey_id)]
                    for survey_id, c in survey_conditions.items()
                    if c == condition
                )
            else:
                units, extra = cells_here, 0.0
            n_whole = sum(c["whole"] for c in cells_here)
            minutes = (sum(c["seconds"] for c in cells_here) + extra) / 60.0
            (actual,) = [
                c for c in summary["conditions"] if c["condition"] == condition
            ]
            assert {k: actual[k] for k in EXPECTED_KEYS} == {
                "n_units": len(units),
                "n_cells": len(cells_here),
                "n_whole_cell": n_whole,
                "minutes_per_whole_cell": (
                    pytest.approx(minutes / n_whole) if n_whole else None
                ),
                "minutes_fallback_cells": 0,
                "whole_cells_per_slice": float(n_whole),
            }


def test_generate_arm_analyse_and_accept_through_the_window(
    autopatch, qtbot, cat_path, tmp_path, dataset
):
    real_tracking = tracking.DEFAULT_OUT.read_text()
    tw = TuningWindow(
        autopatch=autopatch,
        trials_dir=autopatch.tuningTrialsDir,
        catalogue_path=autopatch.tuningCataloguePath,
    )
    try:
        seal, health = tw.newRunGroup(
            _factors(cat_path, "seal_timeout", "min_health"),
            PROTOCOL,
            interactions_expected=False,
            interaction_notes=NOTES,
            run_id="run-a",
        )
        autopatch.newSlice()
        tw.arm(seal)
        tw.linkData(seal, [s.name() for s in dataset["slices"].values()])

        d = brief.next_analysis_dir(record.load(seal.dir), "basic")
        (d / "analyze.py").write_text(ANALYZE_SCRIPT)
        tw.runAnalysis(d)
        qtbot.waitUntil(lambda: tw.lastRun is not None, timeout=60000)
        assert tw.lastRun["exit_code"] == 0, tw.lastRun["output"]

        tw.accept(seal, d, "Halving the timeout costs nothing.")
        tw.disarm()
    finally:
        tw.close()

    seal, health = record.load(seal.dir), record.load(health.dir)
    assert (seal.status, health.status) == ("closed", "collecting")
    assert seal.verdict == "Halving the timeout costs nothing."
    assert seal.results["analysis"] == d.name
    # The dataset fixture has no ledger, so wall clock falls back to attempt durations:
    # 30.0 is c1 (whole, 60 s, A), c3 (180 s, A), c5 (whole, 60 s, B, access 20 MΩ);
    # 60.0 is c2 (120 s, A), c4 (whole, 240 s, B, access 30 MΩ, over the gate).
    assert seal.results["conditions"] == [
        {
            "condition": 30.0,
            "n_units": 3,
            "n_cells": 3,
            "n_whole_cell": 2,
            "minutes_per_whole_cell": pytest.approx((60 + 180 + 60) / 60 / 2),
            "whole_cells_per_slice": 1.0,
            "n_passing_gate": 2,
        },
        {
            "condition": 60.0,
            "n_units": 2,
            "n_cells": 2,
            "n_whole_cell": 1,
            "minutes_per_whole_cell": pytest.approx((120 + 240) / 60 / 1),
            "whole_cells_per_slice": 0.5,
            "n_passing_gate": 0,
        },
    ]
    assert health.results is None
    assert (seal.dir / "accepted_analysis.py").read_text() == ANALYZE_SCRIPT

    statuses = {f.name: f.status for f in catalogue.load(cat_path)}
    assert statuses == {"seal_timeout": "tested", "min_health": "running"}

    table = (tmp_path / "tracking.md").read_text()
    assert table == tracking.render(
        catalogue.load(cat_path), record.all_trials(autopatch.tuningTrialsDir)
    )
    seal_row, health_row = (
        _tracking_row(table, n) for n in ("seal_timeout", "min_health")
    )
    assert seal_row[4:6] == ["tested", seal.id]
    assert seal_row[6] == (
        "30.0: 2.5 min/whole cell, 1.0 whole cells/slice<br>"
        "60.0: 6.0 min/whole cell, 0.5 whole cells/slice"
    )
    assert seal_row[7] == "Halving the timeout costs nothing."
    assert health_row[4:] == ["running", health.id, "", ""]
    assert tracking.DEFAULT_OUT.read_text() == real_tracking
