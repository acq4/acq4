"""Tests for run-group scaffolding: trial dirs, catalogue updates, mutator stubs, statistics warning."""

import importlib.util
import shutil
from pathlib import Path

import pytest

from acq4.modules.Autopatch.performance_tuning import catalogue, record, scaffold
from acq4.modules.Autopatch.performance_tuning.mutators import base

PROTOCOL = "acq4/modules/Autopatch/example_protocols/example_patch.py"
TRIALS_GITIGNORE = Path(scaffold.__file__).parent / "trials" / ".gitignore"


@pytest.fixture
def cat_path(tmp_path):
    path = tmp_path / "factors.yaml"
    shutil.copy(catalogue.DEFAULT_PATH, path)
    return path


@pytest.fixture
def factors(cat_path):
    return catalogue.load(cat_path)


def make_group(factors, tmp_path, cat_path, **kw):
    kw.setdefault("interactions_expected", True)
    kw.setdefault("interaction_notes", "both touch patching timing")
    return scaffold.new_run_group(
        factors,
        PROTOCOL,
        trials_dir=tmp_path / "trials",
        catalogue_path=cat_path,
        **kw,
    )


def test_next_trial_id_starts_at_001(tmp_path):
    assert scaffold.next_trial_id(tmp_path) == "001"


def test_next_trial_id_follows_highest(tmp_path):
    (tmp_path / "001-a").mkdir()
    (tmp_path / "007-b").mkdir()
    assert scaffold.next_trial_id(tmp_path) == "008"


def test_two_factor_group_shares_run_fields(factors, tmp_path, cat_path):
    trials = make_group(factors, tmp_path, cat_path)
    assert [t.id for t in trials] == ["001", "002"]
    assert [t.dir.name for t in trials] == ["001-seal-timeout", "002-min-health"]
    assert len({t.run_id for t in trials}) == 1
    assert {t.protocol for t in trials} == {PROTOCOL}
    assert trials[0].mutators == trials[1].mutators
    assert set(trials[0].mutators) == {"seal_timeout", "min_health"}
    assert trials[0].mutators["seal_timeout"] == {
        "class": "SealTimeout",
        "unit": "cell",
        "conditions": [30.0, 60.0],
    }


def test_each_trial_has_own_primary_factor_and_fields(factors, tmp_path, cat_path):
    trials = make_group(factors, tmp_path, cat_path)
    assert [t.primary_factor for t in trials] == ["seal_timeout", "min_health"]
    assert trials[0].title == factors[0].summary
    assert trials[0].hypothesis == factors[0].hypothesis
    assert trials[0].status == "planned"
    assert trials[0].data == []
    assert trials[0].results is None and trials[0].verdict is None
    assert trials[0].closed_on is None
    assert trials[0].interactions_expected is True
    assert trials[0].interaction_notes == "both touch patching timing"


def test_dirs_are_empty_and_saved_records_validate(factors, tmp_path, cat_path):
    trials = make_group(factors, tmp_path, cat_path)
    for t in trials:
        assert list((t.dir / "analyses").iterdir()) == []
        assert list((t.dir / "data").iterdir()) == []
    loaded = record.all_trials(tmp_path / "trials")
    for t in loaded:
        assert record.validate(t, [o for o in loaded if o is not t]) == []


def test_catalogue_marks_factors_running(factors, tmp_path, cat_path):
    make_group(factors, tmp_path, cat_path)
    by_name = {f.name: f for f in catalogue.load(cat_path)}
    assert by_name["seal_timeout"].status == "running"
    assert by_name["seal_timeout"].trials == ["001"]
    assert by_name["min_health"].trials == ["002"]


def test_run_id_default_and_explicit(factors, tmp_path, cat_path):
    trials = make_group(factors[:1], tmp_path, cat_path)
    assert trials[0].run_id.endswith("-seal_timeout")
    other = make_group(factors[1:], tmp_path, cat_path, run_id="mine")
    assert other[0].run_id == "mine"
    assert other[0].id == "002"


