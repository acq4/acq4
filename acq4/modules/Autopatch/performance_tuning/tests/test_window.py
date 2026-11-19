"""Tests for the performance tuning review window: lifecycle methods, arming against a real Autopatch window, and the Autopatch button."""

import importlib.util
import json
import os
import shutil
import sys
import threading
import warnings
from datetime import date
from pathlib import Path

import pytest

import acq4
import acq4.util.DataManager as dm
from acq4.modules.Autopatch.performance_tuning import (
    brief,
    catalogue,
    join,
    lifecycle,
    record,
    scaffold,
)
from acq4.modules.Autopatch.performance_tuning.ledger import (
    MIRROR_NAME,
    JsonlLedger,
    ledger_path,
)
from acq4.modules.Autopatch.performance_tuning.mutators import MUTATORS
from acq4.modules.Autopatch.performance_tuning.mutators.base import ScopeMutator
from acq4.modules.Autopatch.performance_tuning.window import (
    NewRunGroupDialog,
    Refused,
    TuningWindow,
)
from acq4.modules.Autopatch.tests.conftest import fakeManager  # noqa: F401
from acq4.modules.Autopatch.tests.test_window_integration import _makeWindow, qapp
from acq4.util import Qt, tuning_points
from acq4.util.tuning_points import TuningPointWarning

from .conftest import RUN_ID, make_cell

PROTOCOL = "acq4/modules/Autopatch/example_protocols/example_patch.py"

ANALYZE_SCRIPT = """\
from pathlib import Path

from acq4.modules.Autopatch.performance_tuning import join, record, report

trial = record.load(Path.cwd().parent.parent)
frame = join.attempts_with_conditions(trial.dir / "data", trial.run_id)
report.write(frame, trial, "out")
"""


class _WrapA(ScopeMutator):
    name = "wrap_a"
    unit = "cell"
    wraps = {"patching"}
    conditions = [1, 2]


class _WrapB(ScopeMutator):
    name = "wrap_b"
    unit = "cell"
    wraps = {"patching"}
    conditions = [1, 2]


@pytest.fixture(autouse=True)
def _clean():
    tuning_points.uninstall()
    yield
    tuning_points.uninstall()


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


def _tuning(tmp_path, cat_path, **kw):
    return TuningWindow(trials_dir=tmp_path / "trials", catalogue_path=cat_path, **kw)


@pytest.fixture
def tw(autopatch, tmp_path, cat_path):
    w = _tuning(tmp_path, cat_path, autopatch=autopatch)
    yield w
    w.close()


@pytest.fixture
def standalone(qapp, tmp_path, cat_path, fakeManager):
    w = _tuning(tmp_path, cat_path, manager=fakeManager)
    yield w
    w.close()


def _factors(cat_path, *names):
    entries = {f.name: f for f in catalogue.load(cat_path)}
    return [entries[n] for n in names]


def _entry(cat_path, name):
    return next(f for f in catalogue.load(cat_path) if f.name == name)


def _warning_pair_trial(tmp_path, interactions_expected):
    trial_dir = tmp_path / "trials" / "001-wrap-a"
    (trial_dir / "analyses").mkdir(parents=True)
    trial = record.Trial(
        dir=trial_dir,
        id="001",
        slug="wrap-a",
        run_id="run-warn",
        title="wrap pair",
        status="planned",
        created=date.today().isoformat(),
        primary_factor="wrap_a",
        hypothesis="h",
        protocol=PROTOCOL,
        mutators={
            cls.name: {"class": cls.__name__, "unit": "cell", "conditions": [1, 2]}
            for cls in (_WrapA, _WrapB)
        },
        interactions_expected=interactions_expected,
    )
    record.save(trial)
    return trial


def test_generate_arm_and_disarm(tw, autopatch, cat_path):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    assert tw.trialList.topLevelItemCount() == 1
    autopatch.newSlice()

    tw.arm(trial)

    panel = autopatch.protocolPanel
    assert panel.isPinned()
    assert panel.protocolFile.path == str(record.acq4_root() / PROTOCOL)
    assert trial.run_id in panel.bannerLabel.text()
    assert trial.id in panel.bannerLabel.text()
    assert tuning_points.installed().run_id == trial.run_id
    unit = autopatch._tuningSliceUnit
    assert unit is not None and not unit.closed
    assert record.load(trial.dir).status == "collecting"

    tw.disarm()

    assert not panel.isPinned()
    assert tuning_points.installed() is None
    assert unit.closed
    assert record.load(trial.dir).status == "collecting"


