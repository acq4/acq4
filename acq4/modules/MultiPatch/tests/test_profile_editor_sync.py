"""Tests that the patch profile editor's tree follows profile changes made from
outside it -- by a protocol action, say -- without echoing them back into the
profile store."""
from __future__ import annotations

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.util import Qt


@pytest.fixture
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture
def profiles(monkeypatch):
    """Isolate the class-level profile store, and mark it already loaded so that
    nothing reaches for the Manager's config."""
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
        # deleteLater() needs an event-loop turn to land, and until it does the
        # widget is still connected to the (process-wide) notifier, where it
        # would answer the next test's profile changes.
        Qt.disconnect(
            PatchPipetteStateManager.profileNotifier().sigProfileConfigChanged,
            widget.profileConfigChanged,
        )
        widget.deleteLater()


@pytest.fixture
def resyncs(monkeypatch):
    """Names of the profiles the editor re-applied to its tree from the store.

    The notifier fires on every write, this editor's own included, so what marks
    an echo is not an emission but the editor acting on one.
    """
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
    # Not merely equal to the default: unpinned, so the editor's own writeback
    # leaves it out of the profile rather than storing it again.
    assert not param.valueModifiedSinceResetToDefault()


def test_an_external_change_reaches_profiles_that_copy_from_it(editor):
    derived = _param(editor, "derived", "seal", "autoSealTimeout")
    assert derived.defaultValue() == 45.0

    PatchPipetteStateManager.addProfile(
        "default", {"seal": {"autoSealTimeout": 12.0}}, overwrite=True
    )

    # The inherited *default* is what moves, which is all an edit in this editor
    # has ever moved on a profile that copies from the edited one.
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
