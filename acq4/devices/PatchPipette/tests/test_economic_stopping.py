"""Unit tests for the stopping rule the seal and reseal states share.

The rule's behaviour inside a particular state is covered by that state's own
tests; these pin the arithmetic itself, and in particular the prize value, which
only the reseal state has a use for.
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.PatchPipette.states._economics import (
    EconomicStopping,
    finite_or_nan,
)

# (90 + 0.4*12 + 0.6*30) / 0.4 = 282
TERMS = dict(
    restart_cost=90.0,
    success_probability=0.4,
    expected_success_duration=12.0,
    expected_failure_duration=30.0,
)


def _rule(**overrides):
    kwargs = dict(target=1e9, slope_tau=2.0, min_decision_time=5.0, **TERMS)
    kwargs.update(overrides)
    return EconomicStopping(**kwargs)


# ---- the threshold ----


def test_the_threshold_is_the_expected_time_to_the_next_success():
    assert _rule().abandon_threshold == pytest.approx(282.0)


def test_no_success_probability_leaves_the_threshold_infinite():
    """The shipped default: nothing is ever abandoned, because there is nothing
    better to go to."""
    assert np.isinf(EconomicStopping(target=1e9).abandon_threshold)


def test_a_certain_success_costs_only_the_overhead_and_one_episode():
    rule = _rule(success_probability=1.0)
    assert rule.abandon_threshold == pytest.approx(90.0 + 12.0)


# ---- the prize value ----


def test_a_cheaper_prize_is_abandoned_sooner():
    """Half the worth, half the time worth spending on it."""
    assert _rule(prize_value=0.5).abandon_threshold == pytest.approx(141.0)


def test_a_better_prize_earns_more_patience():
    assert _rule(prize_value=2.0).abandon_threshold == pytest.approx(564.0)


def test_the_default_prize_value_changes_nothing():
    assert _rule(prize_value=1.0).abandon_threshold == _rule().abandon_threshold


def test_a_worthless_prize_is_abandoned_at_once():
    rule = _rule(prize_value=0.0)
    assert rule.abandon_threshold == pytest.approx(0.0)
    # Even a cell one second from success is not worth a nucleus worth nothing.
    _, _, _, give_up = rule.evaluate(elapsed=10.0, current_avg=1e9 - 1, slope=10.0)
    assert give_up is True


# ---- the projection ----


def test_the_projection_is_zero_at_or_past_the_target():
    assert _rule().projected_time(1e9, slope=0.0) == pytest.approx(0.0)
    assert _rule().projected_time(2e9, slope=-1.0) == pytest.approx(0.0)


def test_the_projection_is_infinite_without_a_positive_slope():
    assert np.isinf(_rule().projected_time(50e6, slope=0.0))
    assert np.isinf(_rule().projected_time(50e6, slope=-0.1))


def test_the_projection_reads_off_the_slope():
    # ln(1e9/50e6) / 0.1
    assert _rule().projected_time(50e6, slope=0.1) == pytest.approx(np.log(20) / 0.1)


def test_the_projection_is_infinite_for_a_nonpositive_measurement():
    assert np.isinf(_rule().projected_time(0.0, slope=0.1))


# ---- the slope ----


def test_the_slope_holds_across_a_repeated_timestamp():
    """A duplicated timestamp stalls the estimate rather than dividing by zero."""
    assert _rule().slope(0.0, 100e6, 200e6, previous_slope=0.25) == pytest.approx(0.25)


def test_the_slope_holds_across_a_nonpositive_reading():
    assert _rule().slope(1.0, 0.0, 200e6, previous_slope=0.25) == pytest.approx(0.25)
    assert _rule().slope(1.0, 100e6, -1.0, previous_slope=0.25) == pytest.approx(0.25)


def test_the_slope_moves_toward_a_rising_measurement():
    assert _rule().slope(1.0, 100e6, 200e6, previous_slope=0.0) > 0


# ---- the odds ----


def test_the_odds_are_flat_without_a_decay_constant():
    rule = _rule()
    assert rule.survival_odds(0.0) == pytest.approx(0.4)
    assert rule.survival_odds(600.0) == pytest.approx(0.4)


def test_the_odds_decay_when_a_constant_was_fitted():
    rule = _rule(probability_decay_tau=10.0)
    assert rule.survival_odds(10.0) == pytest.approx(0.4 * np.exp(-1))


def test_the_odds_are_zero_without_a_probability():
    assert EconomicStopping(target=1e9).survival_odds(1.0) == pytest.approx(0.0)


# ---- the verdict ----


def test_nothing_is_abandoned_before_the_minimum_decision_time():
    _, _, _, give_up = _rule().evaluate(elapsed=4.9, current_avg=50e6, slope=0.0)
    assert give_up is False


def test_a_hopeless_episode_is_abandoned_once_judging_is_allowed():
    projected, odds, cost, give_up = _rule().evaluate(
        elapsed=5.0, current_avg=50e6, slope=0.0
    )
    assert np.isinf(projected) and np.isinf(cost)
    assert odds == pytest.approx(0.4)
    assert give_up is True


def test_an_unconfigured_rule_abandons_nothing_however_hopeless():
    """Both sides infinite compares false, which is the behaviour wanted."""
    _, _, cost, give_up = EconomicStopping(target=1e9).evaluate(
        elapsed=1e6, current_avg=50e6, slope=0.0
    )
    assert np.isinf(cost)
    assert give_up is False


def test_a_promising_episode_is_kept():
    _, _, cost, give_up = _rule().evaluate(elapsed=10.0, current_avg=500e6, slope=0.1)
    assert cost < 282.0
    assert give_up is False


# ---- plotting ----


def test_infinities_are_dropped_for_plotting():
    out = finite_or_nan(np.array([1.0, np.inf, -np.inf, 2.0]))
    assert np.isnan(out[1]) and np.isnan(out[2])
    assert out[0] == 1.0 and out[3] == 2.0
