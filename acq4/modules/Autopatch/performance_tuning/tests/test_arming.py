"""Tests for arming: static conflict checks, install and uninstall."""

import random

import pytest

from acq4.modules.Autopatch.performance_tuning import arming
from acq4.modules.Autopatch.performance_tuning.mutators.base import (
    ProfileParamMutator,
    ScopeMutator,
    ValueMutator,
)
from acq4.util import tuning_points
from acq4.util.tests.data_dir_helpers import strip_uuid
from acq4.util.tests.memory_ledger import MemoryLedger
from acq4.util.tuning_points import TuningPointError


def _value(name="v", answers=("min_health",), conditions=(0.5, 0.7)):
    return type(
        "V",
        (ValueMutator,),
        dict(
            name=name, unit="survey", answers=set(answers), conditions=list(conditions)
        ),
    )()


def _scope(name="s", wraps=("patching",), conditions=(1, 2)):
    return type(
        "S",
        (ScopeMutator,),
        dict(name=name, unit="cell", wraps=set(wraps), conditions=list(conditions)),
    )()


def _profile(name, params, conditions=(1.0, 2.0)):
    return type(
        "P",
        (ProfileParamMutator,),
        dict(name=name, unit="cell", params=params, conditions=list(conditions)),
    )()


@pytest.fixture(autouse=True)
def _clean():
    tuning_points.uninstall()
    yield
    tuning_points.uninstall()


def test_unknown_point_is_refused():
    r = arming.check([_value(answers=("nope",))])
    assert any("nope" in e and "v" in e for e in r.errors)


def test_value_mutator_answering_a_scope_point_is_refused():
    r = arming.check([_value(answers=("patching",))])
    assert any("patching" in e for e in r.errors)


def test_scope_mutator_wrapping_a_value_point_is_refused():
    r = arming.check([_scope(wraps=("min_health",))])
    assert any("min_health" in e for e in r.errors)


def test_two_value_mutators_on_one_point_are_refused():
    r = arming.check([_value("a"), _value("b")])
    assert any("a" in e and "b" in e and "min_health" in e for e in r.errors)


def test_same_profile_key_is_refused():
    r = arming.check(
        [
            _profile("a", (("seal", "autoSealTimeout"),)),
            _profile("b", (("seal", "autoSealTimeout"),)),
        ]
    )
    assert any("a" in e and "b" in e and "seal" in e for e in r.errors)


def test_disjoint_profile_keys_are_silent():
    r = arming.check(
        [
            _profile("a", (("seal", "autoSealTimeout"),)),
            _profile("b", (("seal", "sealThreshold"),)),
        ]
    )
    assert (r.errors, r.warnings) == ([], [])


def test_two_scope_mutators_on_one_point_warn():
    r = arming.check([_scope("a"), _scope("b")])
    assert r.errors == []
    assert any("a" in w and "b" in w and "patching" in w for w in r.warnings)


def test_scope_and_profile_mutator_on_one_point_warn():
    r = arming.check([_scope("a"), _profile("b", (("seal", "autoSealTimeout"),))])
    assert any("a" in w and "b" in w and "patching" in w for w in r.warnings)


def test_fewer_than_two_conditions_is_refused():
    r = arming.check([_value(conditions=(0.5,))])
    assert any("v" in e and "condition" in e for e in r.errors)


def test_a_plain_object_is_refused():
    class Plain:
        name = "plain"
        unit = "cell"
        conditions = [1, 2]

    r = arming.check([Plain()])
    assert any("plain" in e for e in r.errors)


def test_clean_set_has_no_errors_or_warnings():
    r = arming.check([_value(), _scope()])
    assert (r.errors, r.warnings) == ([], [])


def test_install_refuses_on_errors():
    with pytest.raises(TuningPointError, match="nope"):
        arming.install(
            "run-1", [_value(answers=("nope",))], MemoryLedger(random.Random(0))
        )
    assert tuning_points.installed() is None


def test_install_and_uninstall():
    arming.install("run-1", [_value()], MemoryLedger(random.Random(0)))
    assert tuning_points.installed().run_id == "run-1"
    arming.uninstall()
    assert tuning_points.installed() is None


def test_install_passes_the_cell_close_hook_through():
    hook = lambda cell_dir: {}
    arming.install(
        "run-1", [_value()], MemoryLedger(random.Random(0)), cell_close_hook=hook
    )
    assert tuning_points.installed().cell_close_hook is hook


def test_a_mutator_exception_propagates_out_of_value():
    class Boom(ValueMutator):
        name = "boom"
        unit = "survey"
        answers = {"min_health"}
        conditions = [1, 2]

        def value(self, point, default, condition, facts):
            raise RuntimeError("boom")

    arming.install("run-1", [Boom()], MemoryLedger(random.Random(0)))
    with tuning_points.unit("survey"):
        with pytest.raises(RuntimeError, match="boom"):
            tuning_points.value("min_health", 0.5, facts={"score": 1})


def test_refuse_reason_while_orchestrator_running(slice_dir):
    assert "running" in arming.refuse_reason(True, slice_dir)
    assert arming.refuse_reason(False, slice_dir) is None


def test_duplicate_param_name_within_one_mutator_is_refused():
    r = arming.check(
        [_profile("a", (("seal", "autoSealTimeout"), ("approach", "autoSealTimeout")))]
    )
    assert any("a" in e and "autoSealTimeout" in e for e in r.errors)


def test_two_params_in_one_state_on_one_mutator_are_fine():
    r = arming.check(
        [_profile("a", (("seal", "autoSealTimeout"), ("seal", "sealThreshold")))]
    )
    assert (r.errors, r.warnings) == ([], [])


def test_shared_pair_among_multi_param_mutators_is_refused():
    a = _profile("a", (("seal", "autoSealTimeout"), ("seal", "sealThreshold")))
    b = _profile("b", (("seal", "sealThreshold"),))
    r = arming.check([a, b])
    assert any("a" in e and "b" in e and "sealThreshold" in e for e in r.errors)


@pytest.fixture
def slice_dir(tmp_path):
    from acq4.util.DataManager import getDirHandle

    root = getDirHandle(str(tmp_path), create=True)
    root.createIndex()
    return root.mkdir("Slice_000", info={"dirType": "Slice"})


def test_refuse_reason_without_slice_dir():
    assert arming.refuse_reason(False, None) == "no slice directory: press New slice"


def test_refuse_reason_when_slice_dir_lacks_uuid(slice_dir):
    strip_uuid(slice_dir)
    assert (
        arming.refuse_reason(False, slice_dir)
        == "slice directory has no uuid (made before uuids): press New slice"
    )


def test_refuse_reason_accepts_slice_dir_with_uuid(slice_dir):
    assert arming.refuse_reason(False, slice_dir) is None


def test_refuse_reason_reports_running_first(slice_dir):
    assert "running" in arming.refuse_reason(True, None)
