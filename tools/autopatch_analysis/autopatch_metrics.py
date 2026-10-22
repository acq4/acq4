"""Aggregate parsed autopatch attempts into throughput/efficiency tables.

Turns a list of :class:`autopatch_log.Attempt` into pandas DataFrames for the
funnel (find/seal/break-in conversion), throughput, per-state time budget, and
failure-mode breakdown consumed by the analysis notebook.

Attempt-level metrics cover only time a MultiPatch log was recording. The
``session_*``/``survey_time`` functions aggregate :mod:`autopatch_session_log`
spans instead, which also cover cleaning, cell detection, and idle between attempts.
"""

from __future__ import annotations

import math
import os
from statistics import NormalDist
from typing import Iterable

import pandas as pd

from autopatch_log import STAGE_NAMES, Attempt
from autopatch_session_log import StateSpan, SurveySpan

# Funnel stages in order, as (display stage, Attempt-boolean DataFrame column).
# The funnel is rooted at ``approached`` -- attempts that never engaged a cell
# (setup/cleaning cycles) are not real patch attempts and are excluded, so the
# base of the funnel is the count of approached attempts, not all attempts.
# Confidence level for the binomial intervals reported alongside the funnel.
DEFAULT_CONFIDENCE = 0.95

FUNNEL_STAGES = [
    ("approached", "attempted_find"),
    ("found_cell", "found_cell"),
    ("sealed", "sealed"),
    ("broke_in", "broke_in"),
]


# Columns of the per-attempt table, in order. Declared so an empty run still
# yields a well-formed (column-bearing) DataFrame instead of a bare one.
ATTEMPT_COLUMNS = [
    "source",
    "cell_dir",
    "device",
    "attempt_index",
    "start_time",
    "end_time",
    "duration_s",
    "best_stage",
    "best_stage_name",
    "attempted_find",
    "found_cell",
    "sealed",
    "broke_in",
    "gigaseal",
    "outcome",
    "outcome_recorded",
    "final_state",
    "max_seal_resistance",
    "access_resistance",
    "input_resistance",
    "holding_current",
    "capacitance",
    "n_test_pulses",
    "n_state_changes",
]


def attempts_to_dataframe(attempts: Iterable[Attempt]) -> pd.DataFrame:
    """One row per attempt with outcome flags and whole-cell quality numbers."""
    rows = []
    for a in attempts:
        rows.append(
            {
                "source": a.source,
                "cell_dir": os.path.basename(os.path.dirname(a.source)),
                "device": a.device,
                "attempt_index": a.index,
                "start_time": a.start_time,
                "end_time": a.end_time,
                "duration_s": a.duration,
                "best_stage": a.best_stage,
                "best_stage_name": a.best_stage_name,
                "attempted_find": a.attempted_find,
                "found_cell": a.found_cell,
                "sealed": a.sealed,
                "broke_in": a.broke_in,
                "gigaseal": a.gigaseal,
                "outcome": a.outcome,
                "outcome_recorded": a.outcome_recorded,
                "final_state": a.final_state,
                "max_seal_resistance": a.max_seal_resistance,
                "access_resistance": a.access_resistance,
                "input_resistance": a.input_resistance,
                "holding_current": a.holding_current,
                "capacitance": a.capacitance,
                "n_test_pulses": len(a.test_pulses),
                "n_state_changes": len(a.states),
            }
        )
    return pd.DataFrame(rows, columns=ATTEMPT_COLUMNS)


