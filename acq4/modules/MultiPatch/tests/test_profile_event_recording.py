"""Tests that MultiPatch records a patch-profile change whoever made it, now that
it listens to the profile store rather than to the editor window."""
from __future__ import annotations

import json

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.util import Qt


class _StandInWindow:
    """The parts of MultiPatchWindow that recording a profile change touches; any
    other attribute resolves to the real MultiPatchWindow method, bound to this."""

    def __init__(self):
        self.eventHistory = []
        self._logWriter = None
        self.recorded = []

    def resetHistory(self):
        self.eventHistory = []

    def recordEvent(self, event):
        self.recorded.append(event)
        self._rememberEvent(event)

    def __getattr__(self, name):
        from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

        method = getattr(MultiPatchWindow, name)
        return lambda *args, **kwargs: method(self, *args, **kwargs)


@pytest.fixture
def profiles(monkeypatch):
    store = {"default": {"seal": {"autoSealTimeout": 30.0}}}
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


@pytest.fixture
def win(profiles):
    window = _StandInWindow()
    notifier = PatchPipetteStateManager.profileNotifier()
    notifier.sigProfileConfigChanged.connect(window.profileConfigChanged)
    try:
        yield window
    finally:
        Qt.disconnect(notifier.sigProfileConfigChanged, window.profileConfigChanged)


def test_a_profile_change_from_anywhere_is_recorded(win):
    PatchPipetteStateManager.addProfile(
        "default", {"seal": {"autoSealTimeout": 12.0}}, overwrite=True
    )

    (event,) = win.recorded
    assert event["event"] == "global patch profiles changed"
    assert event["device"] is None
    assert json.loads(event["profile"]) == {
        "default": {"seal": {"autoSealTimeout": 12.0}}
    }


def test_the_change_is_kept_for_a_log_started_later(win):
    PatchPipetteStateManager.addProfile("tweaked", {"seal": {"sealThreshold": 2e9}})

    assert len(win.eventHistory) == 1
    assert win.eventHistory[0]["event"] == "global patch profiles changed"
