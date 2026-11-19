"""Tests for the tuning-point registry and the API with no runtime installed."""

import subprocess
import sys

import pytest

from acq4.util import tuning_points
from acq4.util.tuning_points import POINTS, TuningPointError, resolve_fact


def test_value_returns_default_when_nothing_installed():
    assert tuning_points.value("min_health", 0.5, facts={"score": 0.9}) == 0.5


def test_scope_is_null_context_when_nothing_installed():
    ran = False
    with tuning_points.scope("patching", facts={"ctx": object()}):
        ran = True
    assert ran


def test_unknown_point_raises():
    with pytest.raises(TuningPointError):
        tuning_points.value("no_such_point", 1)
    with pytest.raises(TuningPointError):
        tuning_points.scope("no_such_point")


def test_value_on_scope_point_raises():
    with pytest.raises(TuningPointError):
        tuning_points.value("patching", None, facts={"ctx": 1})


def test_scope_on_value_point_raises():
    with pytest.raises(TuningPointError):
        tuning_points.scope("min_health", facts={"score": 1})


@pytest.mark.parametrize(
    "facts",
    [None, {}, {"scor": 1}, {"score": 1, "extra": 2}, {"extra": 2}],
)
def test_facts_keys_must_match_registry(facts):
    with pytest.raises(TuningPointError):
        tuning_points.value("min_health", 0.5, facts=facts)


def test_callable_fact_resolved_only_on_read():
    calls = []

    def score():
        calls.append(1)
        return 0.7

    facts = {"score": score}
    assert tuning_points.value("min_health", 0.5, facts=facts) == 0.5
    assert calls == []
    assert resolve_fact(facts, "score") == 0.7
    assert calls == [1]
    assert resolve_fact({"score": 3}, "score") == 3


def test_registry_entries_well_formed():
    assert set(POINTS) >= {
        "min_health",
        "pipette_detector_class",
        "patching",
        "whole_cell",
    }
    for name, point in POINTS.items():
        assert point.kind in ("value", "scope"), name
        assert point.unit_hint in ("cell", "survey", "slice"), name
        assert isinstance(point.facts, tuple), name
        assert all(isinstance(f, str) for f in point.facts), name
        assert point.doc and point.site, name


def test_module_imports_nothing_from_modules_or_experiment():
    code = (
        "import acq4.util.tuning_points, sys; "
        "print([m for m in sys.modules if m.startswith(('acq4.modules','acq4.experiment'))])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"
