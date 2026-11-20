"""Tests for the per-cell outcome record the FSM-driving actions put on a Cell
directory's index: the seal episode's duration, what the attempt reached, and the
clamp quality of whatever recording it won."""
from __future__ import annotations

import numpy as np
import pytest

from acq4.experiment.actions.fsm import (
    _clampQuality,
    _patchOutcomeInfo,
    _recordPatchOutcome,
    _resealOutcomeInfo,
    _stateDuration,
    _stateEntryTime,
)


def _history(rows):
    """A test-pulse analysis array shaped like the writer's, with only the fields
    the outcome record reads."""
    return np.array(
        rows,
        dtype=[
            ("event_time", float),
            ("baseline_current", float),
            ("input_resistance", float),
            ("access_resistance", float),
            ("capacitance", float),
        ],
    )


class _FakeDir:
    def __init__(self, failing=False):
        self.info = {}
        self._failing = failing

    def setInfo(self, *args, **kwargs):
        if self._failing:
            raise OSError("index is not writable")
        self.info.update(kwargs or (args[0] if args else {}))


class _FakeManager:
    def __init__(self, dirHandle):
        self._dir = dirHandle

    def getCurrentDir(self):
        if self._dir is None:
            raise RuntimeError("no storage directory set")
        return self._dir


class _FakeCtx:
    def __init__(self, dirHandle):
        self.manager = _FakeManager(dirHandle)
        self.logged = []

    def log(self, message):
        self.logged.append(message)


# ---- how long a state ran ----


def test_state_duration_spans_its_entry_to_the_next_transition():
    transitions = [(10.0, "approach"), (12.5, "seal"), (40.0, "cell attached")]
    assert _stateDuration(transitions, "seal") == pytest.approx(27.5)


def test_state_duration_is_none_when_the_drive_ended_inside_the_state():
    """A censored episode has a lower bound, not a duration. Reporting the bound as
    a duration would make every interrupted run look like a fast one."""
    transitions = [(10.0, "approach"), (12.5, "seal")]
    assert _stateDuration(transitions, "seal") is None


def test_state_duration_is_none_when_the_state_was_never_entered():
    transitions = [(10.0, "approach"), (11.0, "bath")]
    assert _stateDuration(transitions, "seal") is None


def test_state_duration_measures_the_first_visit():
    """One cell is one attempt, so a second visit is not expected -- but if the log
    holds one, the first is the episode that belongs to this attempt."""
    transitions = [(0.0, "seal"), (10.0, "fouled"), (20.0, "seal"), (25.0, "broken")]
    assert _stateDuration(transitions, "seal") == pytest.approx(10.0)


def test_state_entry_time_is_absolute_wall_clock():
    """The restart overhead is measured as the gap from one cell's seal ending to
    the next cell's beginning, so this has to be comparable across attempts."""
    assert _stateEntryTime([(10.0, "approach"), (12.5, "seal")], "seal") == pytest.approx(12.5)


def test_state_entry_time_is_none_when_the_state_was_never_entered():
    assert _stateEntryTime([(10.0, "approach")], "seal") is None


def test_patch_outcome_info_records_when_the_seal_started():
    info = _patchOutcomeInfo(
        "fouled", [(100.0, "approach"), (140.0, "seal"), (170.0, "fouled")], _history([]), _record()
    )
    assert info["seal_entered_at"] == pytest.approx(140.0)
    assert info["seal_duration_s"] == pytest.approx(30.0)


def test_patch_outcome_info_omits_the_start_when_seal_was_never_entered():
    info = _patchOutcomeInfo("bath", [(100.0, "approach"), (110.0, "bath")], _history([]), _record())
    assert "seal_entered_at" not in info


# ---- clamp quality of the recording that was won ----


def test_clamp_quality_averages_pulses_recorded_after_whole_cell():
    history = _history(
        [
            (1.0, -1e-12, 1e6, 1e6, 1e-12),  # during seal: must not count
            (11.0, -100e-12, 200e6, 20e6, 30e-12),
            (12.0, -140e-12, 240e6, 24e6, 34e-12),
        ]
    )
    quality = _clampQuality(history, [(0.0, "seal"), (10.0, "whole cell")])
    assert quality["input_resistance"] == pytest.approx(220e6)
    assert quality["access_resistance"] == pytest.approx(22e6)
    assert quality["capacitance"] == pytest.approx(32e-12)
    assert quality["holding_current"] == pytest.approx(-120e-12)


def test_clamp_quality_is_empty_when_whole_cell_was_never_reached():
    """There is no recording to judge, and a zero would read as a measured zero."""
    history = _history([(1.0, -1e-12, 1e6, 1e6, 1e-12)])
    assert _clampQuality(history, [(0.0, "seal"), (10.0, "fouled")]) == {}


def test_clamp_quality_is_empty_when_no_pulses_followed_whole_cell():
    history = _history([(1.0, -1e-12, 1e6, 1e6, 1e-12)])
    assert _clampQuality(history, [(0.0, "seal"), (10.0, "whole cell")]) == {}


def test_clamp_quality_ignores_nan_measurements():
    """A pulse with no transient to fit reports NaN. Averaging it in would poison
    every field it touches and silently void the whole record."""
    history = _history(
        [
            (11.0, -100e-12, 200e6, np.nan, 30e-12),
            (12.0, -140e-12, 240e6, 24e6, np.nan),
        ]
    )
    quality = _clampQuality(history, [(10.0, "whole cell")])
    assert quality["access_resistance"] == pytest.approx(24e6)
    assert quality["capacitance"] == pytest.approx(30e-12)
    assert quality["input_resistance"] == pytest.approx(220e6)


