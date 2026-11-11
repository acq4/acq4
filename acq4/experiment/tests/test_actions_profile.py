"""Tests for the patch-profile action: what it pins, and what it leaves behind."""
from __future__ import annotations

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.experiment.actions import change_patch_profile_params
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import OrchestrationError


class _FakeStateManager:
    def __init__(self, profile):
        self._profile = profile

    def getProfile(self):
        return self._profile


class _FakePipette:
    def __init__(self, profile="default"):
        self._stateManager = _FakeStateManager(profile)

    def name(self):
        return "Pipette1"

    def stateManager(self):
        return self._stateManager


@pytest.fixture
def profiles(monkeypatch):
    store = {
        "default": {"seal": {"autoSealTimeout": 30.0}},
        "other": {},
    }
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


@pytest.fixture
def ctx():
    entries = []
    context = ExecutionContext(pipette=_FakePipette(), on_log_action=entries.append)
    context.entries = entries
    return context


def test_the_params_are_pinned_for_the_body_and_dropped_after(ctx, profiles):
    with change_patch_profile_params(ctx, {"seal": {"autoSealTimeout": 12.0}}):
        assert profiles["default"]["seal"]["autoSealTimeout"] == 12.0

    assert profiles["default"]["seal"]["autoSealTimeout"] == 30.0


def test_a_param_the_profile_did_not_pin_goes_back_to_unpinned(ctx, profiles):
    with change_patch_profile_params(ctx, {"seal": {"sealThreshold": 2e9}}):
        assert profiles["default"]["seal"]["sealThreshold"] == 2e9

    assert "sealThreshold" not in profiles["default"]["seal"]


def test_a_state_the_profile_did_not_configure_is_left_unconfigured(ctx, profiles):
    with change_patch_profile_params(ctx, {"bath": {"bathThreshold": 50e6}}):
        assert profiles["default"]["bath"] == {"bathThreshold": 50e6}

    assert "bath" not in profiles["default"]


def test_a_raising_body_still_restores(ctx, profiles):
    with pytest.raises(ZeroDivisionError):
        with change_patch_profile_params(ctx, {"seal": {"autoSealTimeout": 12.0}}):
            raise ZeroDivisionError

    assert profiles["default"]["seal"]["autoSealTimeout"] == 30.0


def test_an_edit_made_during_the_body_survives_the_restore(ctx, profiles):
    with change_patch_profile_params(ctx, {"seal": {"autoSealTimeout": 12.0}}):
        PatchPipetteStateManager.addProfile(
            "default",
            {"seal": {"autoSealTimeout": 12.0, "sealThreshold": 5e9}},
            overwrite=True,
        )

    assert profiles["default"]["seal"] == {
        "autoSealTimeout": 30.0,
        "sealThreshold": 5e9,
    }


def test_a_named_profile_is_changed_instead_of_the_pipettes(ctx, profiles):
    with change_patch_profile_params(
        ctx, {"seal": {"autoSealTimeout": 12.0}}, profile="other"
    ):
        assert profiles["other"]["seal"]["autoSealTimeout"] == 12.0
        assert profiles["default"]["seal"]["autoSealTimeout"] == 30.0

    assert "seal" not in profiles["other"]


def test_a_bare_call_pins_the_params_for_good(ctx, profiles):
    change_patch_profile_params(ctx, {"seal": {"autoSealTimeout": 12.0}})

    assert profiles["default"]["seal"]["autoSealTimeout"] == 12.0


def test_both_the_change_and_the_restore_reach_the_timeline(ctx, profiles):
    with change_patch_profile_params(ctx, {"seal": {"autoSealTimeout": 12.0}}):
        assert [entry.name for entry in ctx.entries] == ["Change Patch Profile Params"]

    assert [entry.name for entry in ctx.entries] == [
        "Change Patch Profile Params",
        "Restore Patch Profile Params",
    ]


def test_an_unknown_parameter_changes_nothing(ctx, profiles):
    with pytest.raises(OrchestrationError, match="noSuchParam"):
        change_patch_profile_params(ctx, {"seal": {"noSuchParam": 1}})

    assert profiles["default"] == {"seal": {"autoSealTimeout": 30.0}}


def test_an_unknown_profile_names_the_ones_there_are(ctx, profiles):
    with pytest.raises(OrchestrationError, match="default"):
        change_patch_profile_params(ctx, {"seal": {}}, profile="nonesuch")


def test_no_selected_profile_is_an_error(profiles):
    ctx = ExecutionContext(pipette=_FakePipette(profile=None))

    with pytest.raises(OrchestrationError, match="no patch profile"):
        change_patch_profile_params(ctx, {"seal": {"autoSealTimeout": 12.0}})
