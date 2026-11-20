"""Tests for the action that pins a slice's measured economics onto the patch
profile: what it reads, what it pins, and what it falls back to."""
from __future__ import annotations

import pytest

from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.experiment.actions import tune_patch_economics
from acq4.experiment.context import ExecutionContext


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


class _FakeDir:
    def __init__(self, info, children=None, parent=None):
        self._info = dict(info)
        self._children = children or {}
        self._parent = parent
        for child in self._children.values():
            child._parent = self

    def info(self):
        return self._info

    def isManaged(self):
        return True

    def isDir(self):
        return True

    def parent(self):
        return self._parent if self._parent is not None else self

    def ls(self):
        return list(self._children)

    def __getitem__(self, name):
        return self._children[name]


def _cellInfo(entered, **overrides):
    info = {
        "dirType": "Cell",
        "patch_outcome": "whole cell",
        "sealed": True,
        "break_in_succeeded": True,
        "give_up_reason": "none",
        "seal_entered_at": entered,
        "seal_duration_s": 10.0,
    }
    info.update(overrides)
    return info


def _sliceTree(n_cells=5, current_info=None, **cell_overrides):
    """A Slice directory holding `n_cells` finished cells, plus the cell being
    worked now, which is the manager's current directory."""
    children = {
        f"Cell_{i:03d}": _FakeDir(_cellInfo(1000.0 + 100 * i, **cell_overrides))
        for i in range(n_cells)
    }
    current = _FakeDir(current_info if current_info is not None else {"dirType": "Cell"})
    children["Cell_current"] = current
    sliceDir = _FakeDir({"dirType": "Slice"}, children)
    _FakeDir({"dirType": "Day"}, {"Slice_000": sliceDir})
    return current


class _FakeManager:
    def __init__(self, currentDir, config=None):
        self._dir = currentDir
        self.config = config if config is not None else {}

    def getCurrentDir(self):
        return self._dir


def _ctx(currentDir, config=None):
    entries = []
    context = ExecutionContext(
        pipette=_FakePipette(),
        manager=_FakeManager(currentDir, config),
        on_log_action=entries.append,
    )
    context.entries = entries
    context.messages = []
    context.log = context.messages.append
    return context


@pytest.fixture
def profiles(monkeypatch):
    store = {
        "default": {
            "seal": {
                "restartCost": 90.0,
                "sliceSealProbability": 0.4,
                "expectedSealDuration": 12.0,
                "expectedFailedSealDuration": 30.0,
                "sealProbabilityDecayTau": 20.0,
            }
        }
    }
    monkeypatch.setattr(PatchPipetteStateManager, "profiles", store)
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    return store


def test_the_measured_terms_are_pinned_for_the_body(profiles):
    """Five cells, all sealing, 100 s apart with 10 s episodes: p of 1 and a
    restart overhead of 90 s, measured rather than configured."""
    ctx = _ctx(_sliceTree(n_cells=5))
    with tune_patch_economics(ctx):
        seal = profiles["default"]["seal"]
        assert seal["sliceSealProbability"] == pytest.approx(1.0)
        assert seal["restartCost"] == pytest.approx(90.0)
        assert seal["expectedSealDuration"] == pytest.approx(10.0)


def test_the_pinned_terms_are_restored_afterward(profiles):
    ctx = _ctx(_sliceTree(n_cells=5))
    with tune_patch_economics(ctx):
        pass
    assert profiles["default"]["seal"]["sliceSealProbability"] == pytest.approx(0.4)
    assert profiles["default"]["seal"]["restartCost"] == pytest.approx(90.0)


def test_the_profile_values_stand_in_below_the_cell_threshold(profiles):
    """Three cells is not a slice worth believing, so the hand-set defaults on the
    profile are what the rule runs on."""
    ctx = _ctx(_sliceTree(n_cells=3))
    with tune_patch_economics(ctx):
        assert profiles["default"]["seal"]["sliceSealProbability"] == pytest.approx(0.4)


def test_the_cell_threshold_comes_from_the_rig_configuration(profiles):
    ctx = _ctx(_sliceTree(n_cells=3), config={"misc": {"minCellsForSliceStats": 3}})
    with tune_patch_economics(ctx):
        assert profiles["default"]["seal"]["sliceSealProbability"] == pytest.approx(1.0)


def test_the_decay_constant_is_never_overwritten_by_a_measurement(profiles):
    """Fitting a survival curve is the offline pass's job; the rig only carries
    whatever that pass wrote onto the profile."""
    ctx = _ctx(_sliceTree(n_cells=5))
    with tune_patch_economics(ctx):
        assert profiles["default"]["seal"]["sealProbabilityDecayTau"] == pytest.approx(20.0)


def test_the_prize_value_defaults_to_one_before_a_recording_exists(profiles):
    """Called ahead of the patch, this cell has no recording to be judged on, and
    an unmeasured cell must not be discounted."""
    ctx = _ctx(_sliceTree(n_cells=5))
    with tune_patch_economics(ctx):
        assert profiles["default"]["reseal"]["prizeValue"] == pytest.approx(1.0)


def test_the_prize_value_is_this_cell_against_the_slice_average(profiles):
    """Called again ahead of the reseal, the patch drive has by then written this
    cell's clamp quality onto its own directory."""
    current = _sliceTree(
        n_cells=5,
        input_resistance=200e6,
        access_resistance=20e6,
        current_info=_cellInfo(1600.0, input_resistance=400e6, access_resistance=20e6),
    )
    ctx = _ctx(current)
    with tune_patch_economics(ctx):
        # This cell's 20 against an average of 11.67, not against the other
        # cells' 10: once its own patch has finished, the cell being judged is a
        # finished attempt on this slice like any other and counts in the
        # average. That dilutes the comparison slightly, immaterially so at any
        # realistic cell count, and the alternative -- hiding a real attempt from
        # the slice's own history -- is worse.
        assert profiles["default"]["reseal"]["prizeValue"] == pytest.approx(20.0 / (70.0 / 6))


def test_a_directory_with_no_slice_above_it_falls_back_to_the_profile(profiles):
    """A headless run, or one started outside a slice, must not fail here."""
    ctx = _ctx(_FakeDir({"dirType": "Cell"}))
    with tune_patch_economics(ctx):
        assert profiles["default"]["seal"]["sliceSealProbability"] == pytest.approx(0.4)
    assert any("slice" in m.lower() for m in ctx.messages)


def test_an_unreadable_storage_directory_falls_back_to_the_profile(profiles):
    class _Broken:
        def getCurrentDir(self):
            raise RuntimeError("no storage directory set")

    ctx = _ctx(None)
    ctx.manager = _Broken()
    with tune_patch_economics(ctx):
        assert profiles["default"]["seal"]["sliceSealProbability"] == pytest.approx(0.4)
