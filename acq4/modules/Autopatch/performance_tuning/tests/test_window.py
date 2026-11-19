"""Tests for the performance tuning review window: lifecycle methods, arming against a real Autopatch window, and the Autopatch button."""

import importlib.util
import json
import shutil
import warnings
from datetime import date
from pathlib import Path

import pytest

from acq4.modules.Autopatch.performance_tuning import brief, catalogue, record
from acq4.modules.Autopatch.performance_tuning.ledger import JsonlLedger, ledger_path
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
def autopatch(qapp, tmp_path, config_dir):
    w = _makeWindow(tmp_path)
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


def _warning_pair_trial(tmp_path, signoff):
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
        interaction_signoff=signoff,
    )
    record.save(trial)
    return trial


def test_generate_arm_and_disarm(tw, autopatch, cat_path):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL, "")
    assert tw.trialList.topLevelItemCount() == 1
    autopatch.newSlice()

    tw.arm(trial)

    panel = autopatch.protocolPanel
    assert panel.isPinned()
    assert panel.protocolFile.path == str(record._acq4_root() / PROTOCOL)
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
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL, "")
    with pytest.raises(tuning_points.TuningPointError, match="no slice directory"):
        tw.arm(trial)
    assert not autopatch.protocolPanel.isPinned()
    assert tuning_points.installed() is None
    assert record.load(trial.dir).status == "planned"


def test_arm_with_a_warning_pair_is_refused_without_a_signoff(
    tw, autopatch, tmp_path, monkeypatch
):
    monkeypatch.setitem(MUTATORS, "wrap_a", _WrapA)
    monkeypatch.setitem(MUTATORS, "wrap_b", _WrapB)
    trial = _warning_pair_trial(tmp_path, signoff="  ")
    autopatch.newSlice()
    with pytest.raises(Refused, match="signoff"):
        tw.arm(trial)
    assert tuning_points.installed() is None
    assert not autopatch.protocolPanel.isPinned()


def test_arm_with_a_warning_pair_and_a_signoff_reports_the_warning(
    tw, autopatch, tmp_path, monkeypatch
):
    monkeypatch.setitem(MUTATORS, "wrap_a", _WrapA)
    monkeypatch.setitem(MUTATORS, "wrap_b", _WrapB)
    trial = _warning_pair_trial(tmp_path, signoff="independent; mc")
    autopatch.newSlice()
    assert any("wrap_a" in w and "wrap_b" in w for w in tw.armWarnings(trial))
    tw.arm(trial)
    assert tuning_points.installed().run_id == "run-warn"
    tw.disarm()


def test_arm_refused_on_a_stale_snapshot(tw, autopatch, cat_path):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL, "")
    trial.mutators["min_health"]["conditions"] = [0.1, 0.2]
    record.save(trial)
    autopatch.newSlice()
    with pytest.raises(Refused, match="conditions were"):
        tw.arm(trial)
    assert tuning_points.installed() is None
    assert not autopatch.protocolPanel.isPinned()


def test_tuning_point_warnings_are_collected_while_armed(tw, autopatch, cat_path):
    (trial,) = tw.newRunGroup(_factors(cat_path, "min_health"), PROTOCOL, "")
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
        _factors(cat_path, "seal_timeout", "min_health"), PROTOCOL, "independent"
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
        assert loaded.data == ["slice_a"]
        link = trial.dir / "data" / "slice_a"
        assert link.is_symlink() and link.resolve() == Path(slices[0])


def test_new_analysis_creates_the_dir_and_brief(standalone, cat_path, fakeManager):
    fakeManager.config = {"misc": {"analysisAgent": "touch {dir}/launched"}}
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL, "")
    d = standalone.newAnalysis(
        trial, "deep-cells", "Does it hold for deep cells?", "script"
    )
    assert d == trial.dir / "analyses" / "001-deep-cells"
    text = (d / "BRIEF.md").read_text()
    assert "Does it hold for deep cells?" in text
    assert "analyze.py" in text


def test_new_analysis_rejects_a_slug_that_escapes(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL, "")
    for slug in ("../x", "Bad", "-x", "", "a/b"):
        with pytest.raises(ValueError, match="slug"):
            standalone.newAnalysis(trial, slug, "q", "script")
    assert list((trial.dir / "analyses").iterdir()) == []