def test_clamp_quality_omits_a_field_that_is_entirely_nan():
    history = _history([(11.0, -100e-12, 200e6, np.nan, 30e-12)])
    quality = _clampQuality(history, [(10.0, "whole cell")])
    assert "access_resistance" not in quality
    assert quality["input_resistance"] == pytest.approx(200e6)


def test_clamp_quality_tolerates_an_empty_history():
    assert _clampQuality(_history([]), [(10.0, "whole cell")]) == {}


# ---- the record itself ----


def _record(**overrides):
    record = {
        "attemptedSeal": True,
        "sealSuccessful": True,
        "breakinSuccessful": True,
        "spontaneousBreakin": None,
        "sealGiveUpReason": None,
    }
    record.update(overrides)
    return record


def test_patch_outcome_info_reports_the_terminal_state_and_seal_duration():
    info = _patchOutcomeInfo(
        "whole cell",
        [(0.0, "approach"), (5.0, "seal"), (18.0, "cell attached"), (20.0, "whole cell")],
        _history([]),
        _record(),
    )
    assert info["patch_outcome"] == "whole cell"
    assert info["seal_duration_s"] == pytest.approx(13.0)
    assert info["sealed"] is True
    assert info["break_in_succeeded"] is True


def test_patch_outcome_info_carries_the_give_up_reason():
    info = _patchOutcomeInfo(
        "fouled",
        [(0.0, "seal"), (30.0, "fouled")],
        _history([]),
        _record(sealSuccessful=False, breakinSuccessful=None, sealGiveUpReason="economic"),
    )
    assert info["patch_outcome"] == "fouled"
    assert info["give_up_reason"] == "economic"
    assert info["sealed"] is False
    assert info["break_in_succeeded"] is False


def test_patch_outcome_info_reports_no_reason_when_the_seal_was_not_given_up_on():
    info = _patchOutcomeInfo("whole cell", [(0.0, "seal"), (9.0, "break in")], _history([]), _record())
    assert info["give_up_reason"] == "none"


def test_patch_outcome_info_omits_a_censored_seal_duration():
    """Absent rather than zero: the slice statistics must not average in a bound."""
    info = _patchOutcomeInfo("fouled", [(0.0, "approach")], _history([]), _record())
    assert "seal_duration_s" not in info


def test_patch_outcome_info_includes_clamp_quality():
    history = _history([(11.0, -100e-12, 200e6, 20e6, 30e-12)])
    info = _patchOutcomeInfo("whole cell", [(0.0, "seal"), (10.0, "whole cell")], history, _record())
    assert info["access_resistance"] == pytest.approx(20e6)
    assert info["holding_current"] == pytest.approx(-100e-12)


def test_patch_outcome_info_values_survive_a_repr_round_trip():
    """The .index is written with repr() and read back with eval(); a numpy scalar
    left in the payload is written as a tagged object no reader can load."""
    history = _history([(11.0, -100e-12, 200e6, 20e6, 30e-12)])
    info = _patchOutcomeInfo("whole cell", [(0.0, "seal"), (10.0, "whole cell")], history, _record())
    assert eval(repr(info)) == info
    for key, value in info.items():
        assert type(value) in (str, float, bool), f"{key} is {type(value)}"


def test_reseal_outcome_info_reports_its_terminal_and_duration():
    info = _resealOutcomeInfo("outside out", [(0.0, "reseal"), (120.0, "outside out")])
    assert info == {
        "reseal_outcome": "outside out",
        "reseal_duration_s": pytest.approx(120.0),
        "reseal_give_up_reason": "none",
    }


def test_reseal_outcome_info_omits_a_censored_duration():
    assert _resealOutcomeInfo("whole cell", [(0.0, "reseal")]) == {
        "reseal_outcome": "whole cell",
        "reseal_give_up_reason": "none",
    }


def test_reseal_outcome_info_carries_the_give_up_reason():
    """What tells a reseal abandoned because the nucleus was not worth chasing
    from one that merely ran out of time."""
    info = _resealOutcomeInfo(
        "whole cell",
        [(0.0, "reseal"), (60.0, "whole cell")],
        {"resealGiveUpReason": "economic"},
    )
    assert info["reseal_give_up_reason"] == "economic"


# ---- the write ----


def test_record_patch_outcome_writes_the_info_onto_the_current_directory():
    dirHandle = _FakeDir()
    ctx = _FakeCtx(dirHandle)
    _recordPatchOutcome(ctx, {"patch_outcome": "whole cell", "sealed": True})
    assert dirHandle.info == {"patch_outcome": "whole cell", "sealed": True}
    assert ctx.logged == []


def test_record_patch_outcome_never_raises_when_the_index_is_unwritable():
    """The cell has already been patched by the time this runs; a failed record
    must not turn a successful attempt into a failed run."""
    ctx = _FakeCtx(_FakeDir(failing=True))
    _recordPatchOutcome(ctx, {"patch_outcome": "whole cell"})
    assert len(ctx.logged) == 1
    assert "outcome" in ctx.logged[0]


def test_record_patch_outcome_never_raises_without_a_storage_directory():
    ctx = _FakeCtx(None)
    _recordPatchOutcome(ctx, {"patch_outcome": "whole cell"})
    assert len(ctx.logged) == 1


def test_record_patch_outcome_writes_nothing_for_an_empty_record():
    dirHandle = _FakeDir()
    ctx = _FakeCtx(dirHandle)
    _recordPatchOutcome(ctx, {})
    assert dirHandle.info == {}
