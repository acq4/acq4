"""Tests for run-group scaffolding: trial dirs, catalogue updates, mutator stubs, statistics warning."""

import importlib.util
import shutil
from pathlib import Path

import pytest

from acq4.modules.Autopatch.performance_tuning import catalogue, record, scaffold
from acq4.modules.Autopatch.performance_tuning.mutators import base

from .conftest import MUTATORS_INIT

PROTOCOL = "acq4/modules/Autopatch/example_protocols/_example_patch.py"
TRIALS_GITIGNORE = Path(scaffold.__file__).parent / "trials" / ".gitignore"


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


@pytest.fixture
def idea_catalogue(cat_path):
    factors = catalogue.load(cat_path)
    factors.append(
        catalogue.Factor(
            name="approach_speed",
            summary="Pipette approach speed",
            mutator=None,
            hypothesis="h",
            priority="low",
            status="untested",
        )
    )
    catalogue.save(factors, cat_path)
    return cat_path


@pytest.fixture
def mutators_dir(tmp_path):
    d = tmp_path / "mutators"
    d.mkdir()
    (d / "__init__.py").write_text(MUTATORS_INIT)
    return d


def finished_stub(mutators_dir, base_name="ProfileParamMutator", point="patching"):
    param = "approach.belowSurfaceSpeed" if base_name == "ProfileParamMutator" else None
    path = scaffold.mutator_stub(
        "approach_speed", base_name, point, mutators_dir=mutators_dir, param=param
    )
    text = path.read_text().replace(
        '["replace me: first condition", "replace me: second condition"]',
        "[5e-6, 1e-5]",
    )
    path.write_text(text)
    return path


def test_registering_a_finished_stub_wires_it_everywhere(idea_catalogue, mutators_dir):
    finished_stub(mutators_dir)
    registry = {}
    cls = scaffold.register_mutator(
        "approach_speed", mutators_dir, idea_catalogue, registry
    )
    assert cls.name == "approach_speed" and cls.conditions == [5e-6, 1e-5]
    assert registry == {"approach_speed": cls}
    init = (mutators_dir / "__init__.py").read_text()
    assert "from .approach_speed import ApproachSpeed\n" in init
    assert "build_registry((SealTimeout, MinHealth, ApproachSpeed))" in init
    entry = next(
        f for f in catalogue.load(idea_catalogue) if f.name == "approach_speed"
    )
    assert entry.mutator == "approach_speed"


def _unchanged(mutators_dir, idea_catalogue, registry, init_before, cat_before):
    assert registry == {}
    assert (mutators_dir / "__init__.py").read_text() == init_before
    assert idea_catalogue.read_text() == cat_before


@pytest.mark.parametrize(
    "prepare, message",
    [
        (
            lambda d: scaffold.mutator_stub(
                "approach_speed",
                "ProfileParamMutator",
                "patching",
                d,
                param="approach.belowSurfaceSpeed",
            ),
            "replace me",
        ),
        (lambda d: finished_stub(d, "ValueMutator", "min_health"), "implement value"),
        (lambda d: finished_stub(d, "ScopeMutator", "patching"), "implement around"),
        (
            lambda d: finished_stub(d, "ProfileParamMutator", "no_such_scope"),
            "unknown tuning point",
        ),
        (lambda d: None, "no stub"),
    ],
)
def test_an_unfinished_or_broken_stub_is_refused_and_nothing_changes(
    idea_catalogue, mutators_dir, prepare, message
):
    prepare(mutators_dir)
    init_before = (mutators_dir / "__init__.py").read_text()
    cat_before = idea_catalogue.read_text()
    registry = {}
    with pytest.raises(scaffold.InvalidMutator, match=message):
        scaffold.register_mutator(
            "approach_speed", mutators_dir, idea_catalogue, registry
        )
    _unchanged(mutators_dir, idea_catalogue, registry, init_before, cat_before)


def test_a_registered_name_is_refused(idea_catalogue, mutators_dir):
    finished_stub(mutators_dir)
    with pytest.raises(scaffold.InvalidMutator, match="already registered"):
        scaffold.register_mutator(
            "approach_speed", mutators_dir, idea_catalogue, {"approach_speed": object}
        )


def test_awaiting_registration_lists_factors_with_a_stub_and_no_mutator(
    idea_catalogue, mutators_dir
):
    assert scaffold.awaiting_registration(mutators_dir, idea_catalogue) == []
    finished_stub(mutators_dir)
    assert scaffold.awaiting_registration(mutators_dir, idea_catalogue) == [
        "approach_speed"
    ]