def _analysed_trial(window, cat_path, dataset):
    (trial,) = window.newRunGroup(
        _factors(cat_path, "seal_timeout"), PROTOCOL, "", run_id="run-a"
    )
    window.linkData(trial, [s.name() for s in dataset["slices"].values()])
    trial = record.load(trial.dir)
    d = brief.next_analysis_dir(trial, "basic")
    (d / "analyze.py").write_text(ANALYZE_SCRIPT)
    return trial, d


def test_run_analysis_runs_the_script_and_shows_the_report(
    standalone, cat_path, dataset
):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    text = standalone.runAnalysis(d)
    assert (d / "out" / "summary.json").exists()
    assert text == (d / "out" / "report.txt").read_text()
    assert "seal_timeout" in text


def test_run_analysis_reports_a_failing_script(standalone, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    (d / "analyze.py").write_text("raise SystemExit('broken on purpose')\n")
    with pytest.raises(Refused, match="broken on purpose"):
        standalone.runAnalysis(d)


def test_run_analysis_opens_a_notebook(standalone, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    (d / "analyze.py").unlink()
    (d / "analyze.ipynb").write_text("{}")
    opened = []
    standalone._openUrl = lambda url: opened.append(url.toLocalFile())
    assert standalone.runAnalysis(d) is None
    assert opened == [str(d / "analyze.ipynb")]


def test_open_analyses_folder(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL, "")
    opened = []
    standalone._openUrl = lambda url: opened.append(url.toLocalFile())
    standalone.openAnalysesFolder(trial)
    assert opened == [str(trial.dir / "analyses")]


def test_accept_copies_the_script_and_updates_record_and_catalogue(
    standalone, cat_path, dataset
):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    standalone.runAnalysis(d)
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
    with pytest.raises(Refused, match="summary.json"):
        standalone.accept(trial, d, "v")
    (d / "out" / "summary.json").write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(Refused, match="missing key"):
        standalone.accept(trial, d, "v")
    loaded = record.load(trial.dir)
    assert (loaded.status, loaded.results, loaded.verdict) == ("planned", None, None)
    assert not (trial.dir / "accepted_analysis.py").exists()
    assert _entry(cat_path, "seal_timeout").status == "running"


def test_accept_of_a_notebook_exports_it_or_refuses_without_nbconvert(
    standalone, cat_path, dataset
):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    standalone.runAnalysis(d)
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
        assert record.load(trial.dir).status == "planned"
    else:
        standalone.accept(trial, d, "v")
        assert "x = 1" in (trial.dir / "accepted_analysis.py").read_text()


def test_reject_appends_a_note(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL, "")
    standalone.reject(trial, "too few cells")
    standalone.reject(trial, "still too few")
    loaded = record.load(trial.dir)
    assert loaded.review_notes == ["too few cells", "still too few"]
    assert (loaded.status, loaded.results) == ("planned", None)


def test_abandon_resets_the_factor(standalone, cat_path):
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL, "")
    assert _entry(cat_path, "seal_timeout").status == "running"
    standalone.abandon(trial, "rig down for a month")
    loaded = record.load(trial.dir)
    assert loaded.status == "abandoned"
    assert loaded.review_notes == ["abandoned: rig down for a month"]
    assert _entry(cat_path, "seal_timeout").status == "untested"


def test_standalone_mode_disables_arm(standalone, cat_path):
    assert not standalone.armBtn.isEnabled()
    assert not standalone.disarmBtn.isEnabled()
    assert standalone.armBtn.toolTip()
    (trial,) = standalone.newRunGroup(_factors(cat_path, "seal_timeout"), PROTOCOL, "")
    with pytest.raises(Refused, match="Autopatch"):
        standalone.arm(trial)


def test_autopatch_button_opens_one_tuning_window(autopatch):
    autopatch.tuningBtn.click()
    first = autopatch._tuningWindow
    assert isinstance(first, TuningWindow)
    assert first.isVisible()
    assert first.autopatch is autopatch
    autopatch.tuningBtn.click()
    assert autopatch._tuningWindow is first
    autopatch.teardown()
    assert not first.isVisible()
    assert autopatch._tuningWindow is None


def test_selecting_an_analysis_shows_its_report(standalone, cat_path, dataset):
    trial, d = _analysed_trial(standalone, cat_path, dataset)
    text = standalone.runAnalysis(d)
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
    factors, protocol, signoff = dialog.choice()
    assert [f.name for f in factors] == [
        f.name for f in catalogue.candidates(2, catalogue.load(cat_path))
    ]
    assert protocol == PROTOCOL
    assert signoff == ""
