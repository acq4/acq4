"""Unit tests for the economic columns SealAnalysis computes alongside its
success/failure detection: the projected time to a seal, the odds this episode
pays off, and the comparison against the cost of starting over on a fresh cell.

These are computed on every test pulse whether or not the state is allowed to act
on them, so a run with early exit disabled still records what the rule would have
decided.
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.seal import SealAnalysis

# A slice worth 282 s per gigaseal: (90 + 0.4*12 + 0.6*30) / 0.4.
SLICE = dict(
    restart_cost=90.0,
    seal_probability=0.4,
    expected_seal_duration=12.0,
    expected_failed_seal_duration=30.0,
)
EXPECTED_W = 282.0


def _analysis(**overrides):
    kwargs = dict(
        success_tau=1.0,
        success_at=1e9,
        hold_tau=0.1,
        hold_at=100e6,
        failure_tau=10.0,
        failure_resistance_threshold=50e6,
        failure_dRdt_threshold=1e6,
        break_in_tau=3.0,
        break_in_capacitance_threshold=10e-12,
        break_in_resistance_ceiling=1e9,
        break_in_resistance_floor=0.0,
        slope_tau=2.0,
        min_decision_time=5.0,
    )
    kwargs.update(overrides)
    return SealAnalysis(**kwargs)


def _flat(resistance, duration=30.0, rate=10.0):
    """A resistance that does not move: the flatlined seal the rule should cut."""
    n = int(duration * rate)
    return np.array([(i / rate, resistance, np.nan) for i in range(n)])


def _climbing(start, stop, duration=30.0, rate=10.0):
    """A resistance climbing exponentially from `start` to `stop`."""
    n = int(duration * rate)
    times = np.arange(n) / rate
    values = start * np.exp(np.log(stop / start) * times / duration)
    return np.array([(t, v, np.nan) for t, v in zip(times, values)])


# ---- inert until configured ----


def test_the_columns_are_present_on_every_analysis():
    result = _analysis().process_measurements(_flat(50e6))
    for column in (
        "log_rss_slope",
        "projected_seal_time",
        "survival_q",
        "continue_cost",
        "abandon_threshold",
        "give_up",
    ):
        assert column in result.dtype.names


def test_nothing_is_given_up_on_without_a_seal_probability():
    """The shipped default. An infinite W means there is no better alternative to
    go to, so the rule never fires and autoSealTimeout keeps its job."""
    result = _analysis().process_measurements(_flat(50e6))
    assert np.isinf(result["abandon_threshold"]).all()
    assert not result["give_up"].any()


def test_the_columns_are_computed_even_with_no_economics_configured():
    """Recording what the rule would have decided is the whole point of the
    disabled state; a slope of zero here would be indistinguishable from a real
    flatline when the calibration pass reads it back."""
    result = _analysis().process_measurements(_climbing(50e6, 1e9))
    assert result["log_rss_slope"][-1] > 0


# ---- the slope ----


def test_the_slope_is_positive_while_the_resistance_climbs():
    result = _analysis(**SLICE).process_measurements(_climbing(50e6, 1e9))
    # ln(20) over 30 s, give or take the averaging lag.
    assert result["log_rss_slope"][-1] == pytest.approx(np.log(20) / 30, rel=0.15)


def test_the_slope_is_zero_on_a_flat_resistance():
    result = _analysis(**SLICE).process_measurements(_flat(50e6))
    assert result["log_rss_slope"][-1] == pytest.approx(0.0, abs=1e-6)


def test_the_slope_is_negative_on_a_falling_resistance():
    result = _analysis(**SLICE).process_measurements(_climbing(500e6, 50e6))
    assert result["log_rss_slope"][-1] < 0


# ---- the projection ----


def test_the_projection_shortens_as_the_resistance_climbs():
    result = _analysis(**SLICE).process_measurements(_climbing(50e6, 1e9))
    later = result["projected_seal_time"][-1]
    earlier = result["projected_seal_time"][len(result) // 2]
    assert 0 <= later < earlier


def test_the_projection_is_infinite_on_a_flat_resistance():
    result = _analysis(**SLICE).process_measurements(_flat(50e6))
    assert np.isinf(result["projected_seal_time"][-1])


def test_the_projection_is_infinite_on_a_falling_resistance():
    result = _analysis(**SLICE).process_measurements(_climbing(500e6, 50e6))
    assert np.isinf(result["projected_seal_time"][-1])


def test_the_projection_is_zero_once_the_threshold_is_reached():
    result = _analysis(**SLICE).process_measurements(_climbing(50e6, 4e9))
    assert result["projected_seal_time"][-1] == pytest.approx(0.0)


# ---- the threshold to beat ----


def test_the_abandon_threshold_is_the_expected_time_to_the_next_seal():
    result = _analysis(**SLICE).process_measurements(_flat(50e6))
    assert result["abandon_threshold"][-1] == pytest.approx(EXPECTED_W)


def test_the_abandon_threshold_ignores_the_episode_in_progress():
    """It describes the alternative, which does not change while this cell runs."""
    result = _analysis(**SLICE).process_measurements(_climbing(50e6, 1e9))
    assert result["abandon_threshold"] == pytest.approx(EXPECTED_W)


# ---- the odds ----


def test_survival_odds_are_flat_without_a_decay_constant():
    result = _analysis(**SLICE).process_measurements(_flat(50e6))
    assert result["survival_q"] == pytest.approx(0.4)


def test_survival_odds_decay_with_elapsed_time_when_configured():
    result = _analysis(**SLICE, probability_decay_tau=10.0).process_measurements(
        _flat(50e6, duration=10.0)
    )
    assert result["survival_q"][0] == pytest.approx(0.4)
    # One tau in, less a frame: the last pulse of a 10 s run at 10 Hz lands at 9.9 s.
    assert result["survival_q"][-1] == pytest.approx(0.4 * np.exp(-0.99), rel=1e-3)


# ---- the decision ----


def test_a_flatlined_seal_is_given_up_on():
    result = _analysis(**SLICE).process_measurements(_flat(50e6))
    assert result["give_up"][-1]
    assert np.isinf(result["continue_cost"][-1])


def test_nothing_is_given_up_on_before_the_minimum_decision_time():
    """Early on there is no slope to read; judging there would abandon every cell
    on measurement noise."""
    result = _analysis(**SLICE, min_decision_time=5.0).process_measurements(_flat(50e6))
    early = result[result["time"] < 5.0]
    assert not early["give_up"].any()
    assert result["give_up"][-1]


def test_a_cell_that_is_climbing_well_is_not_given_up_on():
    result = _analysis(**SLICE).process_measurements(_climbing(50e6, 1e9))
    assert not result["give_up"][int(5.5 * 10):].any()
    assert result["continue_cost"][-1] < EXPECTED_W


def test_the_continue_cost_is_the_projection_over_the_odds():
    result = _analysis(**SLICE).process_measurements(_climbing(50e6, 1e9))
    row = result[-1]
    assert row["continue_cost"] == pytest.approx(row["projected_seal_time"] / row["survival_q"])


def test_give_up_reports_the_last_measurement():
    analysis = _analysis(**SLICE)
    analysis.process_measurements(_climbing(50e6, 1e9))
    assert analysis.give_up() is False
    analysis = _analysis(**SLICE)
    analysis.process_measurements(_flat(50e6))
    assert analysis.give_up() is True


def test_give_up_is_false_before_any_measurement():
    assert _analysis(**SLICE).give_up() is False


# ---- reading the decisions back off a log ----


def test_the_decision_series_are_plottable(qapp):
    """The point of computing these while disabled is reading them back, so the
    log viewer has to be able to draw them."""
    plots = SealAnalysis.plots_for_data(
        [_climbing(50e6, 1e9)],
        success_tau=1.0,
        success_at=1e9,
        hold_tau=0.1,
        hold_at=100e6,
        failure_tau=10.0,
        failure_resistance_threshold=50e6,
        failure_dRdt_threshold=1e6,
        break_in_tau=3.0,
        break_in_capacitance_threshold=10e-12,
        break_in_resistance_ceiling=1e9,
        break_in_resistance_floor=0.0,
        **SLICE,
    )
    names = [series.get("name") for group in plots.values() for series in group]
    assert "Projected Seal Time" in names
    assert "Cost of Continuing" in names
    assert "Cost of Starting Over" in names
    assert "Give Up" in names


def test_plotted_series_carry_no_infinities(qapp):
    """A flatlined seal's cost is deliberately infinite; a curve of infinities is
    not drawable, so they are dropped to NaN on the way out."""
    plots = SealAnalysis.plots_for_data(
        [_flat(50e6)],
        success_tau=1.0,
        success_at=1e9,
        hold_tau=0.1,
        hold_at=100e6,
        failure_tau=10.0,
        failure_resistance_threshold=50e6,
        failure_dRdt_threshold=1e6,
        break_in_tau=3.0,
        break_in_capacitance_threshold=10e-12,
        break_in_resistance_ceiling=1e9,
        break_in_resistance_floor=0.0,
        **SLICE,
    )
    for group in plots.values():
        for series in group:
            values = np.asarray(series["y"], dtype=float)
            assert not np.isinf(values).any()
