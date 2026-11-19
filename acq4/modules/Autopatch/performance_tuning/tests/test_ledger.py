"""Tests for the JSONL assignment ledger."""

import os
import random
import warnings

import pytest

import acq4.util.DataManager as dm
from acq4.modules.Autopatch.performance_tuning.ledger import (
    JsonlLedger,
    ledger_path,
    read_lines,
)
from acq4.util import tuning_points
from acq4.util.tuning_points import INELIGIBLE, Runtime, TuningPointWarning


class ConfigDir:
    def __init__(self, root):
        self.root = root

    def configFileName(self, name):
        return os.path.join(self.root, name)


def decision(mutator, unit, unit_id, slice_id, condition=None, slice_dir=None, **kw):
    line = {
        "event": "decision",
        "mutator": mutator,
        "unit": unit,
        "unit_id": unit_id,
        "slice_id": slice_id,
        "slice_dir": slice_dir,
    }
    if condition is None:
        line["eligible"] = False
    else:
        line["condition"] = condition
    line.update(kw)
    return line


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "config" / "modules" / "AutopatchTuning" / "runs" / "r.jsonl")


def test_ledger_path_uses_config_file_name(tmp_path):
    p = ledger_path(ConfigDir(str(tmp_path)), "run-7")
    assert p == str(tmp_path / "modules" / "AutopatchTuning" / "runs" / "run-7.jsonl")


def test_round_trip_and_gitignore(path):
    ledger = JsonlLedger(path)
    line = decision("m", "cell", "c1", "s1", condition="a")
    ledger.record(line)
    assert read_lines(path) == [line]
    assert ledger.lines() == [line]
    gitignore = os.path.join(os.path.dirname(os.path.dirname(path)), ".gitignore")
    assert open(gitignore).read() == "*\n"


def test_existing_gitignore_untouched(path):
    gitignore = os.path.join(os.path.dirname(os.path.dirname(path)), ".gitignore")
    os.makedirs(os.path.dirname(gitignore))
    with open(gitignore, "w") as f:
        f.write("custom\n")
    ledger = JsonlLedger(path)
    ledger.record(decision("m", "cell", "c1", "s1", condition="a"))
    ledger.record(decision("m", "cell", "c2", "s1", condition="a"))
    assert open(gitignore).read() == "custom\n"


def test_slice_mirror(path, tmp_path):
    slice_dir = tmp_path / "slice_000"
    slice_dir.mkdir()
    ledger = JsonlLedger(path)
    mirrored = decision("m", "cell", "c1", "s1", "a", slice_dir=str(slice_dir))
    ledger.record(mirrored)
    ledger.record(decision("m", "survey", "v1", None, "a"))
    assert read_lines(str(slice_dir / "performance_tuning_ledger.jsonl")) == [mirrored]
    assert len(read_lines(path)) == 2


def test_cell_units_counted_within_slice(path):
    ledger = JsonlLedger(path, random.Random(0))
    for i in range(2):
        ledger.record(decision("m", "cell", f"o{i}", "other", "a"))
    ledger.record(decision("m", "cell", "c1", "mine", "b"))
    assert ledger.choose("m", "cell", ["a", "b"], "mine") == "a"


def test_survey_units_counted_across_run(path):
    ledger = JsonlLedger(path, random.Random(0))
    ledger.record(decision("m", "survey", "v1", "s1", "b"))
    assert ledger.choose("m", "survey", ["a", "b"], "s2") == "a"


def test_ineligible_not_counted(path):
    ledger = JsonlLedger(path, random.Random(0))
    ledger.record(decision("m", "cell", "c1", "s1"))
    ledger.record(decision("m", "cell", "c2", "s1", "b"))
    assert ledger.choose("m", "cell", ["a", "b"], "s1") == "a"


def test_decisions_lookup_and_ineligible_sentinel(path):
    ledger = JsonlLedger(path)
    ledger.record(decision("m", "cell", "c1", "s1"))
    ledger.record(decision("m", "cell", "c2", "s1", {"x": 1}))
    assert ledger.decisions("m", "cell", "c1") is INELIGIBLE
    assert ledger.decisions("m", "cell", "c2") == {"x": 1}
    assert ledger.decisions("m", "cell", "nope") is None
    assert ledger.decisions("other", "cell", "c1") is None


def test_tie_broken_by_seeded_rng(path):
    picks = [
        JsonlLedger(path, random.Random(seed)).choose("m", "slice", ["a", "b"], None)
        for seed in range(20)
    ]
    assert set(picks) == {"a", "b"}
    again = [
        JsonlLedger(path, random.Random(seed)).choose("m", "slice", ["a", "b"], None)
        for seed in range(20)
    ]
    assert picks == again


def test_structured_conditions_compared_by_json(path):
    ledger = JsonlLedger(path, random.Random(0))
    ledger.record(decision("m", "survey", "v1", None, {"k": 1, "j": 2}))
    offered = [{"k": 3}, {"j": 2, "k": 1}]
    assert ledger.choose("m", "survey", offered, None) == {"k": 3}


def test_restart_sees_prior_lines(path):
    first = JsonlLedger(path, random.Random(0))
    first.record(decision("m", "cell", "c1", "s1", "b"))
    second = JsonlLedger(path, random.Random(0))
    assert second.decisions("m", "cell", "c1") == "b"
    assert second.choose("m", "cell", ["a", "b"], "s1") == "a"
    second.record(decision("m", "cell", "c2", "s1", "a"))
    assert len(read_lines(path)) == 2


def test_slice_dirs_first_seen_order(path, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ledger = JsonlLedger(path)
    for name in [str(b), None, str(a), str(b)]:
        ledger.record(
            {"event": "unit_open", "unit": "slice", "unit_id": "x", "slice_dir": name}
        )
    assert ledger.slice_dirs() == [str(b), str(a)]


class RecordingMutator:
    name = "m"
    unit = "cell"
    answers = {"min_health"}
    conditions = ["a", "b"]

    def eligible(self, facts):
        return True

    def value(self, point, default, condition, facts):
        return condition


def test_runtime_against_jsonl_ledger(path, tmp_path):
    root = dm.getDirHandle(str(tmp_path / "data"), create=True)
    slice_dir = root.mkdir("slice_000", info={"dirType": "Slice"})

    def run(ledger, names):
        runtime = Runtime("r", [RecordingMutator()], ledger)
        tuning_points.install(runtime)
        try:
            s = tuning_points.open_unit("slice", slice_dir=slice_dir)
            picks = []
            for name in names:
                cell = slice_dir.mkdir(name, info={"dirType": "Cell"})
                c = tuning_points.open_unit("cell", cell_dir=cell)
                picks.append(
                    tuning_points.value("min_health", None, facts={"score": 0.9})
                )
                tuning_points.close_unit(c)
            tuning_points.close_unit(s)
            return picks
        finally:
            tuning_points.uninstall()

    with warnings.catch_warnings():
        warnings.simplefilter("error", TuningPointWarning)
        first = run(JsonlLedger(path, random.Random(0)), ["c0", "c1", "c2", "c3"])
        assert sorted(first) == ["a", "a", "b", "b"]
        # a restarted run in the same slice continues the balance
        second = run(JsonlLedger(path, random.Random(1)), ["c4", "c5"])
    assert sorted(second) == ["a", "b"]
    mirror = read_lines(
        os.path.join(slice_dir.name(), "performance_tuning_ledger.jsonl")
    )
    assert mirror == read_lines(path)
    assert sum(1 for line in mirror if line["event"] == "decision") == 6
