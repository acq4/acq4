"""Tests for the slice-level seal statistics read back off a slice's cell
directories: the terms the early-exit rule compares, and the cold-start defaults
it falls back to before a slice has enough cells to speak for itself."""
from __future__ import annotations

import pytest

from acq4.experiment.slice_statistics import (
    SealTerms,
    SliceStatistics,
    cell_quality,
    seal_terms_from_records,
)

DEFAULTS = SealTerms(
    restart_cost=90.0,
    seal_probability=0.4,
    expected_seal_duration=12.0,
    expected_failed_seal_duration=30.0,
    probability_decay_tau=20.0,
    expected_quality=10.0,
)


def _cell(**overrides):
    """A cell directory's index as the patch drive writes it."""
    record = {
        "patch_outcome": "whole cell",
        "sealed": True,
        "break_in_succeeded": True,
        "give_up_reason": "none",
        "seal_entered_at": 1000.0,
        "seal_duration_s": 10.0,
    }
    record.update(overrides)
    return record


def _failed(**overrides):
    failure = {
        "patch_outcome": "fouled",
        "sealed": False,
        "break_in_succeeded": False,
        "give_up_reason": "timeout",
    }
    failure.update(overrides)
    return _cell(**failure)


# ---- cold start ----


def test_defaults_are_returned_below_the_cell_threshold():
    terms = seal_terms_from_records([_cell(), _cell()], DEFAULTS, min_cells=5)
    assert terms.seal_probability == pytest.approx(0.4)
    assert terms.expected_seal_duration == pytest.approx(12.0)
    assert terms.measured is False
    assert terms.n_cells == 2


def test_defaults_are_returned_for_an_empty_slice():
    terms = seal_terms_from_records([], DEFAULTS, min_cells=5)
    assert terms.measured is False
    assert terms.n_cells == 0
    assert terms.restart_cost == pytest.approx(90.0)


def test_records_without_an_outcome_are_not_counted():
    """A cell directory made but never driven says nothing about this slice."""
    records = [_cell(), {"score": 0.9}, {"location": "(1, 2, 3) um"}]
    assert seal_terms_from_records(records, DEFAULTS, min_cells=5).n_cells == 1


# ---- the measured terms ----


def test_seal_probability_is_sealed_over_attempts_that_entered_seal():
    records = [_cell(), _cell(), _failed(), _failed(), _failed()]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.measured is True
    assert terms.seal_probability == pytest.approx(0.4)


def test_an_attempt_that_never_entered_seal_is_outside_the_probability():
    """Its cost belongs in the restart overhead, not in the odds of a seal: there
    was no seal episode to succeed or fail."""
    lost = _failed(give_up_reason="none")
    del lost["seal_entered_at"]
    del lost["seal_duration_s"]
    records = [_cell(), _cell(), _failed(), _failed(), lost]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.seal_probability == pytest.approx(0.5)


def test_expected_durations_average_their_own_outcome():
    records = [
        _cell(seal_duration_s=10.0),
        _cell(seal_duration_s=20.0),
        _failed(seal_duration_s=30.0),
        _failed(seal_duration_s=40.0),
        _failed(seal_duration_s=50.0),
    ]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.expected_seal_duration == pytest.approx(15.0)
    assert terms.expected_failed_seal_duration == pytest.approx(40.0)


def test_a_censored_episode_contributes_no_duration():
    """No seal_duration_s means the drive ended inside the episode; averaging its
    absence as a zero would make the slice look faster than it is."""
    censored = _cell()
    del censored["seal_duration_s"]
    records = [_cell(seal_duration_s=10.0), _cell(seal_duration_s=20.0), censored, _failed(), _failed()]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.expected_seal_duration == pytest.approx(15.0)


def test_seal_probability_of_zero_is_reported_as_measured():
    """A slice that has sealed nothing is information, not missing data. The rule
    turns an unsealable slice into an infinite W and stops abandoning cells."""
    records = [_failed() for _ in range(5)]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.measured is True
    assert terms.seal_probability == pytest.approx(0.0)


# ---- restart cost ----


def test_restart_cost_is_the_gap_between_consecutive_seal_episodes():
    records = [
        _cell(seal_entered_at=1000.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1100.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1200.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1300.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1400.0, seal_duration_s=10.0),
    ]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.restart_cost == pytest.approx(90.0)


def test_restart_cost_absorbs_an_attempt_that_never_reached_seal():
    """This is what makes it the *amortized* overhead: a wasted approach between
    two seals is inside the gap, with no term of its own."""
    lost = _failed()
    del lost["seal_entered_at"]
    del lost["seal_duration_s"]
    records = [
        _cell(seal_entered_at=1000.0, seal_duration_s=10.0),
        lost,
        _cell(seal_entered_at=1300.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1600.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1900.0, seal_duration_s=10.0),
    ]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.restart_cost == pytest.approx(290.0)


def test_restart_cost_is_a_median_so_an_idle_gap_does_not_dominate():
    """An operator's lunch break is a gap between two seal episodes and is not a
    restart cost. A mean would let one of them swamp a whole slice."""
    records = [
        _cell(seal_entered_at=1000.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1100.0, seal_duration_s=10.0),
        _cell(seal_entered_at=1200.0, seal_duration_s=10.0),
        _cell(seal_entered_at=5000.0, seal_duration_s=10.0),  # back from lunch
        _cell(seal_entered_at=5100.0, seal_duration_s=10.0),
    ]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.restart_cost == pytest.approx(90.0)