def test_arm_refused_without_a_slice_leaves_nothing_armed(tw, autopatch, cat_path):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    with pytest.raises(tuning_points.TuningPointError, match="no slice directory"):
        tw.arm(trial)
    assert not autopatch.protocolPanel.isPinned()
    assert tuning_points.installed() is None
    assert record.load(trial.dir).status == "planned"


def test_arm_with_a_warning_pair_is_refused_without_an_interactions_answer(
    tw, autopatch, tmp_path, monkeypatch
):
    monkeypatch.setitem(MUTATORS, "wrap_a", _WrapA)
    monkeypatch.setitem(MUTATORS, "wrap_b", _WrapB)
    trial = _warning_pair_trial(tmp_path, interactions_expected=None)
    autopatch.newSlice()
    with pytest.raises(Refused, match="interact"):
        tw.arm(trial)
    assert tuning_points.installed() is None
    assert not autopatch.protocolPanel.isPinned()


def test_arm_with_a_warning_pair_and_an_answer_reports_the_warning(
    tw, autopatch, tmp_path, monkeypatch
):
    monkeypatch.setitem(MUTATORS, "wrap_a", _WrapA)
    monkeypatch.setitem(MUTATORS, "wrap_b", _WrapB)
    trial = _warning_pair_trial(tmp_path, interactions_expected=False)
    autopatch.newSlice()
    assert any("wrap_a" in w and "wrap_b" in w for w in tw.armWarnings(trial))
    tw.arm(trial)
    assert tuning_points.installed().run_id == "run-warn"
    tw.disarm()


def test_arm_refused_on_a_stale_snapshot(tw, autopatch, cat_path):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    trial.mutators["min_health"]["conditions"] = [0.1, 0.2]
    record.save(trial)
    autopatch.newSlice()
    with pytest.raises(Refused, match="conditions were"):
        tw.arm(trial)
    assert tuning_points.installed() is None
    assert not autopatch.protocolPanel.isPinned()


def _retired_factor_trial(window, cat_path):
    (trial,) = window.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    trial.mutators = {"retired_factor": trial.mutators["min_health"]}
    trial.primary_factor = "retired_factor"
    record.save(trial)
    window.refresh()
    return trial


def test_arm_warnings_refuses_a_snapshot_naming_an_unregistered_mutator(
    standalone, cat_path, tmp_path
):
    trial = _retired_factor_trial(standalone, cat_path)
    with pytest.raises(Refused, match="retired_factor: no mutator registered"):
        lifecycle.arm_warnings(tmp_path / "trials", trial)


def _closing_the_next_message_box(qapp, shown):
    def close():
        box = qapp.activeModalWidget()
        shown.append(box.text())
        box.accept()

    Qt.QTimer.singleShot(0, close)


def test_arm_button_shows_a_refusal_for_an_unregistered_mutator(
    tw, autopatch, qapp, cat_path
):
    trial = _retired_factor_trial(tw, cat_path)
    autopatch.newSlice()
    (item,) = tw.trialList.findItems(trial.id, Qt.Qt.MatchRecursive, 0)
    tw.trialList.setCurrentItem(item)
    shown = []
    _closing_the_next_message_box(qapp, shown)
    tw._onArm()
    assert len(shown) == 1 and "no mutator registered" in shown[0]
    assert tuning_points.installed() is None


def _pretend_wheel_install(tmp_path, monkeypatch):
    """Point acq4 at a site-packages layout, with no pyproject.toml above the package."""
    package = tmp_path / "site-packages" / "acq4"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.setattr(acq4, "__file__", str(package / "__init__.py"))


def test_a_wheel_install_refuses_to_run_an_analysis(tmp_path, monkeypatch):
    _pretend_wheel_install(tmp_path, monkeypatch)
    with pytest.raises(Refused, match="source checkout"):
        lifecycle.script_command(tmp_path)


def test_a_wheel_install_marks_trials_invalid_and_refuses_to_arm(
    tw, autopatch, cat_path, monkeypatch, tmp_path
):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    autopatch.newSlice()
    _pretend_wheel_install(tmp_path, monkeypatch)
    assert any("source checkout" in p for p in lifecycle.problems(trial, [trial]))
    tw.refresh()
    with pytest.raises(Refused, match="source checkout"):
        tw.arm(trial)
    assert tuning_points.installed() is None


