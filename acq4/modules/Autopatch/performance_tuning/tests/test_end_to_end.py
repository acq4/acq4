"""End-to-end tests: a catalogue becomes a run group, runs through the orchestrator, and is analysed and accepted."""

import json
import shutil
import warnings
from collections import Counter

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

PROTOCOL = "acq4/modules/Autopatch/example_protocols/example_patch.py"
SIGNOFF = "Health cutoff acts on queueing, seal timeout inside patching. — test"
RUN_ID = "run-e2e"
CELLS_PER_SURVEY = 3
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
def cat_path(tmp_path):
    path = tmp_path / "factors.yaml"
    shutil.copy(catalogue.DEFAULT_PATH, path)
    return path


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
        SIGNOFF,
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

    cells = [_Cell(f"c{i}") for i in range(CELLS_PER_SURVEY * SURVEYS_WITH_CELLS)]
    batches = [
        cells[i : i + CELLS_PER_SURVEY] for i in range(0, len(cells), CELLS_PER_SURVEY)
    ] + [None]
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

    for i, d in enumerate(cellDirs):
        write_log(d, duration=60.0 + 30.0 * i, whole_cell=i % 2 == 0)
    lifecycle.link_data(trials_dir, trials[0], [slice_dir.name()])

    for trial in trials:
        trial = record.load(trial.dir)
        frame = join.attempts_with_conditions(trial.dir / "data", RUN_ID)
        out = trial.dir / "analyses" / "001-e2e" / "out"
        summary = report.write(frame, trial, out)
        assert (
            report.validate_summary(json.loads((out / "summary.json").read_text()))
            == []
        )
        assert summary["primary_factor"] == trial.primary_factor
        assert summary["unit"] == MUTATORS[trial.primary_factor].unit
        assert not summary["no_units_assigned"]
        conditions = summary["conditions"]
        assert sum(c["n_cells"] for c in conditions) == len(cells)
        assert sum(c["n_whole_cell"] for c in conditions) == len(cells) // 2
        if trial.primary_factor == "min_health":
            assert sum(c["n_units"] for c in conditions) == SURVEYS_WITH_CELLS
        else:
            assert [c["n_units"] for c in conditions] == [3, 3]


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
            SIGNOFF,
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
    assert [c["condition"] for c in seal.results["conditions"]] == [30.0, 60.0]
    assert health.results is None
    assert (seal.dir / "accepted_analysis.py").read_text() == ANALYZE_SCRIPT

    statuses = {f.name: f.status for f in catalogue.load(cat_path)}
    assert statuses == {"seal_timeout": "tested", "min_health": "running"}

    table = (tmp_path / "tracking.md").read_text()
    assert table == tracking.render(
        catalogue.load(cat_path), record.all_trials(autopatch.tuningTrialsDir)
    )
    assert "Halving the timeout costs nothing." in table
    assert tracking.DEFAULT_OUT.read_text() == real_tracking
