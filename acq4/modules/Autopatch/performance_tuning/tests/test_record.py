"""Tests for trial records: round-trip, validation, snapshot staleness, instantiation."""

import dataclasses

import pytest

from acq4.modules.Autopatch.performance_tuning import record
from acq4.modules.Autopatch.performance_tuning.mutators import MUTATORS
from acq4.modules.Autopatch.performance_tuning.mutators.seal import SealTimeout
from acq4.modules.Autopatch.performance_tuning.mutators.survey import MinHealth

PROTOCOL = "acq4/modules/Autopatch/example_protocols/example_patch.py"
SEAL = {"class": "SealTimeout", "unit": "cell", "conditions": [30.0, 60.0]}
HEALTH = {"class": "MinHealth", "unit": "survey", "conditions": [0.5, 0.7]}


def make_trial(tmp_path, **kw):
    fields = dict(
        dir=tmp_path / "001-seal-timeout",
        id="001",
        slug="seal-timeout",
        run_id="run-a",
        title="Seal timeout 30 s vs 60 s",
        status="planned",
        created="2026-11-13",
        primary_factor="seal_timeout",
        hypothesis="longer is better\n",
        protocol=PROTOCOL,
        mutators={"seal_timeout": dict(SEAL)},
        interaction_signoff="",
        quality_gate=None,
        data=[],
        results=None,
        verdict=None,
        closed_on=None,
        review_notes=[],
    )
    fields.update(kw)
    return record.Trial(**fields)


def two_mutator_trial(tmp_path, **kw):
    return make_trial(
        tmp_path,
        mutators={"seal_timeout": dict(SEAL), "min_health": dict(HEALTH)},
        interaction_signoff="different points, safe together",
        **kw,
    )


def test_round_trip_is_stable(tmp_path):
    trial = two_mutator_trial(
        tmp_path,
        quality_gate={"access_resistance_max": 25.0e6},
        data=["2026.11.14_000"],
    )
    trial.dir.mkdir()
    record.save(trial)
    assert record.load(trial.dir) == trial
    first = (trial.dir / "trial.yaml").read_text()
    record.save(record.load(trial.dir))
    assert (trial.dir / "trial.yaml").read_text() == first


def test_save_writes_spec_field_order(tmp_path):
    trial = make_trial(tmp_path)
    trial.dir.mkdir()
    record.save(trial)
    keys = [
        line.split(":")[0]
        for line in (trial.dir / "trial.yaml").read_text().splitlines()
        if line and not line[0].isspace()
    ]
    assert keys[:4] == ["id", "slug", "run_id", "title"]
    assert (
        keys.index("primary_factor") < keys.index("protocol") < keys.index("mutators")
    )
    assert keys[-1] == "review_notes"


def test_load_rejects_unknown_keys(tmp_path):
    trial = make_trial(tmp_path)
    trial.dir.mkdir()
    record.save(trial)
    with (trial.dir / "trial.yaml").open("a") as f:
        f.write("surprise: 1\n")
    with pytest.raises(ValueError, match="surprise"):
        record.load(trial.dir)


def test_all_trials_loads_every_trial_dir(tmp_path):
    for n in ("001", "002"):
        t = make_trial(tmp_path, id=n, dir=tmp_path / n)
        t.dir.mkdir()
        record.save(t)
    (tmp_path / "not-a-trial").mkdir()
    assert [t.id for t in record.all_trials(tmp_path)] == ["001", "002"]


def test_valid_trial_has_no_errors(tmp_path):
    assert record.validate(make_trial(tmp_path), []) == []


def test_rejects_bad_status(tmp_path):
    errors = record.validate(make_trial(tmp_path, status="done"), [])
    assert any("status" in e for e in errors)


def test_rejects_primary_factor_not_in_mutators(tmp_path):
    errors = record.validate(make_trial(tmp_path, primary_factor="min_health"), [])
    assert any("primary_factor" in e for e in errors)


