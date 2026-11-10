"""Unit tests for the economic columns ResealAnalysis computes alongside its
stretch/tear detection.

Reseal's prize is a nucleus rather than a gigaseal, and cells differ in what
theirs is worth, so unlike the seal state's rule this one is scaled by a prize
value -- see SliceStatistics.prizeValue for where that comes from.
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.reseal import ResealAnalysis

# (600 + 0.5*120 + 0.5*300) / 0.5 = 1620
TERMS = dict(
    restart_cost=600.0,
    nucleus_probability=0.5,
    expected_reseal_duration=120.0,
    expected_failed_reseal_duration=300.0,
)
EXPECTED_W = 1620.0


def _analysis(**overrides):
    kwargs = dict(
        stretch_threshold=0.005,
        tearing_threshold=-0.00128,
        torn_threshold=50e6,
        detection_tau=1.0,
        repair_tau=10.0,
        target=500e6,
        slope_tau=2.0,
        min_decision_time=5.0,
    )
    kwargs.update(overrides)
    return ResealAnalysis(**kwargs)


def _flat(resistance, duration=200.0, rate=5.0):
    """A resistance that settles and then stops moving."""
    n = int(duration * rate)
    return np.array([(i / rate, resistance) for i in range(n)])


def _climbing(start, stop, duration=200.0, rate=5.0):
    n = int(duration * rate)
    times = np.arange(n) / rate
    values = start * np.exp(np.log(stop / start) * times / duration)
    return np.array(list(zip(times, values)))


def test_the_columns_are_present():
    result = _analysis().process_measurements(_flat(100e6))
    for column in (
        "log_rss_slope",
        "projected_reseal_time",
        "survival_q",
        "continue_cost",
        "abandon_threshold",
        "give_up",
    ):
        assert column in result.dtype.names


def test_nothing_is_given_up_on_unconfigured():
    """The shipped default, as for seal: the columns are recorded and the verdict
    is never positive."""
    result = _analysis().process_measurements(_flat(100e6))
    assert np.isinf(result["abandon_threshold"]).all()
    assert not result["give_up"].any()


def test_the_threshold_is_the_expected_time_to_the_next_nucleus():
    result = _analysis(**TERMS).process_measurements(_flat(100e6))
    assert result["abandon_threshold"][-1] == pytest.approx(EXPECTED_W)


def test_a_resistance_that_stops_climbing_short_of_the_target_is_given_up_on():
    result = _analysis(**TERMS).process_measurements(_flat(100e6))
    assert result["give_up"][-1]
    # Far past the threshold rather than literally infinite: an average settling
    # onto a constant approaches it from below, so its slope vanishes without
    # ever reaching zero, and the projection grows without bound instead.
    assert result["continue_cost"][-1] > EXPECTED_W


def test_a_resistance_climbing_toward_the_target_is_kept():
    result = _analysis(**TERMS).process_measurements(_climbing(50e6, 500e6))
    assert not result["give_up"][-1]


def test_the_projection_is_zero_once_the_target_is_reached():
    result = _analysis(**TERMS).process_measurements(_flat(800e6))
    assert result["projected_reseal_time"][-1] == pytest.approx(0.0)
    assert not result["give_up"][-1]


def test_a_cheap_prize_is_given_up_on_sooner():
    """The whole point of the prize value: a nucleus from a cell whose recording
    was poor is worth less time than one from a good cell."""
    cheap = _analysis(**TERMS, prize_value=0.25).process_measurements(_flat(100e6))
    dear = _analysis(**TERMS, prize_value=4.0).process_measurements(_flat(100e6))
    assert cheap["abandon_threshold"][-1] == pytest.approx(EXPECTED_W * 0.25)
    assert dear["abandon_threshold"][-1] == pytest.approx(EXPECTED_W * 4.0)


def test_the_accessors_report_the_last_measurement():
    analysis = _analysis(**TERMS)
    analysis.process_measurements(_flat(100e6))
    assert analysis.give_up() is True
    assert analysis.continue_cost() > EXPECTED_W
    assert analysis.abandon_threshold() == pytest.approx(EXPECTED_W)


def test_give_up_is_false_before_any_measurement():
    assert _analysis(**TERMS).give_up() is False


def test_the_detection_columns_still_work():
    """The economics must not disturb what this analysis already did."""
    result = _analysis(**TERMS).process_measurements(_flat(10e6))
    assert result["torn"][-1]
    assert result["repair_avg"][-1] == pytest.approx(10e6, rel=0.01)


def test_the_decision_series_are_plottable(qapp):
    plots = ResealAnalysis.plots_for_data(
        [_flat(100e6)],
        stretch_threshold=0.005,
        tearing_threshold=-0.00128,
        torn_threshold=50e6,
        detection_tau=1.0,
        repair_tau=10.0,
        target=500e6,
        **TERMS,
    )
    names = [series.get("name") for group in plots.values() for series in group]
    assert "Projected Reseal Time" in names
    assert "Cost of Another Nucleus" in names
    assert "Give Up" in names
    for group in plots.values():
        for series in group:
            assert not np.isinf(np.asarray(series["y"], dtype=float)).any()


# ---- the distance route to success ----
#
# A reseal is declared successful once the tip is `retractionSuccessDistance`
# from the target whatever the resistance is doing, and the resistance route is
# itself gated by `minimumSuccessDistance`. Projecting on resistance alone can
# therefore abandon a cell the state was about to call a success. Under the
# shipped defaults the distance route needs ~909 s against a 600 s
# `resealTimeout` and so never arrives; these cover the rigs where it does.

DISTANCE = dict(
    retraction_rate=1e-6, success_distance=200e-6, minimum_distance=20e-6
)


def test_without_a_measured_distance_the_projection_is_the_trend_alone():
    """Offline replay has no position to read, so the clamp has to stay inert
    rather than invent a retraction."""
    clamped = _analysis(**TERMS, **DISTANCE).process_measurements(_flat(100e6))
    plain = _analysis(**TERMS).process_measurements(_flat(100e6))

    assert clamped["projected_reseal_time"][-1] == pytest.approx(
        plain["projected_reseal_time"][-1]
    )


def test_a_stalled_resistance_is_kept_when_the_retraction_will_arrive():
    """The false abandon this clamp exists to stop: resistance going nowhere, and
    the retraction itself 10 s from declaring success."""
    analysis = _analysis(**TERMS, **DISTANCE)
    analysis.set_retraction_distance(190e-6)

    result = analysis.process_measurements(_flat(100e6))

    assert result["projected_reseal_time"][-1] == pytest.approx(10.0)
    assert not result["give_up"][-1]


def test_a_retraction_too_slow_to_arrive_is_still_given_up_on():
    """The shipped defaults, and why the distance route was left out to begin
    with: 200 um at 0.22 um/s is 909 s, which over even odds is 1818 s against
    the 1620 s another nucleus costs."""
    analysis = _analysis(
        **TERMS, retraction_rate=0.22e-6, success_distance=200e-6, minimum_distance=20e-6
    )
    analysis.set_retraction_distance(0.0)

    result = analysis.process_measurements(_flat(100e6))

    assert result["projected_reseal_time"][-1] == pytest.approx(909.09, rel=1e-3)
    assert result["give_up"][-1]


def test_the_minimum_distance_floors_the_projection():
    """A resealed membrane still is not a success until the tip has backed off, so
    the rule must not promise one the state will refuse to declare."""
    analysis = _analysis(**TERMS, **DISTANCE)
    analysis.set_retraction_distance(5e-6)

    result = analysis.process_measurements(_climbing(50e6, 800e6))

    assert result["projected_reseal_time"][-1] == pytest.approx(15.0)


def test_a_tip_already_past_the_success_distance_projects_zero():
    analysis = _analysis(**TERMS, **DISTANCE)
    analysis.set_retraction_distance(250e-6)

    result = analysis.process_measurements(_flat(100e6))

    assert result["projected_reseal_time"][-1] == pytest.approx(0.0)
    assert not result["give_up"][-1]
