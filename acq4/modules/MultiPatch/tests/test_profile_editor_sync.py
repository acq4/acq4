"""Tests that the profile editor's tree follows changes made outside it without
echoing them back into the store."""
from __future__ import annotations

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.util import Qt


@pytest.fixture
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture
def profiles(monkeypatch):
    # Marked loaded so nothing reaches for the Manager's config.
    store = {
        "default": {"seal": {"autoSealTimeout": 45.0}},
        "derived": {"copyFrom": "default"},
    }
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


@pytest.fixture
def editor(qapp, profiles):
    from acq4.modules.MultiPatch.patchProfileEditor import ProfileEditor

    widget = ProfileEditor()
    try:
        yield widget
    finally:
        # deleteLater() needs an event-loop turn to land; until it does, this
        # widget would answer the next test's changes on the shared notifier.
        Qt.disconnect(
            PatchPipetteStateManager.profileNotifier().sigProfileConfigChanged,
            widget.profileConfigChanged,
        )
        widget.deleteLater()


@pytest.fixture
def resyncs(monkeypatch):
    """Profiles the editor re-applied to its tree. The notifier fires on every
    write, this editor's own included, so an echo shows as the editor acting on
    one rather than as an emission."""
    from acq4.devices.PatchPipette.statemanager import ProfileParameter

    seen = []
    original = ProfileParameter.syncFromConfig

    def record(self, config):
        seen.append(self.name())
        return original(self, config)

    monkeypatch.setattr(ProfileParameter, "syncFromConfig", record)
    return seen


def _param(editor, profile, state, name):
    return editor.param_root.child(profile, state, name)


def test_an_external_change_updates_the_tree(editor, profiles):
    assert _param(editor, "default", "seal", "autoSealTimeout").value() == 45.0

    PatchPipetteStateManager.addProfile(
        "default", {"seal": {"autoSealTimeout": 12.0}}, overwrite=True
    )

    assert _param(editor, "default", "seal", "autoSealTimeout").value() == 12.0


def test_a_param_dropped_externally_goes_back_to_its_default(editor):
    param = _param(editor, "default", "seal", "autoSealTimeout")
    assert param.valueModifiedSinceResetToDefault()

    PatchPipetteStateManager.addProfile("default", {"seal": {}}, overwrite=True)

    assert param.value() == param.defaultValue()
    # Unpinned, not merely equal to the default, so the editor's own writeback
    # leaves it out of the profile.
    assert not param.valueModifiedSinceResetToDefault()


def test_an_external_change_reaches_profiles_that_copy_from_it(editor):
    derived = _param(editor, "derived", "seal", "autoSealTimeout")
    assert derived.defaultValue() == 45.0

    PatchPipetteStateManager.addProfile(
        "default", {"seal": {"autoSealTimeout": 12.0}}, overwrite=True
    )

    # The inherited default is what moves; this editor has never moved the value
    # on a profile that copies from the edited one.
    assert derived.defaultValue() == 12.0


def test_an_external_change_to_an_unknown_profile_is_ignored(editor, profiles):
    PatchPipetteStateManager.addProfile("added-later", {"seal": {"sealThreshold": 2e9}})

    assert profiles["added-later"] == {"seal": {"sealThreshold": 2e9}}
    assert "added-later" not in [child.name() for child in editor.param_root]


def test_the_editors_own_edit_does_not_echo(editor, profiles, resyncs):
    _param(editor, "default", "seal", "autoSealTimeout").setValue(20.0)

    assert profiles["default"]["seal"]["autoSealTimeout"] == 20.0
    assert _param(editor, "default", "seal", "autoSealTimeout").value() == 20.0
    assert resyncs == []


def test_an_external_change_does_resync(editor, resyncs):
    PatchPipetteStateManager.addProfile(
        "default", {"seal": {"autoSealTimeout": 12.0}}, overwrite=True
    )

    assert resyncs == ["default"]


def test_a_none_in_the_config_means_unpinned(editor):
    # A stored profile may hold None for an optional parameter, and no typed
    # parameter in this tree can carry one -- pyqtgraph reads a value back
    # through the parameter's own type, and float(None) raises. The tree's own
    # construction already spells None as "not pinned" (StateParameter.__init__),
    # so syncing has to read it the same way.
    param = _param(editor, "default", "seal", "autoSealTimeout")
    assert param.value() == 45.0

    editor.param_root.child("default").syncFromConfig(
        {"seal": {"autoSealTimeout": None}}
    )

    assert param.value() == 30.0
    assert not param.valueModifiedSinceResetToDefault()


def test_a_none_on_a_parameter_with_no_default_is_left_alone(editor):
    # Same convention, for the parameters whose own default is None: there is
    # no unset value to fall back to, so the tree keeps what it is showing.
    param = _param(editor, "default", "seal", "initialPressure")
    before = param.value()

    editor.param_root.child("default").syncFromConfig(
        {"seal": {"initialPressure": None}}
    )

    assert param.value() == before


def test_an_external_change_pinning_none_does_not_raise(editor, profiles):
    # The path the rig crashed on: an addProfile elsewhere, carrying a None,
    # reaching this editor through the notifier.
    param = _param(editor, "default", "seal", "autoSealTimeout")

    PatchPipetteStateManager.addProfile(
        "default", {"seal": {"autoSealTimeout": None}}, overwrite=True
    )

    assert param.value() == 30.0


def test_a_none_pins_an_optional_parameter(editor, profiles):
    # Optional parameters can hold None, so for them a stored None is a value
    # ("don't set this"), not the absence of one.
    param = _param(editor, "default", "break in", "initialVCHolding")
    assert param.isOptional()
    assert param.value() == param.defaultValue() == -70e-3

    PatchPipetteStateManager.addProfile(
        "default", {"break in": {"initialVCHolding": None}}, overwrite=True
    )
    assert param.value() is None
    assert param.valueModifiedSinceResetToDefault()

    PatchPipetteStateManager.addProfile("default", {"break in": {}}, overwrite=True)
    assert param.value() == -70e-3


def test_setting_an_optional_parameter_to_none_is_stored(editor, profiles):
    _param(editor, "default", "break in", "initialVCHolding").setValue(None)

    assert profiles["default"]["break in"] == {"initialVCHolding": None}


def test_a_table_parameter_round_trips(editor, profiles):
    param = _param(editor, "default", "clean", "cleanSequence")
    assert param.type() == "table"

    param.setValue([(-30e3, 1.0), (60e3, 2.0)])
    assert profiles["default"]["clean"]["cleanSequence"] == [(-30e3, 1.0), (60e3, 2.0)]

    PatchPipetteStateManager.addProfile(
        "default", {"clean": {"cleanSequence": "[(-35*kPa, 2*s)]"}}, overwrite=True
    )
    assert param.value() == [(-35e3, 2.0)]