@pytest.mark.parametrize(
    "protocol",
    ["/etc/passwd", "../outside.py", "acq4/no_such_protocol.py"],
)
def test_rejects_bad_protocol(tmp_path, protocol):
    errors = record.validate(make_trial(tmp_path, protocol=protocol), [])
    assert any("protocol" in e for e in errors)


def test_multiple_mutators_need_signoff(tmp_path):
    trial = two_mutator_trial(tmp_path)
    trial.interaction_signoff = ""
    assert any("interaction_signoff" in e for e in record.validate(trial, []))


def test_single_mutator_needs_no_signoff(tmp_path):
    assert record.validate(make_trial(tmp_path, interaction_signoff=""), []) == []


@pytest.mark.parametrize(
    "change",
    [
        {"protocol": "acq4/modules/Autopatch/example_protocols/example_patch_seq.py"},
        {"mutators": {"min_health": dict(HEALTH)}, "primary_factor": "min_health"},
        {"data": ["2026.11.14_000"]},
    ],
)
def test_siblings_must_agree(tmp_path, change):
    trial = make_trial(tmp_path)
    sibling = make_trial(tmp_path, id="002", **change)
    errors = record.validate(trial, [sibling])
    assert any("002" in e for e in errors)


def test_agreeing_siblings_are_fine(tmp_path):
    sibling = make_trial(tmp_path, id="002")
    assert record.validate(make_trial(tmp_path), [sibling]) == []


def test_fresh_snapshot_is_not_stale(tmp_path):
    assert record.stale_snapshot(two_mutator_trial(tmp_path)) == []


def test_stale_when_conditions_differ(tmp_path, monkeypatch):
    class Longer(SealTimeout):
        conditions = [30.0, 90.0]

    Longer.__name__ = "SealTimeout"
    monkeypatch.setitem(MUTATORS, "seal_timeout", Longer)
    problems = record.stale_snapshot(make_trial(tmp_path))
    assert len(problems) == 1 and "conditions" in problems[0]


def test_stale_when_unit_differs(tmp_path, monkeypatch):
    class Moved(MinHealth):
        unit = "cell"

    Moved.__name__ = "MinHealth"
    monkeypatch.setitem(MUTATORS, "min_health", Moved)
    trial = make_trial(
        tmp_path, mutators={"min_health": dict(HEALTH)}, primary_factor="min_health"
    )
    problems = record.stale_snapshot(trial)
    assert len(problems) == 1 and "unit" in problems[0]


def test_stale_when_class_unknown(tmp_path):
    trial = make_trial(
        tmp_path, mutators={"seal_timeout": dict(SEAL, **{"class": "Gone"})}
    )
    problems = record.stale_snapshot(trial)
    assert len(problems) == 1 and "Gone" in problems[0]


def test_stale_when_factor_not_registered(tmp_path):
    trial = make_trial(tmp_path, mutators={"ghost": dict(SEAL)}, primary_factor="ghost")
    assert any("ghost" in p for p in record.stale_snapshot(trial))


def test_stale_compares_dict_conditions_ignoring_key_order(tmp_path, monkeypatch):
    class Pinned(SealTimeout):
        conditions = [{"a": 1, "b": 2}]

    Pinned.__name__ = "SealTimeout"
    monkeypatch.setitem(MUTATORS, "seal_timeout", Pinned)
    spec = dict(SEAL, conditions=[{"b": 2, "a": 1}])
    assert (
        record.stale_snapshot(make_trial(tmp_path, mutators={"seal_timeout": spec}))
        == []
    )


def test_instantiate_follows_snapshot_order(tmp_path):
    trial = make_trial(
        tmp_path,
        mutators={"min_health": dict(HEALTH), "seal_timeout": dict(SEAL)},
        interaction_signoff="x",
    )
    mutators = record.instantiate(trial)
    assert [type(m) for m in mutators] == [MinHealth, SealTimeout]
