"""Tests for the factor catalogue: load/save, validation, candidate ranking."""

import yaml

from acq4.modules.Autopatch.performance_tuning import catalogue
from acq4.modules.Autopatch.performance_tuning.catalogue import Factor
from acq4.modules.Autopatch.performance_tuning.mutators import MUTATORS


def factor(name="seal_timeout", **kw):
    fields = dict(
        name=name,
        summary="s",
        mutator=name,
        hypothesis="h",
        priority="medium",
        status="untested",
        trials=[],
        notes="",
    )
    fields.update(kw)
    return Factor(**fields)


def test_round_trip_is_stable_and_keeps_order(tmp_path):
    path = tmp_path / "f.yaml"
    factors = [factor("min_health", notes="n"), factor("seal_timeout", trials=["t1"])]
    catalogue.save(factors, path)
    assert catalogue.load(path) == factors
    first = path.read_text()
    catalogue.save(catalogue.load(path), path)
    assert path.read_text() == first
    assert list(yaml.safe_load(first)["factors"][0])[:2] == ["name", "summary"]


def test_valid_factors_have_no_errors():
    assert catalogue.validate([factor("seal_timeout"), factor("min_health")]) == []


def test_validate_flags_bad_enums_duplicates_and_mutators():
    errors = catalogue.validate(
        [
            factor("seal_timeout", priority="urgent", status="done"),
            factor("seal_timeout"),
            factor("wish", mutator="nope"),
            factor("min_health", mutator="seal_timeout"),
        ]
    )
    text = "\n".join(errors)
    assert "priority" in text and "status" in text
    assert "duplicate" in text
    assert "'nope'" in text
    assert "min_health" in text and "seal_timeout" in text


def test_validate_allows_null_mutator():
    assert catalogue.validate([factor("wish", mutator=None)]) == []


def test_load_rejects_unknown_keys(tmp_path):
    path = tmp_path / "f.yaml"
    path.write_text(
        "factors:\n- {name: a, summary: s, mutator: null, hypothesis: h,"
        " priority: low, status: untested, trials: [], bogus: 1}\n"
    )
    try:
        catalogue.load(path)
    except ValueError as e:
        assert "bogus" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_candidates_ranked_untested_with_mutator_only():
    factors = [
        factor("wish", mutator=None, priority="high"),
        factor("min_health", priority="low"),
        factor("seal_timeout", priority="high", status="tested"),
    ]
    assert [f.name for f in catalogue.candidates(5, factors)] == ["min_health"]
    factors[2].status = "untested"
    assert [f.name for f in catalogue.candidates(5, factors)] == [
        "seal_timeout",
        "min_health",
    ]
    assert [f.name for f in catalogue.candidates(1, factors)] == ["seal_timeout"]


def test_candidates_ties_keep_file_order():
    factors = [factor("min_health"), factor("seal_timeout")]
    assert [f.name for f in catalogue.candidates(5, factors)] == [
        "min_health",
        "seal_timeout",
    ]


def test_check_combination_refuses_two_answers_to_one_point(monkeypatch):
    class Twin(MUTATORS["min_health"]):
        name = "twin"

    monkeypatch.setitem(MUTATORS, "twin", Twin)
    chosen = [factor("min_health"), factor("twin")]
    assert catalogue.check_combination(chosen).errors
    names = [f.name for f in catalogue.candidates(5, chosen)]
    assert names == ["min_health"]


def test_shipped_catalogue_validates_and_covers_every_mutator():
    factors = catalogue.load()
    assert catalogue.validate(factors) == []
    assert set(MUTATORS) <= {f.mutator for f in factors}
