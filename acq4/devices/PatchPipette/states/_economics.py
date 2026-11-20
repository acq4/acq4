"""The stopping rule the seal and reseal states share: whether continuing to work
on the cell in hand is expected to cost more time than starting over on a fresh
one."""

from __future__ import annotations

import numpy as np

from ._base import exponential_decay_avg


class EconomicStopping:
    """Whether to keep working on this cell, in units of time.

    The comparison is

        continue  iff  projected_time / survival_odds  <  prize_value * W
        W = (R + p*T_s + (1-p)*T_f) / p

    where `W` is the expected wall-clock from abandoning this cell to the next
    success: one cycle's overhead plus whichever episode it buys, divided by the
    share of cycles that succeed. `projected_time / survival_odds` is the same
    quantity for the cell in hand -- expected remaining time, divided by the odds
    it pays off.

    `prize_value` scales what a success here is worth against what a success on a
    replacement would be worth, and so is folded into the threshold rather than
    applied to the projection. It is 1 wherever every success is worth the same,
    which is the seal state's whole situation.

    Both sides are in seconds and neither is a probability-weighted average of
    the other, which is what makes the rule readable in a log: an operator can
    see the two durations the rig weighed.

    Every degenerate input resolves toward *not* abandoning anything. No success
    probability leaves `W` infinite, and `inf > inf` is false, so an unconfigured
    rule never fires -- which is what lets these parameters ship at zero and
    leave a state behaving exactly as it did before the rule existed.
    """

    def __init__(
        self,
        target,
        slope_tau=2.0,
        min_decision_time=5.0,
        restart_cost=0.0,
        success_probability=0.0,
        expected_success_duration=0.0,
        expected_failure_duration=0.0,
        probability_decay_tau=0.0,
        prize_value=1.0,
    ):
        self._target = target
        self._slope_tau = slope_tau
        self._min_decision_time = min_decision_time
        self._success_probability = success_probability
        self._probability_decay_tau = probability_decay_tau
        # Constant for the whole episode -- it describes the alternative, which
        # the cell in hand cannot change -- so it is computed once here rather
        # than on every measurement.
        if success_probability > 0:
            self.abandon_threshold = prize_value * (
                restart_cost
                + success_probability * expected_success_duration
                + (1 - success_probability) * expected_failure_duration
            ) / success_probability
        else:
            self.abandon_threshold = np.inf

    def slope(self, dt, previous_avg, current_avg, previous_slope) -> float:
        """d(ln x)/dt, exponentially averaged over *slope_tau*.

        Taken from an already-averaged measurement rather than a raw reading,
        because a slope read off unsmoothed test pulses is dominated by their
        noise.

        Holds the previous estimate when there is no interval to divide by or no
        positive pair to take a logarithm of, so a duplicated timestamp or a
        nonpositive reading stalls the estimate rather than destroying it.
        """
        if dt <= 0 or previous_avg <= 0 or current_avg <= 0:
            return float(previous_slope)
        raw = (np.log(current_avg) - np.log(previous_avg)) / dt
        slope, _ = exponential_decay_avg(dt, previous_slope, raw, self._slope_tau)
        return float(slope)

    def projected_time(self, current_avg, slope) -> float:
        """Seconds for `current_avg` to reach the target on this slope.

        Zero once the target is reached, and infinite on a flat or falling slope:
        on that trajectory the target never arrives, so the cost of continuing is
        unbounded however cheap a replacement would be.
        """
        if current_avg >= self._target:
            return 0.0
        if slope > 0 and current_avg > 0:
            return (np.log(self._target) - np.log(current_avg)) / slope
        return np.inf

    def survival_odds(self, elapsed) -> float:
        """The chance this episode still ends in success, given it has run this
        long without doing so.

        Flat at the configured probability unless a decay constant was fitted for
        this preparation, since assuming a decay nobody measured would abandon
        cells on an invented curve.
        """
        if self._success_probability <= 0:
            return 0.0
        if self._probability_decay_tau > 0:
            return self._success_probability * np.exp(
                -elapsed / self._probability_decay_tau
            )
        return self._success_probability

    def evaluate(
        self, elapsed, current_avg, slope, projected=None
    ) -> tuple[float, float, float, bool]:
        """`(projected_time, survival_odds, continue_cost, give_up)` for one
        measurement.

        `projected` replaces the trend-derived projection, for a caller whose
        success criterion this rule cannot see: reseal can be declared successful
        by retraction distance as well as by resistance, and a projection off the
        resistance trend alone would abandon cells the state was about to pass.
        Such a caller combines the routes itself and hands the result in, rather
        than this rule learning what a retraction is.
        """
        if projected is None:
            projected = self.projected_time(current_avg, slope)
        odds = self.survival_odds(elapsed)
        continue_cost = projected / odds if odds > 0 else np.inf
        give_up = bool(
            elapsed >= self._min_decision_time
            and continue_cost > self.abandon_threshold
        )
        return projected, odds, continue_cost, give_up


def finite_or_nan(values: np.ndarray) -> np.ndarray:
    """`values` with the infinities replaced by NaN, so a plot skips them.

    The economic columns are deliberately infinite wherever the episode is going
    nowhere or the preparation offers nothing better, which is meaningful in the
    record and unplottable in a curve.
    """
    return np.where(np.isfinite(values), values, np.nan)
