"""Aggregate parsed autopatch attempts into throughput/efficiency tables.

Turns a list of :class:`autopatch_log.Attempt` into pandas DataFrames for the
funnel (find/seal/break-in conversion), throughput, per-state time budget, and
failure-mode breakdown consumed by the analysis notebook.

Attempt-level metrics only see time a MultiPatch log was being recorded, which
is the patch work alone. The ``session_*``/``survey_time`` functions at the end
aggregate :mod:`autopatch_session_log` spans instead, which also cover what
happens between attempts (cleaning, cell detection, idle).
"""

from __future__ import annotations

import os
from typing import Iterable

import pandas as pd

from autopatch_log import STAGE_NAMES, Attempt
from autopatch_session_log import StateSpan, SurveySpan

# Funnel stages in order, as (display stage, Attempt-boolean DataFrame column).
# The funnel is rooted at ``approached`` -- attempts that never engaged a cell
# (setup/cleaning cycles) are not real patch attempts and are excluded, so the
# base of the funnel is the count of approached attempts, not all attempts.
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


def funnel_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Counts and conversion percentages at each funnel stage.

    The funnel is rooted at ``approached`` (attempts that engaged a cell), so
    never-approached attempts are excluded even if they are present in ``df``.
    ``pct_of_approached`` is the share of approached attempts reaching a stage;
    ``conversion_from_prev`` is the share of the previous stage that advanced.
    """
    approached = int(df["attempted_find"].sum()) if len(df) else 0
    rows = []
    prev = None
    for stage, column in FUNNEL_STAGES:
        count = int(df[column].sum()) if len(df) else 0
        rows.append(
            {
                "stage": stage,
                "count": count,
                "pct_of_approached": (
                    (100.0 * count / approached) if approached else 0.0
                ),
                # first stage is 100% by definition; a downstream stage whose
                # predecessor had zero attempts converts at 0%, not 100%.
                "conversion_from_prev": (
                    100.0
                    if prev is None
                    else (100.0 * count / prev if prev else 0.0)
                ),
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

    Only spans the log records the pipette *leaving* are counted. An attempt's
    last state has no exit -- ``state_intervals`` runs it to the end of the log
    -- so including it would report "time until the log stopped" as a dwell
    time. That is meaningless for the terminal states every attempt ends in
    (``whole cell``, ``fouled``), which read as milliseconds when the log ends
    on the transition that entered them.

    ``mean_s`` divides by ``n_attempts`` -- the attempts that actually entered
    and left the state -- not by the size of the run, so a state only two
    attempts ever reached reports the mean of those two. An attempt that
    re-enters a state contributes all of its visits as one value; ``n_visits``
    counts the raw intervals behind that.
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


def throughput(df: pd.DataFrame) -> pd.Series:
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
            "mean_attempt_minutes": df["duration_s"].mean() / 60.0,
        }
    )


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
#
# The attempt-level metrics above only see time the MultiPatch recorder was
# running, which is the patch work alone. These aggregate
# ``autopatch_session_log`` spans, which cover the whole run.

# Which cost each patch state is. ``recording`` is the whole-cell time whose
# length is set by the experiment's task protocol, so it is reported separately
# and never folded into the overhead: it is the work, not the cost of getting
# there. Everything not named here is ``other`` rather than silently idle.
PATCHING, CLEANING, RECORDING, IDLE, OTHER = (
    "patching",
    "cleaning",
    "recording",
    "idle",
    "other",
)
STATE_CATEGORIES = {
    # engaging a cell: descending to the target, hunting the membrane, sealing,
    # breaking in
    "approach": PATCHING,
    "cell detect": PATCHING,
    "contact cell": PATCHING,
    "seal": PATCHING,
    "cell attached": PATCHING,
    "break in": PATCHING,
    # holding the recording: length is the task protocol's, not the rig's
    "whole cell": RECORDING,
    "reseal": RECORDING,
    "home with nucleus": RECORDING,
    "collect": RECORDING,
    # getting the tip usable again
    "clean": CLEANING,
    "blowout": CLEANING,
    # parked, travelling, or waiting for the queue to pick the next cell
    "out": IDLE,
    "bath": IDLE,
    "fouled": IDLE,
    "broken": IDLE,
}

# Category order for display: the funnel's own work first, then what it costs.
CATEGORY_ORDER = [PATCHING, CLEANING, IDLE, RECORDING, OTHER]

# States that mean the rig is doing the run's work, used to trim the analyzed
# window: it opens on the first attempt to engage a cell and closes when the last
# cleaning/recording/patching finishes, so the setup before and the idle after
# (a pipette left ``fouled`` overnight) are not charged to the run.
_WINDOW_OPENING = {PATCHING}
_WINDOW_CLOSING = {PATCHING, CLEANING, RECORDING}

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

    A device that never entered a patching state has no window: it sat out the
    run, and charging the run for its idle would be counting a pipette that was
    never in play. See ``_WINDOW_OPENING``/``_WINDOW_CLOSING``.
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


def session_time_budget(spans: Iterable[StateSpan]) -> pd.DataFrame:
    """Time in each patch state over the run, per device, within its window.

    One row per (device, state), clipped to that device's active window, with
    the cost category and the share of the window it accounts for. Unlike
    ``state_dwell_times`` this covers the states between attempts -- cleaning and
    idle -- which no MultiPatch log was recording.
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

    Reported apart from ``session_time_budget`` because it is *concurrent* with
    it, not another slice of it: a survey runs while the pipette sits in some
    state, so adding the two would double-count. ``blocking_minutes`` is the part
    that overlapped a non-patching state -- survey time the rig spent waiting
    rather than overlapping useful pipette work -- and ``per_candidate_s`` is the
    survey cost amortized over the cells it turned up.
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

    ``active_minutes`` is wall-clock over the analyzed window, so unlike
    ``throughput``'s ``active_hours`` (which sums the MultiPatch logs, i.e. the
    patch work only) it includes the cleaning and idle between attempts. The
    ``*_per_attempt_minutes`` figures divide by ``n_attempts`` when given, which
    is what an extra attempt actually costs.
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
    "funnel_counts",
    "failure_mode_counts",
    "state_dwell_times",
    "state_timeline",
    "throughput",
    "cumulative_whole_cells",
    "categorize_state",
    "session_active_windows",
    "session_time_budget",
    "session_category_totals",
    "session_time_summary",
    "survey_time",
]
