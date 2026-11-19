"""Tests for the mutator base classes, SealTimeout and the MUTATORS registry."""

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.experiment.context import ExecutionContext
from acq4.modules.Autopatch.performance_tuning.mutators import MUTATORS
from acq4.modules.Autopatch.performance_tuning.mutators.base import (
    Mutator,
    ProfileParamMutator,
)
from acq4.modules.Autopatch.performance_tuning.mutators.seal import SealTimeout


class _FakeStateManager:
    def getProfile(self):
        return "default"


class _FakePipette:
    def name(self):
        return "Pipette1"

    def stateManager(self):
        return _FakeStateManager()


@pytest.fixture
def profiles(monkeypatch):
    store = {"default": {"seal": {"autoSealTimeout": 30.0}}}
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


@pytest.fixture
def ctx():
    return ExecutionContext(pipette=_FakePipette(), on_log_action=lambda e: None)


class _TwoParam(ProfileParamMutator):
    name = "two_param"
    unit = "cell"
    params = {"seal": "autoSealTimeout", "whole cell": "detectionTau"}
    conditions = [
        {"autoSealTimeout": 10.0, "detectionTau": 1.0},
        {"autoSealTimeout": 20.0, "detectionTau": 2.0},
    ]


def test_seal_timeout_pins_and_restores_the_profile_param(ctx, profiles):
    m = SealTimeout()
    with m.around("patching", 60.0, {"ctx": ctx}):
        assert profiles["default"]["seal"]["autoSealTimeout"] == 60.0
    assert profiles["default"]["seal"]["autoSealTimeout"] == 30.0


def test_seal_timeout_declaration():
    m = SealTimeout()
    assert (m.name, m.unit, m.wraps) == ("seal_timeout", "cell", {"patching"})
    assert m.conditions == [30.0, 60.0]
    assert m.eligible({}) is True


def test_dict_condition_sets_every_declared_param(ctx, profiles):
    with _TwoParam().around("patching", _TwoParam.conditions[1], {"ctx": ctx}):
        assert profiles["default"]["seal"]["autoSealTimeout"] == 20.0
        assert profiles["default"]["whole cell"]["detectionTau"] == 2.0
    assert profiles["default"]["seal"]["autoSealTimeout"] == 30.0
    assert "whole cell" not in profiles["default"]


def test_registry_names_are_unique_and_match_classes():
    assert all(name == cls.name for name, cls in MUTATORS.items())
    assert issubclass(MUTATORS["seal_timeout"], Mutator)
    assert MUTATORS["seal_timeout"] is SealTimeout
