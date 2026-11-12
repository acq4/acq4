"""Tests for upgrading deprecated patch profile forms (string tables, parallel pulse lists)."""
from __future__ import annotations

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.devices.PatchPipette.states.break_in import BreakInState
from acq4.devices.PatchPipette.states.clean import CleanState
from acq4.devices.PatchPipette.states.clear_access import ClearAccessState


@pytest.fixture
def profiles(monkeypatch):
    # Marked loaded so nothing reaches for the Manager's config.
    store = {}
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


def test_string_table_is_evaluated_with_units():
    config = CleanState.upgradeConfig(
        {'cleanSequence': "[(-35*kPa, 2.0*s)] + [(65*kPa, 1.0*s)] * 2", 'rinseSequence': []}, 'p')
    assert config == {'cleanSequence': [(-35e3, 2.0), (65e3, 1.0), (65e3, 1.0)], 'rinseSequence': []}


def test_current_config_is_unchanged():
    config = {'pulses': [(1, 0.2, -30e3, 0)], 'pulseInterval': 3}
    assert BreakInState.upgradeConfig(config, 'p') == config


def test_break_in_lists_merge_into_pulses():
    config = BreakInState.upgradeConfig({
        'nPulses': "[1, 2]",
        'pulseDurations': "[0.2*s, 0.3*s]",
        'pulsePressures': [-5e3, -10e3],
        'pulseInterval': 3,
    }, 'p')
    # no zapDurations: zaps off
    assert config == {'pulses': [(1, 0.2, -5e3, 0), (2, 0.3, -10e3, 0)], 'pulseInterval': 3}


def test_break_in_missing_lists_come_from_default_pulses():
    config = BreakInState.upgradeConfig({'pulsePressures': [-1e3] * 10, 'zapDurations': "[]"}, 'p')
    default = BreakInState.defaultConfig()['pulses']
    assert config['pulses'] == [(n, d, -1e3, 0) for n, d, _, _ in default]


def test_mismatched_list_lengths_raise():
    with pytest.raises(ValueError, match='same length'):
        BreakInState.upgradeConfig({'nPulses': [1, 1], 'zapDurations': [1e-3]}, 'p')


def test_clear_access_lists_merge_into_pulses():
    config = ClearAccessState.upgradeConfig(
        {'nPulses': [1], 'pulseDurations': [0.5], 'pulsePressures': [-20e3]}, 'p')
    assert config == {'pulses': [(1, 0.5, -20e3)]}


def test_addProfile_upgrades_and_validates(profiles):
    PatchPipetteStateManager.addProfile("legacy", {
        "break in": {"nPulses": "[1]", "pulseDurations": "[0.2]", "pulsePressures": "[-30*kPa]"},
        "clean": {"cleanSequence": "[(-35*kPa, 2*s)]"},
    })
    assert profiles["legacy"] == {
        "break in": {"pulses": [(1, 0.2, -30e3, 0)]},
        "clean": {"cleanSequence": [(-35e3, 2.0)]},
    }