def test_restart_cost_falls_back_to_the_default_without_two_episodes():
    records = [_cell(), _failed(), _failed(), _failed(), _failed()]
    for record in records[1:]:
        del record["seal_entered_at"]
        del record["seal_duration_s"]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.restart_cost == pytest.approx(90.0)


def test_restart_cost_ignores_a_negative_gap():
    """Two pipettes sealing concurrently would interleave their episodes; the
    overlap is not a negative overhead."""
    records = [
        _cell(seal_entered_at=1000.0, seal_duration_s=500.0),
        _cell(seal_entered_at=1100.0, seal_duration_s=10.0),
        _cell(seal_entered_at=2000.0, seal_duration_s=10.0),
        _cell(seal_entered_at=2100.0, seal_duration_s=10.0),
        _cell(seal_entered_at=2200.0, seal_duration_s=10.0),
    ]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.restart_cost == pytest.approx(90.0)


# ---- the decay tau is never measured ----


def test_probability_decay_tau_always_comes_from_the_defaults():
    """Fitting a survival curve needs the offline calibration pass; the rig only
    ever carries the number that pass produced."""
    terms = seal_terms_from_records([_cell() for _ in range(5)], DEFAULTS, min_cells=5)
    assert terms.probability_decay_tau == pytest.approx(20.0)


# ---- recording quality ----


def test_cell_quality_is_the_input_over_access_resistance_ratio():
    assert cell_quality({"input_resistance": 200e6, "access_resistance": 20e6}) == pytest.approx(10.0)


def test_cell_quality_is_none_without_both_measurements():
    assert cell_quality({"input_resistance": 200e6}) is None
    assert cell_quality({"access_resistance": 20e6}) is None
    assert cell_quality({}) is None


def test_cell_quality_is_none_for_a_nonpositive_access_resistance():
    assert cell_quality({"input_resistance": 200e6, "access_resistance": 0.0}) is None
    assert cell_quality({"input_resistance": 200e6, "access_resistance": -1.0}) is None


def test_expected_quality_averages_the_cells_that_have_one():
    records = [
        _cell(input_resistance=200e6, access_resistance=20e6),
        _cell(input_resistance=300e6, access_resistance=20e6),
        _cell(),
        _failed(),
        _failed(),
    ]
    terms = seal_terms_from_records(records, DEFAULTS, min_cells=5)
    assert terms.expected_quality == pytest.approx(12.5)


def test_expected_quality_falls_back_to_the_default_with_no_recordings():
    terms = seal_terms_from_records([_failed() for _ in range(5)], DEFAULTS, min_cells=5)
    assert terms.expected_quality == pytest.approx(10.0)


# ---- the prize value ----


def test_prize_value_is_this_cell_against_the_slice_average():
    stats = SliceStatistics(defaults=DEFAULTS)
    terms = SealTerms(expected_quality=10.0)
    assert stats.prizeValue({"input_resistance": 200e6, "access_resistance": 10e6}, terms) == pytest.approx(2.0)
    assert stats.prizeValue({"input_resistance": 100e6, "access_resistance": 20e6}, terms) == pytest.approx(0.5)


def test_prize_value_is_one_without_information():
    """No measurement, or no slice average to compare against, must not discount
    the cell -- an unmeasured cell is not a bad one."""
    stats = SliceStatistics(defaults=DEFAULTS)
    assert stats.prizeValue({}, SealTerms(expected_quality=10.0)) == pytest.approx(1.0)
    assert stats.prizeValue(
        {"input_resistance": 200e6, "access_resistance": 10e6}, SealTerms(expected_quality=0.0)
    ) == pytest.approx(1.0)


# ---- reading them off a slice directory ----


class _FakeHandle:
    def __init__(self, info, isDir=True, failing=False):
        self._info = info
        self._isDir = isDir
        self._failing = failing

    def isDir(self):
        return self._isDir

    def info(self):
        if self._failing:
            raise OSError("index is unreadable")
        return self._info


class _FakeDir:
    def __init__(self, children):
        self._children = children

    def ls(self):
        return list(self._children)

    def __getitem__(self, name):
        return self._children[name]


def test_statistics_without_a_directory_report_the_defaults():
    assert SliceStatistics(defaults=DEFAULTS).sealTerms().measured is False


def test_statistics_read_only_the_cell_directories():
    children = {
        "Cell_000": _FakeHandle({"dirType": "Cell", **_cell()}),
        "Cell_001": _FakeHandle({"dirType": "Cell", **_cell()}),
        "tiles": _FakeHandle({"dirType": "Folder"}),
        "regions.yaml": _FakeHandle({}, isDir=False),
    }
    stats = SliceStatistics(dirHandle=_FakeDir(children), defaults=DEFAULTS, min_cells=2)
    terms = stats.sealTerms()
    assert terms.n_cells == 2
    assert terms.measured is True


def test_statistics_skip_a_cell_whose_index_cannot_be_read():
    """One unreadable directory must not blind the rule to the rest of the slice."""
    children = {
        "Cell_000": _FakeHandle({"dirType": "Cell", **_cell()}),
        "Cell_001": _FakeHandle({"dirType": "Cell", **_cell()}),
        "Cell_002": _FakeHandle(None, failing=True),
    }
    stats = SliceStatistics(dirHandle=_FakeDir(children), defaults=DEFAULTS, min_cells=2)
    assert stats.sealTerms().n_cells == 2


def test_statistics_survive_a_directory_that_cannot_be_listed():
    class _Broken:
        def ls(self):
            raise OSError("gone")

    terms = SliceStatistics(dirHandle=_Broken(), defaults=DEFAULTS).sealTerms()
    assert terms.measured is False
    assert terms.n_cells == 0