@pytest.mark.parametrize(
    "statuses", [["closed"], ["abandoned"], ["closed", "abandoned"]]
)
def test_arm_refuses_a_run_group_with_no_open_trial(tw, autopatch, cat_path, statuses):
    trials = tw.newRunGroup(
        _factors(cat_path, "seal_timeout", "min_health")[: len(statuses)],
        PROTOCOL,
        interactions_expected=False if len(statuses) > 1 else None,
    )
    for trial, status in zip(trials, statuses):
        trial.status = status
        record.save(trial)
    autopatch.newSlice()
    with pytest.raises(Refused, match="closed or abandoned"):
        tw.arm(trials[0])
    assert tuning_points.installed() is None


def test_arm_accepts_a_run_group_with_one_trial_still_open(tw, autopatch, cat_path):
    closed, open_ = tw.newRunGroup(
        _factors(cat_path, "seal_timeout", "min_health"),
        PROTOCOL,
        interactions_expected=False,
    )
    closed.status = "closed"
    record.save(closed)
    autopatch.newSlice()
    tw.arm(open_)
    assert tuning_points.installed() is not None
    tw.disarm()


def test_tuning_point_warnings_are_collected_while_armed(tw, autopatch, cat_path):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    autopatch.newSlice()
    before = warnings.showwarning
    tw.arm(trial)
    warnings.warn("same text", TuningPointWarning)
    warnings.warn("same text", TuningPointWarning)
    assert tw.tuningWarnings == ["same text", "same text"]
    assert tw.warningList.count() == 2
    tw.disarm()
    assert warnings.showwarning is before


def test_link_data_from_ledger_slice_dirs(
    tw, autopatch, cat_path, fakeManager, tmp_path
):
    trials = tw.newRunGroup(
        _factors(cat_path, "seal_timeout", "min_health"),
        PROTOCOL,
        interactions_expected=False,
    )
    slices = []
    for name in ("slice_a", "slice_b"):
        d = tmp_path / "rig" / name
        d.mkdir(parents=True)
        slices.append(str(d))
    ledger = JsonlLedger(ledger_path(fakeManager, trials[0].run_id))
    for i, d in enumerate(slices):
        ledger.record(
            {
                "event": "unit_open",
                "unit": "slice",
                "unit_id": f"slice-{i}",
                "run_id": trials[0].run_id,
                "slice_dir": d,
            }
        )

    assert tw.linkableSliceDirs(trials[0]) == slices
    tw.linkData(trials[0], slices[:1])
    assert tw.linkableSliceDirs(trials[1]) == slices[1:]

    for trial in trials:
        loaded = record.load(trial.dir)
        assert loaded.data == ["rig_slice_a"]
        link = trial.dir / "data" / "rig_slice_a"
        assert link.is_symlink() and link.resolve() == Path(slices[0])


def _ledger_slices(fakeManager, run_id, slices):
    ledger = JsonlLedger(ledger_path(fakeManager, run_id))
    for i, d in enumerate(slices):
        ledger.record(
            {
                "event": "unit_open",
                "unit": "slice",
                "unit_id": f"slice-{i}",
                "run_id": run_id,
                "slice_dir": d,
            }
        )


def _day_slices(tmp_path, *days):
    slices = []
    for day in days:
        d = tmp_path / "rig" / day / "slice_000"
        d.mkdir(parents=True)
        slices.append(str(d))
    return slices


def test_same_named_slices_from_two_days_are_both_offered_and_linked(
    standalone, cat_path, fakeManager, config_dir, tmp_path
):
    trials = standalone.newRunGroup(
        _factors(cat_path, "seal_timeout", "min_health"),
        PROTOCOL,
        interactions_expected=False,
    )
    slices = _day_slices(tmp_path, "2026.11.15_000", "2026.11.16_000")
    _ledger_slices(fakeManager, trials[0].run_id, slices)

    standalone.linkData(trials[0], slices[:1])
    assert standalone.linkableSliceDirs(trials[1]) == slices[1:]
    standalone.linkData(trials[1], slices[1:])
    assert standalone.linkableSliceDirs(trials[0]) == []

    names = ["2026.11.15_000_slice_000", "2026.11.16_000_slice_000"]
    for trial in trials:
        assert record.load(trial.dir).data == names
        for name, target in zip(names, slices):
            link = trial.dir / "data" / name
            assert link.is_symlink() and link.resolve() == Path(target)