def test_multi_factor_requires_an_interactions_answer(factors, tmp_path, cat_path):
    with pytest.raises(scaffold.InvalidRunGroup, match="interact"):
        make_group(factors, tmp_path, cat_path, interactions_expected=None)
    assert not (tmp_path / "trials").exists()


def test_no_interactions_expected_needs_no_notes(factors, tmp_path, cat_path):
    trials = make_group(
        factors, tmp_path, cat_path, interactions_expected=False, interaction_notes=""
    )
    assert [t.interactions_expected for t in trials] == [False, False]


def test_single_factor_needs_no_interactions_answer(factors, tmp_path, cat_path):
    assert (
        len(make_group(factors[:1], tmp_path, cat_path, interactions_expected=None))
        == 1
    )


def test_combination_errors_refuse_before_writing(factors, tmp_path, cat_path):
    with pytest.raises(ValueError):
        make_group([factors[0], factors[0]], tmp_path, cat_path)
    assert not (tmp_path / "trials").exists()
    assert catalogue.load(cat_path)[0].status == "untested"


def load_stub(path):
    spec = importlib.util.spec_from_file_location("stub_mod", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "base_name, point, param, attr, expected",
    [
        ("ValueMutator", "min_health", None, "answers", {"min_health"}),
        ("ScopeMutator", "patching", None, "wraps", {"patching"}),
        (
            "ProfileParamMutator",
            "patching",
            "seal.autoSealTimeout",
            "params",
            (("seal", "autoSealTimeout"),),
        ),
        (
            "ProfileParamMutator",
            "patching",
            "seal.autoSealTimeout",
            "wraps",
            {"patching"},
        ),
        (
            "ProfileParamMutator",
            "whole_cell",
            "seal.autoSealTimeout",
            "wraps",
            {"whole_cell"},
        ),
    ],
)
def test_mutator_stub(tmp_path, base_name, point, param, attr, expected):
    path = scaffold.mutator_stub(
        "my_factor", base_name, point, mutators_dir=tmp_path, param=param
    )
    assert path == tmp_path / "my_factor.py"
    module = load_stub(path)
    cls = next(
        v
        for v in vars(module).values()
        if isinstance(v, type) and v.__module__ == "stub_mod"
    )
    assert issubclass(cls, getattr(base, base_name))
    assert cls.name == "my_factor"
    assert cls.unit == "cell"
    assert len(cls.conditions) == 2
    assert getattr(cls, attr) == expected
    assert "replace" in module.__doc__.lower()
    assert "MUTATORS" in module.__doc__


def test_a_profile_param_stub_needs_a_state_and_a_param(tmp_path):
    with pytest.raises(ValueError, match="state.param"):
        scaffold.mutator_stub(
            "f", "ProfileParamMutator", "patching", mutators_dir=tmp_path
        )
    assert not (tmp_path / "f.py").exists()


def test_mutator_stub_methods_raise(tmp_path):
    module = load_stub(
        scaffold.mutator_stub("f", "ValueMutator", "p", mutators_dir=tmp_path)
    )
    cls = next(
        v
        for v in vars(module).values()
        if isinstance(v, type) and v.__module__ == "stub_mod"
    )
    with pytest.raises(NotImplementedError):
        cls().value("p", None, 1, {})


def test_mutator_stub_refuses_overwrite(tmp_path):
    scaffold.mutator_stub("f", "ValueMutator", "p", mutators_dir=tmp_path)
    with pytest.raises(FileExistsError):
        scaffold.mutator_stub("f", "ValueMutator", "p", mutators_dir=tmp_path)


def test_mutator_stub_rejects_unknown_base(tmp_path):
    with pytest.raises(ValueError):
        scaffold.mutator_stub("f", "Mutator", "p", mutators_dir=tmp_path)


def test_statistics_warning_for_survey_unit(factors):
    warning = scaffold.statistics_warning(factors)
    assert "min_health" in warning and "seal_timeout" not in warning
    assert "survey" in warning


def test_no_statistics_warning_for_cell_unit(factors):
    assert scaffold.statistics_warning(factors[:1]) is None


def test_trials_gitignore_contents():
    assert TRIALS_GITIGNORE.read_text() == "*/data/\n*/analyses/\n"
