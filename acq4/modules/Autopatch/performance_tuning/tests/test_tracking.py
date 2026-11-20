"""Tests for the generated tracking table: rows per catalogue factor, headline pairs, and the committed file."""

import shutil
from pathlib import Path

from acq4.modules.Autopatch.performance_tuning import agent, catalogue, record, tracking
from acq4.modules.Autopatch.performance_tuning.catalogue import Factor

from .conftest import TEST_CATALOGUE, committed, committed_names

PROTOCOL = "acq4/modules/Autopatch/example_protocols/_example_patch.py"
SEAL = {"class": "SealTimeout", "unit": "cell", "conditions": [30.0, 60.0]}


def _factor(name, mutator, status="untested", trials=(), priority="medium"):
    return Factor(
        name=name,
        summary=f"{name} summary",
        mutator=mutator,
        hypothesis="h",
        priority=priority,
        status=status,
        trials=list(trials),
    )


def _trial(tmp_path, trial_id, status="collecting", results=None, verdict=None):
    trial = record.Trial(
        dir=tmp_path / f"{trial_id}-seal-timeout",
        id=trial_id,
        slug="seal-timeout",
        run_id=f"run-{trial_id}",
        title="Seal timeout",
        status=status,
        created="2026-11-13",
        primary_factor="seal_timeout",
        hypothesis="h",
        protocol=PROTOCOL,
        mutators={"seal_timeout": dict(SEAL)},
        results=results,
        verdict=verdict,
    )
    trial.dir.mkdir()
    record.save(trial)
    return trial


def _results(pairs):
    return {
        "conditions": [
            {
                "condition": condition,
                "n_units": 3,
                "n_cells": 3,
                "n_whole_cell": 2,
                "minutes_per_whole_cell": minutes,
                "whole_cells_per_slice": per_slice,
                "n_passing_gate": 1,
            }
            for condition, minutes, per_slice in pairs
        ],
        "provenance": {},
        "analysis": "001-basic",
    }


def _row(text, name):
    (line,) = [l for l in text.splitlines() if l.startswith(f"| {name} |")]
    return [cell.strip() for cell in line.strip("|").split("|")]


def test_header_says_generated_and_names_the_columns():
    lines = tracking.render([], []).splitlines()
    assert "generated" in lines[0].lower()
    assert "do not edit" in lines[0].lower()
    header = next(l for l in lines if l.startswith("| name"))
    assert [c.strip() for c in header.strip("|").split("|")] == list(tracking.COLUMNS)


def test_untested_factors_and_factors_without_a_mutator_are_listed():
    text = tracking.render(
        [
            _factor("seal_timeout", "seal_timeout", priority="high"),
            _factor("holding_ramp", None, priority="low"),
        ],
        [],
    )
    assert _row(text, "seal_timeout") == [
        "seal_timeout",
        "SealTimeout",
        "cell",
        "high",
        "untested",
        "",
        "",
        "",
    ]
    assert _row(text, "holding_ramp") == [
        "holding_ramp",
        "needs a mutator",
        "",
        "low",
        "untested",
        "",
        "",
        "",
    ]


def test_a_running_factor_lists_its_trials_without_numbers(tmp_path):
    trial = _trial(tmp_path, "001")
    text = tracking.render(
        [_factor("seal_timeout", "seal_timeout", "running", ["001"])], [trial]
    )
    row = _row(text, "seal_timeout")
    assert row[4:] == ["running", "001", "", ""]


def test_a_closed_trial_contributes_its_headline_pair_and_verdict(tmp_path):
    closed = _trial(
        tmp_path,
        "001",
        status="closed",
        results=_results([(30.0, 12.5, 2.0), (60.0, None, 0.0)]),
        verdict="Halving | costs nothing.\nKeep 30 s.",
    )
    abandoned = _trial(tmp_path, "002", status="abandoned")
    text = tracking.render(
        [_factor("seal_timeout", "seal_timeout", "tested", ["001", "002"])],
        [closed, abandoned],
    )
    row = _row(text.replace("\\|", "<pipe>"), "seal_timeout")
    assert row[4:6] == ["tested", "001, 002"]
    assert row[6] == (
        "30.0: 12.5 min/whole cell, 2.0 whole cells/slice<br>"
        "60.0: – min/whole cell, 0.0 whole cells/slice"
    )
    assert row[7] == "Halving <pipe> costs nothing. Keep 30 s."


def test_trials_of_other_factors_do_not_leak_into_a_row(tmp_path):
    closed = _trial(
        tmp_path,
        "001",
        status="closed",
        results=_results([(30.0, 1.0, 1.0), (60.0, 2.0, 1.0)]),
        verdict="v",
    )
    text = tracking.render([_factor("min_health", "min_health")], [closed])
    assert _row(text, "min_health")[5:] == ["", "", ""]


def test_regenerate_writes_the_rendered_table(tmp_path):
    cat_path = tmp_path / "factors.yaml"
    shutil.copy(TEST_CATALOGUE, cat_path)
    trials_dir = tmp_path / "trials"
    trials_dir.mkdir()
    out = tmp_path / "tracking.md"
    written = tracking.regenerate(cat_path, trials_dir, out)
    assert written == out
    assert out.read_text() == tracking.render(catalogue.load(cat_path), [])
    assert "generated" in out.read_text().splitlines()[0].lower()


def test_committed_tracking_table_is_current(tmp_path):
    cat_path = tmp_path / "factors.yaml"
    cat_path.write_text(committed(catalogue.DEFAULT_PATH))
    trials_dir = tmp_path / "trials"
    for name in committed_names(record.TRIALS_DIR):
        if Path(name).name == record.FILE_NAME:
            (trials_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (trials_dir / name).write_text(committed(record.TRIALS_DIR / name))
    trials_dir.mkdir(exist_ok=True)
    assert committed(tracking.DEFAULT_OUT) == tracking.render(
        catalogue.load(cat_path), record.all_trials(trials_dir)
    )


def test_readme_documents_the_fixed_agent_prompt():
    readme = (tracking.DEFAULT_OUT.parent / "README.md").read_text()
    assert agent.FIXED_PROMPT in readme
    assert "analysisAgent" in readme


def test_readme_says_the_tool_runs_from_a_source_checkout():
    readme = (tracking.DEFAULT_OUT.parent / "README.md").read_text()
    assert "source checkout" in readme