def test_two_same_named_slices_link_in_one_call(standalone, cat_path, tmp_path):
    trials = standalone.newRunGroup(
        _factors(cat_path, "seal_timeout", "min_health"),
        PROTOCOL,
        interactions_expected=False,
    )
    slices = _day_slices(tmp_path, "2026.11.15_000", "2026.11.16_000")
    standalone.linkData(trials[0], slices)
    for trial in trials:
        assert len(record.load(trial.dir).data) == 2
        assert len(list((trial.dir / "data").iterdir())) == 2


def test_relinking_an_already_linked_target_is_a_no_op(standalone, cat_path, tmp_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    (target,) = _day_slices(tmp_path, "2026.11.15_000")
    standalone.linkData(trial, [target])
    standalone.linkData(trial, [target, target])
    assert record.load(trial.dir).data == ["2026.11.15_000_slice_000"]
    assert [p.name for p in (trial.dir / "data").iterdir()] == [
        "2026.11.15_000_slice_000"
    ]


def test_same_named_slices_are_read_through_their_links(standalone, cat_path, tmp_path):
    (trial,) = standalone.newRunGroup(
        _factors(cat_path, "seal_timeout"), PROTOCOL, run_id=RUN_ID
    )
    slices = []
    for day in ("2026.11.15_000", "2026.11.16_000"):
        (tmp_path / "rig" / day).mkdir(parents=True)
        root = dm.getDirHandle(str(tmp_path / "rig" / day))
        s = root.mkdir("slice_000", info={"dirType": "Slice"})
        make_cell(s, "cell_000", {"seal_timeout": 30.0}, duration=60.0, whole_cell=True)
        with open(os.path.join(s.name(), MIRROR_NAME), "w") as f:
            f.write(
                json.dumps({"event": "unit_open", "unit": "slice", "run_id": RUN_ID})
                + "\n"
            )
        slices.append(s.name())
    standalone.linkData(trial, slices)

    frame = join.attempts_with_conditions(trial.dir / "data", RUN_ID)
    assert sorted(frame["source"].map(os.path.dirname).map(os.path.realpath)) == [
        os.path.realpath(os.path.join(s, "cell_000")) for s in slices
    ]
    assert len(join.slice_ledger_lines(trial.dir / "data", RUN_ID)) == 2


def test_new_analysis_creates_the_dir_and_brief(standalone, cat_path, fakeManager):
    fakeManager.config = {"misc": {"analysisAgent": "touch {dir}/launched"}}
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    d = standalone.newAnalysis(
        trial, "deep-cells", "Does it hold for deep cells?", "script"
    )
    assert d == trial.dir / "analyses" / "001-deep-cells"
    text = (d / "BRIEF.md").read_text()
    assert "Does it hold for deep cells?" in text
    assert "analyze.py" in text


def test_new_analysis_rejects_a_slug_that_escapes(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    for slug in ("../x", "Bad", "-x", "", "a/b"):
        with pytest.raises(ValueError, match="slug"):
            standalone.newAnalysis(trial, slug, "q", "script")
    assert list((trial.dir / "analyses").iterdir()) == []


def _analysed_trial(window, cat_path, dataset):
    (trial,) = window.newRunGroup(
        _factors(cat_path, "seal_timeout"), PROTOCOL, run_id="run-a"
    )
    window.linkData(trial, [s.name() for s in dataset["slices"].values()])
    trial = record.load(trial.dir)
    d = brief.next_analysis_dir(trial, "basic")
    (d / "analyze.py").write_text(ANALYZE_SCRIPT)
    return trial, d


def _collecting(trial):
    trial = record.load(trial.dir)
    trial.status = "collecting"
    record.save(trial)
    return trial


def _run(window, qtbot, d):
    window.runAnalysis(d)
    qtbot.waitUntil(lambda: window.lastRun is not None, timeout=60000)
    assert window.lastRun["dir"] == d
    return window.lastRun


def test_run_analysis_runs_the_script_and_shows_the_report(
    standalone, qtbot, cat_path, dataset
):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    process = standalone.runAnalysis(d)
    assert isinstance(process, Qt.QProcess)
    qtbot.waitUntil(lambda: standalone.lastRun is not None, timeout=60000)
    run = standalone.lastRun
    assert run["exit_code"] == 0
    assert (d / "out" / "summary.json").exists()
    assert run["report"] == (d / "out" / "report.txt").read_text()
    assert "seal_timeout" in run["report"]
    shown = standalone.runView.toPlainText()
    assert "exited with status 0" in shown
    assert run["report"].splitlines()[0] in shown


def test_run_analysis_reports_a_failing_script(standalone, qtbot, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    (d / "analyze.py").write_text("raise SystemExit('broken on purpose')\n")
    run = _run(standalone, qtbot, d)
    assert run["exit_code"] == 1
    assert "broken on purpose" in run["output"]
    shown = standalone.runView.toPlainText()
    assert "exited with status 1" in shown
    assert "broken on purpose" in shown


def test_run_analysis_command_runs_this_checkout(tmp_path):
    program, args, env = lifecycle.script_command(tmp_path)
    assert (program, args) == (sys.executable, ["analyze.py"])
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(record.acq4_root())


def test_run_analysis_opens_a_notebook(standalone, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    (d / "analyze.py").unlink()
    (d / "analyze.ipynb").write_text("{}")
    opened = []
    standalone._openUrl = lambda url: opened.append(url.toLocalFile())
    assert standalone.runAnalysis(d) is None
    assert opened == [str(d / "analyze.ipynb")]


def test_open_analyses_folder(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    opened = []
    standalone._openUrl = lambda url: opened.append(url.toLocalFile())
    standalone.openAnalysesFolder(trial)
    assert opened == [str(trial.dir / "analyses")]


def test_accept_copies_the_script_and_updates_record_and_catalogue(
    standalone, qtbot, cat_path, dataset
):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    trial = _collecting(trial)
    _run(standalone, qtbot, d)
    summary = json.loads((d / "out" / "summary.json").read_text())

    standalone.accept(trial, d, "Halving the timeout costs nothing.")

    assert (trial.dir / "accepted_analysis.py").read_text() == ANALYZE_SCRIPT
    loaded = record.load(trial.dir)
    assert loaded.status == "closed"
    assert loaded.verdict == "Halving the timeout costs nothing."
    assert loaded.closed_on == date.today().isoformat()
    assert loaded.results["analysis"] == d.name
    assert loaded.results["provenance"] == summary["provenance"]
    headline = loaded.results["conditions"]
    assert [c["condition"] for c in headline] == [30.0, 60.0]
    assert set(headline[0]) == {
        "condition",
        "n_units",
        "n_cells",
        "n_whole_cell",
        "minutes_per_whole_cell",
        "whole_cells_per_slice",
        "n_passing_gate",
    }
    assert headline[0]["n_whole_cell"] == summary["conditions"][0]["n_whole_cell"]
    assert _entry(cat_path, "seal_timeout").status == "tested"


def test_accept_refused_without_a_valid_summary(standalone, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    trial = _collecting(trial)
    with pytest.raises(Refused, match="summary.json"):
        standalone.accept(trial, d, "v")
    (d / "out" / "summary.json").write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(Refused, match="missing key"):
        standalone.accept(trial, d, "v")
    loaded = record.load(trial.dir)
    assert (loaded.status, loaded.results, loaded.verdict) == (
        "collecting",
        None,
        None,
    )
    assert not (trial.dir / "accepted_analysis.py").exists()
    assert _entry(cat_path, "seal_timeout").status == "running"


def test_accept_of_a_notebook_exports_it_or_refuses_without_nbconvert(
    standalone, qtbot, cat_path, dataset
):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    trial = _collecting(trial)
    _run(standalone, qtbot, d)
    (d / "analyze.py").unlink()
    (d / "analyze.ipynb").write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "metadata": {},
                        "source": ["x = 1\n"],
                        "outputs": [],
                        "execution_count": None,
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        )
    )
    if importlib.util.find_spec("nbconvert") is None:
        with pytest.raises(Refused, match="nbconvert"):
            standalone.accept(trial, d, "v")
        assert record.load(trial.dir).status == "collecting"
    else:
        standalone.accept(trial, d, "v")
        assert "x = 1" in (trial.dir / "accepted_analysis.py").read_text()


def test_reject_appends_a_note(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    standalone.reject(trial, "too few cells")
    standalone.reject(trial, "still too few")
    loaded = record.load(trial.dir)
    assert loaded.review_notes == ["too few cells", "still too few"]
    assert (loaded.status, loaded.results) == ("planned", None)


def test_abandon_resets_the_factor(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    assert _entry(cat_path, "seal_timeout").status == "running"
    standalone.abandon(trial, "rig down for a month")
    loaded = record.load(trial.dir)
    assert loaded.status == "abandoned"
    assert loaded.review_notes == ["abandoned: rig down for a month"]
    assert _entry(cat_path, "seal_timeout").status == "untested"


def _tracking_row(cat_path, name):
    text = cat_path.with_name("tracking.md").read_text()
    (line,) = [l for l in text.splitlines() if l.startswith(f"| {name} |")]
    return [cell.strip() for cell in line.strip("|").split("|")]


def test_new_run_group_regenerates_tracking_beside_the_catalogue(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    assert _tracking_row(cat_path, "seal_timeout")[4:6] == ["running", trial.id]


def test_abandon_regenerates_tracking_beside_the_catalogue(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    standalone.abandon(trial, "rig down for a month")
    assert _tracking_row(cat_path, "seal_timeout")[4:6] == ["untested", trial.id]


def test_standalone_mode_disables_arm(standalone, cat_path):
    assert not standalone.armBtn.isEnabled()
    assert not standalone.disarmBtn.isEnabled()
    assert standalone.armBtn.toolTip()
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL)
    with pytest.raises(Refused, match="Autopatch"):
        standalone.arm(trial)


def test_autopatch_button_opens_one_tuning_window(autopatch):
    autopatch.tuningBtn.click()
    first = autopatch._tuningWindow
    assert isinstance(first, TuningWindow)
    assert first.trials_dir == autopatch.tuningTrialsDir
    assert first.catalogue_path == autopatch.tuningCataloguePath
    assert first.isVisible()
    assert first.autopatch is autopatch
    autopatch.tuningBtn.click()
    assert autopatch._tuningWindow is first
    autopatch.teardown()
    assert not first.isVisible()
    assert autopatch._tuningWindow is None


def test_selecting_an_analysis_shows_its_report(standalone, qtbot, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    text = _run(standalone, qtbot, d)["report"]
    standalone.refresh()
    (item,) = standalone.trialList.findItems(trial.id, Qt.Qt.MatchRecursive, 0)
    standalone.trialList.setCurrentItem(item)
    assert standalone.analysesList.count() == 1
    assert standalone.analysesList.item(0).text() == f"{d.name}  (summary)"
    standalone.analysesList.setCurrentRow(0)
    assert text.splitlines()[0] in standalone.analysisView.toPlainText()
    assert "seal_timeout" in standalone.details.toPlainText()


def test_new_run_group_dialog_proposes_candidates(qapp, cat_path):
    dialog = NewRunGroupDialog(cat_path)
    factors, protocol, _, _ = dialog.choice()
    assert [f.name for f in factors] == [
        f.name for f in catalogue.candidates(2, catalogue.load(cat_path))
    ]
    assert protocol == PROTOCOL


def _ok(dialog):
    return dialog.buttons.button(Qt.QDialogButtonBox.Ok)


def _check_only(dialog, *names):
    for i in range(dialog.list.count()):
        item = dialog.list.item(i)
        if item.text() in dialog.factors:
            chosen = dialog.factors[item.text()].name in names
            item.setCheckState(Qt.Qt.Checked if chosen else Qt.Qt.Unchecked)


def test_one_factor_is_not_asked_about_interactions(qapp, cat_path):
    dialog = NewRunGroupDialog(cat_path)
    _check_only(dialog, "seal_timeout")
    assert dialog.interactions.isHidden()
    assert _ok(dialog).isEnabled()
    assert dialog.choice()[2:] == (None, "")


def test_two_factors_must_be_asked_about_interactions(qapp, cat_path):
    dialog = NewRunGroupDialog(cat_path)
    _check_only(dialog, "seal_timeout", "min_health")
    assert not dialog.interactions.isHidden()
    assert "seal_timeout" in dialog.interactionsQuestion.text()
    assert "min_health" in dialog.interactionsQuestion.text()
    assert not _ok(dialog).isEnabled()


def test_answering_no_interactions_needs_no_notes(qapp, cat_path):
    dialog = NewRunGroupDialog(cat_path)
    _check_only(dialog, "seal_timeout", "min_health")
    dialog.noInteractions.setChecked(True)
    assert _ok(dialog).isEnabled()
    assert not dialog.interactionNotes.isEnabled()
    assert dialog.choice()[2:] == (False, "")


def test_answering_yes_takes_optional_notes(qapp, cat_path):
    dialog = NewRunGroupDialog(cat_path)
    _check_only(dialog, "seal_timeout", "min_health")
    dialog.interactionsPossible.setChecked(True)
    assert _ok(dialog).isEnabled()
    assert dialog.interactionNotes.isEnabled()
    assert dialog.choice()[2:] == (True, "")
    dialog.interactionNotes.setPlainText("both slow seals")
    assert dialog.choice()[2:] == (True, "both slow seals")


def test_notes_are_dropped_when_the_answer_changes_to_no(qapp, cat_path):
    dialog = NewRunGroupDialog(cat_path)
    _check_only(dialog, "seal_timeout", "min_health")
    dialog.interactionsPossible.setChecked(True)
    dialog.interactionNotes.setPlainText("both slow seals")
    dialog.noInteractions.setChecked(True)
    assert dialog.choice()[2:] == (False, "")


def test_a_run_group_the_scaffold_refuses_is_a_window_refusal(standalone, cat_path):
    pair = _factors(cat_path, "seal_timeout", "min_health")
    with pytest.raises(lifecycle.REFUSALS, match="interact"):
        standalone.newRunGroup(pair, PROTOCOL)


def test_trial_details_show_the_interactions_answer(standalone, cat_path):
    pair = _factors(cat_path, "seal_timeout", "min_health")
    trial, _ = standalone.newRunGroup(
        pair, PROTOCOL, interactions_expected=True, interaction_notes="both slow seals"
    )
    (item,) = standalone.trialList.findItems(trial.id, Qt.Qt.MatchRecursive, 0)
    standalone.trialList.setCurrentItem(item)
    assert "Interactions: possible. both slow seals" in standalone.details.toPlainText()


def test_warnings_from_a_worker_thread_reach_the_list_on_the_gui_thread(
    tw, autopatch, cat_path, qapp
):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    autopatch.newSlice()
    tw.arm(trial)
    inserted_on = []
    tw.warningList.model().rowsInserted.connect(
        lambda *args: inserted_on.append(threading.current_thread()),
        Qt.Qt.DirectConnection,
    )
    worker = threading.Thread(
        target=lambda: warnings.warn("from the worker", TuningPointWarning)
    )
    worker.start()
    worker.join()
    assert tw.tuningWarnings == []
    qapp.processEvents()
    assert tw.tuningWarnings == ["from the worker"]
    assert inserted_on == [threading.main_thread()]
    tw.disarm()


def test_collection_survives_close_and_reopen_while_armed(autopatch, cat_path):
    before = warnings.showwarning
    autopatch.openTuningWindow()
    tw = autopatch._tuningWindow
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    autopatch.newSlice()
    tw.arm(trial)
    tw.close()
    autopatch.openTuningWindow()
    assert autopatch._tuningWindow is tw
    warnings.warn("after reopening", TuningPointWarning)
    assert tw.tuningWarnings == ["after reopening"]
    autopatch.teardown()
    assert warnings.showwarning is before


def test_destroying_an_armed_window_stops_collection(
    autopatch, tmp_path, cat_path, qapp
):
    before = warnings.showwarning
    tw = _tuning(tmp_path, cat_path, autopatch=autopatch)
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    autopatch.newSlice()
    tw.arm(trial)
    tw.deleteLater()
    qapp.sendPostedEvents(None, Qt.QEvent.DeferredDelete)
    assert warnings.showwarning is before


def test_accept_refused_unless_collecting(standalone, qtbot, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    _run(standalone, qtbot, d)
    with pytest.raises(Refused, match="collecting"):
        standalone.accept(trial, d, "v")
    assert record.load(trial.dir).status == "planned"
    assert not (trial.dir / "accepted_analysis.py").exists()


def test_accept_button_needs_a_valid_summary(standalone, qtbot, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    (item,) = standalone.trialList.findItems(trial.id, Qt.Qt.MatchRecursive, 0)
    standalone.trialList.setCurrentItem(item)
    standalone.analysesList.setCurrentRow(0)
    assert not standalone.acceptBtn.isEnabled()
    _run(standalone, qtbot, d)
    standalone.analysesList.setCurrentRow(0)
    assert standalone.acceptBtn.isEnabled()
    (d / "out" / "summary.json").write_text(json.dumps({"schema_version": 1}))
    standalone.analysesList.setCurrentRow(-1)
    standalone.analysesList.setCurrentRow(0)
    assert not standalone.acceptBtn.isEnabled()
    (d / "out" / "summary.json").write_text("{not json")
    standalone.analysesList.setCurrentRow(-1)
    standalone.analysesList.setCurrentRow(0)
    assert not standalone.acceptBtn.isEnabled()


def test_link_data_checks_every_target_before_linking(standalone, cat_path, tmp_path):
    trials = standalone.newRunGroup(
        _factors(cat_path, "seal_timeout", "min_health"),
        PROTOCOL,
        interactions_expected=False,
    )
    slice_dir = tmp_path / "rig" / "slice_a"
    slice_dir.mkdir(parents=True)
    (trials[1].dir / "data" / "rig_slice_a").mkdir()
    with pytest.raises(Refused, match="rig_slice_a"):
        standalone.linkData(trials[0], [str(slice_dir)])
    assert not (trials[0].dir / "data" / "rig_slice_a").exists()
    assert [record.load(t.dir).data for t in trials] == [[], []]


def test_arm_refuses_a_trial_outside_the_trials_dir(tw, autopatch, cat_path, tmp_path):
    (trial,) = scaffold.new_run_group(
        _factors(cat_path, "min_health"),
        PROTOCOL,
        trials_dir=tmp_path / "elsewhere",
        catalogue_path=cat_path,
    )
    autopatch.newSlice()
    with pytest.raises(Refused, match="not under"):
        tw.arm(trial)
    assert tuning_points.installed() is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_disarm_stops_collection_even_when_unpinning_fails(
    tw, autopatch, cat_path, tmp_path
):
    before = warnings.showwarning
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL)
    autopatch.newSlice()
    tw.arm(trial)
    # Unreadable but still traversable: the protocol directory rescan that
    # unpinning does fails, while the ledger writes under it still work.
    tmp_path.chmod(0o300)
    try:
        with pytest.raises(PermissionError):
            tw.disarm()
    finally:
        tmp_path.chmod(0o700)
    assert tuning_points.installed() is None
    assert warnings.showwarning is before


SLEEPING_SCRIPT = "import time\ntime.sleep(60)\n"


def test_run_analysis_shows_stdout_too(standalone, qtbot, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    (d / "analyze.py").write_text("print('hello from stdout')\n")
    run = _run(standalone, qtbot, d)
    assert "hello from stdout" in run["output"]
    assert "hello from stdout" in standalone.runView.toPlainText()


def test_a_second_run_while_one_is_in_flight_is_refused(standalone, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    (d / "analyze.py").write_text(SLEEPING_SCRIPT)
    process = standalone.runAnalysis(d)
    with pytest.raises(Refused, match="an analysis is already running"):
        standalone.runAnalysis(d)
    standalone.close()
    assert process.state() == Qt.QProcess.NotRunning


def test_destroying_the_window_mid_run_kills_the_process_cleanly(
    qapp, tmp_path, cat_path, dataset, monkeypatch
):
    window = _tuning(tmp_path, cat_path)
    trial, d = _analysed_trial(window, cat_path, dataset)
    (d / "analyze.py").write_text(SLEEPING_SCRIPT)
    hooked = []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: hooked.append(exc))
    messages = []
    Qt.qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    try:
        process = window.runAnalysis(d)
        assert process.waitForStarted()
        window.deleteLater()
        qapp.sendPostedEvents(None, Qt.QEvent.DeferredDelete)
        qapp.processEvents()
    finally:
        Qt.qInstallMessageHandler(None)
    assert hooked == []
    assert not [m for m in messages if "Destroyed while process" in m]
    assert process.state() == Qt.QProcess.NotRunning


def test_accept_button_starts_disabled(standalone):
    assert not standalone.acceptBtn.isEnabled()
