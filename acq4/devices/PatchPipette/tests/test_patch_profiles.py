"""Tests for the patch-profile store's change notification and profile getter."""
from __future__ import annotations

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.util import Qt


@pytest.fixture
def profiles(monkeypatch):
    # Marked loaded so nothing reaches for the Manager's config.
    store = {"default": {"seal": {"autoSealTimeout": 30.0}}}
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


@pytest.fixture
def changes():
    seen = []

    def record(name, config):
        seen.append((name, config))

    notifier = PatchPipetteStateManager.profileNotifier()
    notifier.sigProfileConfigChanged.connect(record)
    try:
        yield seen
    finally:
        Qt.disconnect(notifier.sigProfileConfigChanged, record)


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass


class _FakeDev:
    sigStateChanged = _FakeSignal()
    sigActiveChanged = _FakeSignal()

    def name(self):
        return "Pipette1"


def test_addProfile_notifies_with_the_stored_config(profiles, changes):
    PatchPipetteStateManager.addProfile("tweaked", {"seal": {"sealThreshold": 2e9}})

    assert changes == [("tweaked", {"seal": {"sealThreshold": 2e9}})]


def test_overwriting_a_profile_notifies(profiles, changes):
    PatchPipetteStateManager.addProfile(
        "default", {"seal": {"autoSealTimeout": 45.0}}, overwrite=True
    )

    assert changes == [("default", {"seal": {"autoSealTimeout": 45.0}})]
    assert profiles["default"] == {"seal": {"autoSealTimeout": 45.0}}


def test_a_rejected_profile_notifies_nothing(profiles, changes):
    with pytest.raises(ValueError):
        PatchPipetteStateManager.addProfile("broken", {"seal": {"noSuchParam": 1}})

    assert changes == []
    assert "broken" not in profiles


def test_a_duplicate_profile_notifies_nothing(profiles, changes):
    with pytest.raises(ValueError):
        PatchPipetteStateManager.addProfile("default", {"seal": {}})

    assert changes == []


def test_getProfile_reports_the_selected_profile(profiles):
    manager = PatchPipetteStateManager(_FakeDev())

    # 'default' is in the store, so __init__ selects it.
    assert manager.getProfile() == "default"

    PatchPipetteStateManager.addProfile("tweaked", {})
    manager.setProfile("tweaked")
    assert manager.getProfile() == "tweaked"


def test_getProfile_is_None_with_nothing_selected(monkeypatch):
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", {})
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)

    assert PatchPipetteStateManager(_FakeDev()).getProfile() is None
