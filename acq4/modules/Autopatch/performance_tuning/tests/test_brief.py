"""Tests for analysis brief assembly and analysis directory numbering."""

import json

import pytest

from acq4.modules.Autopatch.performance_tuning import brief
from acq4.modules.Autopatch.performance_tuning.mutators.seal import SealTimeout
from acq4.modules.Autopatch.performance_tuning.tests.test_record import (
    make_trial,
    two_mutator_trial,
)

QUESTION = "does it hold for \"deep\" cells? $(touch pwned) `id` 'x'"


@pytest.fixture
def trial(tmp_path):
    t = two_mutator_trial(tmp_path, data=["slice_000", "slice_001"])
    (t.dir / "data" / "slice_000").mkdir(parents=True)
    (t.dir / "data" / "slice_000" / "performance_tuning_ledger.jsonl").write_text("")
    return t


def test_every_section_in_order(trial):
    text = brief.build_brief(trial, QUESTION)
    markers = [
        trial.hypothesis.strip(),
        "SealTimeout",
        "min_health",
        "performance_tuning_ledger.jsonl",
        brief.METADATA_CONTRACT,
        "attempts_with_conditions",
        "report.write",
        "no earlier analysis",
        "unit count",
        "Write only under",
        QUESTION,
    ]
    positions = [text.index(m) for m in markers]
    assert positions == sorted(positions)


def test_mutator_source_included(trial):
    text = brief.build_brief(trial, "q")
    assert "class SealTimeout(ProfileParamMutator):" in text
    assert "autoSealTimeout" in text


def test_point_registry_entries_included(trial):
    text = brief.build_brief(trial, "q")
    assert "Minimum health score for a surveyed cell" in text


def test_data_paths_absolute_and_missing_marked(trial):
    text = brief.build_brief(trial, "q")
    present = (trial.dir / "data" / "slice_000").resolve()
    missing = (trial.dir / "data" / "slice_001").resolve()
    assert f"{present}/performance_tuning_ledger.jsonl" in text
    assert f"{missing}/performance_tuning_ledger.jsonl" in text
    line = next(l for l in text.splitlines() if str(missing) in l and "missing" in l)
    assert str(present) not in line
    assert not any(str(present) in l and "missing" in l for l in text.splitlines())


def test_question_last_and_verbatim(trial):
    assert brief.build_brief(trial, QUESTION).rstrip().endswith(QUESTION)


def test_no_earlier_analyses_noted(trial):
    assert "no earlier analysis" in brief.build_brief(trial, "q")


def test_latest_summary_embedded(trial):
    older = brief.next_analysis_dir(trial, "older")
    newer = brief.next_analysis_dir(trial, "newer")
    (older / "out" / "summary.json").write_text(json.dumps({"marker": "OLD"}))
    (newer / "out" / "summary.json").write_text(json.dumps({"marker": "NEW"}))
    import os

    os.utime(older / "out" / "summary.json", (1, 1))
    text = brief.build_brief(trial, "q")
    assert "NEW" in text
    assert "OLD" not in text
    assert "no earlier analysis" not in text


def test_kind_selects_file_name(trial):
    assert "analyze.py" in brief.build_brief(trial, "q", kind="script")
    assert "analyze.ipynb" in brief.build_brief(trial, "q", kind="notebook")


def test_unknown_kind_raises(trial):
    with pytest.raises(ValueError):
        brief.build_brief(trial, "q", kind="spreadsheet")


def test_single_mutator_trial(tmp_path):
    t = make_trial(tmp_path)
    text = brief.build_brief(t, "q")
    assert "SealTimeout" in text
    assert "MinHealth" not in text


def test_next_analysis_dir_numbers_and_creates(trial):
    first = brief.next_analysis_dir(trial, "alpha")
    second = brief.next_analysis_dir(trial, "beta")
    assert first.name == "001-alpha"
    assert second.name == "002-beta"
    assert first.parent == trial.dir / "analyses"
    assert (first / "out").is_dir()


def test_write_brief(trial):
    d = brief.next_analysis_dir(trial, "alpha")
    path = brief.write_brief(d, "hello")
    assert path == d / "BRIEF.md"
    assert path.read_text() == "hello"
