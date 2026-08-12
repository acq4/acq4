"""Unit tests for exponential_decay_avg, the rolling average shared by the patch pipette states.

The helper returns both an average and the ratio of the new average to the previous one. Series
that legitimately sit at zero -- membrane capacitance while a seal is intact, for instance -- make
that ratio a division by zero, so these pin the sentinel it reports instead.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from acq4.devices.PatchPipette.states._base import exponential_decay_avg


def test_none_previous_average_seeds_from_the_value():
    """The first measurement becomes the average outright, with no ratio to report."""
    avg, ratio = exponential_decay_avg(0.1, None, 42.0, 1.0)
    assert avg == pytest.approx(42.0)
    assert ratio == 0


def test_ratio_reports_growth_of_the_average():
    avg, ratio = exponential_decay_avg(1.0, 10.0, 20.0, 1.0)
    assert avg == pytest.approx(10.0 + 10.0 * (1 - np.exp(-1.0)))
    assert ratio == pytest.approx(avg / 10.0)


def test_average_decays_toward_the_new_value():
    avg, _ = exponential_decay_avg(1.0, 100.0, 0.0, 1.0)
    assert 0.0 < avg < 100.0


def test_zero_previous_average_reports_no_ratio():
    """From zero the ratio is unbounded, so it reports the same sentinel as a missing average."""
    avg, ratio = exponential_decay_avg(1.0, 0.0, 100.0, 1.0)
    assert avg == pytest.approx(100.0 * (1 - np.exp(-1.0)))
    assert ratio == 0


def test_zero_previous_average_still_advances_the_average():
    """The ratio sentinel must not short-circuit the average itself."""
    avg, _ = exponential_decay_avg(0.5, 0.0, 80.0, 2.0)
    assert avg > 0.0


def test_zero_previous_and_zero_value_stays_at_zero():
    """A series resting at zero must stay there rather than going NaN via 0/0."""
    avg, ratio = exponential_decay_avg(0.2, 0.0, 0.0, 3.0)
    assert avg == 0.0
    assert ratio == 0


def test_series_resting_at_zero_emits_no_warnings():
    """Repeated zeros must not spam RuntimeWarnings from the ratio term."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        avg = None
        for _ in range(50):
            avg, _ = exponential_decay_avg(0.2, avg, 0.0, 3.0)
    assert avg == 0.0


def test_leaving_a_zero_series_emits_no_warnings():
    """The transition off zero -- a real break-in -- must also stay warning free."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        avg = 0.0
        for _ in range(20):
            avg, _ = exponential_decay_avg(0.2, avg, 100e-12, 3.0)
    assert avg > 0.0