def wilson_interval(
    successes: int, trials: int, confidence: float = DEFAULT_CONFIDENCE
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, as ``(lo, hi)`` fractions.

    Preferred over the textbook normal approximation because a run is a handful
    of attempts at proportions close to 0 and 1, where that approximation gives
    intervals running off the end of the scale.
    """
    if trials <= 0:
        return (float("nan"), float("nan"))
    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    margin = (z / denominator) * math.sqrt(
        p * (1 - p) / trials + z * z / (4 * trials * trials)
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def _pct_interval(
    successes: int, trials: int, confidence: float = DEFAULT_CONFIDENCE
) -> tuple[float, float]:
    lo, hi = wilson_interval(successes, trials, confidence)
    return (100.0 * lo, 100.0 * hi)


def funnel_counts(
    df: pd.DataFrame, confidence: float = DEFAULT_CONFIDENCE
) -> pd.DataFrame:
    """Counts and conversion percentages at each funnel stage, with Wilson CIs.

    The funnel is rooted at ``approached`` (attempts that engaged a cell), so
    never-approached attempts are excluded even if they are present in ``df``.
    ``pct_of_approached`` is the share of approached attempts reaching a stage;
    ``conversion_from_prev`` is the share of the previous stage that advanced.
    Each gets a ``_lo``/``_hi`` pair holding the Wilson interval on that
    proportion, treating attempts as independent trials -- optimistic, since
    attempts sharing a slice and a pipette fail together.
    """
    approached = int(df["attempted_find"].sum()) if len(df) else 0
    rows = []
    prev = None
    for stage, column in FUNNEL_STAGES:
        count = int(df[column].sum()) if len(df) else 0
        if prev is None:
            # The base stage is its own denominator: 100% by definition, not an
            # estimate, so it carries no interval.
            pct_lo = pct_hi = conv_lo = conv_hi = 100.0
        else:
            pct_lo, pct_hi = _pct_interval(count, approached, confidence)
            conv_lo, conv_hi = _pct_interval(count, prev, confidence)
        rows.append(
            {
                "stage": stage,
                "count": count,
                "pct_of_approached": (
                    (100.0 * count / approached) if approached else 0.0
                ),
                "pct_of_approached_lo": pct_lo,
                "pct_of_approached_hi": pct_hi,
                # first stage is 100% by definition; a downstream stage whose
                # predecessor had zero attempts converts at 0%, not 100%.
                "conversion_from_prev": (
                    100.0
                    if prev is None
                    else (100.0 * count / prev if prev else 0.0)
                ),
                "conversion_from_prev_lo": conv_lo,
                "conversion_from_prev_hi": conv_hi,
            }
        )
        prev = count
    return pd.DataFrame(rows)


def failure_mode_counts(df: pd.DataFrame) -> pd.DataFrame:
    """How many attempts ended in each outcome, most common first."""
    counts = df["outcome"].value_counts()
    return (
        counts.rename_axis("outcome")
        .reset_index(name="count")
        .assign(pct=lambda d: 100.0 * d["count"] / len(df) if len(df) else 0.0)
    )


def state_dwell_times(attempts: Iterable[Attempt]) -> pd.DataFrame:
    """Seconds spent in each patch state: total, and mean per attempt.

    Each attempt's last state is excluded; it has no exit, so its interval runs
    to the end of the log. ``mean_s`` divides by ``n_attempts`` (attempts that
    entered and left the state), summing an attempt's repeat visits into one
    value; ``n_visits`` counts the raw intervals.
    """
    rows = []
    for i, a in enumerate(attempts):
        for state, t0, t1 in a.state_intervals()[:-1]:
            rows.append({"attempt": i, "state": state, "seconds": t1 - t0})
    if not rows:
        return pd.DataFrame(
            columns=["state", "total_s", "mean_s", "n_attempts", "n_visits"]
        )
    df = pd.DataFrame(rows)
    per_attempt = df.groupby(["state", "attempt"])["seconds"].sum()
    agg = (
        per_attempt.groupby("state")
        .agg(total_s="sum", mean_s="mean", n_attempts="count")
        .join(df.groupby("state").size().rename("n_visits"))
        .reset_index()
        .sort_values("total_s", ascending=False)
        .reset_index(drop=True)
    )
    return agg


# Columns of the state-timeline table, so an empty run still yields a
# well-formed (column-bearing) DataFrame.
TIMELINE_COLUMNS = [
    "folder",
    "cell_dir",
    "device",
    "attempt_index",
    "state",
    "t_start",
    "t_end",
]


def state_timeline(attempts: Iterable[Attempt]) -> pd.DataFrame:
    """Long-form (folder, device, state, t_start, t_end) spans for a Gantt view.

    One row per state interval of every attempt, keyed by ``folder`` (the
    directory holding the log). Times are absolute (epoch seconds); the notebook
    rebases them per folder. This intentionally includes non-approached attempts
    so the idle time trimmed from the active-time window stays visible.
    """
    rows = []
    for a in attempts:
        folder = os.path.dirname(a.source)
        cell_dir = os.path.basename(folder)
        for state, t0, t1 in a.state_intervals():
            rows.append(
                {
                    "folder": folder,
                    "cell_dir": cell_dir,
                    "device": a.device,
                    "attempt_index": a.index,
                    "state": state,
                    "t_start": t0,
                    "t_end": t1,
                }
            )
    return pd.DataFrame(rows, columns=TIMELINE_COLUMNS)


def throughput(df: pd.DataFrame, confidence: float = DEFAULT_CONFIDENCE) -> pd.Series:
    """Run-level throughput: active time, attempt and whole-cell rates.

    Rates use ``active_hours`` -- the summed per-log span of the attempts in
    ``df`` -- rather than the global first-to-last span, so pointing at logs
    recorded on different days doesn't count the idle gaps between runs against
    the rate. Pass the approached attempts (see ``approached_attempts``) so this
    span covers only the autopatch demo's active window and not the pipette
    setup/cleaning idle before the first cell or after the last.

    ``n_outcome_unlogged`` counts the attempts whose log stops in a state the
    pipette only passes through, so it never recorded how they ended (see
    ``Attempt.outcome_recorded``). Every count and rate here is a lower bound by
    that many attempts: those cells went somewhere the log does not say.
    """
    if df.empty:
        return pd.Series(dtype=float)
    per_log = df.groupby("source").agg(t0=("start_time", "min"), t1=("end_time", "max"))
    active_h = (per_log["t1"] - per_log["t0"]).sum() / 3600.0
    span_h = (df["end_time"].max() - df["start_time"].min()) / 3600.0
    n_attempts = len(df)
    n_whole = int(df["broke_in"].sum())
    yield_lo, yield_hi = _pct_interval(n_whole, n_attempts, confidence)
    return pd.Series(
        {
            "n_logs": df["source"].nunique(),
            "n_attempts": n_attempts,
            "n_found": int(df["found_cell"].sum()),
            "n_sealed": int(df["sealed"].sum()),
            "n_whole_cell": n_whole,
            "n_outcome_unlogged": int((~df["outcome_recorded"]).sum()),
            "active_hours": active_h,
            "span_hours": span_h,
            "attempts_per_hour": (n_attempts / active_h) if active_h else float("nan"),
            "whole_cells_per_hour": (n_whole / active_h) if active_h else float("nan"),
            "overall_yield_pct": 100.0 * n_whole / n_attempts if n_attempts else 0.0,
            "overall_yield_lo_pct": yield_lo,
            "overall_yield_hi_pct": yield_hi,
            "mean_attempt_minutes": df["duration_s"].mean() / 60.0,
        }
    )


# Targets closer together than this are the same cell re-targeted rather than a
# second cell (cells sit roughly 15 µm apart at the densities we patch).
DISTINCT_TARGET_DISTANCE = 15e-6

# Columns of the consistency table, so an empty run still yields a well-formed
# (column-bearing) DataFrame.
CONSISTENCY_COLUMNS = [
    "folder",
    "location",
    "device",
    "n_logs",
    "n_attempts",
    "n_cleaning",
    "seal_episodes",
    "n_targets",
    "n_whole_cell",
    "anomalies",
    "ok",
]


def _count_distinct_targets(
    points: list[tuple[float, ...]], min_distance: float
) -> int:
    """Targets kept only when farther than ``min_distance`` from every earlier one."""
    kept: list[tuple[float, ...]] = []
    for point in points:
        if all(math.dist(point, other) > min_distance for other in kept):
            kept.append(point)
    return len(kept)


def consistency_report(
    attempts: Iterable[Attempt], min_target_distance: float = DISTINCT_TARGET_DISTANCE
) -> pd.DataFrame:
    """Check the one-attempt-per-cell-directory contract, one row per folder and device.

    A functioning Autopatch run opens a cell directory per patch attempt, so a
    directory should hold exactly one approached attempt working one cell. That
    contract is what makes the funnel a count of cells rather than a count of
    recording stretches, so this reports what each directory actually holds and
    names every departure from it: several attempts, none at all, several
    sealing episodes, several distinct targets, or several whole-cell
    recordings. Every count but ``n_cleaning`` should read 1.

    Pass **all** attempts, since the cleaning cycles the funnel drops are part
    of what a directory legitimately contains.
    """
    attempts = list(attempts)
    if not attempts:
        return pd.DataFrame(columns=CONSISTENCY_COLUMNS)
    groups: dict[tuple[str, str], list[Attempt]] = {}
    for a in attempts:
        groups.setdefault((os.path.dirname(a.source), a.device), []).append(a)

    rows = []
    for (folder, device), group in sorted(groups.items()):
        approached = [a for a in group if a.attempted_find]
        n_targets = _count_distinct_targets(
            [t for a in group for t in a.targets], min_target_distance
        )
        seal_episodes = sum(a.seal_episodes for a in group)
        n_whole = sum(1 for a in group if a.broke_in)
        anomalies = []
        if not approached:
            anomalies.append("no approached attempt")
        elif len(approached) > 1:
            anomalies.append(f"{len(approached)} attempts")
        if seal_episodes > 1:
            anomalies.append(f"{seal_episodes} seal episodes")
        if n_targets > 1:
            anomalies.append(f"{n_targets} distinct targets")
        if n_whole > 1:
            anomalies.append(f"{n_whole} whole cells")
        rows.append(
            {
                "folder": folder,
                "location": os.path.join(*folder.split(os.sep)[-2:]),
                "device": device,
                "n_logs": len({a.source for a in group}),
                "n_attempts": len(approached),
                "n_cleaning": len(group) - len(approached),
                "seal_episodes": seal_episodes,
                "n_targets": n_targets,
                "n_whole_cell": n_whole,
                "anomalies": ", ".join(anomalies),
                "ok": not anomalies,
            }
        )
    return pd.DataFrame(rows, columns=CONSISTENCY_COLUMNS)


def cumulative_whole_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Whole-cell successes over wall-clock, for a cumulative-yield plot."""
    if df.empty:
        return pd.DataFrame(columns=["minutes", "cumulative_whole_cells"])
    t0 = df["start_time"].min()
    wc = df[df["broke_in"]].sort_values("end_time")
    return pd.DataFrame(
        {
            "minutes": (wc["end_time"] - t0) / 60.0,
            "cumulative_whole_cells": range(1, len(wc) + 1),
        }
    )


# --- session-log time budget --------------------------------------------------

# Cost category per patch state; anything unlisted is ``other``. ``recording``
# is reported separately and never folded into the overhead total.
PATCHING, CLEANING, RECORDING, IDLE, OTHER = (
    "patching",
    "cleaning",
    "recording",
    "idle",
    "other",
)
STATE_CATEGORIES = {
    "approach": PATCHING,
    "cell detect": PATCHING,
    "contact cell": PATCHING,
    "seal": PATCHING,
    "cell attached": PATCHING,
    "break in": PATCHING,
    "whole cell": RECORDING,
    "reseal": RECORDING,
    "home with nucleus": RECORDING,
    "collect": RECORDING,
    "clean": CLEANING,
    "blowout": CLEANING,
    "out": IDLE,
    "bath": IDLE,
    "fouled": IDLE,
    "broken": IDLE,
}

CATEGORY_ORDER = [PATCHING, CLEANING, IDLE, RECORDING, OTHER]

# The analyzed window opens on the first patching span and closes on the last
# patching/cleaning/recording span, excluding setup before and idle after.
_WINDOW_OPENING = {PATCHING}
_WINDOW_CLOSING = {PATCHING, CLEANING, RECORDING}

# Categories in which a device is doing something. Wall-clock in none of them is
# the rig stopped. Same membership as _WINDOW_CLOSING, for a different question:
# that one asks when the run ended, this one asks whether work is happening now.
WORKING_CATEGORIES = frozenset({PATCHING, CLEANING, RECORDING})

# Columns of the idle-span table, so an empty run still yields a well-formed
# (column-bearing) DataFrame.
IDLE_SPAN_COLUMNS = ["t_start", "t_end", "minutes"]

BUDGET_COLUMNS = [
    "device",
    "category",
    "state",
    "total_s",
    "mean_s",
    "n_visits",
    "pct_of_active",
]


def categorize_state(state: str) -> str:
    """Which time-budget category a patch state belongs to."""
    return STATE_CATEGORIES.get(state, OTHER)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def session_active_windows(spans: Iterable[StateSpan]) -> dict:
    """``{(source, device): (t_start, t_end)}`` for each device that patched.

    A device that never entered a patching state is omitted.
    """
    opens: dict = {}
    closes: dict = {}
    for s in spans:
        key = (s.source, s.device)
        cat = categorize_state(s.state)
        if cat in _WINDOW_OPENING:
            opens[key] = min(opens.get(key, s.t_start), s.t_start)
        if cat in _WINDOW_CLOSING:
            closes[key] = max(closes.get(key, s.t_end), s.t_end)
    return {
        key: (t0, closes[key]) for key, t0 in opens.items() if closes.get(key, t0) > t0
    }


def session_idle_spans(
    spans: Iterable[StateSpan], min_minutes: float = 10.0
) -> pd.DataFrame:
    """Stretches of at least ``min_minutes`` in which no device was working.

    A device is working while it is patching, cleaning or holding a recording;
    everything else -- parked, travelling, waiting on a human, or logging
    nothing at all -- is autopatch stopped. Stretches shorter than
    ``min_minutes`` are the ordinary rhythm between cells and are dropped, so
    what survives is the rig genuinely halted: paused for a bug, waiting, or
    between sessions.

    Times are absolute (epoch seconds), spanning the whole session log rather
    than the active window, so setup before the first cell shows up as stopped
    rather than disappearing.
    """
    spans = list(spans)
    if not spans:
        return pd.DataFrame(columns=IDLE_SPAN_COLUMNS)
    run_start = min(s.t_start for s in spans)
    run_end = max(s.t_end for s in spans)
    working = sorted(
        (s.t_start, s.t_end)
        for s in spans
        if categorize_state(s.state) in WORKING_CATEGORIES
    )
    rows = []
    cursor = run_start
    for t_start, t_end in working:
        if t_start - cursor >= min_minutes * 60.0:
            rows.append(
                {
                    "t_start": cursor,
                    "t_end": t_start,
                    "minutes": (t_start - cursor) / 60.0,
                }
            )
        cursor = max(cursor, t_end)
    if run_end - cursor >= min_minutes * 60.0:
        rows.append(
            {"t_start": cursor, "t_end": run_end, "minutes": (run_end - cursor) / 60.0}
        )
    return pd.DataFrame(rows, columns=IDLE_SPAN_COLUMNS)


def session_time_budget(spans: Iterable[StateSpan]) -> pd.DataFrame:
    """Time in each patch state over the run, per device, within its window.

    One row per (device, state), clipped to that device's active window, with
    the cost category and the share of the window it accounts for.
    """
    spans = list(spans)
    windows = session_active_windows(spans)
    rows = []
    for s in spans:
        window = windows.get((s.source, s.device))
        if window is None:
            continue
        seconds = _overlap(s.t_start, s.t_end, *window)
        if seconds <= 0:
            continue
        rows.append(
            {
                "device": s.device,
                "category": categorize_state(s.state),
                "state": s.state,
                "seconds": seconds,
            }
        )
    if not rows:
        return pd.DataFrame(columns=BUDGET_COLUMNS)
    active_s = sum(t1 - t0 for t0, t1 in windows.values())
    df = pd.DataFrame(rows)
    agg = (
        df.groupby(["device", "category", "state"])["seconds"]
        .agg(total_s="sum", mean_s="mean", n_visits="count")
        .reset_index()
    )
    agg["pct_of_active"] = 100.0 * agg["total_s"] / active_s if active_s else 0.0
    agg["_order"] = agg["category"].map(
        {c: i for i, c in enumerate(CATEGORY_ORDER)}
    )
    return (
        agg.sort_values(["_order", "total_s"], ascending=[True, False])
        .drop(columns="_order")
        .reset_index(drop=True)[BUDGET_COLUMNS]
    )


def session_category_totals(budget: pd.DataFrame) -> pd.DataFrame:
    """Roll ``session_time_budget`` up to one row per cost category."""
    if budget.empty:
        return pd.DataFrame(columns=["category", "minutes", "pct_of_active"])
    totals = budget.groupby("category")[["total_s", "pct_of_active"]].sum()
    totals = totals.reindex([c for c in CATEGORY_ORDER if c in totals.index])
    return pd.DataFrame(
        {
            "category": totals.index,
            "minutes": totals["total_s"].to_numpy() / 60.0,
            "pct_of_active": totals["pct_of_active"].to_numpy(),
        }
    )


def survey_time(
    spans: Iterable[StateSpan], surveys: Iterable[SurveySpan]
) -> pd.Series:
    """Cost of finding cells: tile surveys clipped to the run's active window.

    Concurrent with ``session_time_budget``, not a slice of it; adding the two
    double-counts. ``blocking_minutes`` is the part overlapping a non-patching
    state; ``per_candidate_s`` is survey seconds per candidate found.
    """
    surveys = list(surveys)
    windows = session_active_windows(spans)
    if not surveys or not windows:
        return pd.Series(dtype=float)
    # One run-level window per source: surveys are scope-wide, not per pipette.
    by_source: dict = {}
    for (source, _device), (t0, t1) in windows.items():
        lo, hi = by_source.get(source, (t0, t1))
        by_source[source] = (min(lo, t0), max(hi, t1))
    active_s = sum(t1 - t0 for t0, t1 in windows.values())
    seconds = 0.0
    candidates = 0
    n = 0
    for s in surveys:
        window = by_source.get(s.source)
        if window is None:
            continue
        overlap = _overlap(s.t_start, s.t_end, *window)
        if overlap <= 0:
            continue
        seconds += overlap
        candidates += s.n_candidates
        n += 1
    blocking = 0.0
    for span in spans:
        if categorize_state(span.state) == PATCHING:
            continue
        window = windows.get((span.source, span.device))
        if window is None:
            continue
        for s in surveys:
            if s.source != span.source:
                continue
            lo = max(span.t_start, s.t_start, window[0])
            hi = min(span.t_end, s.t_end, window[1])
            blocking += max(0.0, hi - lo)
    return pd.Series(
        {
            "n_surveys": n,
            "minutes": seconds / 60.0,
            "mean_minutes": (seconds / n / 60.0) if n else float("nan"),
            "pct_of_active": (100.0 * seconds / active_s) if active_s else 0.0,
            "blocking_minutes": blocking / 60.0,
            "n_candidates": candidates,
            "per_candidate_s": (seconds / candidates) if candidates else float("nan"),
        }
    )


def session_time_summary(
    spans: Iterable[StateSpan],
    surveys: Iterable[SurveySpan] = (),
    n_attempts: int | None = None,
) -> pd.Series:
    """Headline numbers for where the run's clock went.

    ``active_minutes`` is wall-clock over the analyzed window, including the
    cleaning and idle between attempts. The ``*_per_attempt`` keys are present
    only when ``n_attempts`` is given.
    """
    spans = list(spans)
    budget = session_time_budget(spans)
    if budget.empty:
        return pd.Series(dtype=float)
    windows = session_active_windows(spans)
    active_s = sum(t1 - t0 for t0, t1 in windows.values())
    totals = budget.groupby("category")["total_s"].sum()
    survey = survey_time(spans, surveys)
    out = {
        "active_minutes": active_s / 60.0,
        "patching_minutes": float(totals.get(PATCHING, 0.0)) / 60.0,
        "cleaning_minutes": float(totals.get(CLEANING, 0.0)) / 60.0,
        "idle_minutes": float(totals.get(IDLE, 0.0)) / 60.0,
        "recording_minutes": float(totals.get(RECORDING, 0.0)) / 60.0,
        "other_minutes": float(totals.get(OTHER, 0.0)) / 60.0,
        "detection_minutes": float(survey.get("minutes", 0.0)),
        "n_clean_cycles": int(
            budget.loc[budget["category"] == CLEANING, "n_visits"].sum()
        ),
        "n_surveys": int(survey.get("n_surveys", 0)),
    }
    overhead_s = float(totals.get(CLEANING, 0.0) + totals.get(IDLE, 0.0) + totals.get(OTHER, 0.0))
    out["overhead_minutes"] = overhead_s / 60.0
    out["overhead_pct"] = (100.0 * overhead_s / active_s) if active_s else 0.0
    if n_attempts:
        out["minutes_per_attempt"] = out["active_minutes"] / n_attempts
        out["cleaning_per_attempt_minutes"] = out["cleaning_minutes"] / n_attempts
        out["idle_per_attempt_minutes"] = out["idle_minutes"] / n_attempts
        out["detection_per_attempt_minutes"] = out["detection_minutes"] / n_attempts
    return pd.Series(out)


# Re-export for notebook convenience.
__all__ = [
    "STAGE_NAMES",
    "STATE_CATEGORIES",
    "CATEGORY_ORDER",
    "attempts_to_dataframe",
    "consistency_report",
    "funnel_counts",
    "wilson_interval",
    "failure_mode_counts",
    "state_dwell_times",
    "state_timeline",
    "throughput",
    "cumulative_whole_cells",
    "categorize_state",
    "session_active_windows",
    "session_idle_spans",
    "session_time_budget",
    "session_category_totals",
    "session_time_summary",
    "survey_time",
]
